import socket
import json
import threading
from .event_emitter import EventEmitter
from typing import Optional, Dict, Any
class SupervisorServer:
    def __init__(self, host="0.0.0.0", port=9001):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.conn=None
        self.addr=None
        self.emitter = EventEmitter()

    def start(self):
        """서버 시작"""
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        print(f"[Supervisor] Listening on {self.host}:{self.port}")

        while True:
            self.conn, self.addr = self.server_socket.accept()
            threading.Thread(
                target=self.handle_client,
                daemon=True
            ).start()

    def handle_client(self,):
        """클라이언트 연결 처리"""
        print(f"[Supervisor] Connected by {self.addr}")
        try:
            while True:
                data = self.conn.recv(4096)
                if not data:
                    break

                try:
                    task_data = json.loads(data.decode())             
                    self.emitter.emit("coder_message", task_data)

                except json.JSONDecodeError:
                    print("[Supervisor] Invalid JSON received:", data.decode())

        except Exception as e:
            print(f"[Supervisor] Error: {e}")

    def send_supervisor_response(self, response):
        """supervisor 처리 결과 전송"""
        try:
            response = json.dumps(response).encode("utf-8")
            if isinstance(response, str):
                response = response.encode("utf-8")
            self.conn.sendall(response)
        except Exception as e:
            print(f"[Supervisor] 응답 전송 오류: {e}")
            self.conn.sendall(b"Error!!")

    def run_main(self):
        """메인 스레드 실행"""
        server_thread = threading.Thread(target=self.start, daemon=True)
        server_thread.start()
    


if __name__ == "__main__":
    server = SupervisorServer()
    server.run_main()