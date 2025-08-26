from utils.network import supervisor_socket
from transformers import AutoModelForCausalLM, AutoTokenizer
import re, logging, json, yaml
from utils.db.db import DBManager
from utils.web.web_manager import WebManager

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
                    
                    coder_input = {
                        "files": [
                            {
                                "filename": "model.py",
                                "content": """\
                    import torch
                    import torch.nn as nn

                    class SimpleMLP(nn.Module):
                        def __init__(self, input_dim=784, hidden_dim=128, output_dim=10):
                            super(SimpleMLP, self).__init__()
                            self.layers = nn.Sequential(
                                nn.Linear(input_dim, hidden_dim),
                                nn.ReLU(),
                                nn.Linear(hidden_dim, output_dim)
                            )
                        
                        def forward(self, x):
                            return self.layers(x)
                    """,
                                "language": "python",
                                "type": "code"
                            },
                            {
                                "filename": "train.py",   
                                "content": """\
                    import torch
                    import torch.nn as nn
                    import torch.optim as optim
                    from torchvision import datasets, transforms
                    from torch.utils.data import DataLoader

                    from model import SimpleMLP

                    # 하이퍼파라미터
                    batch_size = 64
                    lr = 0.001
                    epochs = 5

                    # 데이터셋 (MNIST 예시)
                    transform = transforms.Compose([
                        transforms.ToTensor(),
                        transforms.Lambda(lambda x: x.view(-1))  # (1,28,28) -> (784,)
                    ])

                    train_dataset = datasets.MNIST(root="./data", train=True, transform=transform, download=True)
                    test_dataset = datasets.MNIST(root="./data", train=False, transform=transform, download=True)

                    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
                    test_loader = DataLoader(test_dataset, batch_size=batch_size)

                    # 모델/손실/최적화기
                    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                    model = SimpleMLP().to(device)
                    criterion = nn.CrossEntropyLoss()
                    optimizer = optim.Adam(model.parameters(), lr=lr)

                    # 학습 루프
                    for epoch in range(epochs):
                        model.train()
                        total_loss = 0
                        for x, y in train_loader:
                            x, y = x.to(device), y.to(device)

                            optimizer.zero_grad()
                            preds = model(x)
                            loss = criterion(preds, y)
                            loss.backward()
                            optimizer.step()

                            total_loss += loss.item()

                        print(f"Epoch [{epoch+1}/{epochs}], Loss: {total_loss/len(train_loader):.4f}")

                    # 평가
                    model.eval()
                    correct, total = 0, 0
                    with torch.no_grad():
                        for x, y in test_loader:
                            x, y = x.to(device), y.to(device)
                            preds = model(x)
                            predicted = preds.argmax(dim=1)
                            correct += (predicted == y).sum().item()
                            total += y.size(0)

                    print(f"Test Accuracy: {100*correct/total:.2f}%")
                    """,
                                "language": "python",
                                "type": "code"
                            }
                        ]
                    }
                    self.handle_setup(coder_input)
                        
                            
                        


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
