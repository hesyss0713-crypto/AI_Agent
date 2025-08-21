import subprocess
from bs4 import BeautifulSoup


class Manager():
    
    def __init__(self):
        pass
    
    
    def get_information_web(self,url):
        if "git" in url:
            readme_section = soup.select_one("article.markdown-body")
        
        pass

    def download(self,url):
        subprocess.run(["wget", "-O", "", ""])
        pass
    
    def pip_install(self,):
        pass
    
    def apt_install(self,):
        pass