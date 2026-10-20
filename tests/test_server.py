import time
from concurrent.futures import ThreadPoolExecutor
from threading import get_ident

import pytest
from fastapi.testclient import TestClient

from agentize_bridge.server import AgentizeServer
from agentize_bridge.executor import (
    CommandExecutionError,
    CommandNotFoundError,
)


@pytest.fixture
def server():
    instance = AgentizeServer()
    yield instance
    instance.close()


@pytest.fixture
def client(server):
    return TestClient(server.fastapi_app, raise_server_exceptions=False)


# -------------------- 命令注册 --------------------

def test_register_command(server):
    @server.command()
    def greet(name: str):
        return f"Hello, {name}"

    assert "greet" in server._commands
    assert server._commands["greet"].fn is greet


def test_register_command_with_custom_options(server):
    @server.command(
        name="custom-greet",
        description="Custom greeting",
        thread="worker",
        timeout=5.0,
    )
    def greet(name: str):
        return f"Hello, {name}"

    command = server._commands["custom-greet"]

    assert command.fn is greet
    assert command.description == "Custom greeting"
    assert command.thread == "worker"
    assert command.timeout == 5.0


def test_register_command_uses_docstring(server):
    @server.command()
    def greet(name: str):
        """Greet someone."""
        return f"Hello, {name}"

    assert server._commands["greet"].description == "Greet someone."


def test_register_command_rejects_duplicate_name(server):
    @server.command(name="duplicate")
    def first():
        pass

    with pytest.raises(ValueError, match="已经被注册"):
        @server.command(name="duplicate")
        def second():
            pass


def test_register_command_rejects_invalid_command(server):
    with pytest.raises(ValueError, match="无效的命令名称"):
        @server.command(name="invalid name")
        def process():
            pass


# -------------------- 命令列表与健康检查 --------------------

def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_commands_endpoint(server, client):
    @server.command(description="Add two numbers")
    def add(a: int, b: int):
        return a + b

    response = client.get("/commands")

    assert response.status_code == 200

    commands = response.json()
    assert len(commands) == 1
    assert commands[0]["name"] == "add"
    assert commands[0]["description"] == "Add two numbers"
    assert commands[0]["thread"] == "worker"
    assert commands[0]["input_schema"]["required"] == ["a", "b"]


def test_list_commands_returns_empty_list(client):
    response = client.get("/commands")

    assert response.status_code == 200
    assert response.json() == []


# -------------------- worker 命令执行 --------------------

def test_dispatch_worker_command_returns_result(server):
    @server.command(thread="worker")
    def add(a: int, b: int):
        return a + b

    result = server._dispatch("add", {"a": 2, "b": 3}, timeout=2)

    assert result == 5


def test_worker_command_runs_in_worker_thread(server):
    main_thread_id = get_ident()

    @server.command(thread="worker")
    def get_thread_id():
        return get_ident()

    worker_thread_id = server._dispatch("get_thread_id", {}, timeout=2)

    assert worker_thread_id != main_thread_id


def test_dispatch_worker_command_wraps_execution_error(server):
    @server.command(thread="worker")
    def fail():
        raise ValueError("test failure")

    with pytest.raises(CommandExecutionError, match="test failure"):
        server._dispatch("fail", {}, timeout=2)


# -------------------- main 命令调度 --------------------

def test_dispatch_main_command_waits_for_run_pending(server):
    @server.command(thread="main")
    def add(a: int, b: int):
        return a + b

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            server._dispatch,
            "add",
            {"a": 2, "b": 3},
            timeout=2,
        )

        deadline = time.monotonic() + 1
        while server._queue.qsize() == 0:
            if time.monotonic() >= deadline:
                pytest.fail("命令没有进入队列")
            time.sleep(0.001)

        assert not future.done()

        processed = server.run_pending()

        assert processed == 1
        assert future.result(timeout=1) == 5


def test_run_pending_respects_limit(server):
    @server.command()
    def identity(value: int):
        return value

    futures = [
        server._queue.submit("identity", {"value": value})
        for value in range(3)
    ]

    assert server.run_pending(limit=2) == 2
    assert futures[0].result() == 0
    assert futures[1].result() == 1
    assert not futures[2].done()

    assert server.run_pending() == 1
    assert futures[2].result() == 2


def test_run_pending_returns_zero_when_queue_is_empty(server):
    assert server.run_pending() == 0


def test_run_pending_handles_unknown_command(server):
    future = server._queue.submit("missing", {})

    assert server.run_pending() == 1

    with pytest.raises(CommandNotFoundError, match="找不到指令"):
        future.result()


def test_run_pending_handles_command_execution_error(server):
    @server.command()
    def fail():
        raise ValueError("test failure")

    future = server._queue.submit("fail", {})

    assert server.run_pending() == 1

    with pytest.raises(CommandExecutionError, match="test failure"):
        future.result()


def test_run_pending_preserves_result_order(server):
    @server.command()
    def identity(value: int):
        return value

    futures = [
        server._queue.submit("identity", {"value": value})
        for value in range(3)
    ]

    assert server.run_pending() == 3
    assert [future.result() for future in futures] == [0, 1, 2]


# -------------------- HTTP 命令调用 --------------------

def test_http_execute_worker_command(server, client):
    @server.command(thread="worker")
    def add(a: int, b: int):
        return a + b

    response = client.post(
        "/command/add",
        json={"a": 2, "b": 3},
    )

    assert response.status_code == 200
    assert response.json() == 5


def test_http_execute_unknown_command(client):
    response = client.post(
        "/command/missing",
        json={},
    )

    assert response.status_code == 404
    assert "找不到指令" in response.json()["detail"]


def test_http_execute_command_with_missing_argument(server, client):
    @server.command(thread="worker")
    def greet(name: str):
        return f"Hello, {name}"

    response = client.post(
        "/command/greet",
        json={},
    )

    assert response.status_code == 422


def test_http_execute_command_with_extra_argument(server, client):
    @server.command(thread="worker")
    def greet(name: str):
        return f"Hello, {name}"

    response = client.post(
        "/command/greet",
        json={"name": "Alice", "extra": True},
    )

    assert response.status_code == 422


def test_http_execute_command_with_invalid_body(server, client):
    @server.command(thread="worker")
    def greet(name: str):
        return f"Hello, {name}"

    response = client.post(
        "/command/greet",
        json=["Alice"],
    )

    assert response.status_code == 422


def test_http_execute_command_with_timeout(server, client):
    @server.command(thread="worker")
    def slow():
        time.sleep(0.1)
        return "done"

    response = client.post(
        "/command/slow?timeout=0.01",
        json={},
    )

    assert response.status_code == 504
    assert response.json()["detail"] == "command 'slow' timed out"


def test_http_execute_command_rejects_nonpositive_timeout(server, client):
    @server.command(thread="worker")
    def process():
        return "done"

    response = client.post(
        "/command/process?timeout=0",
        json={},
    )

    assert response.status_code == 422


# -------------------- 生命周期 --------------------

def test_dispatch_rejects_calls_after_close():
    server = AgentizeServer()
    server.close()

    with pytest.raises(RuntimeError, match="已经关闭"):
        server._dispatch("missing", {})


def test_close_is_idempotent(server):
    server.close()
    server.close()

    assert server._closed


def test_command_registration_does_not_start_http_server(server):
    @server.command()
    def process():
        pass

    assert server._http_server is None
    assert server._http_thread is None
