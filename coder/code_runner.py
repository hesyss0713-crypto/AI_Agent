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
    """Registry 기반 다중 Provider 액션 실행기
    응답 포맷(고정): {"result": "", "metadata": { ... }}
      - result: 항상 빈 문자열("") 사용
      - metadata: { ok: bool, stdout: Any, stderr: str|None, action: str, kwargs: dict, 식별자..., started_at, finished_at, duration_ms }
    """x

    def __init__(self, host: str, port: int, python_executable: str | None = None, timeout: int = 60):
        self.python = python_executable or sys.executable
        self.timeout = timeout

        self.file_manager = FileManager()
        self.web_manager = WebManager()

        self.client = CoderClient(host, port)
        self.client.on_message_callback = self._on_message

        # provider 우선순위: FileManager → WebManager → CodeRunner(self)
        providers = [self.file_manager, self.web_manager, self]
        self.action_map: Dict[str, Any] = {}
        for name, func in registry.items():
            for provider in providers:
                if hasattr(provider, func.__name__):
                    self.action_map[name] = getattr(provider, func.__name__)
                    break

    # ---------------- Message Normalizer (신포맷 전용) ---------------- #
    @staticmethod
    def _normalize_incoming(message: dict) -> Tuple[str | None, Dict[str, Any], Dict[str, Any]]:
        """Supervisor → CodeRunner 수신 메시지를 내부 공통 포맷으로 변환 (신포맷 전용)
        기대 포맷: {"action": str, "kwargs": dict, (선택) task_id/id }
        반환: (action, kwargs, reply_meta)
        """
        if not isinstance(message, dict):
            return None, {}, {}
        action = message.get("action")
        if not isinstance(action, str) or not action:
            return None, {}, {}
        kwargs = message.get("kwargs") or {}
        if not isinstance(kwargs, dict):
            kwargs = {}
        reply_meta: Dict[str, Any] = {}
        if "task_id" in message:
            reply_meta["task_id"] = message["task_id"]
        if "id" in message:
            reply_meta["id"] = message["id"]
        if "request_id" in message:
            reply_meta["request_id"] = message["request_id"]
        return action, kwargs, reply_meta

    # ---------------- Result Wrapper ---------------- #
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

    # ---------------- Socket Glue ---------------- #
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
                    # 허용 형태가 아니면 stdout으로 래핑
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
    runner = CodeRunner(host="172.17.0.1", port=9006)
    runner.run()
