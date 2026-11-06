import threading
import pytest

from agentize_bridge.container import Container


class DummyService:
    def __init__(self, value: int = 0):
        self.value = value


# -------------------- 基础生命周期 --------------------

def test_register_and_resolve():
    container = Container()
    service = DummyService(value=42)

    container.register("dummy", service)

    assert container.resolve("dummy") is service


def test_register_duplicate_name_raises():
    container = Container()
    container.register("dummy", DummyService(1))

    with pytest.raises(ValueError, match="已经被注册"):
        container.register("dummy", DummyService(2))


def test_resolve_unregistered_name_raises():
    container = Container()

    with pytest.raises(KeyError, match="不存在"):
        container.resolve("missing")


def test_unregister_removes_instance():
    container = Container()
    container.register("dummy", DummyService())

    container.unregister("dummy")

    with pytest.raises(KeyError):
        container.resolve("dummy")


def test_unregister_nonexistent_name_is_safe():
    container = Container()
    # 对不存在的 key 注销不应抛出异常
    container.unregister("never_existed")


# -------------------- 并发安全 --------------------

def test_thread_safe_concurrent_registration():
    """
    多个线程同时注册同一个名称，应当只有一个成功，其余抛出 ValueError。
    验证 RLock 是否发挥了作用。
    """
    container = Container()
    success_count = 0
    error_count = 0
    lock = threading.Lock()

    def register_worker():
        nonlocal success_count, error_count
        try:
            container.register("concurrent_key", DummyService())
            with lock:
                success_count += 1
        except ValueError:
            with lock:
                error_count += 1

    threads = [threading.Thread(target=register_worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 并发环境下，必须有且仅有 1 个线程注册成功
    assert success_count == 1
    assert error_count == 9


def test_thread_safe_concurrent_resolve():
    """
    并发读取时的安全性验证（虽说是字典读，但配合写入时测更稳）
    """
    container = Container()
    service = DummyService()
    container.register("shared_key", service)

    results = []
    lock = threading.Lock()

    def resolve_worker():
        try:
            res = container.resolve("shared_key")
            with lock:
                results.append(res)
        except KeyError:
            pass

    threads = [threading.Thread(target=resolve_worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 20
    # 保证拿到的都是同一个实例
    assert all(r is service for r in results)
