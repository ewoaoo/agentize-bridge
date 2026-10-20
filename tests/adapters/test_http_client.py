import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from agentize_bridge.adapters.http_client import HttpClient, HttpClientError


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return self.content


def test_init_strips_trailing_slash():
    client = HttpClient("http://localhost:8765///")

    assert client.base_url == "http://localhost:8765"


def test_get_builds_request(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(b'{"status": "ok"}')

    monkeypatch.setattr(
        "agentize_bridge.adapters.http_client.urlopen",
        fake_urlopen,
    )

    client = HttpClient("http://localhost:8765", timeout=10)
    result = client.get("/health")

    request = captured["request"]
    assert result == {"status": "ok"}
    assert request.full_url == "http://localhost:8765/health"
    assert request.method == "GET"
    assert captured["timeout"] == 10


def test_post_sends_json_body(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return FakeResponse(b'{"result": 42}')

    monkeypatch.setattr(
        "agentize_bridge.adapters.http_client.urlopen",
        fake_urlopen,
    )

    client = HttpClient("http://localhost:8765")
    result = client.post("/test", {"value": 42})

    request = captured["request"]
    assert result == {"result": 42}
    assert request.method == "POST"
    assert json.loads(request.data.decode("utf-8")) == {"value": 42}
    assert request.get_header("Content-type") == "application/json"


def test_request_without_body_sends_no_data(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return FakeResponse(b'{"status": "ok"}')

    monkeypatch.setattr(
        "agentize_bridge.adapters.http_client.urlopen",
        fake_urlopen,
    )

    HttpClient("http://localhost:8765").get("/health")

    assert captured["request"].data is None


def test_request_returns_none_for_empty_response(monkeypatch):
    monkeypatch.setattr(
        "agentize_bridge.adapters.http_client.urlopen",
        lambda request, timeout: FakeResponse(b""),
    )

    client = HttpClient("http://localhost:8765")

    assert client.get("/empty") is None


def test_request_parses_json_response(monkeypatch):
    monkeypatch.setattr(
        "agentize_bridge.adapters.http_client.urlopen",
        lambda request, timeout: FakeResponse(
            '{"message": "你好"}'.encode("utf-8")
        ),
    )

    client = HttpClient("http://localhost:8765")

    assert client.get("/test") == {"message": "你好"}


def test_request_rejects_invalid_json_response(monkeypatch):
    monkeypatch.setattr(
        "agentize_bridge.adapters.http_client.urlopen",
        lambda request, timeout: FakeResponse(b"not json"),
    )

    client = HttpClient("http://localhost:8765")

    with pytest.raises(HttpClientError, match="无效的 JSON 响应"):
        client.get("/test")


def test_http_error_is_wrapped(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=BytesIO(b'{"detail": "command not found"}'),
        )

    monkeypatch.setattr(
        "agentize_bridge.adapters.http_client.urlopen",
        fake_urlopen,
    )

    client = HttpClient("http://localhost:8765")

    with pytest.raises(HttpClientError, match="HTTP 404") as exc_info:
        client.get("/missing")

    assert "command not found" in str(exc_info.value)


def test_url_error_is_wrapped(monkeypatch):
    monkeypatch.setattr(
        "agentize_bridge.adapters.http_client.urlopen",
        lambda request, timeout: (_ for _ in ()).throw(
            URLError("connection refused")
        ),
    )

    client = HttpClient("http://localhost:8765")

    with pytest.raises(HttpClientError, match="HTTP 请求失败") as exc_info:
        client.get("/health")

    assert "connection refused" in str(exc_info.value)


def test_call_command_encodes_command_name(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return FakeResponse(b'{"result": "ok"}')

    monkeypatch.setattr(
        "agentize_bridge.adapters.http_client.urlopen",
        fake_urlopen,
    )

    client = HttpClient("http://localhost:8765")
    result = client.call_command("image/process", {"threshold": 0.5})

    assert result == {"result": "ok"}
    assert captured["request"].full_url == (
        "http://localhost:8765/command/image%2Fprocess"
    )
    assert json.loads(captured["request"].data.decode("utf-8")) == {
        "threshold": 0.5
    }


def test_call_command_passes_timeout(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return FakeResponse(b'{"result": "ok"}')

    monkeypatch.setattr(
        "agentize_bridge.adapters.http_client.urlopen",
        fake_urlopen,
    )

    client = HttpClient("http://localhost:8765")
    client.call_command("process", {"value": 1}, timeout=5)

    assert captured["request"].full_url == (
        "http://localhost:8765/command/process?timeout=5"
    )


def test_call_command_omits_timeout_when_none(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return FakeResponse(b'{"result": "ok"}')

    monkeypatch.setattr(
        "agentize_bridge.adapters.http_client.urlopen",
        fake_urlopen,
    )

    client = HttpClient("http://localhost:8765")
    client.call_command("process", {})

    assert captured["request"].full_url == (
        "http://localhost:8765/command/process"
    )
