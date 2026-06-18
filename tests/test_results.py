# ruff: noqa: E402, I001
"""Phase 0 result tests."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth.errors import StackUnderflow
from faifth.results import ExecutionResult
from faifth.values import IntValue


def test_success_result_with_value_serializes_cleanly() -> None:
    result = ExecutionResult.success(IntValue(25), metadata={"steps": 4})
    assert result.status == "ok"
    assert result.error is None
    assert result.value == IntValue(25)
    assert result.to_dict() == {
        "status": "ok",
        "value": {"type": "int", "value": 25},
        "error": None,
        "metadata": {"steps": 4},
    }


def test_failure_result_with_error_serializes_cleanly() -> None:
    result = ExecutionResult.failure(StackUnderflow(), metadata={"trace_id": "abc"})
    assert result.status == "error"
    assert result.value is None
    assert result.error == StackUnderflow()
    assert result.to_dict() == {
        "status": "error",
        "value": None,
        "error": {
            "type": "StackUnderflow",
            "code": "faifth.stack_underflow",
            "message": "Stack underflow",
            "metadata": {},
            "context": {},
        },
        "metadata": {"trace_id": "abc"},
    }


def test_result_metadata_is_isolated_from_input_mutation() -> None:
    metadata = {"x": 1}
    result = ExecutionResult.success(metadata=metadata)
    metadata["x"] = 2
    assert result.metadata["x"] == 1


def test_success_cannot_contain_error() -> None:
    with pytest.raises(ValueError):
        ExecutionResult(status="ok", error=StackUnderflow())


def test_error_result_must_contain_error() -> None:
    with pytest.raises(ValueError):
        ExecutionResult(status="error")


def test_error_result_cannot_contain_value() -> None:
    with pytest.raises(ValueError):
        ExecutionResult(status="error", value=IntValue(1), error=StackUnderflow())
