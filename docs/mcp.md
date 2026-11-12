<sub>[文档](README.md) / MCP</sub>

# MCP

> 每个命令对应 AI 客户端中的一个工具。

`agentize-bridge-mcp` 通过 stdio 运行，启动时读取 `/commands`，把每个命令注册成一个 MCP 工具。参数 Schema 原样透传，校验仍由 HTTP 服务端负责。

## 配置 Claude Desktop

```json
{
  "mcpServers": {
    "my-app": {
      "command": "agentize-bridge-mcp",
      "args": ["--url", "http://127.0.0.1:8765"]
    }
  }
}
```

未将命令安装到 `PATH` 时，可改用 `uv` 启动：

```json
{
  "mcpServers": {
    "my-app": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/agentize-bridge",
               "agentize-bridge-mcp", "--url", "http://127.0.0.1:8765"]
    }
  }
}
```

## 选项

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--url` | `http://127.0.0.1:8765` | 服务地址，也可用环境变量 `AGENTIZE_BRIDGE_URL` |
| `--timeout` | `30` | 单次调用的等待上限（秒） |

## 行为

- 调用成功时，结果以 JSON 文本返回。
- 调用失败（参数校验不通过、命令报错、超时）时，**错误原因会作为工具错误返回给模型**，而不是笼统的协议错误，模型因此能根据提示修正参数后重试。

> [!IMPORTANT]
> 工具列表在进程启动时读取**一次**。服务端增删命令后，需要重启 MCP 进程（在 Claude Desktop 中即重启该应用）后才会生效。启动时若应用尚未运行，MCP 进程将连接失败。

---

<div align="center">

[← CLI](cli.md) · [安全与限制 →](security.md)

</div>
