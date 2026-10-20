import pytest
from concurrent.futures import Future
from queue import Empty

from agentize_bridge.command import CommandRequest
from agentize_bridge.queues import CommandQueue


def test_submit_returns_future():
    queue = CommandQueue()

    future = queue.submit("greet", {"name": "Alice"})

    assert isinstance(future, Future)
    assert not future.done()


def test_submit_adds_request_to_queue():
    queue = CommandQueue()
    arguments = {"name": "Alice", "greeting": "Hello"}

    future = queue.submit("greet", arguments)
    request = queue.get_nowait()

    assert isinstance(request, CommandRequest)
    assert request.name == "greet"
    assert request.arguments == arguments
    assert request.future is future


def test_submit_preserves_arguments():
    queue = CommandQueue()
    arguments = {"count": 3, "enabled": True}

    queue.submit("process", arguments)
    request = queue.get_nowait()

    assert request.arguments is arguments


def test_submit_multiple_requests_preserves_fifo_order():
    queue = CommandQueue()

    future1 = queue.submit("first", {"value": 1})
    future2 = queue.submit("second", {"value": 2})
    future3 = queue.submit("third", {"value": 3})

    request1 = queue.get_nowait()
    request2 = queue.get_nowait()
    request3 = queue.get_nowait()

    assert [request.name for request in (request1, request2, request3)] == [
        "first",
        "second",
        "third",
    ]
    assert [request.future for request in (request1, request2, request3)] == [
        future1,
        future2,
        future3,
    ]


def test_each_submission_gets_independent_future():
    queue = CommandQueue()

    future1 = queue.submit("process", {})
    future2 = queue.submit("process", {})

    assert future1 is not future2


def test_empty_initially():
    queue = CommandQueue()

    assert queue.empty()


def test_empty_after_submit_and_get():
    queue = CommandQueue()

    queue.submit("process", {})
    assert not queue.empty()

    queue.get_nowait()
    assert queue.empty()


def test_get_nowait_raises_empty_when_queue_is_empty():
    queue = CommandQueue()

    with pytest.raises(Empty):
        queue.get_nowait()


def test_qsize_tracks_pending_requests():
    queue = CommandQueue()

    assert queue.qsize() == 0

    queue.submit("first", {})
    assert queue.qsize() == 1

    queue.submit("second", {})
    assert queue.qsize() == 2

    queue.get_nowait()
    assert queue.qsize() == 1

    queue.get_nowait()
    assert queue.qsize() == 0


def test_task_done_marks_retrieved_task_as_completed():
    queue = CommandQueue()

    queue.submit("process", {})
    queue.get_nowait()

    queue.task_done()

    # task_done() 不会改变队列中的元素数量。
    assert queue.qsize() == 0


def test_task_done_raises_when_called_too_many_times():
    queue = CommandQueue()

    with pytest.raises(ValueError):
        queue.task_done()


def test_multiple_tasks_can_be_marked_done():
    queue = CommandQueue()

    queue.submit("first", {})
    queue.submit("second", {})

    queue.get_nowait()
    queue.task_done()

    queue.get_nowait()
    queue.task_done()

    assert queue.empty()
