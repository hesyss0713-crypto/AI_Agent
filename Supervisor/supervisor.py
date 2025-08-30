import logging
import yaml
from utils.network import supervisor_socket, event_emitter
from utils.db.db import DBManager
from utils.router import CommandRouter
from utils.intent import IntentClassifier
from utils.message_builder import build_task, build_response
from handlers.git_handler import GitHandler
from llm.llm_manager import LLMManager
from pathlib import Path
import json
BASE_DIR = Path(__file__).resolve().parent 
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
        self.emitter = self.socket.emitter
        self.emitter.on("coder_message", self.on_coder_message)

    def load_prompts(self, path=BASE_DIR/"config"/"prompts.yaml") -> dict:
        """system prompt yaml 로드"""
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def on_coder_message(self, msg: dict):
        print("[Supervisor] 이벤트 수신:", msg)

        # if msg.get("command") == "git":
        #     if msg.get("action") == "edit":
        #         metadata = msg.get("metadata", {})
        #         print("\n[Supervisor] Coder가 제안한 코드 수정안:")
        #         for filename, content in metadata.items():
        #             print(f"\n--- {filename} ---\n{content}\n")
                
        #         user_input = input("[Supervisor] 이 수정 내용으로 학습을 진행할까요?")
        #         intent = self.intent_cls.get_intent(user_input)

        #         if intent == "positive":
        #             print("[Supervisor] 수정안을 토대로 학습을 진행하겠습니다.")
        #             task = build_task(command="git", action="run", target="train.py")
        #             self.socket.send_supervisor_response(task)
                    
        #         elif intent == "negative":
        #             print("[Supervisor] 수정이 취소되었습니다. 입력 루프로 돌아갑니다.")
        #             raise StopIteration
                
        #         elif intent == "revise":
        #             print("[Supervisor] 수정 재요청")
            
        action = msg["action"]
        result = msg["result"]
        # 2. git clone한 파일 목록 요청
        if action == "clone_repo" and result !=None:
            task = build_task("git", "list_files", metadata={"dir_path": "AI_Agent_Model/"})
            self.socket.send_supervisor_response(task)

        
        # 3. 파일 목록 요청후 (사용자 승인하에) 가상 환경 생성
        elif action == "list_files" and result !=None:
            task = build_task("git", "create_venv", metadata={"dir_path": "AI_Agent_Model/","requirements":"requirements.txt"})
            self.socket.send_supervisor_response(task)
        
        
        ## 4. 파일 내용 읽어 들이기
        elif action == "create_venv" and result !=None:
            task = build_task("git", "read_py_files", metadata={"dir_path": "AI_Agent_Model/"})
            self.socket.send_supervisor_response(task)
        
        
        # 5. 파일 수정 요청
        elif action == "read_py_files" and result !=None:
            coder_input = self.load_prompts(path=BASE_DIR/"config"/"experiment.yaml")["file_content"]
            model_summary = self.git_handler.summarize_experiment(coder_input, persistent=False)
            print(model_summary)
# -------------------------------------------------------------------------------------------------------------------------

            # 수정할지 안할지 정해야함. [그냥 진행, 아예 빠져나가기] -> 사용자 입력으로 받아야하니 on_coder말고 여기서 받아서 진행.(아예 빠져나가기 -> continue while 처음으로 돌리기)
            edit_input = "model.py에 fc_layer 를 3개만 추가해줘"
            target, metadata = self.git_handler.generate_edit_task(edit_input, coder_input, persistent=False)
            task = build_task(command="git", action="edit", target=target, metadata=metadata)
            self.socket.send_supervisor_response(task)
    
#         #6번  수정된 모델 train
        elif action == "edit" and result !=None:
            task = build_task(command='train', action='run_in_venv', target='train.py', metadata={"cwd":"AI_Agent_Model/","venv_path":"AI_Agent_Model/venv"})
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

                # 1번 git clone 요청
                task = build_task(command="git", action= "clone_repo", metadata={"git_url":"https://github.com/hesyss0713-crypto/AI_Agent_Model"})
                self.socket.send_supervisor_response(task)
                
                
                
                
    #             # ===== 2. Command별 처리 =====
    #             if command == "git":
    #                 url = self.git_handler.handle(text, persistent=persistent)
    #                 task = build_task(command=command, action= "clone_repo_and_scan", metadata={"git_url":url})
    #                 self.socket.send_supervisor_response(task)
    #                 ## coder로 부터 세팅 되었다고 알림 받아야함. on_coder에서    
    # # -------------------------------------------------------------------------------------------------------------------------
    #                 # git repo clone 이후 → experiment 요약 + 수정
    #                 coder_input = self.load_prompts(path=BASE_DIR/"config"/"experiment.yaml")["file_content"]
    #                 model_summary = self.git_handler.summarize_experiment(coder_input, persistent=persistent)
    #                 print(model_summary)
    # # -------------------------------------------------------------------------------------------------------------------------

    #                 # 수정할지 안할지 정해야함. [그냥 진행, 아예 빠져나가기] -> 사용자 입력으로 받아야하니 on_coder말고 여기서 받아서 진행.(아예 빠져나가기 -> continue while 처음으로 돌리기)
    #                 edit_input = input("수정할 내용을 입력해주세요: ")
    #                 target, metadata = self.git_handler.generate_edit_task(edit_input, coder_input, persistent=persistent)
                    

    #                 task = build_task(command=command, action="edit", target=target, metadata=metadata)
    #                 self.socket.send_supervisor_response(task)
                    
    # # --------------user 실행 여부 check --------------------------------------------------------------------------------------------
                    
    #                 task = build_task(command='train', action='run', target='train.py')
    #                 self.socket.send_supervisor_response(task)

    #             elif command == "conversation":
    #                 reply = self.llm.run_with_prompt(self.prompts["conversation"], text, persistent=persistent)
    #                 print("[Conversation]", reply)

    #             else:
    #                 print(f"[Supervisor] 아직 구현되지 않은 명령: {command}")
            
            except StopIteration:
                continue

if __name__ == "__main__":
    model_name = "Qwen/Qwen2.5-1.5B-Instruct"
    host = "0.0.0.0"
    port = 9002
    supervisor = Supervisor(model_name, host, port)
    supervisor.run()