import asyncio
import inspect
from typing import Any, Mapping

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
            inspect.signature(command.fn).bind(**arguments)
        except TypeError as exc:
            raise CommandArgumentsError(str(exc)) from exc

        try:
            result = command.fn(**arguments)
            if inspect.isawaitable(result):
                result = asyncio.run(result)
            return result
        except Exception as exc:
            raise CommandExecutionError(f"指令 {command.name!r} 运行失败: {exc}") from exc
