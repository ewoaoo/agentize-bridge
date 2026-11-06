import inspect
from typing import Callable, Optional


def get_instance_class_name(fn: Callable) -> Optional[str]:
    """
    如果是未绑定的实例方法（第一个参数为 self），返回其类名。
    否则（普通函数、静态方法、类方法等）返回 None。
    """
    qualname = getattr(fn, "__qualname__", "")

    # 1. 必须有类名限定（排除模块级普通函数、嵌套函数）
    if "." not in qualname or "<locals>" in qualname:
        return None

    # 2. 检查第一个参数是不是 self
    try:
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        if params and params[0].name == "self":
            # 提取类名：例如 "MyClass.do_work" -> "MyClass"
            return qualname.split(".")[-2]
    except (ValueError, TypeError):
        pass

    return None
