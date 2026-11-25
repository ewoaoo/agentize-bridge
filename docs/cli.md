<sub>[文档](README.md) / CLI</sub>

# CLI

> 在终端中列出并调用命令。CLI 是 HTTP 服务的客户端。

## 命令

```bash
agentize-bridge list
agentize-bridge call add --args '{"a": 2, "b": 3}'
```

| 子命令 | 说明 |
| --- | --- |
| `list` | 打印所有命令及其参数 Schema |
| `call <name> --args '<JSON>'` | 调用命令；`--args` 必须是 JSON 对象，缺省为 `{}` |

结果以带缩进的 JSON 写入标准输出，中文不会被转义。

## 选项

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--url` | `http://127.0.0.1:8765` | 服务地址，也可用环境变量 `AGENTIZE_BRIDGE_URL` |
| `--timeout` | `30` | 命令的等待上限（秒） |

`--url` 与 `--timeout` 写在子命令**之前**：

```bash
agentize-bridge --url http://127.0.0.1:9000 --timeout 10 call get_state
```

## 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 成功 |
| `1` | 出错：连接失败、HTTP 错误、`--args` 不是合法的 JSON 对象。错误信息输出到标准错误 |

> [!NOTE]
> 客户端在 `--timeout` 之外额外保留约 5 秒的网络余量，因此命令超时时，将收到服务端返回的 `504`，而非本地连接超时。

---

<div align="center">

[← HTTP API](http-api.md) · [MCP →](mcp.md)

</div>
