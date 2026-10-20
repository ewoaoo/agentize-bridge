# agentize-bridge

> Expose commands from an existing Python application over HTTP, CLI, and MCP.

`agentize-bridge` 把已有 Python 应用内部的函数注册成“命令”，再通过一条共享的 HTTP 服务暴露出去。CLI 和 MCP 适配器都是这条 HTTP 服务的客户端，因此只需要维护一套命令定义。

支持有主线程约束的应用：桌面 GUI、游戏循环，以及那些状态只能在主线程里安全读写的程序。

## 特性

- 一个装饰器注册命令，自动生成常见类型的 JSON Schema
- 三种调用方式：HTTP、CLI、MCP（stdio）
- `worker` 命令在线程池执行，`main` 命令回到宿主主线程执行
- 提供健康检查和命令列表端点
- 命令列表可被 MCP 适配器直接转换为工具

## 从源码使用

本项目目前不通过 PyPI 分发，直接从源码使用即可：

```bash
git clone <repository-url>
cd agentize-bridge
uv sync
```

需要构建 wheel 时：

```bash
uv build
```

构建产物位于 `dist/` 目录。完整示例见 [`examples/app.py`](examples/app.py)。

要求 Python 3.11 及以上。

## 快速开始

创建 `app.py`：

```python
import time

from agentize_bridge import AgentizeServer

server = AgentizeServer("My App")


@server.command(thread="worker")
def add(a: int, b: int) -> int:
    """把两个数字相加。"""
    return a + b


@server.command(thread="main")
def get_state() -> dict:
    """读取只能在主线程访问的应用状态。"""
    return {"ready": True}


if __name__ == "__main__":
    server.start_http(host="127.0.0.1", port=8765)
    try:
        while True:
            server.run_pending()
            time.sleep(0.01)
    except KeyboardInterrupt:
        server.close()
```

运行：

```bash
python app.py
```

调用：

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/commands
curl -X POST http://127.0.0.1:8765/command/add \
  -H 'Content-Type: application/json' \
  -d '{"a": 2, "b": 3}'
```

## HTTP API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康检查，返回 `{"status": "ok"}` |
| GET | `/commands` | 列出已注册命令及其输入 schema |
| POST | `/command/{name}` | 调用命令，请求体是 JSON 对象 |

`POST /command/{name}` 支持 `?timeout=秒数` 覆盖本次调用的等待时间。

错误响应沿用 FastAPI 的 `{"detail": ...}` 格式：

- `404`：命令不存在
- `422`：参数缺失、多余或无法绑定
- `500`：命令执行失败
- `503`：主线程命令队列已满
- `504`：等待超时

> 超时只会让调用方收到 504，不会中止已经在执行的命令。

## CLI

```bash
agentize-bridge list
agentize-bridge call add --args '{"a": 2, "b": 3}'
```

默认连接 `http://127.0.0.1:8765`，可以用 `--url` 或环境变量 `AGENTIZE_BRIDGE_URL` 修改。

## MCP

`agentize-bridge-mcp` 通过 stdio 运行，并连接到已经启动的 HTTP 服务。

Claude Desktop 配置示例：

```json
{
  "mcpServers": {
    "agentize-bridge": {
      "command": "agentize-bridge-mcp",
      "args": ["--url", "http://127.0.0.1:8765"]
    }
  }
}
```

MCP 适配器在启动时读取一次 `/commands`，命令列表是启动时的快照；服务端新增命令后需要重启 MCP 进程。

## 线程模型

这是使用本项目时最需要注意的部分。

### `thread="worker"`（默认）

命令在后台线程池执行，适合不依赖宿主主线程的逻辑。异步函数必须使用这种模式。

### `thread="main"`

命令不会直接执行，而是进入队列，等待宿主程序在自己的主循环里调用：

```python
while True:
    server.run_pending()
    time.sleep(0.01)
```

`run_pending()` 必须在拥有应用状态的线程上调用。如果宿主不调用它，`main` 命令会一直等待，直到调用方超时。对 GUI 应用来说，通常把 `run_pending()` 放在定时器或帧循环里。

## 安全

当前版本**没有身份验证**。服务默认只绑定 `127.0.0.1`，请保持这个默认值，不要把端口暴露到不可信网络。任何能访问这个端口的人都可以调用你注册的命令。

## 限制

- 没有鉴权、TLS、限流
- 主线程命令队列有容量上限，队列满时返回 503
- 超时不会中止已经开始的命令
- MCP 工具列表是启动时的快照
- 没有流式输出、进度通知或长任务 job id
- `close(wait=True)` 会等待正在执行的 worker 命令结束
- JSON Schema 目前覆盖常见标量、列表、字典、枚举和 `Literal`，更复杂的类型暂不保证

## 开发

```bash
uv sync --group test
uv run pytest
```

## License

MIT
