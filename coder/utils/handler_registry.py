from typing import Callable, Dict


# 액션명 → (원본 함수 객체)
registry: Dict[str, Callable] = {}


def register(action_name: str):
    """액션 핸들러 등록 데코레이터
    - 메서드/함수 어디에 붙어도 전역 registry에 등록됩니다.
    - 같은 이름이 중복되면 마지막 등록이 우선합니다.
    """
    def decorator(func: Callable):
        registry[action_name] = func
        return func
        return decorator