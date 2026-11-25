from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agentize-bridge")
except PackageNotFoundError:  # 未安装、直接从源码目录运行时
    __version__ = "0+unknown"
