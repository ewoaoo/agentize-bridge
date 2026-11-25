import inspect
import json
import logging
import sys
import time
from contextlib import ExitStack
from contextvars import ContextVar
from os import PathLike
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Message, Receive, Scope, Send

__all__ = ["AccessLogApp"]

LogMode = Literal["simple", "full"]

_ACCESS_LOGGER = "agentize_bridge.access_logger"
_ACCESS_DETAIL = "agentize_bridge.access_detail"


class AccessLogApp:
    """ 在原应用的 ASGI 入口记录访问日志 """

    def __init__(
            self,
            app: FastAPI,
            *,
            mode: LogMode = "simple",
            file_path: str | PathLike[str] | None = None
    ) -> None:
        if mode not in ("simple", "full"):
            raise ValueError(f"无效的日志模式: {mode!r}")

        self._app = app
        self._console_level = logging.WARNING if mode == "simple" else logging.INFO
        self._path = Path(file_path) if file_path is not None else None
        self._replacing_access = ContextVar("agentize_bridge.replacing_access", default=False)
        self._http_error_handler = app.exception_handlers.get(HTTPException, http_exception_handler)
        app.add_exception_handler(HTTPException, self._handle_http_error)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ 转发 ASGI 调用，在 HTTP 响应开始时替换原生访问行 """
        if scope["type"] == "lifespan":
            await self._serve_lifespan(scope, receive, send)
            return

        logger = scope.get("state", {}).get(_ACCESS_LOGGER)
        if scope["type"] != "http" or logger is None:
            await self._app(scope, receive, send)
            return

        started_at = time.perf_counter()

        async def send_response(message: Message) -> None:
            if message["type"] != "http.response.start":
                await send(message)
                return

            elapsed_ms = (time.perf_counter() - started_at) * 1000
            # _serve_lifespan 安装的过滤器只在发送此消息时跳过 Uvicorn 的访问行。
            token = self._replacing_access.set(True)
            try:
                await send(message)
            finally:
                self._replacing_access.reset(token)

            try:
                self._write_access(logger, scope, message["status"], elapsed_ms)
            except Exception:
                try:
                    logging.getLogger(__name__).exception("HTTP 访问日志记录失败")
                except Exception:
                    # 即使宿主的诊断输出失败，也要继续发送响应体。
                    pass

        await self._app(scope, receive, send_response)

    async def _serve_lifespan(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ 在应用确认启动前安装 logger 和过滤器，由同一个 ExitStack 负责清理 """
        native_access = logging.getLogger("uvicorn.access")

        def keep_native_access(_record: logging.LogRecord) -> bool:
            return not self._replacing_access.get()

        with ExitStack() as resources:
            async def send_lifespan(message: Message) -> None:
                if message["type"] == "lifespan.startup.complete":
                    state = scope["state"]
                    logger = self._open_access_logger(resources)

                    native_access.addFilter(keep_native_access)
                    resources.callback(native_access.removeFilter, keep_native_access)
                    state[_ACCESS_LOGGER] = logger
                    resources.callback(state.pop, _ACCESS_LOGGER, None)
                    resources.callback(setattr, logger, "disabled", True)

                await send(message)

            await self._app(scope, receive, send_lifespan)

    def _open_access_logger(self, resources: ExitStack) -> logging.Logger:
        """ 配置控制台和可选文件，并将 handler 的关闭动作登记到应用生命周期 """
        logger = logging.Logger("agentize_bridge.access", level=logging.INFO)
        plain = logging.Formatter("%(levelname)s: %(message)s")

        console = logging.StreamHandler(sys.stdout)
        resources.callback(console.close)
        console.setLevel(self._console_level)
        console.setFormatter(_ConsoleFormatter() if console.stream.isatty() else plain)
        logger.addHandler(console)

        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(self._path, mode="a", encoding="utf-8")
            resources.callback(file_handler.close)
            file_handler.setFormatter(plain)
            logger.addHandler(file_handler)

        return logger

    async def _handle_http_error(self, request: Request, exc: HTTPException) -> Response:
        """ 记录 HTTP 异常的业务详情，由原有异常处理器生成响应 """
        state = request.scope.get("state", {})
        if _ACCESS_LOGGER in state:
            detail = exc.detail
            if exc.status_code == 500 and isinstance(detail, str) and exc.__cause__ is not None:
                # 命令路由将 CommandExecutionError 包装为 HTTPException，前者保留原始异常。
                cause = exc.__cause__
                detail = cause.__cause__ if cause.__cause__ is not None else cause
            state[_ACCESS_DETAIL] = detail

        handler = self._http_error_handler
        if inspect.iscoroutinefunction(handler):
            return await handler(request, exc)

        response = await run_in_threadpool(handler, request, exc)
        if inspect.isawaitable(response):
            return await response
        return response

    @staticmethod
    def _write_access(logger: logging.Logger, scope: Scope, status: int, elapsed_ms: float) -> None:
        """ 根据状态码定级，将地址、路径、耗时和详情写成一行 """
        level = logging.INFO
        if status >= 500:
            level = logging.ERROR
        elif status >= 400:
            level = logging.WARNING

        client = scope.get("client")
        address = f"{client[0]}:{client[1]}" if client else "-"
        target = json.dumps(f'{scope["method"]} {scope["path"]}', ensure_ascii=False)

        detail = scope.get("state", {}).get(_ACCESS_DETAIL)
        suffix = ""
        if detail is not None:
            if isinstance(detail, BaseException):
                detail = f"{type(detail).__name__}: {detail}"
            try:
                encoded = json.dumps(detail, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                detail = str(detail)
                encoded = json.dumps(detail, ensure_ascii=False)
            suffix = f" | {encoded[1:-1] if isinstance(detail, str) else encoded}"

        logger.log(level, "%s - %s %d %.1fms%s", address, target, status, elapsed_ms, suffix)


class _ConsoleFormatter(logging.Formatter):
    """ 为终端访问日志设置级别颜色，每行独立重置终端样式 """

    colors = {logging.INFO: "\x1b[32m", logging.WARNING: "\x1b[33m", logging.ERROR: "\x1b[31m"}
    reset = "\x1b[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.colors.get(record.levelno, "")
        return f"{self.reset}{color}{record.levelname}:{self.reset} {record.getMessage()}"
