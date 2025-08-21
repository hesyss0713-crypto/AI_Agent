import requests, zipfile, io, os
import subprocess
import warnings
import base64

class FileManager():
    
    def __init__(self):
        pass

        
    def zip_file(self, zip_path:str,folder_path:str, file_path: str):
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                if folder_path is not None:
                    for root, dirs, files in os.walk(folder_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            # 상대 경로를 저장 (압축파일 안에서 폴더 구조 유지)
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
    
    
    
    def delete_file(self,file_path):
        file_name=file_path.split('/')[-1]
        try:
            os.remove(file_path)
            
            return {"stdout": f"Remove the files :{file_name}" , "stderr":None}
            
        except Exception as e:
            print(e)
            return {"stdout": None , "stderr":str(e)}
   
    

     