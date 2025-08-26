from utils.network import supervisor_socket
from transformers import AutoModelForCausalLM, AutoTokenizer
import re, logging, json, yaml
from utils.db.db import DBManager
from utils.web.web_manager import WebManager
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


logging.basicConfig(level=logging.INFO)


class Supervisor():
    def __init__(self, model_name: str, host: str, port: int):
        self.model = None
        self.tokenizer = None
        self.model_name = model_name

        # 기본 메시지 버퍼
        self.messages = [{"role": "system", "content": "You are a helpful assistant."}]

        # 소켓, DB, 웹 매니저
        self.socket = supervisor_socket.SupervisorServer(host, port)
        #self.db = DBManager()
        self.web_manager = WebManager()

        # config 로드
        file_path = os.path.join(BASE_DIR, "config", "prompts.yaml")
        with open(file_path, "r", encoding="utf-8") as f:
            self.prompts = yaml.safe_load(f)

    # ===== 모델 로드 =====
    def load_model(self) -> None:
        try:
            print("Load model:", self.model_name)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name, torch_dtype="auto", device_map="auto"
            )
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            print("Done.")
        except Exception:
            logging.error("모델 로드 실패", exc_info=True)

    # ===== LLM 호출 =====
    def _generate(self, messages, max_new_tokens: int = 256) -> str:
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)
        output_ids = self.model.generate(**inputs, max_new_tokens=max_new_tokens)
        output_ids = [out[len(inp):] for inp, out in zip(inputs.input_ids, output_ids)]
        return self.tokenizer.batch_decode(output_ids, skip_special_tokens=True)[0]

    # ===== command 분류 =====
    def get_command(self, user_text: str) -> str:
        system_cls = self.prompts["classifier"]
        temp = [
            {"role": "system", "content": system_cls},
            {"role": "user", "content": user_text},
        ]
        raw = self._generate(temp, max_new_tokens=8)
        norm = re.sub(r"[^a-z]", "", raw.lower())
        for cand in ["git", "setup", "code", "train", "summarize", "compare", "agent", "conversation"]:
            if cand in norm:
                return cand
        return "conversation"

    # ===== system prompt 선택 =====
    def get_system_prompt(self, command: str) -> str:
        return self.prompts.get(command, self.prompts["conversation"])

    # ===== 실행 루프 =====
    def run_supervisor(self):
        try:
            self.socket.run_main()
            text = input("[Supervisor] 무엇을 도와드릴까요? ")
            while True:
                if text.lower() == "exit":
                    print("[Supervisor] 종료")
                    break

                command = self.get_command(text)

                # ----------------- GIT 단계 -----------------
                if command == "git":
                    url = self.extract_urls(text)
                    readme_text = self.web_manager.get_information_web(url)

                    if not readme_text:
                        print("[Supervisor] README.md를 가져올 수 없습니다.")
                        continue

                    # 요약 생성
                    messages = [
                        {"role": "system", "content": self.get_system_prompt("git")},
                        {"role": "user", "content": readme_text[:2000]},
                    ]
                    project_summary = self._generate(messages, max_new_tokens=400).strip()

                    # 유저 확인
                    tmp_status = input(
                        f"[Supervisor] 해당 프로젝트 요약:\n{project_summary}\n\n"
                        "해당 프로젝트가 맞습니까? [Y/N] "
                    )
                    if tmp_status.lower() != "y":
                        print("[Supervisor] 프로젝트 진행을 취소합니다.")
                        continue

                    # DB 저장
                    # self.db.insert_supervisor_log(
                    #     requester="user1",
                    #     command="git",
                    #     code=None,
                    #     prompt=text,
                    #     supervisor_reply=project_summary,
                    #     filename=None,
                    #     agent_name="giter",
                    #     url=url
                    # )
                    print("[Supervisor] 프로젝트 확인 완료. 다음 단계: setup")
                    task ={
                        "action" : "clone_repo",
                        "url" : url
                    }

                    msg = json.dumps(task) + "\n"
                    self.socket.send_supervisor_response(msg.encode())
                    print(f"[Supervisor] Coder에게 git clone 요청 : {url}")



        except Exception as e:
            logging.error("run_supervisor 오류", exc_info=True)

    # ===== URL 추출 =====
    def extract_urls(self, prompt: str) -> str:
        url_pattern = r'(https?://[^\s]+)'
        match = re.search(url_pattern, prompt)
        return match.group(0) if match else ""


if __name__ == "__main__":
    model_name = "Qwen/Qwen2.5-1.5B-Instruct"
    host = "0.0.0.0"
    port = 9006
    supervisor = Supervisor(model_name, host, port)
    supervisor.load_model()
    supervisor.run_supervisor()