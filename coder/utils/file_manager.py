import subprocess
import zipfile
from pathlib import Path
from typing import List, Dict, Any
import shutil

from .handler_registry import register

class FileManager:
    def __init__(self, root: str | None = None):
        self.root = Path(root) if root else None

    @staticmethod
    def _ok(stdout: Any) -> Dict[str, Any]:
        return {"stdout": stdout, "stderr": None}

    @staticmethod
    def _err(msg: str) -> Dict[str, Any]:
        return {"stdout": None, "stderr": msg}

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
        """Write multiple files in one call.
        - target: list of file paths to write
        - metadata: {<path or filename>: <content>}
        Behavior:
          * If a target file already exists, create a backup: file.ext.bak (or .bak.N)
          * If metadata contains only the basename key (e.g., "model.py"), it will match any target with that name.
        Return stdout as a dict: {message, changes:[{file, bak}], errors?}
        """
        
        
        try:
            if not isinstance(target, list):
                return self._err("target must be a list of paths")

            changes: List[Dict[str, Any]] = []
            errors: List[str] = []

            def _content_for(fp: Path) -> str | None:
                if str(fp) in metadata:
                    return metadata[str(fp)]
                if fp.name in metadata:
                    return metadata[fp.name]
                return None

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
                fp = Path(path_str)
                content = _content_for(fp)
                if content is None:
                    errors.append(f"no content for: {path_str}")
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
                    errors.append(f"{path_str}: {e}")

            result = {"message": f"edited {len(changes)} files", "changes": changes}
            if errors:
                result["errors"] = errors
            if errors:
                return {"stdout": result, "stderr": "".join(errors)}
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