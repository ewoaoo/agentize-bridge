import asyncio
import inspect
from typing import Any, Mapping

from pydantic import ValidationError

from .command import Command


class CommandNotFoundError(LookupError):
    pass


class CommandArgumentsError(ValueError):
    pass


class CommandExecutionError(RuntimeError):
    pass


class CommandExecutor:
    def execute(self, command: Command, arguments: Mapping[str, Any]) -> Any:
        if not isinstance(arguments, Mapping):
            raise CommandArgumentsError("指令参数必须是一个 JSON 对象")

        try:
            validated = command.args_model.model_validate(dict(arguments))
        except ValidationError as exc:
            summary = "; ".join(f"{'.'.join(map(str, e['loc'])) or '<root>'}: {e['msg']}" for e in exc.errors())
            raise CommandArgumentsError(f"参数无效: {summary}") from exc
        # getattr 而不是 model_dump()：保留嵌套模型 / dataclass 实例
        kwargs = {name: getattr(validated, name) for name in type(validated).model_fields}

        try:
            result = command.fn(**kwargs)
            if inspect.isawaitable(result):
                result = asyncio.run(result)
            return result
        except Exception as exc:
            raise CommandExecutionError(f"指令 {command.name!r} 运行失败: {exc}") from exc
