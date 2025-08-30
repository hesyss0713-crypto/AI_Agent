# code_runner.py
import json
import logging
import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from utils.coder_socket import CoderClient
from utils.handler_registry import register, registry
from utils.file_manager import FileManager
from utils.web_manager import WebManager

logger = logging.getLogger(__name__)

class CodeRunner:
    def __init__(self, host: str, port: int, python_executable: str | None = None, timeout: int = 60):
        self.python = python_executable or sys.executable
        self.timeout = timeout

        self.file_manager = FileManager(root="/workspace/")
        self.web_manager = WebManager()
        self.client = CoderClient(host, port)
        self.client.on_message_callback = self._on_message

        providers = [self.file_manager, self.web_manager, self]
        self.action_map: Dict[str, Any] = {}
        for name, func in registry.items():
            for provider in providers:
                if hasattr(provider, func.__name__):
                    self.action_map[name] = getattr(provider, func.__name__)
                    break

    @register("run_python")
    def run_python(self, code: str, timeout: int | None = None) -> dict:
        if not code:
            return {"stdout": None, "stderr": "code is empty"}
        tmp = None
        to = timeout or self.timeout
        try:
            fd, tmp = tempfile.mkstemp(suffix=".py")
            os.close(fd)
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(code)
            import subprocess
            result = subprocess.run([self.python, tmp], capture_output=True, text=True, timeout=to)
            if result.returncode != 0:
                return {"stdout": result.stdout, "stderr": result.stderr or f"returncode={result.returncode}"}
            return {"stdout": result.stdout, "stderr": None}
        except subprocess.TimeoutExpired:
            return {"stdout": None, "stderr": "Execution timed out"}
        except Exception as e:
            return {"stdout": None, "stderr": str(e)}
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    @staticmethod
    def _normalize_incoming(message: dict) -> Tuple[str | None, Dict[str, Any], Dict[str, Any]]:
        """Normalize Supervisor ?�� CodeRunner message into (action, kwargs, reply_meta)
        Supports message_builder-style payloads:
          - clone_repo/clone_repo_and_scan: {action, url, (optional) dir_path}
          - edit: {action, target: [...], metadata: {...}}
          - git_*: {action, repo_path|path|repo, optional: remote/branch/ref/create/paths/message/user_name/user_email/set_upstream}
          - run_python: {action, code, (optional) timeout}  (also allows metadata.code/metadata.timeout)
          - pip_install: {action, requirements_path} or target[0]
          - apt_install: {action, package} or target[0]
        Also still accepts {action, kwargs} as a fallback.
        """
        if not isinstance(message, dict):
            return None, {}, {}
        action = message.get("action")
        command = message.get("command")
        if not isinstance(action, str) or not action:
            return None, {}, {}

        kwargs: Dict[str, Any] = {}

        # 1) Action-specific mapping
        if action in ("clone_repo", "clone_repo_and_scan"):
            git_url = message["metadata"].get("git_url") or message.get("git_url")
            dir_path = message.get("dir_path") or "/workspace"
            if git_url is not None:
                kwargs["git_url"] = git_url
            kwargs["dir_path"] = dir_path

        elif action == "edit":
            target = message.get("target") or []
            if not isinstance(target, list):
                target = [target] if target else []
            meta = message.get("metadata") or {}
            if not isinstance(meta, dict):
                meta = {}
            kwargs = {"target": target, "metadata": meta}

        elif action.startswith("git_"):
            repo_path = message.get("repo_path") or message.get("path") or message.get("repo")
            if repo_path:
                kwargs["repo_path"] = repo_path
            for key in ("remote", "branch", "ref", "create", "paths", "message", "user_name", "user_email", "set_upstream"):
                if key in message:
                    kwargs[key] = message[key]

        elif action == "run":
            target = message.get("target") or []
            if not isinstance(target, list):
                target = [target] if target else []
            meta = message.get("metadata") or {}
            if not isinstance(meta, dict):
                meta = {}
            kwargs = {"target": target, "metadata": meta}
        

        elif action == "run_python":
            code = message.get("code")
            if code is None and isinstance(message.get("metadata"), dict):
                code = message["metadata"].get("code")
            if code is not None:
                kwargs["code"] = code
            timeout = message.get("timeout")
            if timeout is None and isinstance(message.get("metadata"), dict):
                timeout = message["metadata"].get("timeout")
            if timeout is not None:
                kwargs["timeout"] = timeout
        
        elif action == "list_files":
            meta = message.get("metadata")
            kwargs["dir_path"] = meta["dir_path"]
        
        elif action == "read_py_files":
            meta = message.get("metadata")
            kwargs["dir_path"] = meta["dir_path"]
        
        elif action == "create_venv":
            metadata = message.get("metadata")
            kwargs = metadata
        
        elif action == "run_in_venv":
            kwargs["target"]=message.get("target")
            kwargs["cwd"]=message.get("metadata")["cwd"]
            kwargs["venv_path"]=message.get("metadata")["venv_path"]
            
        elif action == "pip_install":
            rp = message.get("requirements_path")
            tgt = message.get("target")
            if rp is None and isinstance(tgt, list) and tgt:
                rp = tgt[0]
            if rp is None and isinstance(message.get("metadata"), dict):
                rp = message["metadata"].get("requirements_path")
            if rp is not None:
                kwargs["requirements_path"] = rp

        elif action == "apt_install":
            pkg = message.get("package")
            tgt = message.get("target")
            if pkg is None and isinstance(tgt, list) and tgt:
                pkg = tgt[0]
            if pkg is None and isinstance(message.get("metadata"), dict):
                pkg = message["metadata"].get("package")
            if pkg is not None:
                kwargs["package"] = pkg

        # 2) Fallback to explicit kwargs if provided
        elif isinstance(message.get("kwargs"), dict):
            kwargs = message["kwargs"]

        # 3) Reply metadata passthrough
        reply_meta: Dict[str, Any] = {}
        for k in ("task_id", "id", "request_id"):
            if k in message:
                reply_meta[k] = message[k]

        return command, action, kwargs, reply_meta

    @staticmethod
    def _wrap_payload(command: str, action: str | None, kwargs: Dict[str, Any], reply_meta: Dict[str, Any], handler_result: Dict[str, Any], started_at: str, finished_at: str, duration_ms: int) -> Dict[str, Any]:
        stdout = handler_result.get("stdout") if isinstance(handler_result, dict) else None
        stderr = handler_result.get("stderr") if isinstance(handler_result, dict) else None
        
        
        '''
        ## 기본 데이터 형태
        msg={"command": command, "result": stdout, "metadata": metadata}
        msg={"command": command, "result": stderr, "metadata": metadata}
        metadata=
        
        {
            stdout: dict{...}
            stderr: str
            action: str = "clone_repo"
            dir_path: str = "/workspace/
        }
        
        action은 supervisor의 action 정의를 따라가도록 바꿀 예정
        
        ## 액션 clone_repo : Git 클론
        def clone_repo(self, dir_path: str, git_url: str)
        
        
        stdout: {"repo": str , "path" : str}
        stderr: str
        action: str = "clone_repo"
        dir_path: str = "/workspace/
        
        
        ## 액션 "list_files" coder의 git 에 대한 파일 목록 요청
        def list_files(self, path: str):
        stdout: list[dict,dict,dict,...]
        #### EX### 
        [
            {"name": "model.py", "path": "AI_Agent_Model/model.py", "is_dir": False},
            {"name": "train.py", "path": "AI_Agent_Model/train.py", "is_dir": True},
            {"name": "readme.md", "path": "AI_Agent_Model/readme.md", "is_dir": False}
        ]
        
        stderr: str
        action: str = "list_files"
        dir_path: str = "/workspace/"
        
        
        
        ## 액션 "create_venv" Git 기준 가상환경 만들기
         
        def create_venv(self, metadata: Dict[str, Any]) -> Dict[str, Any]:  
            metadata:
            - dir_path (str, 필수): 프로젝트 경로
            - venv_name (str, 선택): 가상환경 폴더명 (기본 '.venv')
            - requirements (str, 선택): requirements.txt 경로(상대/절대 모두 허용)
            - upgrade_deps (bool, 선택): pip/setuptools 업그레이드 여부 (기본 True)
            - python_version (str, 선택): '3.10', '3.11' 같이 원하는 메이저.마이너 버전
            - interpreter (str, 선택): 사용할 파이썬 실행 파일(명령) 경로/이름 (예: '/usr/bin/python3.10', 'py -3.10')
        
        stdout: {"venv": str(venv_path),
                "python": str(py),
                "pip": str(pip),
                "installed": bool(requirements),
                "upgraded": upgrade_deps,
                "interpreter_cmd": interp_cmd,}
                
        stderr: str
        action: str = "create_venv"
        dir_path: str = "/workspace/"
        
        
        ## 액션 edit 요청된 파일의 내용 수정
        
        def edit(self, target: List[str], metadata: Dict[str, str])
         """
        Write multiple files in one call.
        - target: list of file paths to write (e.g., ["model.py"])
        - metadata: {<filename>: <content>}
        Behavior:
        * If a target file already exists, create a backup: file.ext.bak (or .bak.N)
        * Match metadata by filename only (basename).
        Return stdout as a dict: {message, changes:[{file, bak}], errors?}
        """
        
        stdout: str = "message: "edited 2 files", 
        "files": {
                    "file": "AI_Agent_Model/train.py",
                    "bak": "AI_Agent_Model/train.py.bak"
                }
        stderr: str
        action: str = "create_venv"
        dir_path: str = "/workspace/"
        
        
        
        ## 액션 "run_in_venv" 가상환경 python 기반 코드 실행
        def run_in_venv(self, metadata: Dict[str, Any])
        """
        metadata:
          - venv_path (str, 필수): venv 디렉토리
          - argv (list[str], 필수): python 뒤에 올 인자 (예: ["train.py", "--epochs", "10"])
          - cwd (str, 선택): 작업 디렉토리
          - timeout (int, 선택): 실행 제한(초)
        """
        stdout: str   <= 해당 py파일의 실행결과 출력
        stderr: str
        action: str = "run_in_venv"
        dir_path: str = "/workspace/"
        '''

        metadata={
            "stdout":stdout,
            "stderr":stderr,
            **kwargs
        }
        

        if stdout is not None:
            return {"command": command, "action": action, "result": "success", "metadata": metadata}
        elif stdout is None and stderr is not None:
            return {"command": command, "action": action, "result": "fail", "metadata": metadata}
        
        
    def _on_message(self, message: dict):
        command, action, kwargs, reply_meta = self._normalize_incoming(message)

        t0 = time.perf_counter()
        started_at = datetime.now(timezone.utc).isoformat()
        if not action:
            handler_result = {"stdout": None, "stderr": "Missing action"}
        else:
            handler = self.action_map.get(action)
            if not handler:
                handler_result = {"stdout": None, "stderr": f"Unknown action: {action}"}
            else:
                try:
                    result = handler(**kwargs)
                    if not isinstance(result, dict) or ("stdout" not in result and "stderr" not in result):
                        handler_result = {"stdout": result, "stderr": None}
                    else:
                        handler_result = result
                except TypeError as e:
                    handler_result = {"stdout": None, "stderr": f"Bad kwargs for action '{action}': {e}"}
                except Exception as e:
                    logger.exception("handler raised")
                    handler_result = {"stdout": None, "stderr": str(e)}

        duration_ms = int((time.perf_counter() - t0) * 1000)
        finished_at = datetime.now(timezone.utc).isoformat()

        payload = self._wrap_payload(command,action, kwargs, reply_meta, handler_result, started_at, finished_at, duration_ms)
        self.client.send_message(payload)

    def run(self):
        logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
        t = threading.Thread(target=self.client.run, daemon=True)
        t.start()
        t.join()

if __name__ == "__main__":
    runner = CodeRunner(host="172.17.0.1", port=9002)
    runner.run()

# test_normalize.py (optional quick checks)
if False:  # set True to run simple assertions
    from code_runner import CodeRunner as CR
    def _t(msg, exp_kwargs):
        a, kw, _ = CR._normalize_incoming(msg)
        assert a == msg["action"], (a, msg["action"]) 
        assert kw == exp_kwargs, (kw, exp_kwargs)

    _t({"action":"clone_repo","url":"https://x"}, {"git_url":"https://x","dir_path":"/workspace"})
    _t({"action":"edit","target":["a.py"],"metadata":{"a.py":"print(1)"}}, {"target":["a.py"],"metadata":{"a.py":"print(1)"}})
    _t({"action":"git_pull","path":"/r","branch":"dev"}, {"repo_path":"/r","branch":"dev"})
    _t({"action":"run_python","code":"print('ok')","timeout":5}, {"code":"print('ok')","timeout":5})
    _t({"action":"pip_install","target":["/w/req.txt"]}, {"requirements_path":"/w/req.txt"})
    _t({"action":"apt_install","metadata":{"package":"git"}}, {"package":"git"})
