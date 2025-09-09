from typing import Callable, Dict

registry: Dict[str, Callable] = {}

def register(action_name: str):
    def decorator(func: Callable):
        registry[action_name] = func
        return func
    return decorator

# types.py
from typing import Any, Optional, TypedDict, Dict

class HandlerResult(TypedDict, total=False):
    stdout: Any
    stderr: Optional[str]

class RunnerResponse(TypedDict, total=False):
    result: str
    metadata: Dict[str, Any]