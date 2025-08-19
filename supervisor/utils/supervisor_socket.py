import socket
import json
import threading

class SupervisorServer:
    def __init__(self, host="0.0.0.0", port=9000):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn=None
        self.addr=None
        
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

                task_data = json.loads(data.decode())
                print(f"[Supervisor] Received: {task_data}", flush=True)


        except Exception as e:
            print(f"[Supervisor] Error: {e}")


    def send_llm_response(self, response):
        """LLM 처리 결과 전송"""
        try:
            self.conn.sendall(response)
        except Exception as e :
            print(e)

    def run_main(self):
        """메인 스레드 실행"""
        server_thread = threading.Thread(target=self.start, daemon=True)
        server_thread.start()
    


if __name__ == "__main__":
    server = SupervisorServer()
    server.run_main()