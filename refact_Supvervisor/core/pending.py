from collections import deque
import uuid

class PendingActionManager:
    """사용자 입력이 필요한 작업을 관리하는 FIFO 큐"""
    def __init__(self):
        self.queue = deque()

    def add(self, action_type: str, msg: dict):
        print(">>> Pending 추가됨:", action_type, msg)
        """새 pending action 추가"""
        if not msg["response"]:
            msg["response"] = None
        action_id = str(uuid.uuid4())
        self.queue.append({
            "id": action_id,
            "type": action_type,
            "msg": msg
        })
        return action_id

    def pop(self):
        """FIFO: 가장 오래된 pending action 반환"""
        if self.queue:
            return self.queue.popleft()
        return None

    def has_pending(self):
        return bool(self.queue)
