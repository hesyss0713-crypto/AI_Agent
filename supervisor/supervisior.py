from utils import supervisor_socket
from transformers import AutoModelForCausalLM, AutoTokenizer
import logging
import json
logging.basicConfig(level=logging.INFO)


class Supervisor():
    def __init__(self,model_name: str,host : str ,port: int):
        self.model=None
        self.tokenizer=None
        self.model_name = model_name
        self.messages=None
        self.default_system_content="You are a helpful assistant."
        self.prompt= [
    {"role": "system", "content": self.default_system_content},
    {"role": "user", "content": " "}]
        
        self.socket=supervisor_socket.SupervisorServer(host, port)
    
    def load_model(self)->None :
        try:
            print("Load model: "+ self.model_name)
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
        self.prompt[0]["content"]=content

    def set_user_prompt(self, content: str) -> None:
        self.prompt[1]["content"]=content
        
    ## output 생성
    def get_output(self,max_new_token):
        text = self.tokenizer.apply_chat_template(
        self.prompt,
        tokenize=False,
        add_generation_prompt=True
    )
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
    
    
    def get_command(self,text):
        content=f"""Decide whether the above question is related to 
        
        [code, conversation, search, agent] 
        
        Answer strictly with a single word like 'code' or 'search'. and you can choose only one.

        if 'code','python' is in prompt, command must be 'code'."""

        self.set_system_prompt(content)
        self.set_user_prompt(text)
        command=self.get_output(max_new_token=10)
        
        # 후보군 중 첫 번째 매칭 반환
        for candidate in ["conversation", "agent", "search", "code"]:
            if candidate in command:
                return candidate
        return command
    
    def run_supervisor(self):
        try:
            self.socket.run_main()
            while True:
                text = input("Supervisor main thread > ")
                if text.lower() == "exit":
                    print("[Supervisor] 종료")
                    break
                else:
                    print(f"[Supervisor] 명령 '{text}' 처리 중...")

                    self.set_user_prompt(text)

                    # 2. 명령어 추출
                    command = self.get_command(text)
                    
                    # 3. 유저 응답 추출
                    self.set_system_prompt(self.default_system_content)
                    
                    # 4. 모델 응답 생성
                    response_text = self.get_output( max_new_token=500)

                    # 5. 출력 및 직렬화
                    result = {"command": command, "response": response_text}
                    print(result, flush=True)

                    # 6. 전송
                    self.socket.send_llm_response(json.dumps(result).encode())
           
        except Exception as e:
            print(e)

                
            
if __name__=="__main__":
    
    model_name="Qwen/Qwen2.5-1.5B-Instruct"
    host="0.0.0.0"
    port=9006
    supervisor=Supervisor(model_name,host,port)
    supervisor.load_model()
    supervisor.run_supervisor()
    
    

   