from utils.network import supervisor_socket
from transformers import AutoModelForCausalLM, AutoTokenizer
import re, logging, json, yaml
from utils.db.db import DBManager
from utils.web.web_manager import WebManager
import yaml

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
        self.db = DBManager()
        self.web_manager = WebManager()

        # config 로드
        with open("/workspace/AI_Agent/Supervisor/config/prompts.yaml", "r", encoding="utf-8") as f:
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
    
    # ==== Yaml load ====
    def load_config(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)


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

    # ===== 모델 구조 설명 ====
    def summarize_experiment_with_llm(self, coder_input: dict) -> dict:
        """
        coder_input(dict)를 받아 LLM에게 요약을 요청.
        prompts.yaml의 summarize_experiment 프롬프트를 system으로 먹이고
        files 내용을 user message로 전달.
        
        반환:
        {"system_summary": str, "user_summary": str}
        """
        # 파일 리스트 꺼내기
        files = coder_input.get("coder_message", {}).get("metadata", {}).get("files", [])
        
        # 파일들 하나로 합치기
        merged_code = "\n\n".join(
            [f"### {f['filename']}\n{f['content']}" for f in files]
        )
        
        # 메시지 구성
        messages = [
            {"role": "system", "content": self.prompts["summarize_experiment"]},
            {"role": "user", "content": merged_code}
        ]
        
        # LLM 호출
        raw_summary = self._generate(messages, max_new_tokens=256)
        
        # 결과 파싱
        sys_part, user_part = "", ""
        if "[User Summary]" in raw_summary:
            parts = raw_summary.split("[User Summary]")
            sys_part = parts[0].replace("[System Summary]", "").strip()
            user_part = parts[1].strip()
        else:
            sys_part = raw_summary.strip()
            user_part = "No explicit User Summary found."
        
        return {
            "system_summary": sys_part,
            "user_summary": user_part
        }

    # ==== edit_code 부분 =====
    def generate_edit_task(self, user_input: str, experiment: dict) -> dict:
        """
        유저 입력과 experiment 코드(files)를 기반으로
        LLM에게 수정된 전체 코드들을 받아와서
        Coder에 전달할 task JSON으로 만든다.
        """
        files = experiment.get("coder_message", {}).get("metadata", {}).get("files", [])
        
        # 메시지 구성: 파일들을 각각 분리해서 전달
        messages = [
            {"role": "system", "content": self.prompts["edit"]},
            {"role": "user", "content": f"User request: {user_input}"}
        ]
        
        for f in files:
            messages.append(
                {"role": "user", "content": f"### {f['filename']}\n{f['content']}"}
            )
        
        # LLM 호출 → 수정된 코드 블록들 반환 (파일별 구분은 ### filename)
        raw_output = self._generate(messages, max_new_tokens=2048)
        
        # 파싱: 파일별로 코드 나누기
        result = {}
        current_file = None
        buffer = []
        
        for line in raw_output.splitlines():
            if line.startswith("### "):
                if current_file and buffer:
                    result[current_file] = "\n".join(buffer).strip()
                    buffer = []
                current_file = line.replace("### ", "").strip()
            else:
                buffer.append(line)
        
        if current_file and buffer:
            result[current_file] = "\n".join(buffer).strip()
        
        task = {
            "action": "edit",
            "target": list(result.keys()),
            "metadata": result
        }
        
        return task
    
    # ===== system prompt 선택 =====
    def get_system_prompt(self, command: str) -> str:
        return self.prompts.get(command, self.prompts["conversation"])
    
    def handle_setup(self, coder_input: dict):
        """setup 단계: requirements 설치는 생략하고 바로 실행 준비"""
        setup_prompt = self.get_system_prompt("setup")

        messages = [
        {"role": "system", "content": setup_prompt},
        {"role": "user", "content": json.dumps(coder_input)}            
        ]

        raw_plan = self._generate(messages, max_new_tokens=300).strip()
        print("[Supervisor] Setup plan generated:\n", raw_plan)    
            
        files = coder_input.get("files", [])
        if not files:
            print("[Supervisor] 파일이 없습니다.")
            return

        # 1. 준비 완료 메시지
        print("[Supervisor] 프로젝트 준비 완료. 실행을 시작합니다.")
        
        # # 2. DB에도 저장
        # self.db.insert_supervisor_log(
        #     requester="user1",
        #     command="setup",
        #     code=None,
        #     prompt="setup 단계",
        #     supervisor_reply="프로젝트 준비가 완료되었습니다. 학습을 시작합니다.",
        #     filename=None,
        #     agent_name="setup-agent",
        #     url=None
        #     )

        # 3. 실행 task 전송 (예: train.py 있으면 실행)
        for f in files:
            if f["filename"] == "train.py":
                task = {
                    "action": "run",
                    "target": f["filename"]
                }
                print(task)
                print(f"[Supervisor] Coder에게 {f['filename']} 실행 요청")

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

                    # # DB 저장
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

                    # msg = json.dump(task) + "\n"
                    # self.socket.send_supervisor_response(msg.encode())
                    print(f"[Supervisor] Coder에게 git clone 요청 : {url}")
                    
                    coder_input = self.load_config("/workspace/AI_Agent/Supervisor/config/experiment.yaml")
                    coder_input = coder_input["file_content"]
                    model_summary = self.summarize_experiment_with_llm(coder_input)
                    print(model_summary)

                    edit_input = input("수정할 내용을 입력해주세요.")
                    edit_result = self.generate_edit_task(edit_input, coder_input)
                    print(edit_result)


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
    port = 9002
    supervisor = Supervisor(model_name, host, port)
    supervisor.load_model()
    supervisor.run_supervisor()
