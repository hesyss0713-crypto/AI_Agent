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
        self.prompt=None
        self.system_prompt="You are a helpful assistant"
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
        self.system_prompt = content

    def build_system_message(self) -> dict[str, str]:
        return {"role": "system", "content": self.system_prompt}
    
    
    ## message 타입 설정
    def build_messages(self) -> list[dict[str, str]]:
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
        text = f"""
        You are a classifier.
        Task:
        Classify the following request into exactly ONE category.

        Categories:
        -covnersation (usually general conversation, chit-chat)
        -search (weather, person, latest info, etc.)
        -code (algorithms, class, def, implementation)
        -agent (meeting minutes, my file, dataset)

        Rules:
        - Now classify the request into one of: conversation, search, code, agent.

        Request: {self.prompt}
        """
        
        self.system_prompt="You are a classifier"
        self.build_messages()
        
        command = self.get_output(text, max_new_token=10).strip().lower()
        command = command.replace("\n", " ")
        # 후보군 중 첫 번째 매칭 반환
        for candidate in ["conversation", "agent", "search", "code"]:
            if candidate in command:
                return candidate
        return command
    
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
                    command=self.get_command()
                    self.system_prompt="You are a helpful assistant"
                    self.build_messages()
                    response = self.get_output(text,max_new_token=250)
                    print({"command": command, "response": response})
                    response={"command":command, "response":response}
                    response = json.dumps(response).encode()
                    self.socket.send_llm_response(response)
           
        except Exception as e:
            print(e)

                
            
if __name__=="__main__":
    
    model_name="Qwen/Qwen2.5-1.5B-Instruct"
    host="127.0.0.1"
    port=9006
    supervisor=Supervisor(model_name,host,port)
    supervisor.load_model()
    supervisor.run_supervisor()
    
    



   