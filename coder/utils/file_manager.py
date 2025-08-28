import os
import zipfile
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple
from utils.handler_registry import register

class FileManager:
    def __init__(self, root: str | None = None):
        self.root = Path(root) if root else None

    # --------------------- helpers --------------------- #
    @staticmethod
    def _ok(stdout: Any) -> Dict[str, Any]:
        return {"stdout": stdout, "stderr": None}

    @staticmethod
    def _err(msg: str) -> Dict[str, Any]:
        return {"stdout": None, "stderr": msg}

    # --------------------- actions --------------------- #
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
                # 안전하게 빈 디렉토리만 삭제
                try:
                    p.rmdir()
                    return self._ok(f"Deleted empty dir: {path}")
                except OSError:
                    return self._err("Directory not empty. Refuse to delete recursively.")
            return self._err("Path does not exist.")
        except Exception as e:
            return self._err(str(e))