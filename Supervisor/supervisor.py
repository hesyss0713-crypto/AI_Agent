import logging
import yaml
from utils.network import supervisor_socket, event_emitter
from utils.db.db import DBManager
from utils.router import CommandRouter
from utils.intent import IntentClassifier
from utils.message_builder import build_task, build_response
from handlers.git_handler import GitHandler
from llm.llm_manager import LLMManager


logging.basicConfig(level=logging.INFO)


class Supervisor:
    def __init__(self, model_name: str, host: str, port: int):
        # LLM 관리 객체
        self.llm = LLMManager(model_name)

        # DB, 소켓
        self.db = DBManager()
        self.socket = supervisor_socket.SupervisorServer(host, port)

        # config 로드 (prompts.yaml)
        self.prompts = self.load_prompts()

        self.emitter = self.socket.emitter
        # Router, IntentClassifier, Handlers 초기화
        self.router = CommandRouter(self.llm, self.prompts)
        self.intent_cls = IntentClassifier(self.llm, self.prompts)
        self.git_handler = GitHandler(self.llm, self.prompts)
        self.emitter.on("coder_message", self.on_coder_message)

        self.py_files = None

    def load_prompts(self, path="/workspace/AI_Agent/Supervisor/config/prompts.yaml") -> dict:
        """system prompt yaml 로드"""
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def on_coder_message(self, msg: dict):
        print("[Supervisor] 이벤트 수신:", msg)

        if msg.get("command") == "git":
            if msg.get("action") == "edit":
                metadata = msg.get("metadata", {})
                print("\n[Supervisor] Coder가 제안한 코드 수정안:")
                for filename, content in metadata.items():
                    print(f"\n--- {filename} ---\n{content}\n")
                
                user_input = input("[Supervisor] 이 수정 내용으로 학습을 진행할까요?")
                intent = self.intent_cls.get_intent(user_input)

                if intent == "positive":
                    print("[Supervisor] 수정안을 토대로 학습을 진행하겠습니다.")
                    task = build_task(command="git", action="run_in_venv", target="train.py",metadata={"cwd":"simple-object-detection/","venv_path":"simple-object-detection/venv"})
                    self.socket.send_supervisor_response(task)
                    
                elif intent == "negative":
                    print("[Supervisor] 수정이 취소되었습니다. 입력 루프로 돌아갑니다.")
                    raise StopIteration
                 
                elif intent == "revise":
                    print("[Supervisor] 수정 재요청")

            elif msg.get("action") == "clone_repo":
                if msg.get("result") == "success":
                    print("[Supervisor] 환경 세팅 완료.")
                    task = build_task("git", "read_py_files", metadata={"dir_path": "simple-object-detection/"})
                    self.socket.send_supervisor_response(task)                
            
            elif msg.get("action") == "read_py_files":
                self.py_files = msg
                print(f"files_py_msg : {msg}")
                model_summary = self.git_handler.summarize_experiment(msg, persistent=True)
                print(model_summary["system_summary"])

                user_input = input("[Supervisor] 이 내용으로 진행할까요?")
                intent = self.intent_cls.get_intent(user_input)

                if intent == "positive":
                    task = build_task("git", "create_venv", metadata={"dir_path": "simple-object-detection/","requirements":"requirements.txt"})
                    self.socket.send_supervisor_response(task)

                elif intent == "negative":
                    print("[Supervisor] 취소되었습니다. 입력 루프로 돌아갑니다.")
                    raise StopIteration                
            
            elif msg.get("action") == "create_venv":
                if msg.get("result") == "success":
                    edit_input = input("수정할 내용을 입력해주세요: ")
                    target, metadata = self.git_handler.generate_edit_task(edit_input, self.py_files, persistent=True)
                    task = build_task(command="git", action="edit", target=target, metadata=metadata)
                    self.socket.send_supervisor_response(task)




    def run(self):
        """Supervisor 메인 실행 루프"""
        self.llm.load_model()
        self.socket.run_main()

        while True:
            try:
                text = input("[Supervisor] 무엇을 도와드릴까요?")

                if text.lower() == "exit":
                    print("[Supervisor] 종료")
                    break

                if text.lower() == "reset":
                    self.llm.reset_memory()
                    print("[Supervisor] 대화 메모리 초기화됨.")
                    continue


                # ===== 1. Command 분류 =====
                command, persistent = self.router.get_command(text)

                # ===== 2. Command별 처리 =====
                if command == "git":
                    url = self.git_handler.handle(text, persistent=persistent)
                    task = build_task(command=command, action="clone_repo", metadata={"git_url":url})
                    self.socket.send_supervisor_response(task)

            except StopIteration:
                continue

if __name__ == "__main__":
    model_name = "Qwen/Qwen2.5-1.5B-Instruct"
    host = "0.0.0.0"
    port = 9002
    supervisor = Supervisor(model_name, host, port)
    supervisor.run()