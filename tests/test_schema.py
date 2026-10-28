import datetime
import inspect
import json
import uuid
from enum import Enum
from typing import Annotated, Any, Literal

import pytest
from pydantic import BaseModel, Field, ValidationError
from pydantic.errors import PydanticUserError

from agentize_bridge.schema import _clean, build_args_model, input_schema


# -------------------- 辅助 --------------------

def make_fn(annotation, default=inspect.Parameter.empty):
    """造一个只有 value 参数、注解为 annotation 的函数，便于参数化类型。"""

    def fn(value):
        pass

    fn.__annotations__ = {"value": annotation}
    if default is not inspect.Parameter.empty:
        fn.__defaults__ = (default,)
    return fn


def schema_of(annotation, default=inspect.Parameter.empty):
    return input_schema(build_args_model(make_fn(annotation, default)))


def value_schema(annotation, default=inspect.Parameter.empty):
    return schema_of(annotation, default)["properties"]["value"]


def resolve(schema, node):
    """解析 #/$defs/X 引用（本规范不内联，嵌套类型以 $ref 出现）。"""
    ref = node.get("$ref")
    if ref is None:
        return node
    assert ref.startswith("#/$defs/")
    return schema["$defs"][ref.removeprefix("#/$defs/")]


class Color(Enum):
    RED = "red"
    GREEN = "green"


class Point(BaseModel):
    x: int
    y: int


# -------------------- 基础类型 --------------------

@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        (str, {"type": "string"}),
        (int, {"type": "integer"}),
        (float, {"type": "number"}),
        (bool, {"type": "boolean"}),
        (None, {"type": "null"}),
        (Any, {}),
    ]
)
def test_basic_types(annotation, expected):
    assert value_schema(annotation) == expected


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        (Literal["red", "green"], {"enum": ["red", "green"], "type": "string"}),
        (Literal[1, 2, 3], {"enum": [1, 2, 3], "type": "integer"}),
    ]
)
def test_literal(annotation, expected):
    assert value_schema(annotation) == expected


def test_single_value_literal_uses_const():
    # 待本地确认：Pydantic 对单值 Literal 输出 const（合法的 2020-12 写法）
    assert value_schema(Literal["x"]) == {"const": "x", "type": "string"}


def test_optional():
    assert value_schema(int | None) == {"anyOf": [{"type": "integer"}, {"type": "null"}]}


def test_union():
    assert value_schema(str | int) == {"anyOf": [{"type": "string"}, {"type": "integer"}]}


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        (list[int], {"type": "array", "items": {"type": "integer"}}),
        (list[str], {"type": "array", "items": {"type": "string"}}),
        (tuple[float, ...], {"type": "array", "items": {"type": "number"}}),
        (set[bool], {"type": "array", "items": {"type": "boolean"}, "uniqueItems": True}),
    ]
)
def test_array(annotation, expected):
    assert value_schema(annotation) == expected


def test_bare_list_and_dict_only_assert_type():
    # 裸 list/dict 的细节（是否带 items: {} / additionalProperties）待本地确认，这里只锁定 type。
    # 如果发现 items: {} 之类的冗余，在 schema._clean 里加一行去掉即可。
    assert value_schema(list)["type"] == "array"
    assert value_schema(dict)["type"] == "object"
    assert value_schema(dict[str, Any])["type"] == "object"


def test_dict_with_value_type():
    assert value_schema(dict[str, int]) == {
        "type": "object",
        "additionalProperties": {"type": "integer"},
    }


# -------------------- 嵌套 / 复合类型（以 $defs + $ref 出现） --------------------

def test_enum_is_referenced_from_defs():
    schema = schema_of(Color)

    assert resolve(schema, schema["properties"]["value"]) == {"enum": ["red", "green"], "type": "string"}


def test_enum_default_is_serialized_as_value():
    assert value_schema(Color, Color.RED)["default"] == "red"


def test_pydantic_model_parameter():
    schema = schema_of(Point)

    # 嵌套模型默认不封闭（extra=ignore）；需要拒绝多余字段时在模型上写 ConfigDict(extra="forbid")
    assert resolve(schema, schema["properties"]["value"]) == {
        "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
        "required": ["x", "y"],
        "type": "object",
    }


def test_datetime_and_uuid_use_format():
    assert value_schema(datetime.datetime) == {"type": "string", "format": "date-time"}
    assert value_schema(uuid.UUID) == {"type": "string", "format": "uuid"}


def test_unknown_type_is_rejected():
    class CustomType:
        pass

    with pytest.raises(PydanticUserError):
        build_args_model(make_fn(CustomType))


# -------------------- 输出形态：精简、统一 --------------------

def test_no_required_key_when_nothing_is_required():
    def process(count: int = 1):
        pass

    assert "required" not in input_schema(build_args_model(process))


def test_schema_contains_no_titles():
    def process(name: str, tags: list[str] | None = None, mode: Literal["a", "b"] = "a", color: Color = Color.RED):
        pass

    schema = input_schema(build_args_model(process))

    assert '"title"' not in json.dumps(schema)


def test_parameter_named_like_a_keyword_is_kept():
    def process(title: str, default: int = 1):
        pass

    schema = input_schema(build_args_model(process))

    assert schema["properties"] == {
        "title": {"type": "string"},
        "default": {"type": "integer", "default": 1},
    }


def test_annotated_field_description_and_constraints():
    def process(count: Annotated[int, Field(ge=1, description="次数")] = 3):
        pass

    prop = input_schema(build_args_model(process))["properties"]["count"]

    assert prop["description"] == "次数"
    assert prop["minimum"] == 1
    assert prop["default"] == 3


def test_root_is_closed():
    assert schema_of(int)["additionalProperties"] is False


# -------------------- 参数校验（schema 与校验同源） --------------------

def test_model_forbids_extra_arguments():
    model = build_args_model(make_fn(int))

    with pytest.raises(ValidationError):
        model.model_validate({"value": 1, "other": 2})


def test_model_requires_arguments():
    model = build_args_model(make_fn(int))

    with pytest.raises(ValidationError):
        model.model_validate({})


def test_model_rejects_incompatible_values():
    model = build_args_model(make_fn(int))

    with pytest.raises(ValidationError):
        model.model_validate({"value": "abc"})


def test_model_coerces_compatible_values():
    # 有意保留的宽松：Pydantic 默认 lax 模式，"3" 会被接受为 3，而 schema 写的是 integer
    model = build_args_model(make_fn(int))

    assert model.model_validate({"value": "3"}).value == 3


def test_model_keeps_nested_model_instances():
    model = build_args_model(make_fn(Point))

    assert isinstance(model.model_validate({"value": {"x": 1, "y": 2}}).value, Point)


@pytest.mark.parametrize("payload", [{"a": 1}, {"a": 1, "b": 5}, {}, {"a": "x"}, {"a": 1, "z": 0}])
def test_schema_and_model_agree(payload):
    jsonschema = pytest.importorskip("jsonschema")

    def add(a: int, b: int = 2):
        pass

    model = build_args_model(add)
    schema = input_schema(model)
    jsonschema.Draft202012Validator.check_schema(schema)
    schema_ok = jsonschema.Draft202012Validator(schema).is_valid(payload)
    try:
        model.model_validate(payload)
        model_ok = True
    except ValidationError:
        model_ok = False

    assert schema_ok == model_ok


# -------------------- _clean（纯函数） --------------------

def test_clean_removes_titles_but_keeps_parameter_names_and_data():
    raw = {
        "$defs": {"Color": {"enum": ["red"], "title": "Color", "type": "string"}},
        "additionalProperties": False,
        "title": "CommandArguments",
        "type": "object",
        "properties": {
            "title": {"title": "Title", "type": "string"},
            "default": {"title": "Default", "type": "integer", "default": 1},
            "cfg": {"title": "Cfg", "type": "object", "default": {"title": "keep", "items": {}}},
            "c": {"$ref": "#/$defs/Color", "default": "red"},
        },
        "required": ["title"],
    }

    out = _clean(raw)

    assert out["properties"]["title"] == {"type": "string"}
    assert out["properties"]["default"] == {"type": "integer", "default": 1}
    assert out["properties"]["cfg"]["default"] == {"title": "keep", "items": {}}
    assert out["$defs"]["Color"] == {"enum": ["red"], "type": "string"}
    assert "title" not in out
    assert raw["title"] == "CommandArguments"  # 不修改入参
