# ruff: noqa: E402, I001
"""Phase 4 transaction tests."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import (
    CapabilityDenied,
    CapabilitySet,
    InterpreterSession,
    NoActiveTransaction,
    TransactionAlreadyActive,
)


def test_transaction_commit_preserves_changes() -> None:
    session = InterpreterSession()

    record = session.begin_transaction()
    assert record.status == "active"
    session.execute(": square ( int -- int ) dup * ;")
    committed = session.commit_transaction()

    assert committed.status == "committed"
    assert session.dictionary.has("square")
    assert session.transaction_status == "committed"


def test_transaction_rollback_restores_dictionary() -> None:
    session = InterpreterSession()

    session.begin_transaction()
    session.execute(": temporary dup ;")
    rolled_back = session.rollback_transaction()

    assert rolled_back.status == "rolled_back"
    assert session.dictionary.has("temporary") is False
    assert session.transaction_status == "rolled_back"


def test_transaction_auto_rolls_back_on_error() -> None:
    session = InterpreterSession()

    session.begin_transaction()
    session.execute(": square ( int -- int ) dup * ;")
    result = session.execute("true square")

    assert result.status == "error"
    assert result.transaction_rolled_back is True
    assert session.dictionary.has("square") is False
    assert session.transaction_status == "rolled_back"


def test_nested_transactions_are_rejected() -> None:
    session = InterpreterSession()

    session.begin_transaction()

    with pytest.raises(TransactionAlreadyActive):
        session.begin_transaction()


def test_transaction_begin_requires_permission() -> None:
    session = InterpreterSession(
        capabilities=CapabilitySet.of("core.compute", "core.stack")
    )

    with pytest.raises(CapabilityDenied):
        session.begin_transaction()


def test_commit_and_rollback_require_active_transaction() -> None:
    session = InterpreterSession()

    with pytest.raises(NoActiveTransaction):
        session.commit_transaction()

    with pytest.raises(NoActiveTransaction):
        session.rollback_transaction()
