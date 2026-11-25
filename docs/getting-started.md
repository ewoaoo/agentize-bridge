<sub>[文档](README.md) / 快速开始</sub>

# 快速开始

> 快速使应用可以被 `curl` 与 AI 调用。

## 安装

```bash
git clone https://github.com/ewoaoo/agentize-bridge.git
cd agentize-bridge
uv sync            # 或：pip install -e .
```

## 最小示例

```python
import time

from agentize_bridge import AgentizeServer,command


@command()
def add(a: int, b: int = 2) -> int:
    """把两个数字相加。"""
    return a + b


@command(thread="main", timeout=5)
def get_state() -> dict:
    """读取只能在主线程访问的应用状态。"""
    return {"ready": True}


if __name__ == "__main__":
    server = AgentizeServer("My App")
    server.start_http(host="127.0.0.1", port=8765)
    try:
        while True:
            server.run_pending()   # 在主线程中执行 thread="main" 的命令
            time.sleep(0.01)
    except KeyboardInterrupt:
        server.close()
```

接入包含三步：**注册命令**、**启动 HTTP**、**在主循环中调用 `run_pending()`**。命令均为 `worker` 线程时，第三步可省略。

## 调用命令

运行 `python app.py` 后，三种方式等价：

```bash
# HTTP
curl -X POST http://127.0.0.1:8765/command/add \
  -H 'Content-Type: application/json' -d '{"a": 2, "b": 3}'

# CLI
agentize-bridge call add --args '{"a": 2, "b": 3}'

# MCP：在客户端完成配置后，以工具 add 调用
```

三者的结果均为 `5`，区别只在接入与执行方式。MCP 需先在客户端完成配置，见 [MCP](mcp.md)。

## 启动与关闭

- `start_http()` 在后台线程启动服务，最多等待 10 秒；启动失败（如端口被占用）时抛出异常。每个实例只能启动一次。
- `close()` 可重复调用。关闭时，队列中尚未执行的 `main` 命令会立刻以 `503` 失败，调用方无需等待超时。
- `AgentizeServer` 也支持 `with`，退出时自动 `close()`：

```python
with AgentizeServer("My App") as server:
    server.start_http()
    ...
```

## 访问日志

通过 `AgentizeServer` 的构造参数配置 `start_http()` 的访问日志。默认的 `log_mode="simple"` 在控制台显示 `4xx` 和 `5xx` 请求，`log_mode="full"` 显示全部访问记录。Uvicorn 的启停信息和底层诊断照常输出。

```python
with AgentizeServer("My App", log_mode="full", log_file="logs/access.log") as server:
    server.start_http()
    ...
```

`log_file` 是可选路径。设置后，两种控制台模式都会以 UTF-8 将完整访问记录追加到该文件。文件在应用启动时打开，退出时关闭。

每条访问记录包含客户端地址、请求方法、路径、状态码和耗时。命令失败时，记录还会带上可用的业务错误详情。

---

<div align="center">

[定义命令 →](commands.md)

</div>
