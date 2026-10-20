from concurrent.futures import Future
from queue import Queue, Empty, Full
from typing import Any

from fastapi import HTTPException

from .command import CommandRequest


class CommandQueue:
    def __init__(self, maxsize: int = 64):
        if maxsize <= 0 or maxsize > 64:
            raise ValueError("maxsize 必须在 1 到 64 之间")
        self._queue: Queue[CommandRequest] = Queue(maxsize=maxsize)

    def submit(self, name: str, arguments: dict[str, Any]) -> Future:
        future: Future[Any] = Future()
        try:
            self._queue.put_nowait(CommandRequest(name, arguments, future))
        except Full as exc:
            raise HTTPException(status_code=503, detail="指令队列已满") from exc
        return future

    def get_nowait(self) -> CommandRequest:
        try:
            return self._queue.get_nowait()
        except Empty:
            raise

    def task_done(self) -> None:
        self._queue.task_done()

    def empty(self) -> bool:
        return self._queue.empty()

    def qsize(self) -> int:
        return self._queue.qsize()
