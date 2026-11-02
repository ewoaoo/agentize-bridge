"""start_http 安装的 Host / Origin 守卫。

守卫只在 start_http 里安装。这里直接调用 _install_local_guard，避免真的占用端口。
"""
import pytest
from fastapi.testclient import TestClient

from agentize_bridge.server import AgentizeServer

HOST = "127.0.0.1"
PORT = 8765
DEFAULT_BASE_URL = f"http://{HOST}:{PORT}"


@pytest.fixture
def guarded():
    server = AgentizeServer()
    calls = []

    @server.command()
    def ping() -> str:
        calls.append(1)
        return "pong"

    server._install_local_guard(HOST, PORT)
    yield server, calls
    server.close()


def make_client(server, base_url=DEFAULT_BASE_URL):
    # base_url 决定请求带的 Host 头
    return TestClient(server.fastapi_app, base_url=base_url, raise_server_exceptions=False)


@pytest.mark.parametrize("base_url", [
    "http://127.0.0.1:8765",
    "http://localhost:8765",
    "http://127.0.0.1",
    "http://localhost",
])
def test_allowed_hosts_pass(guarded, base_url):
    server, _ = guarded

    assert make_client(server, base_url).get("/health").status_code == 200


@pytest.mark.parametrize("base_url", [
    "http://evil.example.com",
    "http://evil.example.com:8765",
    "http://127.0.0.1.evil.com:8765",
])
def test_foreign_host_is_rejected_before_command_runs(guarded, base_url):
    server, calls = guarded

    response = make_client(server, base_url).post("/command/ping", json={})

    assert response.status_code == 400
    assert calls == []


@pytest.mark.parametrize("origin", [
    "http://127.0.0.1:8765",
    "http://localhost:8765",
])
def test_same_origin_is_allowed(guarded, origin):
    server, calls = guarded

    response = make_client(server).post("/command/ping", json={}, headers={"Origin": origin})

    assert response.status_code == 200
    assert response.json() == "pong"
    assert calls == [1]


@pytest.mark.parametrize("origin", [
    "http://evil.example.com",
    "http://127.0.0.1:9999",  # 端口不同
    "https://127.0.0.1:8765",  # 协议不同
    "null",  # file:// 或沙盒 iframe
])
def test_foreign_origin_is_rejected_before_command_runs(guarded, origin):
    server, calls = guarded

    response = make_client(server).post("/command/ping", json={}, headers={"Origin": origin})

    assert response.status_code == 403
    assert calls == []


def test_request_without_origin_is_allowed(guarded):
    """CLI、curl、MCP 适配器都不带 Origin 头。"""
    server, calls = guarded

    response = make_client(server).post("/command/ping", json={})

    assert response.status_code == 200
    assert calls == [1]
