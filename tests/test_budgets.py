# ruff: noqa: E402, I001
"""Phase 3 budget tests."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import (
    ExecutionBudget,
    InterpreterSession,
    StackDepthBudgetExceeded,
    StepBudgetExceeded,
)


def test_step_budget_allows_exact_execution() -> None:
    session = InterpreterSession()
    result = session.execute(
        "2 3 + dup *",
        budget=ExecutionBudget(max_steps=5, max_stack_depth=32, max_call_depth=16),
    )

    assert result.status == "ok"
    assert [value.value for value in result.stack] == [25]
    assert result.usage.steps_used == 5


def test_step_budget_rejects_execution_before_final_token() -> None:
    session = InterpreterSession()
    result = session.execute(
        "2 3 + dup *",
        budget=ExecutionBudget(max_steps=4, max_stack_depth=32, max_call_depth=16),
    )

    assert result.status == "error"
    assert isinstance(result.error, StepBudgetExceeded)
    assert result.usage.limit_hit == "steps"


def test_stack_budget_rolls_back_the_token() -> None:
    session = InterpreterSession()
    result = session.execute(
        "1 dup dup",
        budget=ExecutionBudget(max_steps=10, max_stack_depth=2, max_call_depth=16),
    )

    assert result.status == "error"
    assert isinstance(result.error, StackDepthBudgetExceeded)
    assert [value.value for value in result.stack] == [1, 1]
