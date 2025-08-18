import socket
import json
import threading
import sys
import os
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from code_runner import CodeRunner



class CoderClient:
    def __init__(self, host="172.17.0.3", port=9000):
        self.supervisor_host = host
        self.supervisor_port = port
        self.running = True
        

    def handle_connection(self, conn: socket.socket):
        """Supervisor와 연결을 유지하며 task를 받고 실행"""
        with conn:
            while self.running:
                try:
                    # 1. Supervisor → Client : task 수신
                    data = conn.recv(8192)
                    if not data:
                        print("[CoderClient] 연결 종료됨.")
                        break

                    task = json.loads(data.decode())
                    print("[CoderClient] 받은 task:", task)

                    # 2. task 실행
                    code_str = task['code']

                    output, error = self.runner.run(code_str)

                    # 3. 실행 결과 Supervisor에 회신
                    result = {
                        "status": "success" if not error else "error",
                        "task_id": task.get("id"),
                        "output": output,
                        "error": error,
                    }
                    conn.sendall(json.dumps(result).encode())
                    print("[CoderClient] 결과 전송 완료")

                except Exception as e:
                    print(f"[CoderClient] Error: {e}")
                    break

    def run(self):
        """Supervisor와 연결 시도 및 메인 루프"""
        while self.running:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((self.supervisor_host, self.supervisor_port))
                print(f"[CoderClient] Supervisor({self.supervisor_host}:{self.supervisor_port}) 연결 성공")

                self.handle_connection(s)

            except Exception as e:
                print(f"[CoderClient] 연결 실패, 재시도 중... {e}")
                time.sleep(3)  # 연결 실패 시 재시도

        print("[CoderClient] 종료됨.")


if __name__ == "__main__":
    client = CoderClient(host="127.0.0.1", port=9006)
