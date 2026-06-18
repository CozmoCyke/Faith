# ruff: noqa: E402, I001
"""Phase 0 stack tests."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth.errors import InvalidSnapshot, StackOverflow, StackUnderflow
from faifth.stack import Stack, StackSnapshot
from faifth.values import BoolValue, IntValue, StrValue


def test_empty_stack_depth_and_repr() -> None:
    stack = Stack()
    assert stack.depth() == 0
    assert repr(stack) == "Stack(items=(), max_depth=None)"


def test_push_pop_lifo_and_peek() -> None:
    stack = Stack()
    stack.push(IntValue(1))
    stack.push(StrValue("a"))
    assert stack.peek() == StrValue("a")
    assert stack.pop() == StrValue("a")
    assert stack.pop() == IntValue(1)


def test_clear_resets_stack() -> None:
    stack = Stack([IntValue(1), BoolValue(True)])
    stack.clear()
    assert stack.depth() == 0


def test_snapshot_and_restore_are_independent() -> None:
    stack = Stack([IntValue(1), BoolValue(True)])
    snapshot = stack.snapshot()
    stack.pop()
    stack.restore(snapshot)
    assert stack.depth() == 2
    assert stack.peek() == BoolValue(True)


def test_snapshot_is_immutable_copy() -> None:
    stack = Stack([IntValue(1)])
    snapshot = stack.snapshot()
    stack.push(BoolValue(True))
    assert snapshot.items == (IntValue(1),)


def test_underflow_raises_structured_error() -> None:
    stack = Stack()
    with pytest.raises(StackUnderflow):
        stack.pop()
    with pytest.raises(StackUnderflow):
        stack.peek()


def test_overflow_is_enforced_when_configured() -> None:
    stack = Stack(max_depth=1)
    stack.push(IntValue(1))
    with pytest.raises(StackOverflow):
        stack.push(BoolValue(True))


def test_restore_rejects_invalid_snapshot() -> None:
    stack = Stack()
    with pytest.raises(InvalidSnapshot):
        stack.restore("nope")  # type: ignore[arg-type]


def test_snapshot_object_rejects_invalid_payload() -> None:
    with pytest.raises(InvalidSnapshot):
        StackSnapshot(items=(IntValue(1), "bad"))  # type: ignore[arg-type]


def test_stack_equality_depends_on_items_and_limit() -> None:
    assert Stack([IntValue(1)], max_depth=2) == Stack([IntValue(1)], max_depth=2)
    assert Stack([IntValue(1)], max_depth=2) != Stack([IntValue(1)], max_depth=3)
