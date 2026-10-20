import inspect
from enum import Enum
from typing import Any, Union, Literal, get_origin, get_args, Annotated
from types import UnionType


def type_schema(annotation: Any) -> dict[str, Any]:
    """ 将常见的 Python 类型转换为 JSON Schema。"""
    if annotation is inspect.Signature.empty or annotation is Any:
        return {}

    if annotation is None or annotation is type(None):
        return {"type": "null"}
    if annotation is str:
        return {"type": "string"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}

    if annotation in (list, tuple, set, frozenset):
        return {"type": "array", "items": {}}
    if annotation is dict:
        return {"type": "object", "additionalProperties": {}}

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is Literal:
        values = list(args)
        schema: dict[str, Any] = {"enum": values}
        if values:
            first = values[0]
            if isinstance(first, bool):
                schema["type"] = "boolean"
            elif isinstance(first, int):
                schema["type"] = "integer"
            elif isinstance(first, float):
                schema["type"] = "number"
            elif isinstance(first, str):
                schema["type"] = "string"
        return schema

    if origin in (Union, UnionType):
        variants = [type_schema(arg) for arg in args]
        return {"anyOf": variants}
    if annotation in (list, tuple, set, frozenset):
        return {"type": "array", "items": {}}
    if origin in (list, tuple, set, frozenset):
        item_type = args[0] if args else Any
        return {"type": "array", "items": type_schema(item_type)}
    if annotation is dict:
        return {"type": "object", "additionalProperties": {}}
    if origin is dict:
        value_type = args[1] if len(args) > 1 else Any
        return {"type": "object", "additionalProperties": type_schema(value_type)}
    if inspect.isclass(annotation) and issubclass(annotation, Enum):
        values = [member.value for member in annotation]
        return {"enum": values}
    # 未知的注解保持不受约束。
    return {}


def schema_type(schema: dict[str, Any]) -> Any:
    enum = schema.get("enum")
    if isinstance(enum, list):
        return Literal.__getitem__(tuple(enum))

    json_type = schema.get("type")

    if json_type == "array":
        item_type = schema_type(schema.get("items", {}))
        return list.__class_getitem__(item_type)

    type_map: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "object": dict
    }

    return type_map.get(json_type, Any) if isinstance(json_type, str) else Any
