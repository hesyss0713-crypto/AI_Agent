from transformers import AutoModelForCausalLM, AutoTokenizer
import logging
import yaml

logging.basicConfig(level=logging.INFO)

class LLMManager:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.model = None
        self.tokenizer = None
        
        # 기본 메세지 세팅
        self.message = [{"role": "system", "content": "You are a helpful assistant."}]
    
    def load_model(self) -> None:
        try:
            print("모델 로드 중:", self.model_name)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name, torch_dtype="auto", device_map="auto"
            )
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            print("Done.")
        except Exception:
            logging.error("모델 로드 실패", exc_info=True)
    
    def generate(self, messages, max_new_tokens: int = 256) -> str:
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)
        output_ids = self.model.generate(**inputs, max_new_tokens=max_new_tokens)
        output_ids = [out[len(inp):] for inp, out in zip(inputs.input_ids, output_ids)]
        return self.tokenizer.batch_decode(output_ids, skip_special_tokens=True)[0]
    
    def run_with_prompt(self, system_prompt: str, user_content: str, max_new_tokens=256, persistent=False) -> str:
        """
        system + user으로 대답 생성
        - persistent=True → 세션 유지
        - persistent=False → 1회성 실행
        """
        if persistent:
            self.message.append({"role": "system", "content": system_prompt})
            self.message.append({"role": "user", "content": user_content})
            result = self.generate(self.message, max_new_tokens=max_new_tokens)
            self.message.append({"role": "assistant", "content": result})
        else:
            temp_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
            result = self.generate(temp_messages, max_new_tokens=max_new_tokens)
        return result

    def reset_memory(self):
        """메모리 초기화"""
        self.message = [{"role": "system", "content": "You are a helpful assistant."}]

