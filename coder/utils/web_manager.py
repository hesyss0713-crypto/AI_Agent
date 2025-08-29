import importlib.util
import subprocess

from utils.handler_registry import register


class WebManager:
    def __init__(self):
        pass

    @register("pip_install")
    def pip_install(self, requirements_path: str) -> dict:
        try:
            if not requirements_path:
                return {"stdout": None, "stderr": "requirements_path is empty"}
            to_install = []
            with open(requirements_path, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        to_install.append(s)
            missing = []
            for pkg in to_install:
                import_name = pkg.split("==")[0].split(">=")[0].split("<=")[0].split(">")[0].split("<")[0]
                if importlib.util.find_spec(import_name) is None:
                    missing.append(pkg)
            if not missing:
                return {"stdout": "All packages already installed", "stderr": None}
            result = subprocess.run(["pip", "install", *missing], capture_output=True, text=True)
            if result.returncode != 0:
                return {"stdout": result.stdout, "stderr": result.stderr}
            return {"stdout": result.stdout, "stderr": None}
        except Exception as e:
            return {"stdout": None, "stderr": str(e)}

    @register("apt_install")
    def apt_install(self, package: str) -> dict:
        try:
            if not package:
                return {"stdout": None, "stderr": "package is empty"}
            result = subprocess.run(["apt-get", "install", "-y", package], capture_output=True, text=True)
            if result.returncode != 0:
                return {"stdout": result.stdout, "stderr": result.stderr}
            return {"stdout": result.stdout, "stderr": None}
        except Exception as e:
            return {"stdout": None, "stderr": str(e)}