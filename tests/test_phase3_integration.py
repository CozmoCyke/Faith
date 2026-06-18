# ruff: noqa: E402, I001
"""Phase 3 integration tests."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import ExecutionBudget, InterpreterSession


def test_contract_and_budget_flow_together() -> None:
    session = InterpreterSession()
    session.execute(": square ( int -- int ) dup * ;")
    result = session.execute(
        "5 square",
        budget=ExecutionBudget(max_steps=10, max_stack_depth=8, max_call_depth=8),
    )

    assert result.status == "ok"
    assert [value.value for value in result.stack] == [25]
    assert result.usage.steps_used == 4


def test_contract_rejects_wrong_type_without_mutation() -> None:
    session = InterpreterSession()
    session.execute(": square ( int -- int ) dup * ;")

    result = session.execute("true square")

    assert result.status == "error"
    assert [value.value for value in result.stack] == [True]
    assert result.error.code == "faifth.contract_input_mismatch"


def test_composed_contract_words_work() -> None:
    session = InterpreterSession()
    session.execute(": square ( int -- int ) dup * ;")
    session.execute(": fourth-power ( int -- int ) square square ;")

    result = session.execute("2 fourth-power")

    assert result.status == "ok"
    assert [value.value for value in result.stack] == [16]
