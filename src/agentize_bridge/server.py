import threading
import time

import uvicorn
from concurrent.futures import CancelledError, ThreadPoolExecutor
from queue import Empty
from threading import Thread
from typing import Any, Mapping
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from .executor import CommandExecutor, CommandNotFoundError, CommandArgumentsError, CommandExecutionError
from .queues import CommandQueue
from .command import Command, ThreadMode, create_command, DEFAULT_TIMEOUT


class ServerClosedError(RuntimeError):
    """服务已关闭：不再受理新请求，已排队的请求会被失败化。"""


class AgentizeServer:
    """ 注册命令并通过共享的 HTTP/MCP 服务器公开它们 """

    def __init__(self, name: str = "Agentize Bridge"):
        self.name = name
        self._commands: dict[str, Command] = {}
        self._executor = CommandExecutor()
        self._queue = CommandQueue()
        self._workers = ThreadPoolExecutor(thread_name_prefix="agentize-worker")

        self.fastapi_app = FastAPI(title=self.name, version="0.1.0")
        self._http_server: uvicorn.Server | None = None
        self._http_thread: Thread | None = None
        self._closed = False
        self._state_lock = threading.Lock()

        self._register_routes()

    def command(
            self,
            name: str = "",
            description: str = "",
            thread: ThreadMode = "worker",
            timeout: float = DEFAULT_TIMEOUT
    ):
        def register(func):
            command = create_command(
                func,
                name=name,
                description=description,
                thread=thread,
                timeout=timeout
            )
            if command.name in self._commands:
                raise ValueError(f"指令 {command.name} 已经被注册")
            self._commands[command.name] = command
            return func

        return register

    def run_pending(self, limit: int | None = None) -> int:
        """ 从队列中消费命令(应用内主线程循环挂载使用)；关闭后返回 0 """
        processed = 0
        while limit is None or processed < limit:
            with self._state_lock:
                if self._closed:
                    break
                try:
                    request = self._queue.get_nowait()
                except Empty:
                    break

            try:
                if not request.future.set_running_or_notify_cancel():
                    continue
                command = self._commands.get(request.name)
                if command is None:
                    request.future.set_exception(CommandNotFoundError(f"找不到指令 {request.name}"))
                else:
                    try:
                        result = self._executor.execute(command, request.arguments)
                    except Exception as exc:
                        request.future.set_exception(exc)
                    else:
                        request.future.set_result(result)
            finally:
                self._queue.task_done()
            processed += 1
        return processed

    def start_http(self, *, host: str = "127.0.0.1", port: int = 8765):
        """ 在后台线程中启动 HTTP 服务，使应用程序的主循环保持空闲 """
        with self._state_lock:
            if self._closed:
                raise RuntimeError("AgentizeServer 已关闭")
            if self._http_thread is not None:
                raise RuntimeError("HTTP 服务已经启动")

            # Host 和 Origin 校验
            self._install_local_guard(host=host, port=port)

            config = uvicorn.Config(self.fastapi_app, host=host, port=port)
            self._http_server = uvicorn.Server(config)
            self._http_thread = threading.Thread(
                target=self._http_server.run,
                name="agentize-server",
                daemon=True
            )
            self._http_thread.start()

        deadline = time.monotonic() + 10
        while not self._http_server.started:
            if not self._http_thread.is_alive():
                raise RuntimeError("HTTP 服务器启动失败,请检查配置的主机和端口")
            if time.monotonic() >= deadline:
                self._http_server.should_exit = True
                raise TimeoutError("启动 HTTP 服务器时超时")
            time.sleep(0.01)

    def close(self, *, wait: bool = True) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True

            # 失败化队列中尚未执行的请求，避免调用方一直等到客户端超时
            while True:
                try:
                    request = self._queue.get_nowait()
                except Empty:
                    break
                if request.future.set_running_or_notify_cancel():
                    request.future.set_exception(ServerClosedError("AgentizeServer 已关闭"))
                self._queue.task_done()

        if self._http_server is not None:
            self._http_server.should_exit = True
        if (
                wait
                and self._http_thread is not None
                and threading.current_thread() != self._http_thread
        ):
            self._http_thread.join(timeout=5)

        self._workers.shutdown(wait, cancel_futures=not wait)

    def _register_routes(self):
        """ 构建内部的 FastAPI 应用 """
        app = self.fastapi_app

        @app.get("/health")
        def health() -> dict[str, str]:
            return {"status": "ok"}

        @app.get("/commands")
        def list_commands() -> list[dict[str, Any]]:
            return [
                {
                    "name": command.name,
                    "description": command.description,
                    "thread": command.thread,
                    "input_schema": command.input_schema,
                }
                for command in self._commands.values()
            ]

        @app.post("/command/{name}")
        def execute_command(
                name: str,
                arguments: dict[str, Any] = Body(...),
                timeout: float | None = Query(default=None, gt=0)
        ) -> Any:
            try:
                return self._dispatch(name, arguments, timeout=timeout)
            except ServerClosedError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except CommandNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except CommandArgumentsError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except CommandExecutionError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            except TimeoutError as exc:
                raise HTTPException(status_code=504, detail=f"command {name!r} timed out") from exc

    def _dispatch(self, name: str, arguments: Mapping[str, Any], *, timeout: float | None = None) -> Any:
        with self._state_lock:
            if self._closed:
                raise ServerClosedError("AgentizeServer 已经关闭")

            command = self._commands.get(name)
            if command is None:
                raise CommandNotFoundError(f"找不到指令 {name}")

            args = dict(arguments or {})
            if command.thread == "worker":
                future = self._workers.submit(self._executor.execute, command, args)
            else:
                future = self._queue.submit(name, args)
        try:
            effective_timeout = timeout if timeout is not None else command.timeout
            return future.result(timeout=effective_timeout)
        except TimeoutError:
            future.cancel()
            raise
        except CancelledError as exc:
            raise ServerClosedError("AgentizeServer 已关闭") from exc

    def _install_local_guard(self, host: str, port: int) -> None:
        allowed_hosts = {"127.0.0.1", "localhost", host}
        allowed_origins = {f"http://{h}:{port}" for h in allowed_hosts}

        self.fastapi_app.add_middleware(TrustedHostMiddleware, allowed_hosts=sorted(allowed_hosts))

        @self.fastapi_app.middleware("http")
        async def reject_foreign_origin(request, call_next):
            origin = request.headers.get("origin")
            if origin is not None and origin not in allowed_origins:
                return JSONResponse({"detail": "Origin 不被允许"}, status_code=403)
            return await call_next(request)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
