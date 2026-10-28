import asyncio
import contextlib
import json

import pytest
from mcp import Client, MCPError

from agentize_bridge.adapters import mcp_server as mcp_adapter
from agentize_bridge.adapters.http_client import HttpClientError


class FakeClient:
    """假的 HttpClient：记录 call_command 的调用，并返回预设结果。"""

    def __init__(self, result=None, error=None):
        self.calls = []
        self._result = result
        self._error = error

    def call_command(self, name, arguments, timeout=None):
        self.calls.append((name, arguments, timeout))
        if self._error is not None:
            raise self._error
        return self._result


COMMAND = {
    "name": "process_image",
    "description": "Process an image",
    "input_schema": {
        "type": "object",
        "properties": {
            "threshold": {"type": "number"},
            "enabled": {"type": "boolean", "default": False},
        },
        "required": ["threshold"],
        "additionalProperties": False,
    },
}


def _run(server, action):
    """在进程内连接 server（SDK 文档推荐的测试方式），执行 action(client) 并返回结果。"""

    async def run():
        async with Client(server) as client:
            return await action(client)

    try:
        return asyncio.run(run())
    except BaseExceptionGroup as group:
        # Client.__aexit__ 和 ClientSession.__aexit__ 各包一层 ExceptionGroup，
        # 递归剥到最里层，让 pytest.raises(MCPError) 拿到原始异常。
        exc: BaseException = group
        while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
            exc = exc.exceptions[0]
        raise exc from None


# -------------------- 工具列表 --------------------

def test_tools_use_command_metadata_and_pass_schema_through():
    server = mcp_adapter._create_server(FakeClient(), [COMMAND], timeout=10)

    result = _run(server, lambda client: client.list_tools())

    assert [tool.name for tool in result.tools] == ["process_image"]
    tool = result.tools[0]
    assert tool.description == "Process an image"
    assert tool.input_schema == COMMAND["input_schema"]


def test_tool_keeps_defs_and_refs_untouched():
    schema = {
        "$defs": {"Color": {"enum": ["red", "blue"], "type": "string"}},
        "type": "object",
        "properties": {"color": {"$ref": "#/$defs/Color"}},
        "required": ["color"],
        "additionalProperties": False,
    }
    server = mcp_adapter._create_server(
        FakeClient(), [{"name": "paint", "input_schema": schema}], timeout=10
    )

    result = _run(server, lambda client: client.list_tools())

    assert result.tools[0].input_schema == schema


def test_tool_without_schema_uses_empty_object():
    server = mcp_adapter._create_server(FakeClient(), [{"name": "ping"}], timeout=30)

    result = _run(server, lambda client: client.list_tools())

    assert result.tools[0].name == "ping"
    assert result.tools[0].input_schema == {"type": "object", "properties": {}}


def test_tool_list_preserves_command_order():
    commands = [{"name": "ping"}, {"name": "reset"}]
    server = mcp_adapter._create_server(FakeClient(), commands, timeout=30)

    result = _run(server, lambda client: client.list_tools())

    assert [tool.name for tool in result.tools] == ["ping", "reset"]


# -------------------- 调用工具 --------------------

def test_call_tool_forwards_arguments_and_timeout():
    client = FakeClient(result={"result": "成功"})
    server = mcp_adapter._create_server(client, [COMMAND], timeout=12)

    result = _run(server, lambda c: c.call_tool("process_image", {"threshold": 0.5}))

    assert result.is_error is False
    assert json.loads(result.content[0].text) == {"result": "成功"}
    assert client.calls == [("process_image", {"threshold": 0.5}, 12)]


def test_call_tool_without_arguments_sends_empty_object():
    client = FakeClient(result=True)
    server = mcp_adapter._create_server(client, [{"name": "ping"}], timeout=30)

    _run(server, lambda c: c.call_tool("ping"))

    assert client.calls == [("ping", {}, 30)]


def test_call_tool_serializes_none_result():
    server = mcp_adapter._create_server(FakeClient(result=None), [{"name": "reset"}], timeout=30)

    result = _run(server, lambda client: client.call_tool("reset"))

    assert result.content[0].text == "null"


def test_call_tool_returns_http_errors_as_error_results():
    # 服务端的 422 校验信息必须以 is_error 结果交给模型，而不是变成协议错误
    error = HttpClientError('HTTP 422: {"detail":"参数无效: a: Field required"}')
    server = mcp_adapter._create_server(FakeClient(error=error), [COMMAND], timeout=10)

    result = _run(server, lambda client: client.call_tool("process_image", {}))

    assert result.is_error is True
    assert "422" in result.content[0].text
    assert "Field required" in result.content[0].text


def test_call_tool_rejects_unknown_tool():
    server = mcp_adapter._create_server(FakeClient(), [{"name": "ping"}], timeout=30)

    with pytest.raises(MCPError):
        _run(server, lambda client: client.call_tool("missing"))


# -------------------- 启动 --------------------

def test_serve_fetches_commands_and_runs_on_stdio(monkeypatch):
    captured = {}

    class FakeHttpClient:
        def __init__(self, base_url, timeout):
            captured["base_url"] = base_url
            captured["timeout"] = timeout

        def get(self, path):
            captured["path"] = path
            return [{"name": "ping"}, {"name": "reset"}]

    class FakeServer:
        def create_initialization_options(self):
            return "init-options"

        async def run(self, read_stream, write_stream, options):
            captured["run"] = (read_stream, write_stream, options)

    def fake_create_server(client, commands, timeout):
        captured["commands"] = [command["name"] for command in commands]
        captured["server_timeout"] = timeout
        return FakeServer()

    @contextlib.asynccontextmanager
    async def fake_stdio_server():
        yield "read-stream", "write-stream"

    monkeypatch.setattr(mcp_adapter, "HttpClient", FakeHttpClient)
    monkeypatch.setattr(mcp_adapter, "_create_server", fake_create_server)
    monkeypatch.setattr(mcp_adapter, "stdio_server", fake_stdio_server)

    asyncio.run(mcp_adapter._serve("http://localhost:9000", timeout=15))

    assert captured == {
        "base_url": "http://localhost:9000",
        "timeout": 15,
        "path": "/commands",
        "commands": ["ping", "reset"],
        "server_timeout": 15,
        "run": ("read-stream", "write-stream", "init-options"),
    }


def test_main_passes_options_to_serve(monkeypatch):
    captured = {}

    async def fake_serve(base_url, *, timeout=30):
        captured["base_url"] = base_url
        captured["timeout"] = timeout

    monkeypatch.setattr(
        "sys.argv",
        ["agentize-bridge-mcp", "--url", "http://localhost:9000", "--timeout", "15"],
    )
    monkeypatch.setattr(mcp_adapter, "_serve", fake_serve)

    mcp_adapter.main()

    assert captured == {"base_url": "http://localhost:9000", "timeout": 15}


def test_main_uses_environment_url(monkeypatch):
    captured = {}

    async def fake_serve(base_url, *, timeout=30):
        captured["base_url"] = base_url
        captured["timeout"] = timeout

    monkeypatch.setattr("sys.argv", ["agentize-bridge-mcp"])
    monkeypatch.setenv("AGENTIZE_BRIDGE_URL", "http://localhost:9001")
    monkeypatch.setattr(mcp_adapter, "_serve", fake_serve)

    mcp_adapter.main()

    assert captured == {"base_url": "http://localhost:9001", "timeout": 30}
