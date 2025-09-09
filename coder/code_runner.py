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
from utils.common_metadata import CommonMetadata
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
    def _normalize_incoming(message: dict):
        """
        Normalize Supervisor → CodeRunner message into (command, action, kwargs, reply_meta).

        - command: 상위 카테고리 (예: git, run, etc.)
        - action: 실행할 액션명
        - kwargs: handler에 전달할 인자 (metadata + target)
        - reply_meta: 응답 매칭용 id
        """
        if not isinstance(message, dict):
            return None, None, {}, {}

        command = message.get("command")
        action = message.get("action")
        metadata = message.get("metadata", {}) or {}
        target = message.get("target") or []

        if target:
            metadata["target"] = target

        # 공통 metadata 스키마로 매핑 후 None 값 제거
        try:
            meta = CommonMetadata(**metadata)
            kwargs = meta.model_dump(exclude_none=True)
        except Exception as e:
            # 스키마 검증 실패 → 그냥 원본 metadata 사용 (유연성 확보)
            kwargs = {k: v for k, v in metadata.items() if v is not None}

        reply_meta = {k: message[k] for k in ("task_id", "id", "request_id") if k in message}

        return command, action, kwargs, reply_meta

    @staticmethod
    def _wrap_payload(command: str, action: str | None, kwargs: Dict[str, Any], reply_meta: Dict[str, Any], handler_result: Dict[str, Any], started_at: str, finished_at: str, duration_ms: int) -> Dict[str, Any]:
        stdout = handler_result.get("stdout") if isinstance(handler_result, dict) else None
        stderr = handler_result.get("stderr") if isinstance(handler_result, dict) else None
        metadata={
            "stdout":stdout,
            "stderr":stderr,
            **kwargs
        }
        if stdout is not None:
            return {"command": command, "action": action, "result": "success", "metadata": metadata}
        elif stdout is None and stderr is not None:
            return {"command": command, "action": action, "result": "fail", "metadata": metadata}
        
        
    def _on_message(self, message: dict):
        command, action, kwargs, reply_meta = self._normalize_incoming(message)

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

        payload = self._wrap_payload(command,action, kwargs, reply_meta, handler_result, started_at, finished_at, duration_ms)
        self.client.send_message(payload)

    def run(self):
        logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
        t = threading.Thread(target=self.client.run, daemon=True)
        t.start()
        t.join()

if __name__ == "__main__":
    runner = CodeRunner(host="172.17.0.1", port=9002)
    runner.run()


