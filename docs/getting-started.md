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

---

<div align="center">

[定义命令 →](commands.md)

</div>
