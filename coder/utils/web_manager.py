import subprocess
import requests, zipfile, io, os
from bs4 import BeautifulSoup
import importlib.util
import warnings
import base64

class WebManager():
    def __init__(self):
        self.git_readme=None
        self.result=None
    '''
    인터넷 정보
    git인 경우 readme 추출
    
    git이 아닌 경우 헤드라인 내용 추출
    
    '''
    def get_information_web(self,url):
        res = requests.get(url)
        soup = BeautifulSoup(res.text, "lxml")
        if "github.com" in url:
            readme_section = soup.select_one("article.markdown-body")
            if readme_section:
                if readme_section:
                    self.web_information=readme_section.get_text("\n", strip=True)
        else:
            soup = BeautifulSoup(res.text, "lxml")
            self.web_information = soup.select(".titleline > a")
            for web_text in self.web_information[:5]:
                print(web_text.text, "→", web_text["href"])
            
                
    ## URL기반 다운
    def download(self,command,url):
        if command=="down":
            res = requests.get(url)
            with zipfile.ZipFile(io.BytesIO(res.content)) as zip_ref:
                zip_ref.extractall("flask_repo")
                print("Donload your file as a Zip")

        if command=="git":
            os.system(f"git clone {url}")
            print("Clone a git repository")

    def Upload_Project(self,url : str, file_path : str ,commit_str : str ):
        token = os.getenv("GITHUB_TOKEN")
        if token is None:
            warnings.warn(
                "GITHUB TOKEN is not specified. \nPlease set your environment variable",
                UserWarning
            )
            warnings.warn('export GITHUB_TOKEN="Your Token"', UserWarning)
            return {"error": "No GitHub token provided"}
        try:
            # 파일 읽어서 base64 인코딩
            with open(file_path, "rb") as f:
                content = base64.b64encode(f.read()).decode("utf-8")

            # API 요청
            res = requests.put(
                url,
                headers={"Authorization": f"token {token}"},
                json={
                    "message": commit_str,
                    "content": content,
                    "branch": "main"
                }
            )
        except Exception as e:
            print(e)
        return res.json()
    
    # default Requiremetns 참조
    def pip_install(self,file_path):
        try:
            if file_path!=None:
                with open(file_path) as f:
                    packages = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                
                for pkg in packages:
                    # 버전 조건 있는 경우 (예: requests==2.28.0) 처리
                    install_name = pkg
                    import_name = pkg.split("==")[0].split(">=")[0].split("<=")[0].split(">")[0].split("<")[0]
                    
                    if importlib.util.find_spec(import_name) is None:
                        print(f"[INFO] Installing {install_name} ...")
                        subprocess.check_call(["pip", "install", install_name])
                    else:
                        print(f"[OK] {import_name} already installed.")
            else:
                print("Specify your requirements path.")
        except Exception as e:
            print(e)
        
    
    ## apt list 조회 후 패키지 설치
    def apt_install(self,package:str):
        
        result = subprocess.run(
        ["apt", "list", "--installed"],
        capture_output=True,
        text=True
        )

        # 2) 설치 여부 확인
        if package in result.stdout:
            print(f"[OK] {package} is already installed.")
            return

        # 3) 설치 실행
        print(f"[INFO] Installing {package} ...")
        install_result = subprocess.run(
            ["apt-get", "install", "-y", package],
            capture_output=True,
            text=True
        )
        if install_result.returncode == 0:
            print(f"[DONE] {package} installed successfully.")
        else:
            print(f"[ERROR] Failed to install {package}\n{install_result.stderr}")
            
        