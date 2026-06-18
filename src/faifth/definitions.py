from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .errors import InvalidDefinition, UnterminatedDefinition
from .tokenizer import Token


@dataclass(frozen=True, slots=True)
class ParsedDefinition:
    name: str
    name_token: Token
    body_tokens: tuple[Token, ...]
    start_index: int
    end_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "name_token": self.name_token.to_dict(),
            "body_tokens": [token.to_dict() for token in self.body_tokens],
            "start_index": self.start_index,
            "end_index": self.end_index,
        }


class DefinitionParser:
    def parse(self, tokens: Sequence[Token], start_index: int) -> ParsedDefinition:
        if start_index >= len(tokens):
            raise InvalidDefinition(
                "Definition start is out of range",
                context={"start_index": start_index},
            )
        start_token = tokens[start_index]
        if start_token.text != ":":
            raise InvalidDefinition(
                "Definition must start with ':'",
                context={"token": start_token.text, "index": start_index},
            )
        if start_index + 1 >= len(tokens):
            raise InvalidDefinition(
                "Definition name is missing",
                context={"index": start_index},
            )

        name_token = tokens[start_index + 1]
        if name_token.text in {":", ";"}:
            raise InvalidDefinition(
                "Definition name is invalid",
                context={"name": name_token.text, "index": name_token.index},
            )

        body_tokens: list[Token] = []
        index = start_index + 2
        while index < len(tokens):
            token = tokens[index]
            if token.text == ";":
                if not body_tokens:
                    raise InvalidDefinition(
                        "Definition body cannot be empty",
                        context={"name": name_token.text, "index": name_token.index},
                    )
                return ParsedDefinition(
                    name=name_token.text,
                    name_token=name_token,
                    body_tokens=tuple(body_tokens),
                    start_index=start_index,
                    end_index=index + 1,
                )
            if token.text == ":":
                raise InvalidDefinition(
                    "Nested definitions are not allowed",
                    context={
                        "name": name_token.text,
                        "index": token.index,
                    },
                )
            body_tokens.append(token)
            index += 1

        raise UnterminatedDefinition(
            f"Unterminated definition: {name_token.text}",
            context={"name": name_token.text, "index": name_token.index},
        )


def parse_definition(tokens: Sequence[Token], start_index: int) -> ParsedDefinition:
    return DefinitionParser().parse(tokens, start_index)


__all__ = ["DefinitionParser", "ParsedDefinition", "parse_definition"]
