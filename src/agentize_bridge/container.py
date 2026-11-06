import threading
from enum import Enum
from typing import Dict, Any, Callable


class Container:
    def __init__(self):
        self._lock = threading.RLock()
        self._instances: Dict[str, Any] = {}

    def register(self, name: str, instance: Any) -> None:
        with self._lock:
            if name in self._instances:
                raise ValueError(f"{name!r} 已经被注册")
            self._instances[name] = instance

    def unregister(self, name: str) -> None:
        with self._lock:
            self._instances.pop(name, None)

    def resolve(self, name: str) -> Any:
        with self._lock:
            if name not in self._instances:
                raise KeyError(f"{name!r} 不存在")
            return self._instances[name]
