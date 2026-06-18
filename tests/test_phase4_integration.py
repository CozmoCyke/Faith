# ruff: noqa: E402, I001
"""Phase 4 integration tests."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import CapabilitySet, ExecutionBudget, InterpreterSession


def _stack_as_ints(result) -> list[int]:
    return [value.value for value in result.stack]


def test_permission_transaction_and_budget_flow_together() -> None:
    session = InterpreterSession(
        capabilities=CapabilitySet.of(
            "core.compute",
            "core.stack",
            "dictionary.define",
            "transaction.manage",
            "introspection.read",
        )
    )

    session.begin_transaction()
    session.execute(": square ( int -- int ) dup * ;")
    result = session.execute(
        "5 square",
        budget=ExecutionBudget(max_steps=10, max_stack_depth=8, max_call_depth=8),
    )
    committed = session.commit_transaction()

    assert result.status == "ok"
    assert _stack_as_ints(result) == [25]
    assert result.used_capabilities.to_tuple() == ("core.compute", "core.stack")
    assert committed.status == "committed"


def test_failed_call_inside_transaction_rolls_back_state() -> None:
    session = InterpreterSession(
        capabilities=CapabilitySet.of(
            "core.compute",
            "core.stack",
            "dictionary.define",
            "transaction.manage",
        )
    )

    session.begin_transaction()
    session.execute(": square ( int -- int ) dup * ;")
    result = session.execute("true square")

    assert result.status == "error"
    assert result.transaction_rolled_back is True
    assert session.dictionary.has("square") is False
    assert session.transaction_status == "rolled_back"
