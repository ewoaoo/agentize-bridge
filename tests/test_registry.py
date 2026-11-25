import pytest

from agentize_bridge.registry import command, snapshot, clear


@pytest.fixture(autouse=True)
def clean_registry():
    clear()
    yield
    clear()


def test_command_writes_to_global_pool_and_returns_function():
    @command(name="greet")
    def greet(name: str) -> str:
        return f"Hello, {name}"

    assert "greet" in snapshot()
    assert snapshot()["greet"].fn is greet
    assert greet("Alice") == "Hello, Alice"


def test_command_rejects_duplicate_name():
    @command(name="dup")
    def first():
        pass

    with pytest.raises(ValueError, match="已经被注册"):
        @command(name="dup")
        def second():
            pass


def test_snapshot_is_independent_copy():
    @command(name="ping")
    def ping():
        pass

    s = snapshot()
    s.clear()

    assert "ping" in snapshot()  # 修改 snapshot 不影响全局池


def test_clear_empties_pool():
    @command(name="ping")
    def ping():
        pass

    clear()

    assert snapshot() == {}
