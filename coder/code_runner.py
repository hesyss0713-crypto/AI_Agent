# runner.py
import subprocess
import tempfile
import os
import sys
import shutil
import time
import re
from utils import coder_socket


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

    def __init__(self,host : str, port : int, timeout: int = 10, display: str | None = None, python_executable: str | None = None):
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

    # ---------------- Public API ---------------- #

    def run(self, code_str: str, mode: str = "background"):
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
                # ✅ B안 강제: 타이핑 실패 시 조용히 폴백하지 않고 에러로 알려줌
                log_file = self._run_in_terminal_typing(tmp_file, code_str, title="llm")
                self.last_meta["log"] = log_file
                return "", ""
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
            # 터미널 모드에서 실패 원인을 바로 보여줌
            return "", f"[terminal-typing-error] {e}"

    def cleanup_last_file(self):
        """마지막 실행에서 생성된 임시 파일/로그를 정리."""
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
    coder=CodeRunner(host="172.17.0.1",port=9001)
    coder.coder_socket.run()
    