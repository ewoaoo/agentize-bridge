from .__version__ import __version__  # 必须在最顶上，内部程序会从这里取版本
from .registry import command
from .server import AgentizeServer

__all__ = ["AgentizeServer","command"]
