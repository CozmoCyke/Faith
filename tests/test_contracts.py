# ruff: noqa: E402, I001
"""Phase 3 contract tests."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import (
    Dictionary,
    InterpreterSession,
    MalformedContract,
    StackContract,
    ValueKind,
)
from faifth.definitions import parse_definition
from faifth.tokenizer import tokenize


def test_parse_contract_annotation_on_definition() -> None:
    parsed = parse_definition(tokenize(": square ( int -- int ) dup * ;"), 0)

    assert parsed.contract == StackContract(
        inputs=(ValueKind.INT,),
        outputs=(ValueKind.INT,),
    )


def test_parse_definition_rejects_malformed_contract() -> None:
    with pytest.raises(MalformedContract):
        parse_definition(tokenize(": bad ( int int ) dup * ;"), 0)


def test_dictionary_inspects_contractful_user_word() -> None:
    dictionary = Dictionary()
    word = dictionary.validate_user_word(
        "square",
        ["dup", "*"],
        contract=StackContract((ValueKind.INT,), (ValueKind.INT,)),
    )
    dictionary.define(word)

    inspected = dictionary.inspect("square")
    assert inspected["contract"] == {"inputs": ["int"], "outputs": ["int"]}


def test_rejects_contract_dependency_without_contract() -> None:
    session = InterpreterSession()
    session.execute(": old-square dup * ;")

    result = session.execute(": checked-fourth ( int -- int ) old-square old-square ;")

    assert result.status == "error"
    assert result.error.code == "faifth.unverifiable_contract"
