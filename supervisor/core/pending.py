from collections import deque
import uuid

class PendingActionManager:
    """사용자 입력이 필요한 작업을 관리하는 FIFO 큐"""
    def __init__(self,emitter):
        self.queue = deque()
        self.emitter = emitter
    def add(self, action_type: str, msg: dict):
        print(">>> Pending 추가됨:", action_type, msg)
        """새 pending action 추가"""
        if not msg["response"]:
            msg["response"] = None
        action_id = str(uuid.uuid4())
        item = {"id": action_id, "type": action_type, "msg": msg}
        self.queue.append(item)
        self.emitter.emit("pending_added", item)
        
        return action_id

    def pop(self):
        """FIFO: 가장 오래된 pending action 반환"""
        if self.queue:
            return self.queue.popleft()
        return None

    def has_pending(self):
        return bool(self.queue)
