# runner.py
import subprocess
import tempfile
import os
import sys
import shutil
import time
import re
from utils import coder_socket,file_manager
import subprocess
import threading

class CodeRunner:
    """
    Linux 전용 CodeRunner

    - run(code_str, open_vscode=False, mode="background")
        mode = "background" : 창 없이 백그라운드 실행 (stdout/stderr 캡처)

      반환값(튜플): (stdout, stderr)
        * background: 실제 캡처한 결과를 반환
        * terminal  : 터미널에 표시가 목적이라 ("", "") 반환
                      (로그 경로는 self.last_meta["log"]에 저장됨)

    - cleanup_last_file():
        마지막 실행에서 만든 임시 파일/로그를 삭제
    """

    def __init__(self,host : str, port : int, timeout: int = None, display: str | None = None, python_executable: str | None = None):
        """
        Args:
            timeout: background 모드에서의 실행 제한(초)
            display: 터미널을 띄울 X 디스플레이. 예) ':0', ':1'. None이면 환경변수 DISPLAY 사용
            python_executable: 사용할 파이썬 인터프리터 경로. 기본은 sys.executable
        """
        self.timeout = timeout
        self.display = display  # 필요 시 ':1' 등으로 지정
        self.python = python_executable or sys.executable
        self.last_meta = {"file": None, "log": None}
        self.coder_socket=coder_socket.CoderClient(host,port)
        self.coder_socket.on_message_callback = self.event_message
        self.file_manager=file_manager.FileManager()

    # ---------------- Public API ---------------- #
    def event_message(self,message):
        # 2. task 실행
        code_str = message['code']
        # file_str = message['file']
        output, error = self.run_code(code_str)
        
        # 3. 실행 결과 SUpervisor에 회신
        result = {
            "status": "success" if not error else "error",
            "task_id": message.get("id"),
            "output": output,
            "error": error,
        }
        self.coder_socket.send_message(result)
    
    def run(self):
        #sokcet start
        coder_socet_thread=threading.Thread(target=self.coder_socket.run())
        coder_socet_thread.start()
        
        
        
    ## Require supervisor send format edit
    ## def run_code(self, code_str: str, mode: str = "background", ):
    def run_code(self, code_str: str, file_path:str =None ,zip_path:str =None, mode: str = "background", ):
        if not code_str:
            return "", "Empty code_str."

        tmp_file = self._save_to_temp_file(code_str)
        self.last_meta = {"file": tmp_file, "log": None}

        try: 
            if mode == "background":
                out, err = self._run_background(tmp_file)
                self._safe_remove(tmp_file)
                self.last_meta = {"file": None, "log": None}
                return out, err

            elif mode == "terminal":
                # 터미널 모드에서 실패 원인을 바로 보여줌
                log_file = self._run_in_terminal_typing(tmp_file, code_str, title="llm")
                self.last_meta["log"] = log_file
                return "", ""
            elif mode == "git_install":
                self.file_manager.make_project(file_path)
            
            
            else:
                out, err = self._run_background(tmp_file)
                self._safe_remove(tmp_file)
                self.last_meta = {"file": None, "log": None}
                err = (err or "") + (("\n" if err else "") + "[fallback:background] invalid mode")
                return out, err

        except Exception as e:
            if mode != "terminal":
                self._safe_remove(tmp_file)
                self.last_meta = {"file": None, "log": None}
            return "", f"[terminal-typing-error] {e}"

    def cleanup_last_file(self):
        
        self._safe_remove(self.last_meta.get("file"))
        self._safe_remove(self.last_meta.get("log"))
        self.last_meta = {"file": None, "log": None}

    # ---------------- Internal helpers ---------------- #

    def _save_to_temp_file(self, code_str: str) -> str:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code_str)
            return f.name

    def _run_background(self, file_path: str):
        try:
            result = subprocess.run(
                [self.python, file_path],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            return stdout, stderr
        except subprocess.TimeoutExpired:
            return "", "Execution timed out."


    @staticmethod
    def _safe_remove(path: str | None):
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
        

if __name__ == "__main__":
    coder=CodeRunner(host="172.17.0.1",port=9006)
    #coder.run()
    
 
    
    # git_url="https://github.com/hesyss0713-crypto/AI_Agent_Model"
    # dir_path="/workspace/"
    # coder.file_manager.make_project(dir_path="/workspace", git_path=git_url)
    # file_list=coder.file_manager.get_list_file(dir_path)
    
    # #if file is .py
  

    # coder.file_manager.root=dir_path
    # coder.python=dir_path+"venv/bin/python"
    # coder.file_manager.make_venv(upgrade_deps=False,gitignore=False)

    # python_file="train.py"
    # dir_path="/workspace/AI_Agent_Model/"
    # coder._run_background(dir_path+python_file)