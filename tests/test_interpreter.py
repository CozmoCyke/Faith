# ruff: noqa: E402, I001
"""Phase 1 interpreter tests."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import BoolValue, Interpreter, IntValue, Stack, UnknownWord
from faifth.errors import StackUnderflow, TypeMismatch
from faifth.interpreter import execute


def _stack_as_ints(result) -> list[int]:
    return [value.value for value in result.stack]


def test_demo_program_produces_expected_stack_and_trace() -> None:
    result = execute("2 3 + dup *")
    assert result.status == "ok"
    assert _stack_as_ints(result) == [25]
    assert result.steps == 5
    assert [entry.stack_after.to_dict()["items"] for entry in result.trace] == [
        [{"type": "int", "value": 2}],
        [{"type": "int", "value": 2}, {"type": "int", "value": 3}],
        [{"type": "int", "value": 5}],
        [{"type": "int", "value": 5}, {"type": "int", "value": 5}],
        [{"type": "int", "value": 25}],
    ]


def test_successive_executions_are_independent() -> None:
    first = execute("1 2 +")
    second = execute("4")
    assert _stack_as_ints(first) == [3]
    assert _stack_as_ints(second) == [4]


def test_unknown_word_is_structured_and_stops_execution() -> None:
    result = execute("1 unknown-word 2")
    assert result.status == "error"
    assert isinstance(result.error, UnknownWord)
    assert result.error.code == "faifth.unknown_word"
    assert result.error.context["word"] == "unknown-word"
    assert _stack_as_ints(result) == [1]
    assert result.steps == 2
    assert [entry.token for entry in result.trace] == ["1", "unknown-word"]


def test_underflow_restores_stack_exactly() -> None:
    result = execute("1 +")
    assert result.status == "error"
    assert isinstance(result.error, StackUnderflow)
    assert _stack_as_ints(result) == [1]
    assert result.trace[-1].status == "error"


def test_type_mismatch_restores_stack_exactly() -> None:
    result = execute("1 true +")
    assert result.status == "error"
    assert isinstance(result.error, TypeMismatch)
    assert tuple(result.stack) == (IntValue(1), BoolValue(True))


def test_initial_stack_is_copied_not_mutated() -> None:
    initial = Stack([IntValue(1)])
    result = Interpreter().execute("dup", initial_stack=initial)
    assert _stack_as_ints(result) == [1, 1]
    assert _stack_as_ints(Interpreter().execute("4", initial_stack=initial)) == [1, 4]
    assert _stack_as_ints(
        Interpreter().execute("4", initial_stack=Stack([IntValue(1)]))
    ) == [1, 4]
    assert tuple(initial) == (IntValue(1),)


def test_depth_primitive_is_available() -> None:
    result = execute("2 3 depth")
    assert result.status == "ok"
    assert _stack_as_ints(result) == [2, 3, 2]
