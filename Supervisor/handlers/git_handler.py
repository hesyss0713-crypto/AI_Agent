from utils.web.web_manager import WebManager
import re

class GitHandler:
    def __init__(self, llm, sysprompts: dict):
        self.llm = llm
        self.web_manager = WebManager()
        self.sysprompts = sysprompts

    def handle(self, text: str, persistent=False):
        """GitHub URL을 받아 README 요약 생성"""
        url = self.extract_urls(text)
        readme_text = self.web_manager.get_information_web(url)

        if not readme_text:
            print("[GitHandler] README.md를 가져올 수 없습니다.")
            return

        # LLM 요약
        summary = self.llm.run_with_prompt(
            self.sysprompts["git"],
            readme_text[:2000],
            max_new_tokens=400,
            persistent=persistent
        )
        print("[GitHandler] 프로젝트 요약:\n", summary)
        print(f"[GitHandler] Coder에게 git clone 요청 : {url}")

    def extract_urls(self, prompt: str) -> str:
        """텍스트에서 URL 추출"""
        url_pattern = r'(https?://[^\s]+)'
        match = re.search(url_pattern, prompt)
        return match.group(0) if match else ""

    def summarize_experiment(self, coder_input: dict, persistent: bool = False) -> dict:
        files = coder_input.get("coder_message", {}).get("metadata", {}).get("files", [])
        merged_code = "\n\n".join([f"### {f['filename']}\n{f['content']}" for f in files])

        raw_summary = self.llm.run_with_prompt(
            self.sysprompts["summarize_experiment"],
            merged_code,
            max_new_tokens=256,
            persistent=persistent
        )

        sys_part, user_part = "", ""
        if "[User Summary]" in raw_summary:
            parts = raw_summary.split("[User Summary]")
            sys_part = parts[0].replace("[System Summary]", "").strip()
            user_part = parts[1].strip()
        else:
            sys_part = raw_summary.strip()
            user_part = "No explicit User Summary found."

        return {"system_summary": sys_part, "user_summary": user_part}

    def generate_edit_task(self, user_input: str, experiment: dict, persistent: bool = False) -> dict:
        files = experiment.get("coder_message", {}).get("metadata", {}).get("files", [])
        messages = [f"User request: {user_input}"]
        for f in files:
            messages.append(f"### {f['filename']}\n{f['content']}")
        combined_message = "\n\n".join(messages)

        raw_output = self.llm.run_with_prompt(
            self.sysprompts["edit"],
            combined_message,
            max_new_tokens=2048,
            persistent=persistent
        )

        result, current_file, buffer = {}, None, []
        for line in raw_output.splitlines():
            if line.startswith("### "):
                if current_file and buffer:
                    result[current_file] = "\n".join(buffer).strip()
                    buffer = []
                current_file = line.replace("### ", "").strip()
            else:
                buffer.append(line)
        if current_file and buffer:
            result[current_file] = "\n".join(buffer).strip()

        return {"action": "edit", "target": list(result.keys()), "metadata": result}