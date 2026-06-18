# ruff: noqa: E402, I001
"""Phase 1 primitive registry tests."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth.errors import TypeMismatch
from faifth.primitives import DEFAULT_PRIMITIVE_MAP, DEFAULT_PRIMITIVES, get_primitive
from faifth.stack import Stack
from faifth.values import BoolValue, IntValue


def test_registry_is_fixed_and_inspectable() -> None:
    assert {primitive.name for primitive in DEFAULT_PRIMITIVES} == {
        "+",
        "-",
        "*",
        "dup",
        "drop",
        "swap",
        "over",
        "=",
        "depth",
    }
    assert get_primitive("+") is not None
    assert DEFAULT_PRIMITIVE_MAP["+"] is get_primitive("+")


def test_add_sub_mul_work_on_stack() -> None:
    add = get_primitive("+")
    sub = get_primitive("-")
    mul = get_primitive("*")
    assert add is not None and sub is not None and mul is not None

    stack = Stack([IntValue(2), IntValue(3)])
    add.execute(stack)
    assert stack.pop() == IntValue(5)

    stack = Stack([IntValue(7), IntValue(2)])
    sub.execute(stack)
    assert stack.pop() == IntValue(5)

    stack = Stack([IntValue(4), IntValue(5)])
    mul.execute(stack)
    assert stack.pop() == IntValue(20)


def test_stack_primitives_work() -> None:
    stack = Stack([IntValue(5)])
    get_primitive("dup").execute(stack)  # type: ignore[union-attr]
    assert tuple(stack) == (IntValue(5), IntValue(5))

    stack = Stack([IntValue(5)])
    get_primitive("drop").execute(stack)  # type: ignore[union-attr]
    assert stack.depth() == 0

    stack = Stack([IntValue(1), IntValue(2)])
    get_primitive("swap").execute(stack)  # type: ignore[union-attr]
    assert tuple(stack) == (IntValue(2), IntValue(1))

    stack = Stack([IntValue(1), IntValue(2)])
    get_primitive("over").execute(stack)  # type: ignore[union-attr]
    assert tuple(stack) == (IntValue(1), IntValue(2), IntValue(1))


def test_equal_and_depth_primitives_work() -> None:
    stack = Stack([IntValue(2), IntValue(2)])
    get_primitive("=").execute(stack)  # type: ignore[union-attr]
    assert tuple(stack) == (BoolValue(True),)

    stack = Stack([IntValue(7), IntValue(8)])
    get_primitive("depth").execute(stack)  # type: ignore[union-attr]
    assert tuple(stack) == (IntValue(7), IntValue(8), IntValue(2))


def test_add_rejects_bool_operands() -> None:
    stack = Stack([IntValue(1), BoolValue(True)])
    with pytest.raises(TypeMismatch):
        get_primitive("+").execute(stack)  # type: ignore[union-attr]