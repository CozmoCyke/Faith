# ruff: noqa: E402, I001
"""Phase 2 user-word execution tests."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import (
    InterpreterSession,
    ProtectedWord,
    RecursiveDefinition,
    StackUnderflow,
    UnexpectedTerminator,
    UnknownWord,
)


def _stack_as_ints(result) -> list[int]:
    return [value.value for value in result.stack]


def test_one_shot_definition_and_call() -> None:
    result = InterpreterSession().execute(": square dup * ; 5 square")

    assert result.status == "ok"
    assert _stack_as_ints(result) == [25]
    assert [entry.kind for entry in result.trace] == [
        "definition",
        "literal",
        "call",
        "primitive",
        "primitive",
        "return",
    ]


def test_multiple_definitions_in_one_source() -> None:
    result = InterpreterSession().execute(
        ": square dup * ; : fourth-power square square ; 2 fourth-power"
    )

    assert result.status == "ok"
    assert _stack_as_ints(result) == [16]


def test_session_persists_dictionary_between_calls() -> None:
    session = InterpreterSession()
    assert session.execute(": square dup * ;").status == "ok"

    result = session.execute("6 square")

    assert result.status == "ok"
    assert _stack_as_ints(result) == [36]
    assert session.dictionary.list_user_words() == ("square",)


def test_sessions_are_isolated() -> None:
    first = InterpreterSession()
    second = InterpreterSession()

    assert first.execute(": square dup * ;").status == "ok"
    result = second.execute("square")

    assert result.status == "error"
    assert isinstance(result.error, UnknownWord)


def test_broken_word_rolls_back_the_stack() -> None:
    session = InterpreterSession()
    result = session.execute(": broken drop drop ; 1 broken")

    assert result.status == "error"
    assert isinstance(result.error, StackUnderflow)
    assert _stack_as_ints(result) == [1]
    assert any(entry.kind == "call" for entry in result.trace)
    assert result.trace[-1].status == "error"


def test_invalid_definitions_are_atomic() -> None:
    session = InterpreterSession()
    result = session.execute(": bad unknown ;")

    assert result.status == "error"
    assert isinstance(result.error, UnknownWord)
    assert "bad" not in session.dictionary.list_user_words()


def test_recursive_and_protected_definitions_are_rejected() -> None:
    session = InterpreterSession()

    recursive = session.execute(": loop loop ;")
    protected = session.execute(": dup drop ;")

    assert recursive.status == "error"
    assert isinstance(recursive.error, RecursiveDefinition)
    assert protected.status == "error"
    assert isinstance(protected.error, ProtectedWord)


def test_unexpected_terminator_is_structured() -> None:
    result = InterpreterSession().execute(";")

    assert result.status == "error"
    assert isinstance(result.error, UnexpectedTerminator)
