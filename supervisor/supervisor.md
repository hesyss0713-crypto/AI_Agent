# 네이밍 컨벤션 & 데이터 사전

## 📌 공통 네이밍 규칙
- **클래스명**: PascalCase (예: ExampleClass)
- **함수명/메서드명**: snake_case (예: example_function)
- **변수명**: snake_case (예: example_variable)
- **상수명**: UPPER_SNAKE_CASE (예: EXAMPLE_CONSTANT)
- **프라이빗 속성**: _(언더스코어) prefix (예: _example_private)
- **모듈명**: snake_case (예: example_module.py)

---

## 📄 supervisor.py
### 🔹 전역 변수 / 함수
| 이름             | 타입             | 설명                       | 예시 |
|------           |------            |------                      |------                                           |
|SuperVisor       |class             |LLM모델 로드 및 소켓 통신 시작|supervisor=Supervisor(model_name,host,port)      |
|self.model_name  |str               |모델명                       |self.model_name="model"
|self.model       |huggingface.model |모델                         |self.model= AutoModelForCausalLM.from_pretrained(self.model_name..)
|self.message_type|str               |llm 모델 및 유저 정의         |
|self.socket      |sock              |socket 클래스                |




### 🔹 class: Supervisor
| 속성/메서드 | 타입 | 설명 | 예시 |
|-------------|------|------|------|
|             |      |      |      |

---

## 📄 coder.py
### 🔹 전역 변수 / 함수
| 이름 | 타입 | 설명 | 예시 |
|------|------|------|------|
|      |      |      |      |

### 🔹 class: CoderClient
| 속성/메서드 | 타입 | 설명 | 예시 |
|-------------|------|------|------|
|             |      |      |      |