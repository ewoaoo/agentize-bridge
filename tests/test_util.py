import pytest
from agentize_bridge.util import get_instance_class_name


def module_level_func(): pass


class SimpleClass:
    def instance_method(self): pass

    @staticmethod
    def static_method(): pass

    @classmethod
    def class_method(cls): pass


class Outer:
    class Inner:
        def nested_method(self): pass


@pytest.mark.parametrize("fn", [
    module_level_func,
    SimpleClass.static_method,
    SimpleClass.class_method,  # classmethod 首参是 cls，不需要注入
    lambda: None,
])
def test_get_instance_class_name_returns_none_for_non_instance_methods(fn):
    assert get_instance_class_name(fn) is None


def test_get_instance_class_name_returns_class_name_for_instance_method():
    assert get_instance_class_name(SimpleClass.instance_method) == "SimpleClass"


def test_get_instance_class_name_handles_nested_classes():
    assert get_instance_class_name(Outer.Inner.nested_method) == "Inner"


def test_get_instance_class_name_ignores_local_functions():
    def outer():
        def inner(self): pass

        return inner

    fn = outer()
    assert get_instance_class_name(fn) is None
