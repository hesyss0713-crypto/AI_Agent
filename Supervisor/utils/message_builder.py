# utils/message_builder.py
from typing import Optional, Dict, Any

def build_task(command: str, action: str, target: str , metadata: Optional[Dict[str, Any]] = None) -> dict:
    """Supervisor → Coder 메시지 생성"""
    return {
        "command": command,
        "action": action,
        "target": target,
        "metadata": metadata or None
    }

def build_response(action: str, result: str, metadata: Optional[Dict[str, Any]] = None) -> dict:
    """Coder → Supervisor 응답 생성"""
    return {
        "coder_message": {
            "action": action,
            "result": result,
            "metadata": metadata or {}
        }
    }
