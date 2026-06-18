# ruff: noqa: E402, I001
"""Phase 1 tokenizer tests."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth.tokenizer import Token, tokenize


def test_empty_source_tokenizes_to_empty_tuple() -> None:
    assert tokenize("") == ()


def test_multiple_spaces_are_ignored() -> None:
    tokens = tokenize("2   3    +")
    assert [token.text for token in tokens] == ["2", "3", "+"]


def test_newlines_preserve_order() -> None:
    tokens = tokenize("2\n3   +")
    assert [token.text for token in tokens] == ["2", "3", "+"]


def test_negative_integer_and_bools_are_preserved_as_tokens() -> None:
    tokens = tokenize("-7 true false dup")
    assert [token.text for token in tokens] == ["-7", "true", "false", "dup"]


def test_token_positions_are_deterministic() -> None:
    tokens = tokenize("2\n3  +")
    assert tokens == (
        Token(text="2", index=0, offset=0, line=1, column=1),
        Token(text="3", index=1, offset=2, line=2, column=1),
        Token(text="+", index=2, offset=5, line=2, column=4),
    )