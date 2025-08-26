from utils import supervisor_socket
from transformers import AutoModelForCausalLM, AutoTokenizer
import re, logging, json
from utils.db.db import DBManager
from utils.web_manager import WebManager

logging.basicConfig(level=logging.INFO)

class Supervisor():
    def __init__(self, model_name: str, host: str, port: int):
        self.model = None
        self.tokenizer = None
        self.model_name = model_name

        # 대화 메시지 버퍼: system 1개로 시작 (이후 add_message로만 관리)
        self.default_system_content = "You are a helpful assistant."
        self.messages = [{"role": "system", "content": self.default_system_content}]

        self.socket = supervisor_socket.SupervisorServer(host, port)
        # self.db = DBManager()
        self.web_manager = WebManager()

    
    def on_message(self,data):
        print("[Main] got message:", data)

 




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

    # ===== 대화 메시지 관리 (add만 존재) =====
    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        # 필요시 최근 N개만 유지 (system은 항상 보존)
        self._trim_messages(max_messages=32)

    def _trim_messages(self, max_messages: int = 32) -> None:
        """system 1개 + 최근 (max_messages-1)개만 유지"""
        if len(self.messages) > max_messages:
            system = self.messages[0]
            rest = self.messages[1:][- (max_messages - 1):]
            self.messages = [system] + rest

    # ===== 공통 generate 헬퍼 =====
    def _generate(self, messages, max_new_tokens: int = 256) -> str:
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)
        output_ids = self.model.generate(**inputs, max_new_tokens=max_new_tokens)
        # 프롬프트 길이만큼 잘라서 순수 생성만 남김
        output_ids = [out[len(inp):] for inp, out in zip(inputs.input_ids, output_ids)]
        return self.tokenizer.batch_decode(output_ids, skip_special_tokens=True)[0]

    # ===== 대화 응답 생성 (현재 self.messages 버퍼로만) =====
    def get_output(self, max_new_token: int) -> str:
        return self._generate(self.messages, max_new_tokens=max_new_token)

    # ===== 코드 블록만 추출 =====
    def get_code(self, text: str) -> str:
        # ChatML 토큰류 제거
        cleaned = re.sub(r"<\|im_start\|>.*?<\|im_end\|>", "", text, flags=re.DOTALL)
        # ```python, ```py, ```(언어 미지정) 모두 지원
        m = re.findall(r"```(?:python|py)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
        return "\n\n".join(s.strip() for s in m) if m else ""

    # ===== 커맨드 분류 (임시 메시지로만; self.messages 오염 X) =====
    def get_command(self, user_text: str) -> str:
        system_cls = (
            "Decide whether the user request is related to exactly one of "
            "[code, conversation, search, agent, git]. "
            "Respond with a single lowercase word only. "
            "If the prompt contains 'code' or 'python', the command must be 'code'."
            "The command must be 'git',if git url is including user prompt. specifically git command means user wanna make a own's project from git repository"
            "if 'project' in user request, it must be git command "
        )
        temp = [
            {"role": "system", "content": system_cls},
            {"role": "user", "content": user_text},
        ]
        raw = self._generate(temp, max_new_tokens=8)

        # 정규화 & 후보 매칭
        norm = re.sub(r"[^a-z]", "", raw.lower())
        for cand in ["code", "conversation", "search", "agent", "git"]:
            if cand in norm:
                return cand
        return "conversation"  # fallback
    
    def extract_urls(self, prompt: str) -> str:
        # URL 패턴 정규식 (http, https 포함)
        url_pattern = r'(https?://[^\s]+)'
        match = re.search(url_pattern, prompt)
        return match.group(0) if match else ""
    
    # ===== 실행 루프 =====
    def run_supervisor(self):
        try:
            self.socket.run_main()
            while True:
                code = None
                url = None
                filename = None            

                text = input("[Supervisor] 무엇을 도와드릴까요? ")
                if text.lower() == "exit":
                    print("[Supervisor] 종료")
                    break

                # 1) 유저 발화 누적
                self.add_message("user", text)

                # 2) 커맨드 분류 (임시 프롬프트 사용)
                command = self.get_command(text)

                # 3) 모델 응답 생성 (대화 버퍼 기반)
                response_text = self.get_output(max_new_token=450)

                if command == "code":
                    code = self.get_code(response_text)
                    filename = input("[Supervisor] 해당 코드를 저장할 파일이름을 정해주세요: ").strip() or None
                
                elif command == "git":
                    url = self.extract_urls(text)
                    rd_me = self.web_manager.get_information_web(url)
                    self.add_message("user",'summurize ' + rd_me)
                    summurize_git = self.get_output(max_new_token=450)
                    
                    tmp_status = input(f"{summurize_git}\n 해당 내용이 맞나요? [Y/N]")
                    
                    if tmp_status =='n' or tmp_status == "N":
                        continue

                # 4) 어시스턴트 응답 누적
                self.add_message("assistant", response_text)

            
                # 6) 로그 저장
                '''
                log_id = self.db.insert_supervisor_log(
                    requester="user1",
                    command=command,
                    code=code,
                    prompt=text,  # 이번 턴의 사용자 입력만 저장
                    supervisor_reply=response_text,
                    filename=filename,
                    agent_name=f"{command}er",
                    url = url
                )
                '''
                # 7) 결과 출력/전송
                result = {
                    "command": command,
                    "code": code,
                    "response_text": response_text,
                    #"log_id": log_id,
                    "filename" : filename,
                    "url" : url
                }
                print(result)
                self.socket.send_supervisor_response(json.dumps(result).encode())

        except Exception as e:
            logging.error("run_supervisor 오류", exc_info=True)


if __name__ == "__main__":
    model_name = "Qwen/Qwen2.5-1.5B-Instruct"
    host = "0.0.0.0"
    port = 9006
    supervisor = Supervisor(model_name, host, port)
    supervisor.socket.on("message", supervisor.on_message)
    supervisor.load_model()
    supervisor.run_supervisor()