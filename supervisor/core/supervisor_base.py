import yaml
import time
import logging
from typing import Optional, Dict, Any
from queue import Queue, Empty

from utils.network import supervisor_socket
from utils.db.db import DBManager
from utils.router import CommandRouter
from core.bridge_client import BridgeClient
from utils.intent import IntentClassifier
from handlers.git_handler import GitHandler
from llm.llm_manager import LLMManager
from core.event_dispatcher import EventDispatcher
from core.pending import PendingActionManager


class Supervisor:
    def __init__(self, model_name: str, host: str, port: int):
        # Core components
        self.llm = LLMManager(model_name)
        self.db = DBManager()
        self.socket = supervisor_socket.SupervisorServer(host, port)
        self.prompts = self.load_prompts()
        self.emitter = self.socket.emitter
        self.dispatcher = EventDispatcher()
        self.pending_manager = PendingActionManager()
        self.logger = logging.getLogger(__name__)

        # Bridge
        self.bridge = None

        # 동기 큐
        self.user_q: "Queue[str]" = Queue()

        # Logic components
        self.router = CommandRouter(self.llm, self.prompts)
        self.intent_cls = IntentClassifier(self.llm, self.prompts)
        self.git_handler = GitHandler(self.llm, self.prompts)

        # 이벤트 연결
        self.emitter.on("coder_message", self.handle_event)
        self.emitter.on("user_message", self.handle_event)

        # py file 상태
        self.py_files: str | None = None

        # dir 이름
        self.last_git_url: str | None = None
        self.last_dir_name: str | None = None

        # 탭 관리
        self.active_tab: Optional[int] = None
        self.last_tab_id: int = 1

    def load_prompts(self, path="/workspace/AI_Agent/supervisor/config/prompts.yaml") -> dict:
        """system prompt yaml 로드"""
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def handle_event(self, msg: dict):
        """이벤트 분배"""
        result = self.dispatcher.dispatch(msg)
        return result

    def _on_bridge_message(self, msg: Dict[str, Any]):
        """브릿지로부터 들어온 메시지 처리"""
        
        try:
            mtype = str(msg.get("type", "")).lower()
            text = str(msg.get("text", "")).strip()

            if mtype == "user_input_pending" and text:
                print(f"[Supervisor] enqueue user_input_pending: {text}")
                # pending 흐름으로 들어가게 dict 형태로 넣음
                self.user_q.put({
                    "action": "user_input_pending",
                    "text": text
                })
                return
            
            if mtype in ("user_input", "input", "prompt", "chat") and text:
                mmtype = "main_input"
                # 외부 입력을 큐로 보냄
                self.user_q.put(text)
                return
            
            if mtype == "reset":
                mmtype = "main_input"
                self.llm.reset_memory()
                self._send_to_bridge(mmtype, "LLM memory reset")
                return

            self._send_to_bridge(mmtype, f"ignored message: {msg}")

        except Exception as e:
            self.logger.exception("[Supervisor] _on_bridge_message error: %s", e)
            self._send_to_bridge(mmtype, f"_on_bridge_message: {e}")

    def _send_to_bridge(self, mtype, text: Dict[str, Any] | str, tabId=None):
        """브릿지로 메시지 전송"""
        if self.bridge:
            message = {
                "type": mtype,
                "text": text,
                "tabId": tabId,
            }
            self.bridge.send(message)

    def enqueue_user_input(self, text: str):
        """외부에서 온 user input 큐에 저장"""
        self.user_q.put(text)

    def _wait_user_text(self) -> str:
        """user_q에서 사용자 입력을 기다림"""
        while True:
            try:
                return self.user_q.get(timeout=0.5)
            except Empty:
                time.sleep(0.05)

def run(self):
    print("🔥 Supervisor run loop 진입")
    self.llm.load_model()
    self.socket.run_main()

    while True:
        try:
            if self.pending_manager.has_pending():
                pending = self.pending_manager.pop()
                self._send_to_bridge(
                    "pending_request",
                    pending["msg"].get("response"),
                    pending.get("tabId"),
                )

                event = self._wait_user_text()

                # ✅ dict로 들어온 경우 (user_input_pending)
                if isinstance(event, dict) and event.get("action") == "user_input_pending":
                    msg = {
                        "command": None,
                        "action": "user_input_pending",
                        "text": event["text"],
                        "pending": pending,
                    }
                    self.emitter.emit("user_message", msg)
                else:
                    # fallback: 문자열로 들어온 경우
                    msg = {
                        "command": None,
                        "action": "user_input_pending",
                        "text": str(event),
                        "pending": pending,
                    }
                    self.emitter.emit("user_message", msg)

                continue

            # pending이 다 비었으면 일반 입력으로
            event = self._wait_user_text()

            # 일반 입력은 무조건 문자열만 허용
            if isinstance(event, dict):
                event = event.get("text", "")

            text = event.strip()

            if text.lower() == "exit":
                print("[Supervisor] 종료")
                break
            if text.lower() == "reset":
                self.llm.reset_memory()
                print("[Supervisor] 대화 메모리 초기화됨.")
                continue

            msg = {
                "command": None,
                "action": "user_input_normal",
                "text": text,
            }
            self.emitter.emit("coder_message", msg)

        except StopIteration:
            continue
