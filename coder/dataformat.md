
## 기본 데이터 형태

```
msg={"command": command, "result": stdout, "metadata": metadata}
msg={"command": command, "result": stderr, "metadata": metadata}

metadata=
{
    stdout: dict{...}
    stderr: str
    action: str = "clone_repo"
    dir_path: str = "/workspace/
}
```
action은 supervisor의 action 정의를 따라가도록 바꿀 예정

## 액션 clone_repo : Git 클론
```
def clone_repo(self, dir_path: str, git_url: str)


stdout: {"repo": str , "path" : str}
stderr: str
action: str = "clone_repo"
dir_path: str = "/workspace/

```

## 액션 "list_files" coder의 git 에 대한 파일 목록 요청

```
def list_files(self, path: str):
    stdout: list[dict,dict,dict,...]
    
    [
        {"name": "model.py", "path": "AI_Agent_Model/model.py", "is_dir": False},
        {"name": "train.py", "path": "AI_Agent_Model/train.py", "is_dir": True},
        {"name": "readme.md", "path": "AI_Agent_Model/readme.md", "is_dir": False}
    ]

stderr: str
action: str = "list_files"
dir_path: str = "/workspace/"
```


## 액션 "create_venv" Git 기준 가상환경 만들기
```   
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
```

## 액션 edit 요청된 파일의 내용 수정
```
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
```


## 액션 "run_in_venv" 가상환경 python 기반 코드 실행
```
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
```
