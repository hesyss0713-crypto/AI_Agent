import socket
import json
import threading

class SupervisorServer:
    def __init__(self, host="0.0.0.0", port=9000):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def start(self):
        """서버 시작"""
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        print(f"[Supervisor] Listening on {self.host}:{self.port}")

        while True:
            conn, addr = self.server_socket.accept()
            threading.Thread(
                target=self.handle_client,
                args=(conn, addr),
                daemon=True
            ).start()

    def receive_all(self, sock):
        """모든 데이터 수신"""
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)

    def handle_client(self, conn, addr):
        """클라이언트 연결 처리"""
        with conn:
            print(f"[Supervisor] Connected by {addr}")
            try:
                data = self.receive_all(conn)
                if not data:
                    return

                task_data = json.loads(data.decode())
                print(f"[Supervisor] Received: {task_data}")

                # 여기서 LLM 처리 → 코드 실행 → 응답
                processed_code = json.dumps({
                    "status": "ok",
                    "message": "코드 실행 완료"
                }).encode()
                self.send_llm_response(conn, processed_code)

            except Exception as e:
                print(f"[Supervisor] Error: {e}")
                conn.sendall(json.dumps({"status": "error", "message": str(e)}).encode())

    def send_llm_response(self, conn, processed_code):
        """LLM 처리 결과 전송"""
        try:
            conn.sendall(processed_code)
        except Exception:
            conn.sendall("Error!!".encode())

    def run_main(self):
        """메인 스레드 실행"""
        server_thread = threading.Thread(target=self.start, daemon=True)
        server_thread.start()

        


if __name__ == "__main__":
    server = SupervisorServer()
    server.run_main()