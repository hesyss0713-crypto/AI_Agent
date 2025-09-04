# utils/common_metadata.py
from typing import Optional, List
from pydantic import BaseModel


class CommonMetadata(BaseModel):
    """
    Supervisor → CodeRunner 메시지에서 metadata로 전달될 수 있는
    공통 키들의 정의.

    필요 시 새로운 키를 여기 추가하면 됨.
    """
    dir_path: Optional[str] = None
    git_url: Optional[str] = None
    venv_path: Optional[str] = None
    venv_name: Optional[str] = None
    requirements: Optional[str] = None
    package: Optional[str] = None
    code: Optional[str] = None
    timeout: Optional[int] = None
    target: Optional[List[str]] = None
    message: Optional[str] = None
    user_name: Optional[str] = None
    user_email: Optional[str] = None