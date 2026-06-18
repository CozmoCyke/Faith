# ruff: noqa: E402, I001
"""Phase 2 definition parser tests."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import InvalidDefinition, UnterminatedDefinition, tokenize
from faifth.definitions import parse_definition


def test_parse_definition_extracts_name_and_body() -> None:
    tokens = tokenize(": square dup * ; 5 square")
    parsed = parse_definition(tokens, 0)

    assert parsed.name == "square"
    assert [token.text for token in parsed.body_tokens] == ["dup", "*"]
    assert parsed.start_index == 0
    assert parsed.end_index == 5


def test_parse_definition_rejects_unterminated_body() -> None:
    tokens = tokenize(": square dup *")

    with pytest.raises(UnterminatedDefinition):
        parse_definition(tokens, 0)


def test_parse_definition_rejects_empty_body() -> None:
    tokens = tokenize(": square ;")

    with pytest.raises(InvalidDefinition):
        parse_definition(tokens, 0)
