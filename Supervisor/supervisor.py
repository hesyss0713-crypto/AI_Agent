import logging
import yaml
from utils.network import supervisor_socket
from utils.db.db import DBManager
from utils.router import CommandRouter
from utils.intent import IntentClassifier
from handlers.git_handler import GitHandler
from llm.llm_manager import LLMManager
import json
logging.basicConfig(level=logging.INFO)


class Supervisor:
    def __init__(self, model_name: str, host: str, port: int):
        # LLM 관리 객체
        self.llm = LLMManager(model_name)

        # DB, 소켓
        #self.db = DBManager()
        self.socket = supervisor_socket.SupervisorServer(host, port)

        # config 로드 (prompts.yaml)
        self.prompts = self.load_prompts()

        # Router, IntentClassifier, Handlers 초기화
        self.router = CommandRouter(self.llm, self.prompts)
        self.intent_cls = IntentClassifier(self.llm, self.prompts)
        self.git_handler = GitHandler(self.llm, self.prompts)

    def load_prompts(self, path="/home/test/CustomProject/AI_Agent/Supervisor/config/prompts.yaml") -> dict:
        """system prompt yaml 로드"""
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def run(self):
        """Supervisor 메인 실행 루프"""
        self.llm.load_model()
        self.socket.run_main()

        while True:
            text = input("[Supervisor] 무엇을 도와드릴까요? ")

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
                msg=self.git_handler.handle(text, persistent=persistent)
                
                
                self.socket.send_supervisor_response(json.dumps(msg))
                
                # git repo clone 이후 → experiment 요약 + 수정
                coder_input = self.load_prompts("/home/test/CustomProject/AI_Agent/Supervisor/config/experiment.yaml")["file_content"]
                model_summary = self.git_handler.summarize_experiment(coder_input, persistent=persistent)
                print(model_summary)

                edit_input = input("수정할 내용을 입력해주세요: ")
                edit_result = self.git_handler.generate_edit_task(edit_input, coder_input, persistent=persistent)
                print(edit_result)

            elif command == "conversation":
                reply = self.llm.run_with_prompt(self.prompts["conversation"], text, persistent=persistent)
                print("[Conversation]", reply)

            else:
                print(f"[Supervisor] 아직 구현되지 않은 명령: {command}")


if __name__ == "__main__":
    model_name = "Qwen/Qwen2.5-1.5B-Instruct"
    host = "0.0.0.0"
    port = 9006
    supervisor = Supervisor(model_name, host, port)
    supervisor.run()