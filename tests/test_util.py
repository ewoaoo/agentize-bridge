import inspect
from enum import Enum
from typing import Any, Literal

import pytest

from agentize_bridge.utils import schema_type, type_schema


# ==================== type_schema ====================

@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        (str, {"type": "string"}),
        (int, {"type": "integer"}),
        (float, {"type": "number"}),
        (bool, {"type": "boolean"}),
        (None, {"type": "null"}),
        (type(None), {"type": "null"}),
        (Any, {}),
        (inspect.Signature.empty, {}),
    ]
)
def test_type_schema_basic_types(annotation, expected):
    assert type_schema(annotation) == expected


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        (Literal["red", "green"], {
            "enum": ["red", "green"],
            "type": "string",
        }),
        (Literal[1, 2, 3], {
            "enum": [1, 2, 3],
            "type": "integer",
        }),
        (Literal[1.0, 2.0], {
            "enum": [1.0, 2.0],
            "type": "number",
        }),
        (Literal[True, False], {
            "enum": [True, False],
            "type": "boolean",
        }),
    ]
)
def test_type_schema_literal(annotation, expected):
    assert type_schema(annotation) == expected


def test_type_schema_optional():
    assert type_schema(int | None) == {
        "anyOf": [
            {"type": "integer"},
            {"type": "null"},
        ]
    }


def test_type_schema_union():
    assert type_schema(str | int) == {
        "anyOf": [
            {"type": "string"},
            {"type": "integer"},
        ]
    }


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        (list[int], {
            "type": "array",
            "items": {"type": "integer"},
        }),
        (list[str], {
            "type": "array",
            "items": {"type": "string"},
        }),
        (tuple[float, ...], {
            "type": "array",
            "items": {"type": "number"},
        }),
        (set[bool], {
            "type": "array",
            "items": {"type": "boolean"},
        }),
        (list, {
            "type": "array",
            "items": {},
        }),
    ]
)
def test_type_schema_array(annotation, expected):
    assert type_schema(annotation) == expected


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        (dict[str, int], {
            "type": "object",
            "additionalProperties": {"type": "integer"},
        }),
        (dict[str, Any], {
            "type": "object",
            "additionalProperties": {},
        }),
        (dict, {
            "type": "object",
            "additionalProperties": {},
        }),
    ]
)
def test_type_schema_dict(annotation, expected):
    assert type_schema(annotation) == expected


def test_type_schema_enum():
    class Color(Enum):
        RED = "red"
        GREEN = "green"

    assert type_schema(Color) == {
        "enum": ["red", "green"],
    }


def test_type_schema_unknown_type():
    class CustomType:
        pass

    assert type_schema(CustomType) == {}


# ==================== schema_type ====================

@pytest.mark.parametrize(
    ("schema", "expected"),
    [
        ({"type": "string"}, str),
        ({"type": "integer"}, int),
        ({"type": "number"}, float),
        ({"type": "boolean"}, bool),
        ({"type": "object"}, dict),
        ({}, Any),
        ({"type": "null"}, Any),
        ({"type": "unknown"}, Any),
    ]
)
def test_schema_type_basic_types(schema, expected):
    assert schema_type(schema) is expected


@pytest.mark.parametrize(
    ("schema", "expected"),
    [
        ({"enum": ["red", "green"]}, Literal["red", "green"]),
        ({"enum": [1, 2, 3]}, Literal[1, 2, 3]),
        ({"enum": [True, False]}, Literal[True, False]),
        ({"enum": [None]}, Literal[None]),
    ],
)
def test_schema_type_enum(schema, expected):
    assert schema_type(schema) == expected


def test_schema_type_empty_enum():
    result = schema_type({"enum": []})

    assert result == Literal.__getitem__(())


@pytest.mark.parametrize(
    ("schema", "expected"),
    [
        ({"type": "array", "items": {"type": "integer"}}, list[int]),
        ({"type": "array", "items": {"type": "string"}}, list[str]),
        ({"type": "array", "items": {"type": "array", "items": {"type": "integer"}}, }, list[list[int]]),
        ({"type": "array"}, list[Any]),
    ]
)
def test_schema_type_array(schema, expected):
    assert schema_type(schema) == expected


def test_schema_type_enum_takes_precedence_over_type():
    schema = {
        "type": "string",
        "enum": ["red", "green"],
    }

    assert schema_type(schema) == Literal["red", "green"]


def test_schema_type_any_of():
    schema = {
        "anyOf": [
            {"type": "integer"},
            {"type": "null"},
        ]
    }

    # 当前 schema_type 不处理 anyOf。
    assert schema_type(schema) is Any


def test_schema_type_object_does_not_preserve_value_schema():
    schema = {
        "type": "object",
        "additionalProperties": {"type": "integer"},
    }

    # 当前实现只映射为 dict，不保留字典值类型。
    assert schema_type(schema) is dict


# ==================== Combined behavior ====================

@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        (str, {"type": "string"}),
        (int, {"type": "integer"}),
        (list[int], {"type": "array", "items": {"type": "integer"}}),
        (dict[str, float], {"type": "object", "additionalProperties": {"type": "number"}})
    ]
)
def test_type_schema_supported_round_trip(annotation, expected):
    assert type_schema(annotation) == expected
