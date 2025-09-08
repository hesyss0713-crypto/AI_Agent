import re


class CommandRouter:
    def __init__(self, llm, sysprompts: dict):
        self.llm = llm
        self.sysprompts = sysprompts

    def get_command(self, user_text: str) -> tuple[str, bool]:
        """
        사용자 입력, router_prompt로 작업 분류
        return (command, persistent flag)
        """
        system_prompt = self.sysprompts["classifier"]
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},            
        ]
        raw = self.llm.generate(messages, max_new_tokens=8)
        norm = re.sub(r"[^a-z]", "", raw.lower())

        for cand in ["git", "code", "train", "conversation"]:
            if cand in norm:

                persistent = cand in ["conversation"]
                return cand, persistent
        return "conversation", True
    
