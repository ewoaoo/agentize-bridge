<sub>[文档](README.md) / 定义命令</sub>

# 定义命令

> 通过装饰器注册命令，同时确定调用方式与参数校验规则。

## 装饰器参数

```python
@server.command(name="", description="", thread="worker", timeout=30)
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `name` | 函数名 | 命令名，只允许 ASCII 字母、数字、`_`、`.`、`-` |
| `description` | 文档字符串首行 | 展示给调用方（包括 AI）；都没有时回退为命令名 |
| `thread` | `"worker"` | 执行线程，见[线程模型](threading.md) |
| `timeout` | `30` | 等待完成的上限（秒），可被请求中的 `?timeout=` 覆盖 |

命令名重复会在注册时抛出 `ValueError`。

> [!TIP]
> `description` 将原样提供给 AI 作为工具说明，建议描述命令的作用，而非实现方式。

## 参数与校验

参数**必须有类型注解**，缺少会在注册时报错。注解同时完成两件事：调用前的校验，以及对外公布的 JSON Schema。

```python
from typing import Annotated, Literal
from pydantic import Field


@server.command(description="按类型创建若干对象")
def spawn(
    kind: Literal["cube", "sphere"],
    count: Annotated[int, Field(ge=1, le=100, description="创建数量")] = 1,
) -> list[str]:
    ...
```

上述定义对外公布的 Schema 如下（示意，字段顺序以实际输出为准）：

```json
{
  "type": "object",
  "properties": {
    "kind": { "enum": ["cube", "sphere"], "type": "string" },
    "count": { "type": "integer", "minimum": 1, "maximum": 100,
               "description": "创建数量", "default": 1 }
  },
  "required": ["kind"]
}
```

### 校验规则

| 情况 | 结果 |
| --- | --- |
| 缺少必填参数、出现多余参数、类型不符 | `422`，命令**不会执行** |
| 可转换的值，如 `"3"` | 自动转成 `3` |
| 参数有默认值 | 可省略，且写入 Schema |

### 不支持的写法

| 写法 | 原因 |
| --- | --- |
| `*args`、`**kwargs`、仅位置参数 | 无法对应 JSON 对象的键 |
| 缺少类型注解 | 需要任意类型时，显式标注 `Any` |
| `async def` + `thread="main"` | 协程只能在工作线程运行 |

## 返回值

返回值需要能序列化为 JSON，原样作为响应体。命令内抛出的异常将返回 `500`，**异常文本会包含在响应中**，见[安全与限制](security.md)。

---

<div align="center">

[← 快速开始](getting-started.md) · [线程模型 →](threading.md)

</div>
