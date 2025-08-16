# runner.py
import subprocess
import tempfile
import os
import sys
import shutil
import time
import re

class CodeRunner:
    """
    Linux 전용 CodeRunner

    - run(code_str, open_vscode=False, mode="background")
        mode = "background" : 창 없이 백그라운드 실행 (stdout/stderr 캡처)
        mode = "terminal"   : 팝업 터미널을 띄워 '타이핑'으로 실행(B안) 시도,
                              실패 시 lxterminal --command(A유형)로 폴백

      반환값(튜플): (stdout, stderr)
        * background: 실제 캡처한 결과를 반환
        * terminal  : 터미널에 표시가 목적이라 ("", "") 반환
                      (로그 경로는 self.last_meta["log"]에 저장됨)

    - cleanup_last_file():
        마지막 실행에서 만든 임시 파일/로그를 삭제
    """

    def __init__(self, timeout: int = 10, display: str | None = None, python_executable: str | None = None):
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

    # ---------------- Public API ---------------- #

    def run(self, code_str: str, open_vscode: bool = False, mode: str = "background"):
        if not code_str:
            return "", "Empty code_str."

        tmp_file = self._save_to_temp_file(code_str)
        self.last_meta = {"file": tmp_file, "log": None}

        try:
            if open_vscode:
                self._open_in_vscode(tmp_file)

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

    def _open_in_vscode(self, file_path: str):
        code_bin = shutil.which("code")
        if code_bin:
            # VSCode 미설치 환경이면 조용히 무시
            subprocess.Popen([code_bin, file_path])

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

    # ============== B안: xdotool로 실제 타이핑 보여주기 ==============

    def _run_in_terminal_typing(self, file_path: str, code_str: str, title: str = "llm") -> str:
        if not shutil.which("xdotool"):
            raise RuntimeError("xdotool not found. Install 'xdotool'.")
        if not (shutil.which("xterm") or shutil.which("lxterminal")):
            raise RuntimeError("No terminal found. Install 'xterm' or 'lxterminal'.")

        disp = self.display if self.display is not None else os.environ.get("DISPLAY", "")
        if not disp:
            raise RuntimeError("No DISPLAY set. Cannot open terminal.")

        env = os.environ.copy()
        env["DISPLAY"] = disp
        env.setdefault("LANG", os.environ.get("LANG", "C.UTF-8"))
        env.setdefault("LC_ALL", os.environ.get("LC_ALL", env["LANG"]))

        # 0) WM 준비 대기 (없으면 Fatal IO가 잘 뜸)
        #    _NET_SUPPORTING_WM_CHECK가 잡힐 때까지 잠깐 대기
        for _ in range(50):
            try:
                probe = subprocess.run(["sh", "-lc", "xprop -root _NET_SUPPORTING_WM_CHECK >/dev/null 2>&1"],
                                    env=env)
                if probe.returncode == 0:
                    break
            except Exception:
                pass
            time.sleep(0.1)

        # 기존 동일 제목 창 정리
        existing = subprocess.run(["xdotool", "search", "--name", title],
                                capture_output=True, text=True, env=env)
        for wid in existing.stdout.strip().split():
            if wid:
                subprocess.run(["xdotool", "windowkill", wid], env=env)

        # 터미널 실행
        self._spawn_terminal(title, env)
        time.sleep(0.4)

        # 창 대기(제목 → 클래스)
        wid = self._wait_for_window(title, env=env, timeout=8.0)
        if not wid:
            wid = self._wait_for_window(None, env=env, timeout=3.0,
                                        class_candidates=["XTerm", "LXTerminal", "lxterminal"])
        if not wid:
            raise RuntimeError("Failed to find terminal window")

        # 활성화(activate) 대신 map/raise/focus만 (activate는 WM 따라 실패)
        self._win_activate(wid, env)

        workdir = os.path.dirname(file_path) or "."
        filename = os.path.basename(file_path)
        log_file = file_path + ".log"

        def type_line(s: str, enter=True, delay=0.15):
            subprocess.run(["xdotool", "type", "--window", wid, s], env=env)
            time.sleep(delay)
            if enter:
                subprocess.run(["xdotool", "key", "--window", wid, "Return"], env=env)
                time.sleep(0.12)

        # 실제 타이핑
        type_line(f"cd {workdir}")
        type_line(f"vi {filename}")
        type_line(":set paste")
        time.sleep(0.1)
        subprocess.run(["xdotool", "type", "--window", wid, "i"], env=env)
        time.sleep(0.12)

        if not code_str:
            raise RuntimeError("Empty code for typing")
        for line in code_str.rstrip("\n").split("\n"):
            subprocess.run(["xdotool", "type", "--window", wid, line], env=env)
            subprocess.run(["xdotool", "key", "--window", wid, "Return"], env=env)
            time.sleep(0.02)

        subprocess.run(["xdotool", "key", "--window", wid, "Escape"], env=env); time.sleep(0.12)
        type_line(":wq!")

        # 화면 + 로그 동시 출력(tee). 창을 열어둠(bash)
        run_cmd = f'{self.python} {filename} 2>&1 | tee -a "{log_file}"; echo; echo "--- finished ---"; bash'
        type_line(run_cmd, delay=0.08)

        return log_file

    
    def _spawn_terminal(self, title: str, env):
        xterm = shutil.which("xterm")
        if xterm:
            subprocess.Popen(
                [xterm, "-T", title, "-fa", "monospace", "-fs", "11"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return
        lxterm = shutil.which("lxterminal")
        if lxterm:
            subprocess.Popen(
                ["lxterminal", f"--title={title}"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL  # vte 경고 숨김
            )
            return
        raise RuntimeError("No terminal found (install xterm or lxterminal).")
    
    def _wait_for_window(self, name_pattern: str | None, env, timeout: float = 8.0, class_candidates=None):
        import time, subprocess
        t0 = time.time()
        while time.time() - t0 < timeout:
            ids = []
            if name_pattern:
                p = subprocess.run(["xdotool", "search", "--name", name_pattern],
                                capture_output=True, text=True, env=env)
                ids += p.stdout.strip().split()
            if not ids and class_candidates:
                for cls in class_candidates:
                    p = subprocess.run(["xdotool", "search", "--class", cls],
                                    capture_output=True, text=True, env=env)
                    ids += p.stdout.strip().split()
            if ids:
                return ids[-1]  # 보통 마지막이 최신
            time.sleep(0.1)
        return None

    def _win_activate(self, wid: str, env):
        import time, subprocess
        # 활성화 대신 map/raise만 수행 (activate는 WM에 따라 실패)
        subprocess.run(["xdotool", "windowmap", wid], env=env)
        time.sleep(0.05)
        subprocess.run(["xdotool", "windowraise", wid], env=env)
        time.sleep(0.10)
        # 포커스도 시도하되 실패해도 무시
        subprocess.run(["xdotool", "windowfocus", wid], env=env)
        time.sleep(0.10)



    # ============== A유형: lxterminal --command (폴백 경로) ==============

    def _run_in_terminal_lx(self, file_path: str) -> str:
        """
        lxterminal을 새 창으로 띄워 파일을 실행.
        출력은 터미널에 표시되고, 동시에 로그 파일로 저장됨.
        실행 종료 후 터미널은 계속 열려 있음.
        Returns:
            log_file_path
        Raises:
            RuntimeError if DISPLAY/lxterminal missing
        """
        lxterm = shutil.which("lxterminal")
        if not lxterm:
            raise RuntimeError("lxterminal not found. Install 'lxterminal'.")

        # DISPLAY 설정 확인
        disp = self.display if self.display is not None else os.environ.get("DISPLAY", "")
        if not disp:
            raise RuntimeError("No DISPLAY set. Cannot open terminal.")

        env = os.environ.copy()
        env["DISPLAY"] = disp
        # 로케일 경고 방지(없으면 조용히 진행)
        env.setdefault("LANG", os.environ.get("LANG", "C.UTF-8"))
        env.setdefault("LC_ALL", os.environ.get("LC_ALL", env["LANG"]))

        log_file = file_path + ".log"
        run_line = (
            f'"{self.python}" "{file_path}" 1>>"{log_file}" 2>&1; '
            f'echo; echo "--- finished ---"; bash'
        )

        subprocess.Popen(
            [lxterm, "--command", f"bash -lc {self._quote_for_shell(run_line)}"],
            env=env
        )
        return log_file

    @staticmethod
    def _quote_for_shell(cmd: str) -> str:
        # 작은따옴표 안전 이스케이프
        return "'" + cmd.replace("'", "'\"'\"'") + "'"

    @staticmethod
    def _safe_remove(path: str | None):
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


if __name__ == "__main__":
    runner = CodeRunner(timeout=5, display=":1")  # GUI 세션이 :1이라면
    sample_code = """
import time
print("Hello from CodeRunner!")
time.sleep(1)
print("Done!")
"""

    print("=== Background Mode ===")
    out, err = runner.run(sample_code, mode="background")
    print("[STDOUT]")
    print(out)
    print("[STDERR]")
    print(err)

    print("\n=== Terminal Mode (typing) ===")
    out, err = runner.run(sample_code, mode="terminal")
    print("[STDOUT]")
    print(out)
    print("[STDERR]")
    print(err)
    print("Log file:", runner.last_meta.get("log"))
