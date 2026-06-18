# ruff: noqa: E402, I001
"""Phase 0 value tests."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth.errors import InvalidValue
from faifth.values import BoolValue, IntValue, StrValue, SymbolValue, ensure_value


def test_int_value_creation_and_equality() -> None:
    assert IntValue(7) == IntValue(7)
    assert IntValue(7).to_dict() == {"type": "int", "value": 7}


def test_bool_value_creation_and_distinction_from_int() -> None:
    assert BoolValue(True) == BoolValue(True)
    assert BoolValue(True) != IntValue(1)
    assert BoolValue(True).to_dict() == {"type": "bool", "value": True}


def test_str_value_creation_and_repr_is_deterministic() -> None:
    value = StrValue("hello")
    assert repr(value) == "StrValue(value='hello')"


def test_symbol_value_creation_and_serialization() -> None:
    value = SymbolValue("core.compute")
    assert value.name == "core.compute"
    assert value.to_dict() == {"type": "symbol", "name": "core.compute"}


def test_value_objects_are_immutable() -> None:
    value = IntValue(3)
    with pytest.raises(AttributeError):
        value.value = 4  # type: ignore[misc]


def test_invalid_value_rejected_for_bool_from_int() -> None:
    with pytest.raises(InvalidValue):
        BoolValue(1)  # type: ignore[arg-type]


def test_invalid_value_rejected_for_int_from_bool() -> None:
    with pytest.raises(InvalidValue):
        IntValue(True)  # type: ignore[arg-type]


def test_invalid_value_rejected_for_symbol_whitespace() -> None:
    with pytest.raises(InvalidValue):
        SymbolValue("bad symbol")


def test_ensure_value_rejects_native_python_values() -> None:
    with pytest.raises(InvalidValue):
        ensure_value(12)
