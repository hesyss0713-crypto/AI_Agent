import re

class IntentClassifier:
    def __init__(self, llm, sysprompts: dict):
        self.llm = llm
        self.sysprompts = sysprompts

    def get_intent(self, user_text: str) -> str:
        """
        user 입력의 의도 판별
        return: "positive", "negative", "neutral", "question"
        """
        system_prompt = self.sysprompts["intent_classifier"]
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},            
        ]
        raw = self.llm.generate(messages, max_new_tokens=8)
        norm = re.sub(r"[^a-z]", "", raw.lower())

        for cand in ["positive", "negative", "neutral", "question"]:
            if cand in norm:
                return cand
        return "unknown"
        
    
