import re

class IntentClassifier:
    def __init__(self, llm, sysprompts: dict):
        self.llm = llm
        self.sysprompts = sysprompts

    def get_intent(self, answer: str, question: str | None = None) -> str:
        """
        사용자 입력의 의도 판별.
        return: "positive", "negative", "revise", "direct"
        """
        system_prompt = self.sysprompts["intent_classifier"]

        # 질문이 있으면 Q/A 형태로 묶어주기
        if question:
            content = f"Q: {question}\nA: {answer}"
        else:
            content = answer

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},            
        ]

        raw = self.llm.generate(messages, max_new_tokens=8)
        norm = re.sub(r"[^a-z]", "", raw.lower())

        # 후보 집합 (direct까지 포함)
        for cand in ["positive", "negative", "revise", "direct"]:
            if cand in norm:
                return cand
        return "negative"
