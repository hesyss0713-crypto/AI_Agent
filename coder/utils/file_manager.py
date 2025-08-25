import requests, zipfile, io, os
import subprocess
import warnings
import base64
import venv

class FileManager():
    
    def __init__(self):
        self.root=None

    
    ## 가상환경 생성
    def make_venv(
        self,
        relpath: str = "venv",
        interpreter: str | None = None,   # 
        upgrade_deps: bool = True,  
        gitignore: bool = True,
    ) -> dict:
        """
        venv폴더가 생성이 되어있지않는 경우 생성
        """
        venv_path = (self.root+relpath)
        if not os.path.exists(venv_path):
            os.mkdir(venv_path)

        # /bin 폴더가 존재하지 않는경우 생성
        if not os.path.exists(venv_path+"/bin"):
            if interpreter:
        
                subprocess.run([interpreter, "-m", "venv", str(venv_path)], check=True)
            else:
        
                venv.create(str(venv_path), with_pip=True, upgrade_deps=upgrade_deps)

        ### 현재 agent, Windows, Linux판별
        if os.name == "nt":
            py  = venv_path / "Scripts" / "python.exe"
            pip = venv_path / "Scripts" / "pip.exe"
            activate = venv_path / "Scripts" / "activate.bat"
        else:
            py  = venv_path + "/bin/python"
            pip = venv_path +"/bin/pip"
            activate = venv_path+"/bin/activate"

        ### pip 업그레이드 및 pip 설치
        if upgrade_deps:
            response=requests.get("https://bootstrap.pypa.io/get-pip.py")
            output_file="get-pip.py"
            with open(output_file ,'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            subprocess.run([py,"get-pip.py"])
            subprocess.run([str(pip), "install", "-U", "pip", "setuptools", "wheel"], check=True)

        ### requirements.txt 설치
        subprocess.run([str(pip), "install", "-r", self.root+"requirements.txt"], text=True, check=True)
    
        ### git ignore 옵션 수정 필요 2025.08.25
        if gitignore:
            gi = self.root / ".gitignore"
            line = f"{relpath}\n"
            if not gi.exists() or line not in gi.read_text(encoding=self.encoding):
                with gi.open("a", encoding=self.encoding) as f:
                    f.write(line)

            return {
        "stdout": {
            "path": str(venv_path),
            "python": str(py),
            "pip": str(pip),
            "activate": str(activate),
        },
        "stderr": None,
    }
    
    
    
    def zip_file(self, zip_path:str,folder_path:str, file_path: str):
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                if folder_path is not None:
                    for root, dirs, files in os.walk(folder_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, folder_path)
                            zipf.write(file_path, arcname)            
                            
                if file_path is not None:   
                    zipf.write(file_path, arcname=file_path.split("/")[-1])
        
            return {"stdout": f"Zip created successfully: {zip_path}", "stderr": None}

        except Exception as e:
            return {"stdout": None, "stderr": str(e)}
    
    def get_list_file(self,dir_path:str):
        try:
            entries=os.scandir(dir_path)
            
            return {"stdout": entries , "stderr": None}
        except Exception as e:
            print(e)
            return {"stdout": None , "stderr":str(e)}
    
    def get_code(self,path):
        pass
    
    #폴더 트리구조 + py 파일 넘기기
    def make_project(self, dir_path:str, zip_file:str =None , git_path:str = None):
        if zip_file is not None and git_path is None:
                with zipfile.ZipFile(zip_file) as z:
                    os.mkdir(dir_path+"zip_file")
                    
                    z.extractall(dir_path+"zip_file")  
        if zip_file is None and git_path is not None:
            os.chdir(dir_path)
            os.system(f"git clone {url}")
            git_name=git_path.split("/")[-1]
            self.root=os.chdir(dir_path+git_name)
            print("Clone a git repository")
            
   
   
    def delete_file(self,file_path):
        file_name=file_path.split('/')[-1]
        try:
            os.remove(file_path)
            
            return {"stdout": f"Remove the files :{file_name}" , "stderr":None}
            
        except Exception as e:
            print(e)
            return {"stdout": None , "stderr":str(e)}
    
    