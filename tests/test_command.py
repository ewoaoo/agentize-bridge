import pytest

from agentize_bridge.command import Command, create_command
from agentize_bridge.utils import type_schema


# -------------------- Command 创建 --------------------

def test_create_command_with_defaults():
    def greet(name: str):
        """Greet someone."""
        return f"Hello, {name}"

    command = create_command(greet)

    assert isinstance(command, Command)
    assert command.name == "greet"
    assert command.fn is greet
    assert command.description == "Greet someone."
    assert command.thread == "worker"
    assert command.timeout is None


def test_create_command_with_custom_options():
    def greet(name: str):
        return f"Hello, {name}"

    command = create_command(
        greet,
        name="custom-greet",
        description="Custom description",
        thread="worker",
        timeout=10.0
    )

    assert command.name == "custom-greet"
    assert command.description == "Custom description"
    assert command.thread == "worker"
    assert command.timeout == 10.0


def test_create_command_uses_function_name_by_default():
    def calculate_total(price: float):
        return price

    command = create_command(calculate_total)

    assert command.name == "calculate_total"


def test_create_command_uses_first_docstring_line():
    def calculate(value: int):
        """Calculate a value.

        More details about the calculation.
        """
        return value

    command = create_command(calculate)

    assert command.description == "Calculate a value."


def test_create_command_description_overrides_docstring():
    def calculate(value: int):
        """Original description."""
        return value

    command = create_command(calculate, description="Custom description")

    assert command.description == "Custom description"


def test_create_command_without_docstring_uses_name():
    def calculate(value: int):
        return value

    command = create_command(calculate)

    assert command.description == "calculate"


# -------------------- 输入 Schema --------------------

def test_create_command_builds_schema_for_typed_parameters():
    def process(name: str, count: int, enabled: bool, ratio: float):
        pass

    command = create_command(process)

    assert command.input_schema == {
        "type": "object",
        "properties": {
            "name": type_schema(str),
            "count": type_schema(int),
            "enabled": type_schema(bool),
            "ratio": type_schema(float),
        },
        "required": ["name", "count", "enabled", "ratio"],
        "additionalProperties": False,
    }


def test_create_command_marks_parameters_with_defaults_as_optional():
    def process(name: str, count: int = 10, enabled: bool = True):
        pass

    command = create_command(process)

    assert command.input_schema["required"] == ["name"]
    assert command.input_schema["properties"]["count"]["default"] == 10
    assert command.input_schema["properties"]["enabled"]["default"] is True


def test_create_command_preserves_parameter_order():
    def process(first: str, second: int, third: bool = False):
        pass

    command = create_command(process)

    assert list(command.input_schema["properties"]) == [
        "first",
        "second",
        "third",
    ]
    assert command.input_schema["required"] == ["first", "second"]


def test_create_command_supports_unannotated_parameters():
    def process(value):
        pass

    command = create_command(process)

    assert "value" in command.input_schema["properties"]
    assert command.input_schema["required"] == ["value"]


def test_create_command_supports_json_compatible_default_values():
    def process(
            text: str = "hello",
            count: int = 3,
            enabled: bool = False,
            items: list = None,
    ):
        pass

    command = create_command(process)

    properties = command.input_schema["properties"]

    assert properties["text"]["default"] == "hello"
    assert properties["count"]["default"] == 3
    assert properties["enabled"]["default"] is False
    assert properties["items"]["default"] is None


def test_create_command_omits_non_json_compatible_defaults():
    marker = object()

    def process(value=marker):
        pass

    command = create_command(process)

    assert "default" not in command.input_schema["properties"]["value"]
    assert "value" not in command.input_schema["required"]


def test_create_command_resolves_type_hints():
    def process(value: "str"):
        pass

    command = create_command(process)

    assert command.input_schema["properties"]["value"] == type_schema(str)


# -------------------- 命令名称校验 --------------------

@pytest.mark.parametrize(
    "name",
    [
        "invalid name",
        "name!",
        "中文",
        "a/b",
    ],
)
def test_create_command_rejects_invalid_names(name):
    def process():
        pass

    with pytest.raises(ValueError, match="无效的命令名称"):
        create_command(process, name=name)


@pytest.mark.parametrize(
    "name",
    [
        "hello",
        "hello_world",
        "hello-world",
        "hello.world",
        "command123",
    ],
)
def test_create_command_accepts_valid_names(name):
    def process():
        pass

    command = create_command(process, name=name)

    assert command.name == name


# -------------------- 线程模式与函数类型 --------------------

@pytest.mark.parametrize("thread", ["invalid", "", "MAIN", None])
def test_create_command_rejects_invalid_thread_mode(thread):
    def process():
        pass

    with pytest.raises(ValueError, match="线程必须是"):
        create_command(process, thread=thread)


def test_create_command_accepts_main_thread():
    def process():
        pass

    command = create_command(process, thread="main")

    assert command.thread == "main"


def test_create_command_accepts_worker_thread():
    def process():
        pass

    command = create_command(process, thread="worker")

    assert command.thread == "worker"


def test_create_command_rejects_async_function_on_main_thread():
    async def process():
        pass

    with pytest.raises(TypeError, match="异步命令不能使用 thread='main'"):
        create_command(process, thread="main")


def test_create_command_accepts_async_function_on_worker_thread():
    async def process():
        return 42

    command = create_command(process, thread="worker")

    assert command.fn is process
    assert command.thread == "worker"


def test_create_command_rejects_varargs():
    def process(*args):
        pass

    with pytest.raises(TypeError, match="必须是一个具名关键字参数"):
        create_command(process)


def test_create_command_rejects_kwargs():
    def process(**kwargs):
        pass

    with pytest.raises(TypeError, match="必须是一个具名关键字参数"):
        create_command(process)


def test_create_command_rejects_positional_only_parameters():
    def process(value, /):
        pass

    with pytest.raises(TypeError, match="必须是一个具名关键字参数"):
        create_command(process)


# -------------------- Command 数据结构 --------------------

def test_command_is_frozen():
    def process():
        pass

    command = create_command(process)

    with pytest.raises(AttributeError):
        command.name = "changed"


def test_command_schema_is_independent_between_commands():
    def first(value: str):
        pass

    def second(count: int):
        pass

    command1 = create_command(first)
    command2 = create_command(second)

    assert list(command1.input_schema["properties"]) == ["value"]
    assert list(command2.input_schema["properties"]) == ["count"]
