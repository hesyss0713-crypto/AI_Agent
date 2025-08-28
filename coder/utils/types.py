from typing import Any, Optional, TypedDict, Dict

class HandlerResult(TypedDict, total=False):
    stdout: Any
    stderr: Optional[str]

class RunnerResponse(TypedDict, total=False):
    result: str
    metadata: Dict[str, Any]
