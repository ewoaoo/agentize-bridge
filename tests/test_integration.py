import asyncio
import json
import threading
import time

import pytest
import uvicorn

from agentize_bridge.server import AgentizeServer
from agentize_bridge.adapters.http_client import HttpClient
from agentize_bridge.adapters.cli import run_cli
from agentize_bridge.adapters import mcp_server as mcp_adapter


@pytest.fixture
def running_server():
    server = AgentizeServer(name="Integration Test")

    @server.command(thread="worker")
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @server.command(thread="main")
    def get_state() -> dict:
        """Get application state."""
        return {"status": "ready"}

    config = uvicorn.Config(
        server.fastapi_app,
        host="127.0.0.1",
        port=0,
        log_level="error",
    )
    http_server = uvicorn.Server(config)
    thread = threading.Thread(target=http_server.run, daemon=True)
    thread.start()

    try:
        deadline = time.monotonic() + 10

        while not http_server.started:
            if not thread.is_alive():
                raise RuntimeError("HTTP 测试服务器启动失败")
            if time.monotonic() >= deadline:
                raise TimeoutError("HTTP 测试服务器启动超时")
            time.sleep(0.01)

        port = http_server.servers[0].sockets[0].getsockname()[1]
        yield server, f"http://127.0.0.1:{port}"

    finally:
        http_server.should_exit = True
        thread.join(timeout=5)
        server.close()


def test_http_client_end_to_end(running_server):
    _, base_url = running_server
    client = HttpClient(base_url)

    assert client.get("/health") == {"status": "ok"}

    commands = client.get("/commands")
    command_names = {command["name"] for command in commands}

    assert {"add", "get_state"} <= command_names
    assert client.call_command("add", {"a": 2, "b": 3}) == 5


def test_cli_end_to_end(running_server, monkeypatch, capsys):
    _, base_url = running_server

    assert run_cli(["--url", base_url, "list"]) == 0

    output = capsys.readouterr()
    commands = json.loads(output.out)

    assert {command["name"] for command in commands} >= {
        "add",
        "get_state",
    }
    assert output.err == ""

    assert run_cli([
        "--url", base_url,
        "call", "add",
        "--args", '{"a": 10, "b": 20}',
    ]) == 0

    output = capsys.readouterr()
    assert json.loads(output.out) == 30
    assert output.err == ""


def test_main_thread_command_runs_through_http(running_server):
    server, base_url = running_server
    client = HttpClient(base_url, timeout=5)

    result = {}
    errors = []

    def call_command():
        try:
            result["value"] = client.call_command("get_state", {})
        except Exception as exc:
            errors.append(exc)

    caller = threading.Thread(target=call_command)
    caller.start()

    deadline = time.monotonic() + 3

    try:
        while caller.is_alive() and time.monotonic() < deadline:
            server.run_pending(limit=1)
            time.sleep(0.01)
    finally:
        caller.join(timeout=5)

    assert not caller.is_alive(), "主线程命令调用未能结束"
    assert errors == []
    assert result["value"] == {"status": "ready"}


def test_mcp_tool_end_to_end(running_server):
    _, base_url = running_server

    async def run_test():
        client = HttpClient(base_url)
        commands = await asyncio.to_thread(client.get, "/commands")

        add_command = next(
            command for command in commands
            if command["name"] == "add"
        )

        tool = mcp_adapter._create_tool(
            client,
            add_command,
            timeout=5,
        )

        result = await tool.fn(a=7, b=8)

        assert json.loads(result) == 15

    asyncio.run(run_test())
