<sub>[文档](README.md) / 实例方法</sub>

# 实例方法

> 把对象的方法直接暴露成命令。

## 用法

在类中为方法添加 `@server.command()`，并将实例放入容器：

```python
server = AgentizeServer("My App")


class Calculator:
    def __init__(self, base: int):
        self.base = base

    @server.command()
    def add_base(self, value: int) -> int:
        """在基础值上累加。"""
        return self.base + value


server.container.register("Calculator", Calculator(base=100))   # 键必须是类名
```

```bash
curl -X POST http://127.0.0.1:8765/command/add_base \
  -H 'Content-Type: application/json' -d '{"value": 5}'          # 105
```

调用时，框架根据方法所属的类名从容器中取出实例，再绑定执行。`self` 不会出现在参数 Schema 中。

类来自第三方、无法添加装饰器时，可注册**未绑定**的方法，效果相同：

```python
server.command()(Calculator.add_base)    # 不是 calculator.add_base
```

## 时机

框架不限定注册的先后，也不要求在 HTTP 启动之前完成：命令与实例都可以随时注册，只要在命令**被调用之前**，容器中已经有对应类名的实例。

这一设计使写法更灵活：装饰器可直接写在类中，实例也可在应用初始化到合适阶段后再创建。代价是框架不做事前检查，实例缺失要到调用时才会暴露（`500`），注册与调用的时序需由使用者保证。

## 规则

| 规则 | 说明 |
| --- | --- |
| 第一个参数名为 `self` | 以此识别实例方法，改用其他名字会被当作普通函数 |
| 键是类名 | 嵌套类取最内层，`Outer.Inner` 用 `"Inner"`；定义在函数内部的类不支持 |
| 一个类名一个实例 | 同名类会冲突，重复注册会抛出 `ValueError` |
| 继承的方法 | 子类继承而未重写的方法，需要在子类中显式重写后再注册 |
| `@staticmethod` / `@classmethod` | 不需要实例，直接注册 |

## 管理容器

```python
server.container.register("Calculator", obj)   # 注册，重名时抛出 ValueError
server.container.unregister("Calculator")       # 移除，不存在时忽略
server.container.resolve("Calculator")          # 取出，不存在时抛出 KeyError
```

容器本身是线程安全的。实例的生命周期由宿主程序负责。

> [!NOTE]
> 实例方法同样遵循 `thread` 设置。访问 GUI 对象时，需指定 `@server.command(thread="main")`。

---

<div align="center">

[← 线程模型](threading.md) · [HTTP API →](http-api.md)

</div>
