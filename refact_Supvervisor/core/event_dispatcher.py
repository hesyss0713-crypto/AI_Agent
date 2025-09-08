import logging

class EventDispatcher:
    def __init__(self):
        self.handlers = {}  # (command, action) → 함수
        self.logger = logging.getLogger(__name__)

    def register(self, command: str, action: str):
        """데코레이터로 핸들러 등록"""
        def decorator(func):
            self.handlers[(command, action)] = func
            return func
        return decorator

    def dispatch(self, msg: dict):
        key = (msg.get("command"), msg.get("action"))
        handler = self.handlers.get(key)
        if handler:
            return handler(msg)
        else:
            self.logger.warning(f"[Dispatcher] 핸들러 없음: {key}")
            return None
