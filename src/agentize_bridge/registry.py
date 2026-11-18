from .command import Command, ThreadMode, DEFAULT_TIMEOUT, create_command

_pending: dict[str, Command] = {}


def command(
        name: str = "",
        description: str = "",
        thread: ThreadMode = "worker",
        timeout: float = DEFAULT_TIMEOUT
):
    def decorator(fn):
        cmd = create_command(fn, name=name, description=description, thread=thread, timeout=timeout)
        if cmd.name in _pending:
            raise ValueError(f"命令 {cmd.name} 已经被注册")
        _pending[cmd.name] = cmd
        return fn

    return decorator


def snapshot() -> dict[str, Command]:
    return dict(_pending)


def clear() -> None:
    _pending.clear()
