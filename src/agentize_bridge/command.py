import inspect
import json
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Callable, Any, get_type_hints, Literal

from .utils import type_schema

ThreadMode = Literal["main", "worker"]


@dataclass(frozen=True)
class Command:
    name: str
    fn: Callable[..., Any]
    description: str
    input_schema: dict[str, Any]
    thread: ThreadMode  # "main": 只能在主线程执行; "worker": 可以在工作线程上执行
    timeout: float | None


@dataclass(slots=True)
class CommandRequest:
    name: str
    arguments: dict[str, Any]
    future: Future[Any]


def create_command(
        fn: Callable[..., Any],
        *,
        name: str = "",
        description: str = "",
        thread: ThreadMode = "worker",
        timeout: float | None = None
):
    if thread not in ("main", "worker"):
        raise ValueError("线程必须是 'main' 或 'worker' 其中之一")
    if not callable(fn):
        raise TypeError("命令必须是可调用的")
    if inspect.iscoroutinefunction(fn) and thread == "main":
        raise TypeError("异步命令不能使用 thread='main'；请使用 thread='worker'，以便协程可以在工作线程上运行")

    signature = inspect.signature(fn)
    try:
        hints = get_type_hints(fn)
    except (NameError, TypeError):
        hints = getattr(fn, "__annotations__", {})

    properties: dict[str, Any] = {}
    required: list[str] = []
    for param in signature.parameters.values():
        if param.kind in (param.POSITIONAL_ONLY, param.VAR_POSITIONAL, param.VAR_KEYWORD):
            raise TypeError(f"指令参数 {param.name!r} 必须是一个具名关键字参数; 仅位置参数和 *args/**kwargs 不被支持")

        annotation = hints.get(param.name, param.annotation)
        property_schema = type_schema(annotation)
        if param.default is not inspect.Signature.empty:
            if _json_compatible(param.default):
                property_schema["default"] = param.default
        else:
            required.append(param.name)
        properties[param.name] = property_schema

    schema = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }

    doc = inspect.getdoc(fn) or ""
    resolved_name = name or fn.__name__
    if not resolved_name or not all(c.isascii() and (c.isalnum() or c in "_.-") for c in resolved_name):
        raise ValueError(f"无效的命令名称: {resolved_name!r}")
    return Command(
        name=resolved_name,
        fn=fn,
        description=description or doc.splitlines()[0] if (description or doc) else resolved_name,
        input_schema=schema,
        thread=thread,
        timeout=timeout
    )


def _json_compatible(value: Any) -> bool:
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError):
        return False
