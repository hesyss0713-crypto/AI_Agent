# utils/message_builder.py
from typing import Optional, Dict, Any
import json

def build_task(command: str, action: str, target: str = None, metadata: Optional[Dict[str, Any]] = None) -> dict:
    """Supervisor → Coder 메시지 생성"""
    msg = {
        "command": command,
        "action": action,
        "target": target,
        "metadata": metadata or None
    }
    return msg

def build_response(action: str, result: str, metadata: Optional[Dict[str, Any]] = None) -> bytes:
    """Coder → Supervisor 응답 생성"""
    msg = {
        "coder_message": {
            "action": action,
            "result": result,
            "metadata": metadata or {}
        }
    }
    return msg