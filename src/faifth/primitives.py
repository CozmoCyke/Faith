from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from types import MappingProxyType
from typing import Any

from .errors import TypeMismatch
from .stack import Stack
from .values import BoolValue, IntValue, Value


@dataclass(frozen=True, slots=True)
class Primitive:
    name: str
    execute: Callable[[Stack], None]
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description}


def _expect_int(value: Value, *, operation: str) -> IntValue:
    if type(value) is not IntValue:
        raise TypeMismatch(
            f"{operation} requires integer operands",
            context={"operation": operation, "received": type(value).__name__},
        )
    return value


def _atomic(execute: Callable[[Stack], None]) -> Callable[[Stack], None]:
    @wraps(execute)
    def wrapped(stack: Stack) -> None:
        snapshot = stack.snapshot()
        try:
            execute(stack)
        except Exception:
            stack.restore(snapshot)
            raise

    return wrapped


def _prim_add(stack: Stack) -> None:
    right = _expect_int(stack.pop(), operation="+")
    left = _expect_int(stack.pop(), operation="+")
    stack.push(IntValue(left.value + right.value))


def _prim_sub(stack: Stack) -> None:
    right = _expect_int(stack.pop(), operation="-")
    left = _expect_int(stack.pop(), operation="-")
    stack.push(IntValue(left.value - right.value))


def _prim_mul(stack: Stack) -> None:
    right = _expect_int(stack.pop(), operation="*")
    left = _expect_int(stack.pop(), operation="*")
    stack.push(IntValue(left.value * right.value))


def _prim_dup(stack: Stack) -> None:
    value = stack.peek()
    stack.push(value)


def _prim_drop(stack: Stack) -> None:
    stack.pop()


def _prim_swap(stack: Stack) -> None:
    right = stack.pop()
    left = stack.pop()
    stack.push(right)
    stack.push(left)


def _prim_over(stack: Stack) -> None:
    right = stack.pop()
    left = stack.pop()
    stack.push(left)
    stack.push(right)
    stack.push(left)


def _prim_equal(stack: Stack) -> None:
    right = stack.pop()
    left = stack.pop()
    stack.push(BoolValue(left == right))


def _prim_depth(stack: Stack) -> None:
    stack.push(IntValue(stack.depth()))


DEFAULT_PRIMITIVES: tuple[Primitive, ...] = (
    Primitive(name="+", execute=_atomic(_prim_add), description="Add two integers"),
    Primitive(
        name="-", execute=_atomic(_prim_sub), description="Subtract two integers"
    ),
    Primitive(
        name="*", execute=_atomic(_prim_mul), description="Multiply two integers"
    ),
    Primitive(
        name="dup", execute=_atomic(_prim_dup), description="Duplicate top item"
    ),
    Primitive(name="drop", execute=_atomic(_prim_drop), description="Drop top item"),
    Primitive(name="swap", execute=_atomic(_prim_swap), description="Swap top two"),
    Primitive(name="over", execute=_atomic(_prim_over), description="Copy second"),
    Primitive(name="=", execute=_atomic(_prim_equal), description="Compare values"),
    Primitive(name="depth", execute=_atomic(_prim_depth), description="Push depth"),
)

DEFAULT_PRIMITIVE_MAP = MappingProxyType(
    {primitive.name: primitive for primitive in DEFAULT_PRIMITIVES}
)


def get_primitive(name: str) -> Primitive | None:
    return DEFAULT_PRIMITIVE_MAP.get(name)


__all__ = ["Primitive", "DEFAULT_PRIMITIVES", "DEFAULT_PRIMITIVE_MAP", "get_primitive"]
