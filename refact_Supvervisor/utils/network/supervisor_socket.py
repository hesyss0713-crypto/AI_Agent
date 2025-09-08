import socket
import json
import threading 
from .event_emitter import EventEmitter
import struct

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"

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
        print(f"{RED}[Supervisor] Listening on {self.host}:{self.port}{RESET}")

        while True:
            self.conn, self.addr = self.server_socket.accept()
            threading.Thread(
                target=self.handle_client,
                daemon=True
            ).start()

    def handle_client(self):
        """클라이언트 연결 처리"""
        print(f"{RED}[Supervisor] Connected by {self.addr}{RESET}")
        buffer = b""
        expected_len = None

        try:
            while True:
                chunk = self.conn.recv(4096)
                if not chunk:
                    break
                buffer += chunk

                # 메시지 처리 루프
                while True:
                    if expected_len is None:
                        if len(buffer) >= 4:
                            expected_len = struct.unpack("!I", buffer[:4])[0]
                            buffer = buffer[4:]
                        else:
                            break

                    if expected_len is not None and len(buffer) >= expected_len:
                        msg = buffer[:expected_len]
                        buffer = buffer[expected_len:]
                        expected_len = None

                        try:
                            task_data = json.loads(msg.decode("utf-8"))
                            self.emitter.emit("coder_message", task_data)
                        except json.JSONDecodeError:
                            print("[Supervisor] Invalid JSON received:", msg.decode())
                    else:
                        break

        except Exception as e:
            print(f"[Supervisor] Error: {e}")

    def send_supervisor_response(self, response):
        """supervisor 처리 결과 전송"""
        try:
            if isinstance(response, (dict, str)):
                response = json.dumps(response).encode("utf-8")
            length_prefix = struct.pack("!I", len(response))
            self.conn.sendall(length_prefix + response)
        except Exception as e:
            print(f"[Supervisor] 응답 전송 오류: {e}")

    def run_main(self):
        """메인 스레드 실행"""
        server_thread = threading.Thread(target=self.start, daemon=True)
        server_thread.start()
    


if __name__ == "__main__":
    server = SupervisorServer()
    server.run_main()