import asyncio
from typing import Any

import pytest

from agentize_bridge.command import create_command
from agentize_bridge.executor import (
    CommandArgumentsError,
    CommandExecutionError,
    CommandExecutor,
)


@pytest.fixture
def executor():
    return CommandExecutor()


# -------------------- 同步命令执行 --------------------

def test_execute_returns_command_result(executor):
    def add(a: int, b: int) -> int:
        return a + b

    command = create_command(add)

    result = executor.execute(command, {"a": 2, "b": 3})

    assert result == 5


def test_execute_passes_arguments_as_keyword_arguments(executor):
    def process(name: str, count: int):
        return name, count

    command = create_command(process)

    result = executor.execute(command, {"name": "Alice", "count": 3})

    assert result == ("Alice", 3)


def test_execute_returns_none(executor):
    def process():
        pass

    command = create_command(process)

    assert executor.execute(command, {}) is None


def test_execute_preserves_return_value_type(executor):
    expected = {"items": [1, 2, 3], "enabled": True}

    def process():
        return expected

    command = create_command(process)

    result = executor.execute(command, {})

    assert result is expected


# -------------------- 参数校验 --------------------

@pytest.mark.parametrize(
    "arguments",
    [
        None,
        [],
        (),
        "invalid",
        123,
    ],
)
def test_execute_rejects_non_mapping_arguments(executor, arguments):
    def process(value: Any):
        return value

    command = create_command(process)

    with pytest.raises(CommandArgumentsError, match="指令参数必须是一个 JSON 对象"):
        executor.execute(command, arguments)


def test_execute_rejects_missing_required_argument(executor):
    def process(name: str, age: int):
        return name, age

    command = create_command(process)

    with pytest.raises(CommandArgumentsError, match="Field required"):
        executor.execute(command, {"name": "Alice"})


def test_execute_rejects_unexpected_argument(executor):
    def process(name: str):
        return name

    command = create_command(process)

    with pytest.raises(CommandArgumentsError, match="Extra inputs are not permitted"):
        executor.execute(command, {"name": "Alice", "age": 18})


def test_execute_rejects_extra_keyword_argument(executor):
    def process(name: str):
        return name

    command = create_command(process)

    with pytest.raises(CommandArgumentsError, match="Extra inputs are not permitted"):
        executor.execute(command, {"name": "Alice", "extra": "value"})


def test_execute_accepts_optional_arguments(executor):
    def process(name: str, greeting: str = "Hello"):
        return f"{greeting}, {name}"

    command = create_command(process)

    result = executor.execute(command, {"name": "Alice"})

    assert result == "Hello, Alice"


def test_execute_accepts_mapping_implementation(executor):
    from collections import UserDict

    def process(value: int):
        return value * 2

    command = create_command(process)

    result = executor.execute(command, UserDict({"value": 5}))

    assert result == 10


# -------------------- 命令执行异常 --------------------

def test_execute_wraps_command_exception(executor):
    def process():
        raise ValueError("invalid value")

    command = create_command(process)

    with pytest.raises(
            CommandExecutionError,
            match="指令 'process' 运行失败: invalid value",
    ) as exc_info:
        executor.execute(command, {})

    assert isinstance(exc_info.value.__cause__, ValueError)


def test_execute_wraps_runtime_error(executor):
    def process():
        raise RuntimeError("runtime failure")

    command = create_command(process)

    with pytest.raises(CommandExecutionError, match="runtime failure") as exc_info:
        executor.execute(command, {})

    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_argument_errors_are_not_wrapped_as_execution_errors(executor):
    def process(value: int):
        return value

    command = create_command(process)

    with pytest.raises(CommandArgumentsError):
        executor.execute(command, {})


# -------------------- 异步命令执行 --------------------

def test_execute_runs_async_command(executor):
    async def process(value: int):
        await asyncio.sleep(0)
        return value * 2

    command = create_command(process, thread="worker")

    result = executor.execute(command, {"value": 21})

    assert result == 42


def test_execute_runs_async_command_returning_none(executor):
    async def process():
        await asyncio.sleep(0)

    command = create_command(process, thread="worker")

    assert executor.execute(command, {}) is None


def test_execute_wraps_async_command_exception(executor):
    async def process():
        raise ValueError("async failure")

    command = create_command(process, thread="worker")

    with pytest.raises(
            CommandExecutionError,
            match="指令 'process' 运行失败: async failure",
    ) as exc_info:
        executor.execute(command, {})

    assert isinstance(exc_info.value.__cause__, ValueError)


def test_execute_handles_sync_function_returning_awaitable(executor):
    async def calculate():
        return 42

    def process():
        return calculate()

    command = create_command(process)

    result = executor.execute(command, {})

    assert result == 42
