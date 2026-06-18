# ruff: noqa: E402, I001
"""Phase 4 permission tests."""

from __future__ import annotations

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import CapabilityDenied, CapabilityEscalationDenied
from faifth import CapabilitySet, InterpreterSession


def _stack_as_ints(result) -> list[int]:
    return [value.value for value in result.stack]


def test_primitive_is_denied_without_required_capability() -> None:
    session = InterpreterSession(capabilities=CapabilitySet.of("core.stack"))

    result = session.execute("2 3 +")

    assert result.status == "error"
    assert isinstance(result.error, CapabilityDenied)
    assert result.error.code == "faifth.capability_denied"
    assert result.missing_capabilities.to_tuple() == ("core.compute",)
    assert _stack_as_ints(result) == [2, 3]


def test_execution_capabilities_cannot_escalate() -> None:
    session = InterpreterSession(capabilities=CapabilitySet.of("core.stack"))

    result = session.execute(
        "2 3 +",
        capabilities=CapabilitySet.of("core.compute", "core.stack"),
    )

    assert result.status == "error"
    assert isinstance(result.error, CapabilityEscalationDenied)
    assert result.error.code == "faifth.capability_escalation_denied"
    assert _stack_as_ints(result) == []


def test_definition_requires_dictionary_define() -> None:
    session = InterpreterSession(
        capabilities=CapabilitySet.of("core.compute", "core.stack")
    )

    result = session.execute(": square dup * ;")

    assert result.status == "error"
    assert isinstance(result.error, CapabilityDenied)
    assert result.missing_capabilities.to_tuple() == ("dictionary.define",)
    assert session.dictionary.has("square") is False


def test_user_word_inherits_transitive_capabilities() -> None:
    session = InterpreterSession()
    session.execute(": square ( int -- int ) dup * ;")
    session.execute(": fourth-power ( int -- int ) square square ;")

    inspected = session.inspect_word("fourth-power")
    assert inspected["required_capabilities"] == {
        "granted": ["core.compute", "core.stack"],
    }
