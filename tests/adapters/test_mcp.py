import asyncio
import inspect
import json

from agentize_bridge.adapters import mcp_server as mcp_adapter


def test_create_tool_uses_command_metadata():
    client = object()
    command = {
        "name": "process_image",
        "description": "Process an image",
        "input_schema": {
            "type": "object",
            "properties": {
                "threshold": {"type": "number"},
                "enabled": {"type": "boolean"},
            },
            "required": ["threshold"],
        },
    }

    tool = mcp_adapter._create_tool(client, command, timeout=10)

    assert tool.name == "process_image"
    assert tool.description == "Process an image"
    assert tool.parameters == command["input_schema"]
    assert tool.fn.__name__ == "process_image"
    assert tool.fn.__doc__ == "Process an image"


def test_create_tool_builds_parameter_signature():
    tool = mcp_adapter._create_tool(
        object(),
        {
            "name": "process",
            "input_schema": {
                "type": "object",
                "properties": {
                    "count": {"type": "integer"},
                    "label": {"type": "string", "default": "default"},
                    "enabled": {"type": "boolean"},
                },
                "required": ["count"],
            },
        },
        timeout=30,
    )

    signature = inspect.signature(tool.fn)
    parameters = signature.parameters

    assert list(parameters) == ["count", "label", "enabled"]
    assert parameters["count"].default is inspect.Parameter.empty
    assert parameters["label"].default == "default"
    assert parameters["enabled"].default is None


def test_create_tool_without_schema_uses_empty_object():
    tool = mcp_adapter._create_tool(
        object(),
        {"name": "ping"},
        timeout=30,
    )

    assert tool.name == "ping"
    assert tool.parameters == {
        "type": "object",
        "properties": {},
    }
    assert list(inspect.signature(tool.fn).parameters) == []


def test_create_tool_invokes_http_client():
    class FakeClient:
        def __init__(self):
            self.calls = []

        def call_command(self, name, arguments, timeout=None):
            self.calls.append((name, arguments, timeout))
            return {"result": "成功"}

    client = FakeClient()
    tool = mcp_adapter._create_tool(
        client,
        {
            "name": "process",
            "input_schema": {
                "type": "object",
                "properties": {
                    "threshold": {"type": "number"},
                },
                "required": ["threshold"],
            },
        },
        timeout=12,
    )

    result = asyncio.run(tool.fn(threshold=0.5))

    assert json.loads(result) == {"result": "成功"}
    assert client.calls == [
        ("process", {"threshold": 0.5}, 12),
    ]


def test_create_tool_serializes_none_result():
    class FakeClient:
        def call_command(self, name, arguments, timeout=None):
            return None

    tool = mcp_adapter._create_tool(
        FakeClient(),
        {"name": "reset"},
        timeout=30,
    )

    result = asyncio.run(tool.fn())

    assert result == "null"


def test_create_server_fetches_commands_and_registers_tools(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, base_url, timeout):
            captured["base_url"] = base_url
            captured["timeout"] = timeout

        def get(self, path):
            captured["path"] = path
            return [
                {
                    "name": "ping",
                    "description": "Check status",
                    "input_schema": {
                        "type": "object",
                        "properties": {},
                    },
                },
                {
                    "name": "reset",
                    "description": "Reset state",
                },
            ]

    class FakeServer:
        def __init__(self, name, tools):
            captured["server_name"] = name
            captured["tools"] = tools

    monkeypatch.setattr(mcp_adapter, "HttpClient", FakeClient)
    monkeypatch.setattr(mcp_adapter, "MCPServer", FakeServer)

    server = asyncio.run(
        mcp_adapter._create_server(
            "http://localhost:9000",
            timeout=15,
        )
    )

    assert isinstance(server, FakeServer)
    assert captured["base_url"] == "http://localhost:9000"
    assert captured["timeout"] == 15
    assert captured["path"] == "/commands"
    assert captured["server_name"] == "agentize-bridge-mcp"
    assert [tool.name for tool in captured["tools"]] == ["ping", "reset"]


def test_main_starts_stdio_server(monkeypatch):
    captured = {}

    class FakeServer:
        def run(self, transport):
            captured["transport"] = transport

    async def fake_create_server(base_url, *, timeout=30):
        captured["base_url"] = base_url
        captured["timeout"] = timeout
        return FakeServer()

    monkeypatch.setattr(
        "sys.argv",
        [
            "agentize-bridge-mcp",
            "--url", "http://localhost:9000",
            "--timeout", "15",
        ],
    )
    monkeypatch.setattr(
        mcp_adapter,
        "_create_server",
        fake_create_server,
    )

    mcp_adapter.main()

    assert captured == {
        "base_url": "http://localhost:9000",
        "timeout": 15,
        "transport": "stdio",
    }


def test_main_uses_environment_url(monkeypatch):
    captured = {}

    class FakeServer:
        def run(self, transport):
            captured["transport"] = transport

    async def fake_create_server(base_url, *, timeout=30):
        captured["base_url"] = base_url
        captured["timeout"] = timeout
        return FakeServer()

    monkeypatch.setattr("sys.argv", ["agentize-bridge-mcp"])
    monkeypatch.setenv(
        "AGENTIZE_BRIDGE_URL",
        "http://localhost:9001",
    )
    monkeypatch.setattr(
        mcp_adapter,
        "_create_server",
        fake_create_server,
    )

    mcp_adapter.main()

    assert captured == {
        "base_url": "http://localhost:9001",
        "timeout": 30,
        "transport": "stdio",
    }