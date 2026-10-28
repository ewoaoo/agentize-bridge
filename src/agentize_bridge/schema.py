import inspect
from typing import Callable, Any, get_type_hints

from pydantic import BaseModel, create_model, ConfigDict

_DATA_KEYS = ("default", "enum", "const", "examples")


def build_args_model(fn: Callable[..., Any]) -> type[BaseModel]:
    signature = inspect.signature(fn)
    hints = get_type_hints(fn, include_extras=True)

    fields: dict[str, Any] = {}
    for param in signature.parameters.values():
        if param.kind in (param.POSITIONAL_ONLY, param.VAR_POSITIONAL, param.VAR_KEYWORD):
            raise TypeError(f"指令参数 {param.name!r} 必须是一个具名关键字参数; 仅位置参数和 *args/**kwargs 不被支持")
        if param.name not in hints:
            raise TypeError(f"参数 {param.name!r} 缺少类型注解（需要任意类型请显式标注 Any）")
        fields[param.name] = (hints[param.name], ... if param.default is param.empty else param.default)

    return create_model("CommandArguments", __config__=ConfigDict(extra="forbid"), **fields)


def input_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = _clean(model.model_json_schema())
    if not schema.get("required"):
        schema.pop("required", None)
    return schema


def _clean(node: Any) -> Any:
    """去掉 Pydantic 自动加的 title；不碰参数名，也不碰 default/enum 里的数据。"""
    if isinstance(node, list):
        return [_clean(item) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "title" and isinstance(value, str):
            continue
        if key in _DATA_KEYS:
            out[key] = value
        elif key == "properties" and isinstance(value, dict):
            out[key] = {name: _clean(sub) for name, sub in value.items()}
        else:
            out[key] = _clean(value)
    return out
