import requests
from bs4 import BeautifulSoup


class WebManager():
    def __init__(self):
        self.git_readme = None
        self.result = None

    def get_information_web(self, url):
        try:
            res = requests.get(url)
            soup = BeautifulSoup(res.text, "lxml")

            if "github.com" in url:
                readme_section = soup.select_one("article.markdown-body")
                if readme_section:
                    self.git_readme = readme_section.get_text("\n", strip=True)
                    return self.git_readme

                # fallback: README raw url
                raw_url = url.rstrip("/") + "/blob/main/README.md"
                res = requests.get(raw_url)
                if res.status_code == 200:
                    return res.text

                return None
            else:
                headlines = soup.select(".titleline > a")
                self.result = [(h.text, h["href"]) for h in headlines[:5]]
                return self.result
        except Exception as e:
            print(e)