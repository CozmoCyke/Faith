from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .contracts import StackContract, ValueKind
from .errors import TypeMismatch
from .stack import Stack
from .values import BoolValue, IntValue, Value


@dataclass(frozen=True, slots=True)
class Primitive:
    name: str
    execute: Callable[[Stack], None]
    contract: StackContract
    behavior: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "primitive",
            "name": self.name,
            "description": self.description,
            "behavior": self.behavior,
            "contract": self.contract.to_dict(),
        }

    def simulate(self, stack: tuple[ValueKind, ...]) -> tuple[ValueKind, ...]:
        match self.behavior:
            case "add" | "sub" | "mul":
                if len(stack) < 2:
                    raise TypeMismatch(
                        f"{self.name} requires two values",
                        context={"primitive": self.name},
                    )
                if stack[-1] is not ValueKind.INT or stack[-2] is not ValueKind.INT:
                    raise TypeMismatch(
                        f"{self.name} requires integer operands",
                        context={"primitive": self.name},
                    )
                return stack[:-2] + (ValueKind.INT,)
            case "dup":
                if not stack:
                    raise TypeMismatch(
                        "dup requires one value",
                        context={"primitive": self.name},
                    )
                return stack + (stack[-1],)
            case "drop":
                if not stack:
                    raise TypeMismatch(
                        "drop requires one value",
                        context={"primitive": self.name},
                    )
                return stack[:-1]
            case "swap":
                if len(stack) < 2:
                    raise TypeMismatch(
                        "swap requires two values",
                        context={"primitive": self.name},
                    )
                return stack[:-2] + (stack[-1], stack[-2])
            case "over":
                if len(stack) < 2:
                    raise TypeMismatch(
                        "over requires two values",
                        context={"primitive": self.name},
                    )
                return stack[:-2] + (stack[-2], stack[-1], stack[-2])
            case "equal":
                if len(stack) < 2:
                    raise TypeMismatch(
                        "= requires two values",
                        context={"primitive": self.name},
                    )
                return stack[:-2] + (ValueKind.BOOL,)
            case "depth":
                return stack + (ValueKind.INT,)
            case _:
                raise TypeMismatch(
                    f"Unsupported primitive behavior: {self.behavior}",
                    context={"primitive": self.name, "behavior": self.behavior},
                )


def _expect_int(value: Value, *, operation: str) -> IntValue:
    if type(value) is not IntValue:
        raise TypeMismatch(
            f"{operation} requires integer operands",
            context={"operation": operation, "received": type(value).__name__},
        )
    return value


def _atomic(execute: Callable[[Stack], None]) -> Callable[[Stack], None]:
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
    Primitive(
        name="+",
        execute=_atomic(_prim_add),
        contract=StackContract((ValueKind.INT, ValueKind.INT), (ValueKind.INT,)),
        behavior="add",
        description="Add two integers",
    ),
    Primitive(
        name="-",
        execute=_atomic(_prim_sub),
        contract=StackContract((ValueKind.INT, ValueKind.INT), (ValueKind.INT,)),
        behavior="sub",
        description="Subtract two integers",
    ),
    Primitive(
        name="*",
        execute=_atomic(_prim_mul),
        contract=StackContract((ValueKind.INT, ValueKind.INT), (ValueKind.INT,)),
        behavior="mul",
        description="Multiply two integers",
    ),
    Primitive(
        name="dup",
        execute=_atomic(_prim_dup),
        contract=StackContract((ValueKind.ANY,), (ValueKind.ANY, ValueKind.ANY)),
        behavior="dup",
        description="Duplicate top item",
    ),
    Primitive(
        name="drop",
        execute=_atomic(_prim_drop),
        contract=StackContract((ValueKind.ANY,), ()),
        behavior="drop",
        description="Drop top item",
    ),
    Primitive(
        name="swap",
        execute=_atomic(_prim_swap),
        contract=StackContract(
            (ValueKind.ANY, ValueKind.ANY),
            (ValueKind.ANY, ValueKind.ANY),
        ),
        behavior="swap",
        description="Swap top two",
    ),
    Primitive(
        name="over",
        execute=_atomic(_prim_over),
        contract=StackContract(
            (ValueKind.ANY, ValueKind.ANY),
            (ValueKind.ANY, ValueKind.ANY, ValueKind.ANY),
        ),
        behavior="over",
        description="Copy second",
    ),
    Primitive(
        name="=",
        execute=_atomic(_prim_equal),
        contract=StackContract((ValueKind.ANY, ValueKind.ANY), (ValueKind.BOOL,)),
        behavior="equal",
        description="Compare values",
    ),
    Primitive(
        name="depth",
        execute=_atomic(_prim_depth),
        contract=StackContract((), (ValueKind.INT,)),
        behavior="depth",
        description="Push depth",
    ),
)

DEFAULT_PRIMITIVE_MAP = MappingProxyType(
    {primitive.name: primitive for primitive in DEFAULT_PRIMITIVES}
)


def get_primitive(name: str) -> Primitive | None:
    return DEFAULT_PRIMITIVE_MAP.get(name)


__all__ = ["Primitive", "DEFAULT_PRIMITIVES", "DEFAULT_PRIMITIVE_MAP", "get_primitive"]
