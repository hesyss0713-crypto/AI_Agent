# event_emitter.py
from threading import RLock
from typing import Callable, Dict, List

class EventEmitter:
    def __init__(self):
        self._ls: Dict[str, List[Callable]] = {}
        self._lock = RLock()

    def on(self, event: str, fn: Callable):
        with self._lock:
            self._ls.setdefault(event, []).append(fn)

    def off(self, event: str, fn: Callable):
        with self._lock:
            if event in self._ls:
                self._ls[event] = [f for f in self._ls[event] if f != fn]

    def emit(self, event: str, *args, **kw):
        with self._lock:
            listeners = list(self._ls.get(event, []))
        for fn in listeners:
            try:
                fn(*args, **kw)
            except Exception as e:
                print(f"[Emitter] '{event}' listener error: {e}")