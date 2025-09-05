import yaml
from utils.network import supervisor_socket
from utils.db.db import DBManager
from utils.router import CommandRouter
from core.bridge_client import BridgeClient
import logging
from utils.intent import IntentClassifier
from handlers.git_handler import GitHandler
from llm.llm_manager import LLMManager
from core.event_dispatcher import EventDispatcher
from queue import Queue, Empty
from typing import Optional, Dict, Any
from core.pending import PendingActionManager
import time

GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"

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

        #Bridge
        self.bridge = None
        self.user_q : "Queue[str]" = Queue()

        # Logic components
        self.router = CommandRouter(self.llm, self.prompts)
        self.intent_cls = IntentClassifier(self.llm, self.prompts)
        self.git_handler = GitHandler(self.llm, self.prompts)

        # 이벤트 연결
        self.emitter.on("coder_message", self.handle_event)
        self.emitter.on("user_message", self.handle_event)

        # py file 상태
        self.py_files : str | None = None

        # dir이름
        self.last_git_url : str | None = None
        self.last_dir_name : str | None = None

    def load_prompts(self, path="/workspace/AI_Agent/refact_Supvervisor/config/prompts.yaml") -> dict:
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

            if mtype in ("user_input", "input", "prompt", "chat") and text:
                # 외부 입력을 큐로 보냄
                self.user_q.put(text)
                self._send_to_bridge({"type": "user_input(received)", "text": text})
                return

            if mtype == "reset":
                self.llm.reset_memory()
                self._send_to_bridge({"type": "system", "text": "LLM memory reset"})
                return

            self._send_to_bridge({"type": "supervisor_log", "text": f"ignored message: {msg}"})
        except Exception as e:
            self.logger.exception("[Supervisor] _on_bridge_message error: %s", e)
            self._send_to_bridge({"type": "error", "text": f"_on_bridge_message: {e}"})

    def _send_to_bridge(self, message: Dict[str, Any] | str):
        """브릿지로 메시지 전송"""
        if self.bridge:
            self.bridge.send(message)

    def enqueue_user_input(self, text: str):
        """외부에서 온 user input 큐에 저장"""
        self.user_q.put(text)

    def _wait_user_text(self) -> str:
        """user_q에서 사용자 입력을 기다림"""
        while True:
            try:
                return self.user_q.get(timeout=0.1)
            except Empty:
                time.sleep(0.05)

    def run(self):
        print("🔥 Supervisor run loop 진입")
        """Supervisor 메인 실행 루프"""
        self.llm.load_model()
        self.socket.run_main()
        
        while True:
            try:
                # 먼저 pending을 전부 처리
                print("큐 상태:", list(self.pending_manager.queue))
                if self.pending_manager.has_pending():
                    pending = self.pending_manager.pop()
                    print(pending)
                    self._send_to_bridge(pending["msg"].get("response"))
                    text = self._wait_user_text()
                    msg = {
                        "command": None,
                        "action": "user_input_pending",
                        "text": text,
                        "pending": pending
                    }
                    self.emitter.emit("user_message",msg)
                    continue

                # pending이 다 비었으면 일반 입력으로
                self._send_to_bridge("Panding is empty")
                text = self._wait_user_text()

                if text.lower() == "exit":
                    print(f"{YELLOW}[Supervisor] 종료{RESET}")
                    break
                if text.lower() == "reset":
                    self.llm.reset_memory()
                    print(f"{YELLOW}[Supervisor] 대화 메모리 초기화됨.{RESET}")
                    continue

                msg = {
                    "command": None,
                    "action": "user_input_normal",
                    "text": text
                }
                self._send_to_bridge(msg)

            except StopIteration:
                continue



