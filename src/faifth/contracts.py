from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .errors import InvalidContract, MalformedContract, UnknownContractType
from .tokenizer import Token


class ValueKind(StrEnum):
    INT = "int"
    BOOL = "bool"
    ANY = "any"

    @classmethod
    def parse(cls, text: str) -> ValueKind:
        try:
            return cls(text)
        except ValueError as exc:  # pragma: no cover - defensive
            raise UnknownContractType(
                f"Unknown contract type: {text}",
                context={"type": text},
            ) from exc


@dataclass(frozen=True, slots=True)
class StackContract:
    inputs: tuple[ValueKind, ...]
    outputs: tuple[ValueKind, ...]

    def __post_init__(self) -> None:
        for field_name, kinds in (("inputs", self.inputs), ("outputs", self.outputs)):
            if not isinstance(kinds, tuple):
                raise InvalidContract(
                    f"{field_name} must be a tuple",
                    context={"field": field_name, "received": type(kinds).__name__},
                )
            for kind in kinds:
                if not isinstance(kind, ValueKind):
                    raise InvalidContract(
                        f"{field_name} contains an invalid value kind",
                        context={
                            "field": field_name,
                            "received": type(kind).__name__,
                        },
                    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "inputs": [kind.value for kind in self.inputs],
            "outputs": [kind.value for kind in self.outputs],
        }

    @property
    def input_count(self) -> int:
        return len(self.inputs)

    @property
    def output_count(self) -> int:
        return len(self.outputs)


def parse_stack_contract(
    tokens: Sequence[str | Token], start_index: int
) -> tuple[StackContract, int]:
    if start_index >= len(tokens):
        raise MalformedContract(
            "Missing contract annotation",
            context={"index": start_index},
        )

    start = _coerce_text(tokens[start_index])
    if start != "(":
        raise MalformedContract(
            "Contract must start with '('",
            context={"token": start, "index": start_index},
        )

    input_kinds: list[ValueKind] = []
    output_kinds: list[ValueKind] = []
    current = input_kinds
    saw_separator = False
    index = start_index + 1

    while index < len(tokens):
        text = _coerce_text(tokens[index])
        if text == ")":
            if not saw_separator:
                raise MalformedContract(
                    "Contract must contain '--'",
                    context={"index": start_index},
                )
            return (
                StackContract(
                    inputs=tuple(input_kinds),
                    outputs=tuple(output_kinds),
                ),
                index + 1,
            )
        if text == "--":
            if saw_separator:
                raise MalformedContract(
                    "Contract can contain only one '--'",
                    context={"index": index},
                )
            saw_separator = True
            current = output_kinds
            index += 1
            continue
        current.append(ValueKind.parse(text))
        index += 1

    raise MalformedContract(
        "Unterminated contract annotation",
        context={"index": start_index},
    )


def check_input_segment(
    observed: Sequence[object],
    expected: Sequence[ValueKind],
) -> tuple[bool, int]:
    if len(observed) < len(expected):
        return False, len(observed)
    return all(
        expected_kind is ValueKind.ANY or _kind_name(item) == expected_kind.value
        for item, expected_kind in zip(observed, expected, strict=False)
    ), len(expected)


def check_output_segment(
    observed: Sequence[object],
    expected: Sequence[ValueKind],
) -> bool:
    if len(observed) != len(expected):
        return False
    return all(
        expected_kind is ValueKind.ANY or _kind_name(item) == expected_kind.value
        for item, expected_kind in zip(observed, expected, strict=False)
    )


def _kind_name(value: object) -> str:
    name = type(value).__name__
    if name == "IntValue":
        return "int"
    if name == "BoolValue":
        return "bool"
    return "any"


def _coerce_text(token: str | Token) -> str:
    return token if isinstance(token, str) else token.text


__all__ = [
    "ValueKind",
    "StackContract",
    "parse_stack_contract",
    "check_input_segment",
    "check_output_segment",
]
