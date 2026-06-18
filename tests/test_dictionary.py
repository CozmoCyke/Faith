# ruff: noqa: E402, I001
"""Phase 2 dictionary tests."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import Dictionary, ProtectedWord, UserWord


def test_dictionary_resolves_primitives_and_starts_empty_for_users() -> None:
    dictionary = Dictionary()

    assert dictionary.has("dup")
    assert dictionary.list_user_words() == ()
    assert dictionary.resolve("dup").name == "dup"


def test_dictionary_builds_and_inspects_user_words() -> None:
    dictionary = Dictionary()

    word = dictionary.validate_user_word("square", ["dup", "*"])
    assert isinstance(word, UserWord)
    dictionary.define(word)

    inspected = dictionary.inspect("square")
    assert inspected == {
        "kind": "user",
        "name": "square",
        "body": ["dup", "*"],
        "dependencies": [],
        "primitive_dependencies": ["dup", "*"],
        "source": None,
        "definition_index": None,
        "metadata": {},
    }
    assert dictionary.list_user_words() == ("square",)


def test_dictionary_rejects_protected_names() -> None:
    dictionary = Dictionary()

    try:
        dictionary.validate_user_word("dup", ["drop"])
    except ProtectedWord as error:
        assert error.context["name"] == "dup"
    else:  # pragma: no cover - sanity guard
        raise AssertionError("expected ProtectedWord")
