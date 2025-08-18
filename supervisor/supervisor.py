from utils import socket
from transformers import AutoModelForCausalLM, AutoTokenizer
import logging
import json
import re
from typing import Dict,List
from utils.db.db import DBManager
logging.basicConfig(level=logging.INFO)


class Supervisor():
    def __init__(self,model_name: str,host : str ,port: int):
        self.model=None
        self.tokenizer=None
        self.model_name = model_name
        self.messages=None
        self.prompt=None
        self.system_prompt="You are a helpful assistant"
        self.socket=socket.SupervisorServer(host, port)
        self.db = DBManager()
    
    def load_model(self)->None :
        try:
            print("Load mode l: "+ self.model_name)
            self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype="auto",
            device_map="auto"
        )
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            print("Done.")
        except Exception as e:
            logging.error("모델 로드 실패", exc_info=True)
    
    
    def set_system_prompt(self, content: str) -> None:
        self.system_prompt = content

    def build_system_message(self) -> Dict[str, str]:
        return {"role": "system", "content": self.system_prompt}
    
    
    ## message 타입 설정
    def build_messages(self) -> List[Dict[str, str]]:
        self.messages= [
                self.build_system_message(),
                {"role": "user", "content": self.prompt or ""},
            ]


    
    ## 프롬프트 입력
    def set_prompt(self,prompt):
        self.prompt=prompt
        self.build_messages()
        text = self.tokenizer.apply_chat_template(
                    self.messages,
                    tokenize=False,
                    add_generation_prompt=True
                )
        return text
    
    ## output 생성
    def get_output(self,text,max_new_token):
        model_inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)

        generated_ids = self.model.generate(
            **model_inputs,
            max_new_tokens=max_new_token
        )
        generated_ids = [
            output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
        ]
        response = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
        
        return response
    
    
    def get_command(self,):
        text = f'''
        {self.prompt}

        Decide whether the above question is related to 
        
        [code, conversation, search, agent] 
        
        Answer strictly with a single word like 'code' or 'search'. and you can choose only one.

        if 'code','python' is in prompt, command must be 'code'.

        '''
        # text = f"""
        # You are a classifier.

        # Task:
        # Classify the following request into exactly ONE category.

        # Categories:
        # -conversation (usually general conversation, chit-chat)
        # -search (weather, person, latest info, etc.)
        # -code (algorithms, class, def, implementation)
        # -agent (meeting minutes, my file, dataset)

        # Rules:
        # - Now classify the request into one of: conversation, search, code, agent.

        # Request: {self.prompt}
        # """
        
        self.system_prompt="You are a classifier"
        self.build_messages()
        
        command = self.get_output(text, max_new_token=10).strip().lower()
        command = command.replace("\n", " ")

        # 후보군 중 첫 번째 매칭 반환
        for candidate in ["conversation", "agent", "search", "code"]:
            if candidate in command:
                return candidate
        return command
    
    def get_code(self, text: str) -> str:
        """
        LLM 응답(예: ChatML 포함)에서 Python 코드만 정제해서 추출.
        - <|im_start|>...<|im_end|> 같은 메타 토큰 제거
        - ```python ... ``` 블록 안 코드만 추출
        """
        # 1. ChatML 같은 메타 토큰 제거
        cleaned = re.sub(r"<\|im_start\|>.*?<\|im_end\|>", "", text, flags=re.DOTALL)

        # 2. 코드 블록만 추출
        matches = re.findall(r"```python\n(.*?)```", cleaned, re.DOTALL)

        if matches:
            return "\n\n".join(m.strip() for m in matches)
        return  
            
    def run_supervisor(self):
        try:
            self.socket.run_main()
            while True:
                cmd = input("Supervisor main thread > ")
                if cmd.lower() == "exit":
                    print("[Supervisor] 종료")
                    break
                else:
                    print(f"[Supervisor] 명령 '{cmd}' 처리 중...")

                    text = self.set_prompt(cmd)

                    # 2. 명령어 추출
                    command = self.get_command()
                    print(f"command is : {command}")
                    # 3. 시스템 프롬프트 원래대로 복원
                    self.set_system_prompt("You are a helpful assistant")
                    self.build_messages()

                    # 4. 모델 응답 생성
                    supervisor_reply = self.get_output(text, max_new_token=350)

                    # 5 code 정제
                    code = self.get_code(supervisor_reply)

                    # 6 filename 명시
                    filename = None
                    if command == "code":
                        filename = input(f"[Supervisor] 해당 코드의 파일명을 입력하세요.")

                    #
                    log_id = self.db.insert_supervisor_log(
                        requester = "uers1",
                        command = command,
                        code = code,
                        prompt = cmd,
                        supervisor_reply = supervisor_reply,
                        filename = filename,
                        agent_name = "coder",
                    )

                    # 6. 출력 및 직렬화
                    result = {
                        "command": command, 
                        "code": code, 
                        "supervisor_reply": supervisor_reply,
                        "log_id" : log_id
                        }
                    
                    print(result, flush=True)

                    # 7. 전송
                    self.socket.send_supervisor_response(json.dumps(result).encode())
           
        except Exception as e:
            print(e)
        
        self.db.close()

                
            
if __name__=="__main__":
    
    model_name="Qwen/Qwen2.5-1.5B-Instruct"
    host="0.0.0.0"
    port=9000
    supervisor=Supervisor(model_name,host,port)
    supervisor.load_model()
    supervisor.run_supervisor()
    