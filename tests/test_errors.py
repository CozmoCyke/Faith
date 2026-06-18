# ruff: noqa: E402, I001
"""Phase 0 error tests."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth.errors import (
    FaifthError,
    InvalidSnapshot,
    InvalidValue,
    StackOverflow,
    StackUnderflow,
    TypeMismatch,
)


def test_error_codes_are_stable() -> None:
    assert StackUnderflow().code == "faifth.stack_underflow"
    assert StackOverflow().code == "faifth.stack_overflow"
    assert TypeMismatch().code == "faifth.type_mismatch"
    assert InvalidValue().code == "faifth.invalid_value"
    assert InvalidSnapshot().code == "faifth.invalid_snapshot"


def test_error_messages_are_present() -> None:
    error = StackUnderflow()
    assert str(error) == "Stack underflow"


def test_error_metadata_and_context_are_serialized() -> None:
    error = FaifthError(
        "custom",
        code="faifth.custom",
        metadata={"a": 1},
        context={"b": 2},
    )
    data = error.to_dict()
    assert data == {
        "type": "FaifthError",
        "code": "faifth.custom",
        "message": "custom",
        "metadata": {"a": 1},
        "context": {"b": 2},
    }


def test_error_repr_is_deterministic() -> None:
    error = InvalidValue(metadata={"x": 1})
    assert (
        repr(error)
        == "InvalidValue(code='faifth.invalid_value', message='Invalid value', "
        "metadata={'x': 1}, context={})"
    )


def test_error_metadata_is_isolated_from_input_mutation() -> None:
    metadata = {"x": 1}
    error = InvalidSnapshot(metadata=metadata)
    metadata["x"] = 2
    assert error.metadata["x"] == 1


def test_error_equality_is_structural() -> None:
    left = StackUnderflow(metadata={"op": "pop"})
    right = StackUnderflow(metadata={"op": "pop"})
    assert left == right
    assert left != StackUnderflow(metadata={"op": "peek"})
