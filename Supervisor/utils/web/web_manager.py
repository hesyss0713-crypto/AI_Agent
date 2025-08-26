import requests
from bs4 import BeautifulSoup

class WebManager():
    def __init__(self):
        self.git_readme = None
        self.result = None

    def get_information_web(self, url):
        res = requests.get(url)
        soup = BeautifulSoup(res.text, "lxml")

        if "github.com" in url:  # GitHub README 추출
            readme_section = soup.select_one("article.markdown-body")
            if readme_section:
                self.git_readme = readme_section.get_text("\n", strip=True)
                return self.git_readme
            return None
        else:  # 뉴스 헤드라인 추출 (예: Hacker News)
            headlines = soup.select(".titleline > a")
            self.result = [(h.text, h["href"]) for h in headlines[:5]]
            return self.result


# 테스트
test = WebManager()
readme_text = test.get_information_web("https://github.com/hesyss0713-crypto/AI_Agent_Model")
print(readme_text[:500]) 