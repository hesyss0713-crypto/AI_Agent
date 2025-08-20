import socket
import json
import threading
import sys
import os
import time
import queue


class CoderClient:
    def __init__(self, host="172.17.0.3", port=9000):
        self.supervisor_host = host
        self.supervisor_port = port
        self.running = True
        self.sock=None
        self.on_message_callback = None 
        
    ## 메세지 받기
    def on_message(self, message: str)->None: # callback
        if self.on_message_callback:
            self.on_message_callback(message)
    
    ## 결과 전송
    def send_message(self,result ):
        self.sock.sendall(json.dumps(result).encode())
        print("[CoderClient] 결과 전송 완료")
    
    
    def handle_connection(self,):
        """Supervisor와 연결을 유지하며 task를 받고 실행"""
        with self.sock :
            while self.running:
                try:
                    # 1. Supervisor → Client : task 수신
                    data = self.sock.recv(8192)
                    if not data:
                        print("[CoderClient] 연결 종료됨.")
                        break

                    message = json.loads(data.decode())
                    print("[CoderClient] 받은 task:", message)
                    
                    self.on_message(message)

                except Exception as e:
                    print(f"[CoderClient] Error: {e}")
                    break

    def run(self):
        """Supervisor와 연결 시도 및 메인 루프"""
        while self.running:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock .connect((self.supervisor_host, self.supervisor_port))
                print(f"[CoderClient] Supervisor({self.supervisor_host}:{self.supervisor_port}) 연결 성공")
                self.handle_connection()

            except Exception as e:
                print(f"[CoderClient] 연결 실패, 재시도 중... {e}")
                time.sleep(3)  # 연결 실패 시 재시도

        print("[CoderClient] 종료됨.")


if __name__ == "__main__":
    client = CoderClient(host="127.0.0.1", port=9006)
