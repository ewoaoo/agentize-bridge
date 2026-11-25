<sub>[文档](README.md) / HTTP API</sub>

# HTTP API

> 所有调用方式共用的基础接口，默认监听 `127.0.0.1:8765`。

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查，返回 `{"status": "ok"}` |
| `GET` | `/commands` | 列出所有命令 |
| `POST` | `/command/{name}` | 调用命令 |

### `GET /commands`

```json
[
  {
    "name": "add",
    "description": "把两个数字相加。",
    "thread": "worker",
    "input_schema": { "type": "object", "properties": { "...": {} } }
  }
]
```

CLI 的 `list` 与 MCP 的工具列表都来自这个接口。

### `POST /command/{name}`

请求体必须是 JSON 对象，命令无参数时传 `{}`。可通过查询参数覆盖超时：

```bash
curl -X POST 'http://127.0.0.1:8765/command/add?timeout=10' \
  -H 'Content-Type: application/json' -d '{"a": 2, "b": 3}'
```

成功时**直接返回命令的返回值**，没有额外包装；出错时返回：

```json
{ "detail": "参数无效: b: Input should be a valid integer" }
```

## 状态码

| 状态码 | 含义 | 常见原因 |
| --- | --- | --- |
| `400` | `Host` 不被允许 | 使用了未授权的主机名访问 |
| `403` | `Origin` 不被允许 | 浏览器页面发起的跨站请求 |
| `404` | 命令不存在 | 命令名拼错，或尚未注册 |
| `422` | 参数未通过校验 | 缺少、多余或类型不符，命令未执行 |
| `500` | 命令执行失败 | 函数内抛出异常；实例方法找不到实例 |
| `503` | 暂时无法受理 | 主线程队列已满，或服务已关闭 |
| `504` | 等待超时 | 见[线程模型](threading.md#队列超时与取消) |

---

<div align="center">

[← 实例方法](instance-methods.md) · [CLI →](cli.md)

</div>
