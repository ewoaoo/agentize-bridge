import asyncio
import json
import threading
import time

import pytest
import uvicorn

from mcp import Client
from agentize_bridge.server import AgentizeServer
from agentize_bridge.adapters.http_client import HttpClient
from agentize_bridge.adapters.cli import run_cli
from agentize_bridge.adapters import mcp_server as mcp_adapter


class Calculator:
    def __init__(self, base: int):
        self.base = base

    def add_base(self, value: int) -> int:
        """Add a value to the base."""
        return self.base + value


class MethodTypeTester:
    def instance_m(self, x: int) -> str:
        return f"instance: {x}"

    @staticmethod
    def static_m(x: int) -> str:
        return f"static: {x}"

    @classmethod
    def class_m(cls, x: int) -> str:
        return f"class ({cls.__name__}): {x}"


class AsyncWorker:
    def __init__(self, prefix: str):
        self.prefix = prefix

    async def process(self, value: int) -> str:
        import asyncio
        await asyncio.sleep(0.01)
        return f"{self.prefix}: {value}"


@pytest.fixture
def running_server():
    server = AgentizeServer(name="Integration Test")

    server.container.register("Calculator", Calculator(base=100))
    server.command(name="add_base", thread="worker")(Calculator.add_base)

    server.command(name="static_m", thread="worker")(MethodTypeTester.static_m)
    server.command(name="class_m", thread="worker")(MethodTypeTester.class_m)

    server.container.register("AsyncWorker", AsyncWorker("async_worker"))
    server.command(name="async_process", thread="worker")(AsyncWorker.process)

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

    assert {"add"} <= command_names
    assert client.call_command("add", {"a": 2, "b": 3}, timeout=5) == 5


def test_cli_end_to_end(running_server, monkeypatch, capsys):
    _, base_url = running_server

    assert run_cli(["--url", base_url, "list"]) == 0

    output = capsys.readouterr()
    commands = json.loads(output.out)

    assert {command["name"] for command in commands} >= {"add"}
    assert output.err == ""

    assert run_cli(["--url", base_url, "call", "add", "--args", '{"a": 10, "b": 20}']) == 0

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
            result["value"] = client.call_command("get_state", {}, timeout=5)
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
        client = HttpClient(base_url, timeout=5)
        commands = await asyncio.to_thread(client.get, "/commands")
        server = mcp_adapter._create_server(client, commands, timeout=5)

        async with Client(server) as mcp_client:
            result = await mcp_client.call_tool("add", {"a": 7, "b": 8})
            assert json.loads(result.content[0].text) == 15

            bad = await mcp_client.call_tool("add", {"a": "x", "b": 1})
            assert bad.is_error is True
            assert "422" in bad.content[0].text

    asyncio.run(run_test())


def test_http_client_end_to_end_with_di(running_server):
    _, base_url = running_server
    client = HttpClient(base_url)

    assert client.call_command("add_base", {"value": 5}, timeout=5) == 105


def test_cli_end_to_end_with_di(running_server, capsys):
    _, base_url = running_server

    assert run_cli(["--url", base_url, "call", "add_base", "--args", '{"value": 20}']) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == 120
    assert output.err == ""


def test_mcp_tool_end_to_end_with_di(running_server):
    _, base_url = running_server

    async def run_test():
        client = HttpClient(base_url, timeout=5)
        commands = await asyncio.to_thread(client.get, "/commands")
        server = mcp_adapter._create_server(client, commands, timeout=5)

        async with Client(server) as mcp_client:
            result_injected = await mcp_client.call_tool("add_base", {"value": 7})
            assert json.loads(result_injected.content[0].text) == 107

    asyncio.run(run_test())


def test_http_client_static_and_class_methods(running_server):
    _, base_url = running_server
    client = HttpClient(base_url)

    # 测试静态方法
    assert client.call_command("static_m", {"x": 10}, timeout=5) == "static: 10"

    # 测试类方法
    assert client.call_command("class_m", {"x": 20}, timeout=5) == "class (MethodTypeTester): 20"


def test_http_client_end_to_end_with_async_di(running_server):
    _, base_url = running_server
    client = HttpClient(base_url)

    # 验证异步实例方法通过 HTTP -> worker 线程 -> executor 的链路
    assert client.call_command("async_process", {"value": 99}, timeout=5) == "async_worker: 99"


def test_cli_end_to_end_with_async_di(running_server, capsys):
    _, base_url = running_server

    assert run_cli([
        "--url", base_url,
        "call", "async_process",
        "--args", '{"value": 42}',
    ]) == 0

    output = capsys.readouterr()
    assert json.loads(output.out) == "async_worker: 42"
    assert output.err == ""


def test_mcp_tool_end_to_end_with_async_di(running_server):
    _, base_url = running_server

    async def run_test():
        client = HttpClient(base_url, timeout=5)
        commands = await asyncio.to_thread(client.get, "/commands")
        server = mcp_adapter._create_server(client, commands, timeout=5)

        async with Client(server) as mcp_client:
            result = await mcp_client.call_tool("async_process", {"value": 7})
            assert json.loads(result.content[0].text) == "async_worker: 7"

    asyncio.run(run_test())
