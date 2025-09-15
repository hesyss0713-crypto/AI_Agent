import subprocess
import zipfile
from pathlib import Path
from typing import List, Dict, Any
import shutil
import venv
from .handler_registry import register
import os, sys


class FileManager:
    def __init__(self, root: str | None = None):
        self.root = Path(root) if root else None

    @staticmethod
    def _ok(stdout: Any) -> Dict[str, Any]:
        return {"stdout": stdout, "stderr": None}

    @staticmethod
    def _err(msg: str) -> Dict[str, Any]:
        return {"stdout": None, "stderr": msg}

    @register("run_in_venv")
    def run_in_venv(
        self,
        venv_path: str,
        target: str = "train.py",
        args: List[str] | None = None,
        cwd: str | None = None,
        timeout: int | float | None = None
    ) -> Dict[str, Any]:
        try:
            if not venv_path:
                return self._err("Required: venv_path")

            venv_path = Path(venv_path).expanduser()
            if not venv_path.is_absolute():
                venv_path = (self.root / venv_path).resolve()
            else:
                venv_path = venv_path.resolve()

            if os.name == "nt":
                py = venv_path / "Scripts" / "python.exe"
            else:
                py = venv_path / "bin" / "python"

            if not py.exists():
                return self._err(f"python not found in {venv_path}")

            workdir = Path(cwd).resolve() if cwd else venv_path.parent.resolve()
            if not workdir.is_relative_to(self.root):
                workdir = self.root / workdir.relative_to("/")

            script = (workdir / target).resolve()
            if not script.exists():
                return self._err(f"target not found: {script}")

            argv = [str(script)]
            if args:
                argv.extend([str(a) for a in args])

            result = subprocess.run(
                [str(py), *argv],
                cwd=str(workdir),
                capture_output=True,
                text=True,
                timeout=timeout if isinstance(timeout, (int, float)) else None
            )

            if result.returncode == 0:
                return self._ok((result.stdout or "").strip())
            return self._err((result.stderr or "").strip() or f"returncode={result.returncode}")

        except subprocess.TimeoutExpired:
            return self._err("Execution timed out")
        except Exception as e:
            return self._err(str(e))

    @register("run")
    def _run(self, cmd: list[str], cwd: Path | None = None) -> Dict[str, Any]:
        try:
            result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
            if result.returncode == 0:
                return self._ok(result.stdout.strip())
            return self._err(result.stderr.strip() or f"returncode={result.returncode}")
        except Exception as e:
            return self._err(str(e))

    def _git(self, repo_path: str, *args: str) -> Dict[str, Any]:
        p = Path(repo_path)
        if not p.exists():
            return self._err(f"Path not found: {repo_path}")
        return self._run(["git", *args], cwd=p)

    @register("clone_repo")
    def clone_repo(self, dir_path: str="/workspace", git_url: str=None) -> Dict[str, Any]:
        try:
            work = Path(dir_path)
            work.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(["git", "clone", git_url], cwd=str(work), capture_output=True, text=True)
            repo_name = git_url.rstrip("/").split("/")[-1]
            return self._ok({"repo": repo_name, "dir_path": str(work / repo_name)})
        except Exception as e:
            return self._err(str(e))

    @register("clone_repo_and_scan")
    def clone_repo_and_scan(self, dir_path: str, git_url: str) -> Dict[str, Any]:
        cloned = self.clone_repo(dir_path, git_url)
        if cloned.get("stderr"):
            repo_name = git_url.rstrip("/").split("/")[-1]
            repo_path = str(Path(dir_path) / repo_name)
            files = self.list_files(repo_name)
            py = self.read_py_files(repo_name)
            return self._ok({
                "repo": repo_name,
                "dir_path": repo_path,
                "file_list": files,
                "py_files": py,
            })
        repo_path = cloned["stdout"]["dir_path"]
        files = self.list_files(repo_path)
        py = self.read_py_files(repo_path)
        return self._ok({
            "repo": cloned["stdout"]["repo"],
            "dir_path": repo_path,
            "file_list": files,
            "py_files": py,
        })

    @register("list_files")
    def list_files(self, dir_path: str) -> Dict[str, Any]:
        try:
            p = Path(dir_path)
            if not p.exists():
                return self._err(f"Path not found: {dir_path}")
            items = []
            for entry in p.iterdir():
                if entry.name in {".venv", "venv", "env"}:
                    continue
                items.append({
                    "name": entry.name,
                    "path": str(entry),
                    "is_dir": entry.is_dir()
                })
            return self._ok(items)
        except Exception as e:
            return self._err(str(e))

    @register("read_py_files")
    def read_py_files(self, dir_path: str) -> Dict[str, Any]:
        try:
            root = self.root / Path(dir_path)
            if not root.exists():
                return self._err(f"Path not found: {dir_path}")

            out: List[Dict[str, str]] = []
            if root.is_file() and root.suffix == ".py":
                if root.name not in {"get-pip.py"}:
                    out.append({
                        "path": str(root),
                        "content": root.read_text(encoding="utf-8", errors="ignore")
                    })
            else:
                for fp in root.rglob("*.py"):
                    if any(part in {".venv", "venv", "env", "__pycache__"} for part in fp.parts):
                        continue
                    if fp.name.startswith("get-pip") or fp.name.startswith("pip-"):
                        continue
                    out.append({
                        "path": str(fp),
                        "content": fp.read_text(encoding="utf-8", errors="ignore")
                    })

            return self._ok(out)
        except Exception as e:
            return self._err(str(e))

    @register("edit")
    def edit(self, target: List[str], files: Dict[str, str]) -> Dict[str, Any]:
        """
        Write multiple files in one call.
        - target: list of file paths to write (e.g., ["AI_Agent_Model/model.py"])
        - files: dictionary mapping (filename or absolute path) → content
        """
        self.root = "/workspace/"
        try:
            if not isinstance(target, list):
                return self._err("target must be a list of paths")

            changes: List[Dict[str, Any]] = []
            errors: List[str] = []

            def _unique_bak(orig: Path) -> Path:
                bak = orig.with_suffix(orig.suffix + ".bak")
                if not bak.exists():
                    return bak
                i = 1
                while True:
                    cand = orig.with_suffix(orig.suffix + f".bak.{i}")
                    if not cand.exists():
                        return cand
                    i += 1

            for path_str in target:
                fp = Path(self.root) / path_str

                # dictionary에서 value(content) 가져오기
                # key가 절대경로(/workspace/...)거나 파일명만 있을 수 있으므로 둘 다 시도
                content = files.get(str(fp)) or files.get(fp.name)

                if content is None:
                    errors.append(f"no content for: {fp}")
                    continue

                try:
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    bak_path: str | None = None
                    if fp.exists():
                        bak = _unique_bak(fp)
                        shutil.copy2(fp, bak)
                        bak_path = str(bak)
                    # ✅ value (content)만 write
                    fp.write_text(content, encoding="utf-8")
                    changes.append({"file": str(fp), "bak": bak_path})
                except Exception as e:
                    errors.append(f"{fp}: {e}")

            result = {"message": f"edited {len(changes)} files", "changes": changes}
            if errors:
                result["errors"] = errors
                return {"stdout": result, "stderr": "\n".join(errors)}
            return self._ok(result)
        except Exception as e:
            return self._err(str(e))

    @register("create_venv")
    def create_venv(
        self,
        dir_path: str,
        venv_name: str = "venv",
        requirements: str | None = None,
        upgrade_deps: bool = True,
        python_version: str | None = None,
        interpreter: str | None = None
    ) -> Dict[str, Any]:
        try:
            project_dir = Path(dir_path).expanduser()
            if project_dir.is_absolute():
                project_dir = project_dir.resolve()
            else:
                project_dir = (self.root / project_dir).resolve()

            project_dir.mkdir(parents=True, exist_ok=True)
            venv_path = project_dir / venv_name

            if venv_path.exists():
                if os.name == "nt":
                    py = venv_path / "Scripts" / "python.exe"
                    pip = venv_path / "Scripts" / "pip.exe"
                    activate = venv_path / "Scripts" / "activate.bat"
                else:
                    py = venv_path / "bin" / "python"
                    pip = venv_path / "bin" / "pip"
                    activate = venv_path / "bin" / "activate"

                return self._ok({
                    "message": f"venv already exists: {venv_path}",
                    "venv": str(venv_path),
                    "python": str(py),
                    "pip": str(pip),
                    "activate": str(activate),
                    "installed": False,
                    "upgraded": False,
                    "interpreter_cmd": None,
                })

            def _resolve_interpreter(version: str | None, explicit: str | None) -> list[str]:
                if explicit:
                    return explicit.split()
                if not version:
                    return [sys.executable]
                candidates: list[list[str]] = []
                if os.name == "nt":
                    candidates += [["py", f"-{version}"]]
                    candidates += [[f"python{version}"], [f"python{version.replace('.', '')}"]]
                else:
                    candidates += [[f"python{version}"], [f"python{version.split('.')[0]}"]]
                for cmd in candidates:
                    exe = shutil.which(cmd[0])
                    if not exe:
                        continue
                    try:
                        out = subprocess.check_output(
                            cmd + ["-c", "import sys;print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
                            text=True
                        ).strip()
                        if out == version or out.startswith(version):
                            cmd[0] = exe
                            return cmd
                    except Exception:
                        continue
                raise FileNotFoundError(f"Python {version} interpreter not found on PATH.")

            interp_cmd = _resolve_interpreter(python_version, interpreter)

            subprocess.check_call([*interp_cmd, "-m", "venv", str(venv_path)])

            if os.name == "nt":
                py = venv_path / "Scripts" / "python.exe"
                pip = venv_path / "Scripts" / "pip.exe"
                activate = venv_path / "Scripts" / "activate.bat"
            else:
                py = venv_path / "bin" / "python"
                pip = venv_path / "bin" / "pip"
                activate = venv_path / "bin" / "activate"

            def _ensure_pip():
                if not pip.exists():
                    url = "https://bootstrap.pypa.io/get-pip.py"
                    get_pip = project_dir / "get-pip.py"
                    subprocess.check_call(["wget", "-O", str(get_pip), url])
                    subprocess.check_call([str(py), str(get_pip)])

            _ensure_pip()

            if upgrade_deps:
                subprocess.check_call([str(py), "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"])

            if requirements:
                req_path = Path(requirements)
                if not req_path.is_absolute():
                    req_path = project_dir / req_path
                if not req_path.exists():
                    return self._err(f"requirements not found: {req_path}")
                subprocess.check_call([str(pip), "install", "-r", str(req_path)])

            return self._ok({
                "venv": str(venv_path),
                "python": str(py),
                "pip": str(pip),
                "activate": str(activate),
                "installed": bool(requirements),
                "upgraded": upgrade_deps,
                "interpreter_cmd": interp_cmd,
            })

        except subprocess.CalledProcessError as cpe:
            return self._err(f"venv/pip failed (returncode={cpe.returncode})")
        except Exception as e:
            return self._err(str(e))

    @register("zip")
    def zip_path(self, zip_path: str, folder_path: str | None = None, file_path: str | None = None) -> Dict[str, Any]:
        try:
            zp = Path(zip_path)
            zp.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(str(zp), "w", zipfile.ZIP_DEFLATED) as z:
                if folder_path:
                    base = Path(folder_path)
                    for fp in base.rglob("*"):
                        if fp.is_file():
                            z.write(str(fp), arcname=str(fp.relative_to(base)))
                if file_path:
                    fp = Path(file_path)
                    if fp.exists():
                        z.write(str(fp), arcname=fp.name)
            return self._ok(f"Zip created: {str(zp)}")
        except Exception as e:
            return self._err(str(e))

    @register("delete")
    def delete_path(self, path: str) -> Dict[str, Any]:
        try:
            p = Path(path)
            if p.is_file():
                p.unlink(missing_ok=True)
                return self._ok(f"Deleted file: {path}")
            if p.is_dir():
                try:
                    p.rmdir()
                    return self._ok(f"Deleted empty dir: {path}")
                except OSError:
                    return self._err("Directory not empty. Refuse to delete recursively.")
            return self._err("Path does not exist.")
        except Exception as e:
            return self._err(str(e))

    @register("git_status")
    def git_status(self, repo_path: str) -> Dict[str, Any]:
        return self._git(repo_path, "status", "-b", "--porcelain")

    @register("git_current_branch")
    def git_current_branch(self, repo_path: str) -> Dict[str, Any]:
        return self._git(repo_path, "rev-parse", "--abbrev-ref", "HEAD")

    @register("git_list_branches")
    def git_list_branches(self, repo_path: str) -> Dict[str, Any]:
        return self._git(repo_path, "branch", "--list")

    @register("git_fetch")
    def git_fetch(self, repo_path: str, remote: str = "origin") -> Dict[str, Any]:
        return self._git(repo_path, "fetch", remote)

    @register("git_pull")
    def git_pull(self, repo_path: str, remote: str = "origin", branch: str = "main") -> Dict[str, Any]:
        return self._git(repo_path, "pull", remote, branch)

    @register("git_checkout")
    def git_checkout(self, repo_path: str, ref: str, create: bool = False) -> Dict[str, Any]:
        args = ["checkout"]
        if create:
            args += ["-b", ref]
        else:
            args += [ref]
        return self._git(repo_path, *args)

    @register("git_add")
    def git_add(self, repo_path: str, paths: List[str] | None = None) -> Dict[str, Any]:
        args = ["add"] + (paths if paths else ["-A"])
        return self._git(repo_path, *args)

    @register("git_commit")
    def git_commit(self, repo_path: str, message: str) -> Dict[str, Any]:
        if not message:
            return self._err("commit message is empty")
        return self._git(repo_path, "commit", "-m", message)

    @register("git_push")
    def git_push(self, repo_path: str, remote: str = "origin", branch: str = "main", set_upstream: bool = False) -> Dict[str, Any]:
        args = ["push", remote, branch]
        if set_upstream:
            args.insert(1, "-u")
        return self._git(repo_path, *args)

    @register("git_config")
    def git_config(self, repo_path: str, user_name: str | None = None, user_email: str | None = None) -> Dict[str, Any]:
        p = Path(repo_path)
        if not p.exists():
            return self._err(f"Path not found: {repo_path}")
        outs = []
        if user_name:
            outs.append(self._run(["git", "config", "user.name", user_name], cwd=p))
        if user_email:
            outs.append(self._run(["git", "config", "user.email", user_email], cwd=p))
        return self._ok([o for o in outs])
