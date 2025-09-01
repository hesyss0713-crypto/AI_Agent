import yaml
from utils.network import supervisor_socket
from utils.db.db import DBManager
from utils.router import CommandRouter
from utils.intent import IntentClassifier
from handlers.git_handler import GitHandler
from llm.llm_manager import LLMManager
from core.event_dispatcher import EventDispatcher
from core.pending import PendingActionManager

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
        return self.dispatcher.dispatch(msg)

    def run(self):
        """Supervisor 메인 실행 루프"""
        self.llm.load_model()
        self.socket.run_main()

        state = "idle"   # idle | pending
        pending = None
        print(f"{YELLOW}[Supervisor] 무엇을 도와드릴까요?{RESET}")
        
        while True:
            try:
                # 먼저 pending을 전부 처리
                while self.pending_manager.has_pending():
                    pending = self.pending_manager.pop()
                    text = input(f"{GREEN}{pending['msg']['response'] or pending['type']} >>> {RESET} ")
                    msg = {
                        "command": None,
                        "action": "user_input_pending",
                        "text": text,
                        "pending": pending
                    }
                    self.emitter.emit("user_message", msg)
                    continue

                # pending이 다 비었으면 일반 입력으로
                text = input(f"{YELLOW} >>> {RESET}")

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
                self.emitter.emit("user_message", msg)

            except StopIteration:
                continue



