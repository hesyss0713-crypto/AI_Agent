# code_runner.py
import json
import logging
import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from utils.coder_socket import CoderClient
from utils.handler_registry import register, registry
from utils.file_manager import FileManager
from utils.web_manager import WebManager

logger = logging.getLogger(__name__)

class CodeRunner:
    def __init__(self, host: str, port: int, python_executable: str | None = None, timeout: int = 60):
        self.python = python_executable or sys.executable
        self.timeout = timeout

        self.file_manager = FileManager(root="/workspace/")
        self.web_manager = WebManager()

        self.client = CoderClient(host, port)
        self.client.on_message_callback = self._on_message

        providers = [self.file_manager, self.web_manager, self]
        self.action_map: Dict[str, Any] = {}
        for name, func in registry.items():
            for provider in providers:
                if hasattr(provider, func.__name__):
                    self.action_map[name] = getattr(provider, func.__name__)
                    break

    @register("run_python")
    def run_python(self, code: str, timeout: int | None = None) -> dict:
        if not code:
            return {"stdout": None, "stderr": "code is empty"}
        tmp = None
        to = timeout or self.timeout
        try:
            fd, tmp = tempfile.mkstemp(suffix=".py")
            os.close(fd)
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(code)
            import subprocess
            result = subprocess.run([self.python, tmp], capture_output=True, text=True, timeout=to)
            if result.returncode != 0:
                return {"stdout": result.stdout, "stderr": result.stderr or f"returncode={result.returncode}"}
            return {"stdout": result.stdout, "stderr": None}
        except subprocess.TimeoutExpired:
            return {"stdout": None, "stderr": "Execution timed out"}
        except Exception as e:
            return {"stdout": None, "stderr": str(e)}
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    @staticmethod
    def _normalize_incoming(message: dict) -> Tuple[str | None, Dict[str, Any], Dict[str, Any]]:
        """Normalize Supervisor → CodeRunner message into (action, kwargs, reply_meta)
        Supports message_builder-style payloads:
          - clone_repo/clone_repo_and_scan: {action, url, (optional) dir_path}
          - edit: {action, target: [...], metadata: {...}}
          - git_*: {action, repo_path|path|repo, optional: remote/branch/ref/create/paths/message/user_name/user_email/set_upstream}
          - run_python: {action, code, (optional) timeout}  (also allows metadata.code/metadata.timeout)
          - pip_install: {action, requirements_path} or target[0]
          - apt_install: {action, package} or target[0]
        Also still accepts {action, kwargs} as a fallback.
        """
        if not isinstance(message, dict):
            return None, {}, {}
        action = message.get("action")
        if not isinstance(action, str) or not action:
            return None, {}, {}

        kwargs: Dict[str, Any] = {}

        # 1) Action-specific mapping
        if action in ("clone_repo", "clone_repo_and_scan"):
            git_url = message.get("git_url") or message.get("url")
            dir_path = message.get("dir_path") or "/workspace"
            if git_url is not None:
                kwargs["git_url"] = git_url
            kwargs["dir_path"] = dir_path

        elif action == "edit":
            target = message.get("target") or []
            if not isinstance(target, list):
                target = [target] if target else []
            meta = message.get("metadata") or {}
            if not isinstance(meta, dict):
                meta = {}
            kwargs = {"target": target, "metadata": meta}

        elif action.startswith("git_"):
            repo_path = message.get("repo_path") or message.get("path") or message.get("repo")
            if repo_path:
                kwargs["repo_path"] = repo_path
            for key in ("remote", "branch", "ref", "create", "paths", "message", "user_name", "user_email", "set_upstream"):
                if key in message:
                    kwargs[key] = message[key]

        elif action == "run":
            target = message.get("target") or []
            if not isinstance(target, list):
                target = [target] if target else []
            meta = message.get("metadata") or {}
            if not isinstance(meta, dict):
                meta = {}
            kwargs = {"target": target, "metadata": meta}
        

        elif action == "run_python":
            code = message.get("code")
            if code is None and isinstance(message.get("metadata"), dict):
                code = message["metadata"].get("code")
            if code is not None:
                kwargs["code"] = code
            timeout = message.get("timeout")
            if timeout is None and isinstance(message.get("metadata"), dict):
                timeout = message["metadata"].get("timeout")
            if timeout is not None:
                kwargs["timeout"] = timeout

        elif action == "pip_install":
            rp = message.get("requirements_path")
            tgt = message.get("target")
            if rp is None and isinstance(tgt, list) and tgt:
                rp = tgt[0]
            if rp is None and isinstance(message.get("metadata"), dict):
                rp = message["metadata"].get("requirements_path")
            if rp is not None:
                kwargs["requirements_path"] = rp

        elif action == "apt_install":
            pkg = message.get("package")
            tgt = message.get("target")
            if pkg is None and isinstance(tgt, list) and tgt:
                pkg = tgt[0]
            if pkg is None and isinstance(message.get("metadata"), dict):
                pkg = message["metadata"].get("package")
            if pkg is not None:
                kwargs["package"] = pkg

        # 2) Fallback to explicit kwargs if provided
        elif isinstance(message.get("kwargs"), dict):
            kwargs = message["kwargs"]

        # 3) Reply metadata passthrough
        reply_meta: Dict[str, Any] = {}
        for k in ("task_id", "id", "request_id"):
            if k in message:
                reply_meta[k] = message[k]

        return action, kwargs, reply_meta

    @staticmethod
    def _wrap_payload(action: str | None, kwargs: Dict[str, Any], reply_meta: Dict[str, Any], handler_result: Dict[str, Any], started_at: str, finished_at: str, duration_ms: int) -> Dict[str, Any]:
        stdout = handler_result.get("stdout") if isinstance(handler_result, dict) else None
        stderr = handler_result.get("stderr") if isinstance(handler_result, dict) else None
        metadata = {
            "ok": (stderr is None or stderr == ""),
            "stdout": stdout,
            "stderr": stderr,
            "action": action,
            "kwargs": kwargs,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            **reply_meta,
        }
        return {"result": "", "metadata": metadata}

    def _on_message(self, message: dict):
        action, kwargs, reply_meta = self._normalize_incoming(message)

        t0 = time.perf_counter()
        started_at = datetime.now(timezone.utc).isoformat()
        if not action:
            handler_result = {"stdout": None, "stderr": "Missing action"}
        else:
            handler = self.action_map.get(action)
            if not handler:
                handler_result = {"stdout": None, "stderr": f"Unknown action: {action}"}
            else:
                try:
                    result = handler(**kwargs)
                    if not isinstance(result, dict) or ("stdout" not in result and "stderr" not in result):
                        handler_result = {"stdout": result, "stderr": None}
                    else:
                        handler_result = result
                except TypeError as e:
                    handler_result = {"stdout": None, "stderr": f"Bad kwargs for action '{action}': {e}"}
                except Exception as e:
                    logger.exception("handler raised")
                    handler_result = {"stdout": None, "stderr": str(e)}

        duration_ms = int((time.perf_counter() - t0) * 1000)
        finished_at = datetime.now(timezone.utc).isoformat()

        payload = self._wrap_payload(action, kwargs, reply_meta, handler_result, started_at, finished_at, duration_ms)
        self.client.send_message(payload)

    def run(self):
        logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
        t = threading.Thread(target=self.client.run, daemon=True)
        t.start()
        t.join()

if __name__ == "__main__":
    runner = CodeRunner(host="172.17.0.1", port=9002)
    runner.run()

# test_normalize.py (optional quick checks)
if False:  # set True to run simple assertions
    from code_runner import CodeRunner as CR
    def _t(msg, exp_kwargs):
        a, kw, _ = CR._normalize_incoming(msg)
        assert a == msg["action"], (a, msg["action"]) 
        assert kw == exp_kwargs, (kw, exp_kwargs)

    _t({"action":"clone_repo","url":"https://x"}, {"git_url":"https://x","dir_path":"/workspace"})
    _t({"action":"edit","target":["a.py"],"metadata":{"a.py":"print(1)"}}, {"target":["a.py"],"metadata":{"a.py":"print(1)"}})
    _t({"action":"git_pull","path":"/r","branch":"dev"}, {"repo_path":"/r","branch":"dev"})
    _t({"action":"run_python","code":"print('ok')","timeout":5}, {"code":"print('ok')","timeout":5})
    _t({"action":"pip_install","target":["/w/req.txt"]}, {"requirements_path":"/w/req.txt"})
    _t({"action":"apt_install","metadata":{"package":"git"}}, {"package":"git"})
