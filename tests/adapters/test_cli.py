import json

from agentize_bridge.adapters import cli
from agentize_bridge.adapters.http_client import HttpClientError


def test_list_prints_commands(monkeypatch, capsys):
    expected = [{"name": "process", "description": "Process an image"}]

    class FakeClient:
        def __init__(self, base_url, timeout):
            assert base_url == "http://127.0.0.1:8765"
            assert timeout == 30

        def get(self, path):
            assert path == "/commands"
            return expected

    monkeypatch.setattr(cli, "HttpClient", FakeClient)

    assert cli.run_cli(["list"]) == 0
    captured = capsys.readouterr()

    assert json.loads(captured.out) == expected
    assert captured.err == ""


def test_list_uses_custom_url_and_timeout(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, base_url, timeout):
            captured["base_url"] = base_url
            captured["timeout"] = timeout

        def get(self, path):
            captured["path"] = path
            return []

    monkeypatch.setattr(cli, "HttpClient", FakeClient)

    assert cli.run_cli([
        "--url", "http://localhost:9000",
        "--timeout", "10",
        "list",
    ]) == 0

    assert captured == {
        "base_url": "http://localhost:9000",
        "timeout": 10,
        "path": "/commands",
    }


def test_url_defaults_to_environment_variable(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, base_url, timeout):
            captured["base_url"] = base_url

        def get(self, path):
            return []

    monkeypatch.setenv("AGENTIZE_BRIDGE_URL", "http://localhost:9001")
    monkeypatch.setattr(cli, "HttpClient", FakeClient)

    assert cli.run_cli(["list"]) == 0
    assert captured["base_url"] == "http://localhost:9001"


def test_url_argument_overrides_environment_variable(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, base_url, timeout):
            captured["base_url"] = base_url

        def get(self, path):
            return []

    monkeypatch.setenv("AGENTIZE_BRIDGE_URL", "http://localhost:9001")
    monkeypatch.setattr(cli, "HttpClient", FakeClient)

    assert cli.run_cli(["--url", "http://localhost:9002", "list"]) == 0
    assert captured["base_url"] == "http://localhost:9002"


def test_call_parses_json_arguments(monkeypatch, capsys):
    captured = {}

    class FakeClient:
        def __init__(self, base_url, timeout):
            pass

        def call_command(self, name, arguments, timeout=None):
            captured["name"] = name
            captured["arguments"] = arguments
            captured["timeout"] = timeout
            return {"result": "成功"}

    monkeypatch.setattr(cli, "HttpClient", FakeClient)

    result = cli.run_cli([
        "--timeout", "15",
        "call", "process",
        "--args", '{"threshold": 0.5, "enabled": true}',
    ])

    assert result == 0
    assert captured == {
        "name": "process",
        "arguments": {"threshold": 0.5, "enabled": True},
        "timeout": 15,
    }

    output = capsys.readouterr()
    assert json.loads(output.out) == {"result": "成功"}
    assert output.err == ""


def test_call_defaults_arguments_to_empty_object(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, base_url, timeout):
            pass

        def call_command(self, name, arguments, timeout=None):
            captured["arguments"] = arguments
            return None

    monkeypatch.setattr(cli, "HttpClient", FakeClient)

    assert cli.run_cli(["call", "process"]) == 0
    assert captured["arguments"] == {}


def test_call_rejects_invalid_json(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, base_url, timeout):
            pass

    monkeypatch.setattr(cli, "HttpClient", FakeClient)

    assert cli.run_cli(["call", "process", "--args", "{invalid}"]) == 1

    output = capsys.readouterr()
    assert output.out == ""
    assert "错误:" in output.err


def test_call_rejects_non_object_json(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, base_url, timeout):
            pass

    monkeypatch.setattr(cli, "HttpClient", FakeClient)

    for value in ("[]", '"text"', "123", "null", "true"):
        assert cli.run_cli(["call", "process", "--args", value]) == 1

        output = capsys.readouterr()
        assert output.out == ""
        assert "--args 必须是一个 JSON 对象" in output.err


def test_http_client_error_returns_one(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, base_url, timeout):
            pass

        def get(self, path):
            raise HttpClientError("HTTP 500: internal error")

    monkeypatch.setattr(cli, "HttpClient", FakeClient)

    assert cli.run_cli(["list"]) == 1

    output = capsys.readouterr()
    assert output.out == ""
    assert "HTTP 500: internal error" in output.err


def test_call_http_error_returns_one(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, base_url, timeout):
            pass

        def call_command(self, name, arguments, timeout=None):
            raise HttpClientError("HTTP 404: not found")

    monkeypatch.setattr(cli, "HttpClient", FakeClient)

    assert cli.run_cli(["call", "missing"]) == 1

    output = capsys.readouterr()
    assert output.out == ""
    assert "HTTP 404: not found" in output.err


def test_missing_action_exits_with_argument_error():
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        cli.run_cli([])

    assert exc_info.value.code == 2


def test_main_returns_run_cli_exit_code(monkeypatch):
    monkeypatch.setattr(cli, "run_cli", lambda: 7)

    assert cli.main() == 7
