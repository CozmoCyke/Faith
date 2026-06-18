from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, TypeGuard

from .errors import InvalidValue

_SYMBOL_RE = re.compile(r"^[^\s]+$")


@dataclass(frozen=True, slots=True)
class IntValue:
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int:
            raise InvalidValue(
                "IntValue requires a plain int",
                context={"field": "value", "received": type(self.value).__name__},
            )

    def to_dict(self) -> dict[str, Any]:
        return {"type": "int", "value": self.value}


@dataclass(frozen=True, slots=True)
class BoolValue:
    value: bool

    def __post_init__(self) -> None:
        if type(self.value) is not bool:
            raise InvalidValue(
                "BoolValue requires a plain bool",
                context={"field": "value", "received": type(self.value).__name__},
            )

    def to_dict(self) -> dict[str, Any]:
        return {"type": "bool", "value": self.value}


@dataclass(frozen=True, slots=True)
class StrValue:
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise InvalidValue(
                "StrValue requires a plain str",
                context={"field": "value", "received": type(self.value).__name__},
            )

    def to_dict(self) -> dict[str, Any]:
        return {"type": "str", "value": self.value}


@dataclass(frozen=True, slots=True)
class SymbolValue:
    name: str

    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name or not _SYMBOL_RE.fullmatch(
            self.name
        ):
            raise InvalidValue(
                "SymbolValue requires a non-empty string without whitespace",
                context={"field": "name", "received": self.name},
            )

    def to_dict(self) -> dict[str, Any]:
        return {"type": "symbol", "name": self.name}


Value = IntValue | BoolValue | StrValue | SymbolValue


def is_value(value: object) -> TypeGuard[Value]:
    return isinstance(value, IntValue | BoolValue | StrValue | SymbolValue)


def ensure_value(value: object) -> Value:
    if not is_value(value):
        raise InvalidValue(
            "Expected a Phase 0 Faifth value",
            context={"received": type(value).__name__},
        )
    return value


__all__ = [
    "IntValue",
    "BoolValue",
    "StrValue",
    "SymbolValue",
    "Value",
    "is_value",
    "ensure_value",
]
