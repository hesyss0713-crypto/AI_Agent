import socket
import json
import time
import threading

class CoderClient:
    def __init__(self, host="172.17.0.3", port=9000, interval=5):
        self.supervisor_host = host
        self.supervisor_port = port
        self.interval = interval
        self.running = True

    def receive_all(self, sock):
        """Supervisor 응답 전체 받기"""
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)

    def send_task(self, task_data):
        """Supervisor에 작업 전송 후 응답 받기"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)  # 연결/수신 타임아웃 5초
                s.connect((self.supervisor_host, self.supervisor_port))
                s.sendall(json.dumps(task_data).encode())
                response_data = self.receive_all(s)
                return json.loads(response_data.decode())
        except socket.timeout:
            return {"status": "error", "message": "Timeout: Supervisor 응답 없음"}
        except ConnectionRefusedError:
            return {"status": "error", "message": "Connection refused: Supervisor 서버 미동작"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def worker_loop(self):
        """백그라운드에서 주기적으로 Supervisor에 작업 전송"""
        while self.running:
            task = {
                "task": "코드 실행",
                "details": {
                    "id": int(time.time()),
                    "code": "print('Hello from Coder!')"
                }
            }
            print("[Coder Thread] Sending task to Supervisor:", task)
            result = self.send_task(task)
            print("[Coder Thread] Supervisor response:", result)

            time.sleep(self.interval)

    def run(self):
        """메인 루프 실행"""
        comm_thread = threading.Thread(target=self.worker_loop, daemon=True)
        comm_thread.start()

        while True:
            cmd = input("[Coder Main] 명령 입력(exit 입력 시 종료): ")
            if cmd.lower() == "exit":
                print("[Coder Main] 종료합니다.")
                self.running = False
                break
            else:
                print(f"[Coder Main] 입력한 명령: {cmd}")

if __name__ == "__main__":
    # Supervisor의 Docker 네트워크 IP나 서비스명으로 설정
    coder = CoderClient(host="172.17.0.3", port=9000, interval=5)
    coder.run()
