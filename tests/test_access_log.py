import json
import logging
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.testclient import TestClient

from agentize_bridge.access_log import AccessLogApp
from agentize_bridge.command import create_command
from agentize_bridge.server import AgentizeServer


@pytest.mark.parametrize("mode", ["simple", "full"])
def test_console_mode_preserves_business_error_details(mode, capsys):
    app = FastAPI()
    logged_app = AccessLogApp(app, mode=mode)
    detail = {"code": "invalid", "fields": ["scale"]}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/invalid")
    def invalid():
        raise HTTPException(status_code=422, detail=detail)

    with TestClient(logged_app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.get("/invalid")

    assert response.status_code == 422
    assert response.json() == {"detail": detail}
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == (2 if mode == "full" else 1)
    if mode == "full":
        assert lines[0].startswith("INFO:")
        assert '"GET /health" 200' in lines[0]
    assert lines[-1].startswith("WARNING:")
    assert '"GET /invalid" 422' in lines[-1]
    assert json.loads(lines[-1].split(" | ", 1)[1]) == detail


def test_file_in_simple_mode_appends_all_access_records(capsys):
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    with TemporaryDirectory() as directory:
        path = Path(directory) / "logs" / "access.log"
        logged_app = AccessLogApp(app, file_path=path)
        assert not path.exists()

        with TestClient(logged_app) as client:
            assert client.get("/health").status_code == 200
        first = path.read_text(encoding="utf-8")
        assert first.startswith("INFO:")
        assert '"GET /health" 200' in first

        with TestClient(logged_app) as client:
            assert client.get("/missing").status_code == 404
        content = path.read_text(encoding="utf-8")
        assert content.startswith(first)
        assert len(content.splitlines()) == 2
        assert '"GET /missing" 404' in content
        assert "\x1b" not in content

    assert not path.exists()
    console = capsys.readouterr().out
    assert "INFO:" not in console
    assert "WARNING:" in console


def test_command_access_log_shows_original_execution_error(capsys):
    def fail():
        raise PermissionError("cannot write output")

    with AgentizeServer() as server:
        server._commands["fail"] = create_command(fail, thread="worker")
        with TestClient(server._http_app) as client:
            response = client.post("/command/fail", json={})

    assert response.status_code == 500
    line, = capsys.readouterr().out.splitlines()
    assert line.startswith("ERROR:")
    assert '"POST /command/fail" 500' in line
    assert line.endswith(" | PermissionError: cannot write output")


@pytest.mark.parametrize("diagnostic_fails", [False, True])
def test_access_log_failure_keeps_response_intact(diagnostic_fails, caplog, monkeypatch):
    app = FastAPI()
    failure = RuntimeError("access log formatter failed")
    diagnostic_logger = logging.getLogger("agentize_bridge.access_log")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    def fail_access_log(*_args):
        raise failure

    monkeypatch.setattr(AccessLogApp, "_write_access", staticmethod(fail_access_log))

    if diagnostic_fails:
        def fail_diagnostic(*_args):
            raise OSError("diagnostic output unavailable")

        monkeypatch.setattr(diagnostic_logger, "exception", fail_diagnostic)

    with caplog.at_level(logging.ERROR, logger=diagnostic_logger.name):
        with TestClient(AccessLogApp(app, mode="full")) as client:
            response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    if not diagnostic_fails:
        record, = [record for record in caplog.records if record.name == diagnostic_logger.name]
        assert record.getMessage() == "HTTP 访问日志记录失败"
        assert record.exc_info[1] is failure
        assert record.exc_info[2] is not None


def test_replaces_native_access_only_for_wrapped_responses(caplog, capsys, monkeypatch):
    native_access = logging.getLogger("uvicorn.access")
    monkeypatch.setattr(native_access, "handlers", [])
    monkeypatch.setattr(native_access, "propagate", True)
    original_filters = list(native_access.filters)
    app = FastAPI()
    logged_app = AccessLogApp(app, mode="full")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    async def protocol(scope, receive, send):
        async def send_with_native_access(message):
            if message["type"] == "http.response.start":
                native_access.info("native access for %s", scope["path"])
            await send(message)

        if scope["type"] == "http" and scope["path"] == "/unavailable":
            await Response(status_code=503)(scope, receive, send_with_native_access)
        else:
            await logged_app(scope, receive, send_with_native_access)

    with caplog.at_level(logging.INFO, logger="uvicorn.access"):
        with TestClient(protocol) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/unavailable").status_code == 503
        native_access.info("native access after shutdown")

    assert native_access.filters == original_filters
    assert [record.getMessage() for record in caplog.records if record.name == native_access.name] == [
        "native access for /unavailable",
        "native access after shutdown"
    ]
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert '"GET /health" 200' in lines[0]


def test_terminal_access_log_resets_previous_color(capsys, monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    with TestClient(AccessLogApp(FastAPI(), mode="full")) as client:
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/missing").status_code == 404

    info, warning = capsys.readouterr().out.splitlines()
    assert info.startswith("\x1b[0m\x1b[32mINFO:\x1b[0m ")
    assert warning.startswith("\x1b[0m\x1b[33mWARNING:\x1b[0m ")


def test_file_open_failure_leaves_native_access_filters_unchanged():
    native_access = logging.getLogger("uvicorn.access")
    original_filters = list(native_access.filters)

    with TemporaryDirectory() as directory:
        with pytest.raises(OSError):
            with TestClient(AccessLogApp(FastAPI(), file_path=directory)):
                pytest.fail("日志文件打不开时，应用不应完成启动")

    assert native_access.filters == original_filters
