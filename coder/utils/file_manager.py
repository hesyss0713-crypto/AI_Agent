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

    
    
    @register("create_venv")
    def create_venv(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        metadata:
        - dir_path (str, 필수): 프로젝트 경로
        - venv_name (str, 선택): 가상환경 폴더명 (기본 '.venv')
        - requirements (str, 선택): requirements.txt 경로(상대/절대 모두 허용)
        - upgrade_deps (bool, 선택): pip/setuptools 업그레이드 여부 (기본 True)
        - python_version (str, 선택): '3.10', '3.11' 같이 원하는 메이저.마이너 버전
        - interpreter (str, 선택): 사용할 파이썬 실행 파일(명령) 경로/이름 (예: '/usr/bin/python3.10', 'py -3.10')
        """
        try:
            dir_path = metadata.get("dir_path")
            if not dir_path:
                return self._err("Required: metadata.dir_path")

            venv_name      = metadata.get("venv_name", ".venv")
            requirements   = metadata.get("requirements")
            upgrade_deps   = bool(metadata.get("upgrade_deps", True))
            python_version = metadata.get("python_version")  # e.g. "3.10"
            explicit_interp= metadata.get("interpreter")     # full path or command

            project_dir = Path(dir_path).expanduser().resolve()
            project_dir.mkdir(parents=True, exist_ok=True)
            venv_path = project_dir / venv_name

            # -------- 인터프리터 해석 로직 --------
            def _resolve_interpreter(version: str | None, explicit: str | None) -> list[str]:
                # 1) 명시된 interpreter 우선
                if explicit:
                    # 공백이 포함될 수 있으니 토큰 단위로 처리
                    return explicit.split()

                # 2) 버전 지정이 없으면 현재 인터프리터 사용
                if not version:
                    return [sys.executable]

                candidates: list[list[str]] = []
                if os.name == "nt":
                    # Windows: py 런처 우선
                    candidates += [["py", f"-{version}"]]
                    candidates += [[f"python{version}"], [f"python{version.replace('.', '')}"]]
                else:
                    # POSIX
                    candidates += [[f"python{version}"], [f"python{version.split('.')[0]}"]]

                for cmd in candidates:
                    exe = shutil.which(cmd[0])
                    if not exe:
                        continue
                    # 버전 검사
                    try:
                        out = subprocess.check_output(
                            cmd + ["-c", "import sys;print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
                            text=True
                        ).strip()
                        if out == version or out.startswith(version):
                            cmd[0] = exe  # 정규화된 절대경로로 치환
                            return cmd
                    except Exception:
                        continue

                raise FileNotFoundError(f"Python {version} interpreter not found on PATH.")

            interp_cmd = _resolve_interpreter(python_version, explicit_interp)

            # -------- venv 생성 --------
            # 주의: --upgrade-deps는 파이썬 버전에 따라 없을 수 있으므로,
            # 여기서는 안전하게 기본 생성 후 pip로 업그레이드 수행.
            subprocess.check_call([*interp_cmd, "-m", "venv", str(venv_path)])

            # python/pip 경로
            if os.name == "nt":
                py = venv_path / "Scripts" / "python.exe"
                pip = venv_path / "Scripts" / "pip.exe"
            else:
                py = venv_path / "bin" / "python"
                pip = venv_path / "bin" / "pip"

            # deps 업그레이드
            if upgrade_deps:
                subprocess.check_call([str(py), "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"])

            # requirements 설치
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
                "installed": bool(requirements),
                "upgraded": upgrade_deps,
                "interpreter_cmd": interp_cmd,  # 어떤 해석기를 사용했는지 기록
            })

        except subprocess.CalledProcessError as cpe:
            return self._err(f"venv/pip failed (returncode={cpe.returncode})")
        except Exception as e:
            return self._err(str(e))

    @register("run_in_venv")
    def run_in_venv(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        metadata:
          - venv_path (str, 필수): venv 디렉토리
          - argv (list[str], 필수): python 뒤에 올 인자 (예: ["train.py", "--epochs", "10"])
          - cwd (str, 선택): 작업 디렉토리
          - timeout (int, 선택): 실행 제한(초)
        """
        try:
            venv_path = metadata.get("venv_path")
            argv = metadata.get("argv")
            if not venv_path:
                return self._err("Required: metadata.venv_path")
            if not argv or not isinstance(argv, list):
                return self._err("Required: metadata.argv (list[str])")

            if os.name == "nt":
                py = Path(venv_path) / "Scripts" / "python.exe"
            else:
                py = Path(venv_path) / "bin" / "python"
            if not py.exists():
                return self._err(f"python not found in {venv_path}")

            cwd = metadata.get("cwd")
            timeout = metadata.get("timeout")

            result = subprocess.run(
                [str(py), *[str(a) for a in argv]],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout if isinstance(timeout, (int, float)) else None
            )
            # 기존 스타일 유지: 성공이면 stdout만 돌려주고, 실패면 stderr를 담아 반환
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
    def clone_repo(self, dir_path: str, git_url: str) -> Dict[str, Any]:
        try:
            work = Path(dir_path)
            work.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(["git", "clone", git_url], cwd=str(work), capture_output=True, text=True)
            if result.returncode != 0:
                return self._err(result.stderr.strip() or "git clone failed")
            repo_name = git_url.rstrip("/").split("/")[-1]
            return self._ok({"repo": repo_name, "path": str(work / repo_name)})
        except Exception as e:
            return self._err(str(e))

    @register("clone_repo_and_scan")
    def clone_repo_and_scan(self, dir_path: str, git_url: str) -> Dict[str, Any]:
        cloned = self.clone_repo(dir_path, git_url)
        if cloned.get("stderr"):
            return cloned
        repo_path = cloned["stdout"]["path"]
        files = self.list_files(repo_path)
        py = self.read_py_files(repo_path)
        return self._ok({
            "repo": cloned["stdout"]["repo"],
            "path": repo_path,
            "file_list": files,
            "py_files": py,
        })

    @register("list_files")
    def list_files(self, path: str) -> Dict[str, Any]:
        try:
            p = Path(path)
            if not p.exists():
                return self._err(f"Path not found: {path}")
            items = []
            for entry in p.iterdir():
                items.append({
                    "name": entry.name,
                    "path": str(entry),
                    "is_dir": entry.is_dir()
                })
            return self._ok(items)
        except Exception as e:
            return self._err(str(e))

    @register("read_py_files")
    def read_py_files(self, root_path: str) -> Dict[str, Any]:
        try:
            root = Path(root_path)
            if not root.exists():
                return self._err(f"Path not found: {root_path}")
            out: List[Dict[str, str]] = []
            if root.is_file() and root.suffix == ".py":
                out.append({"path": str(root), "content": root.read_text(encoding="utf-8", errors="ignore")})
            else:
                for fp in root.rglob("*.py"):
                    out.append({"path": str(fp), "content": fp.read_text(encoding="utf-8", errors="ignore")})
            return self._ok(out)
        except Exception as e:
            return self._err(str(e))

    @register("edit")
    def edit(self, target: List[str], metadata: Dict[str, str]) -> Dict[str, Any]:
        """
        Write multiple files in one call.
        - target: list of file paths to write (e.g., ["model.py"])
        - metadata: {<filename>: <content>}
        Behavior:
        * If a target file already exists, create a backup: file.ext.bak (or .bak.N)
        * Match metadata by filename only (basename).
        Return stdout as a dict: {message, changes:[{file, bak}], errors?}
        """
        self.root = "/workspace/AI_Agent_Model/"
        try:
            if not isinstance(target, list):
                return self._err("target must be a list of paths")
            if not isinstance(metadata, dict):
                return self._err("metadata must be a dict of {path or name: content}")

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
                # 경로 합치기: Path 연산자로 안전하게 처리
                fp = Path(self.root) / path_str
                # metadata는 basename 기준으로만 매칭
                content = (
                            metadata.get(str(fp))      # full path로 매칭
                            or metadata.get(fp.name)   # 파일명만 매칭
                        )
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