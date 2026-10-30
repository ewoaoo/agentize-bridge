import inspect
import json
import math
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Callable, Any, Literal

from pydantic import BaseModel

from .schema import build_args_model, input_schema

ThreadMode = Literal["main", "worker"]

DEFAULT_TIMEOUT: float = 30.0


@dataclass(frozen=True)
class Command:
    name: str
    fn: Callable[..., Any]
    description: str
    input_schema: dict[str, Any]
    thread: ThreadMode  # "main": 只能在主线程执行; "worker": 可以在工作线程上执行
    timeout: float
    args_model: type[BaseModel]  # 同一个模型：既生成 schema，也用来校验参数


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
        timeout: float = DEFAULT_TIMEOUT
):
    if thread not in ("main", "worker"):
        raise ValueError("线程必须是 'main' 或 'worker' 其中之一")
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout 必须是大于 0 的有点数字")
    if not callable(fn):
        raise TypeError("命令必须是可调用的")
    if inspect.iscoroutinefunction(fn) and thread == "main":
        raise TypeError("异步命令不能使用 thread='main'；请使用 thread='worker'，以便协程可以在工作线程上运行")

    args_model = build_args_model(fn)

    doc = inspect.getdoc(fn) or ""
    resolved_name = name or fn.__name__
    if not resolved_name or not all(c.isascii() and (c.isalnum() or c in "_.-") for c in resolved_name):
        raise ValueError(f"无效的命令名称: {resolved_name!r}")
    return Command(
        name=resolved_name,
        fn=fn,
        description=description or doc.splitlines()[0] if (description or doc) else resolved_name,
        input_schema=input_schema(args_model),
        thread=thread,
        timeout=timeout,
        args_model=args_model
    )
