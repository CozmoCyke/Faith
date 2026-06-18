from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    index: int
    offset: int
    line: int
    column: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "index": self.index,
            "offset": self.offset,
            "line": self.line,
            "column": self.column,
        }


class Tokenizer:
    def tokenize(self, source: str) -> tuple[Token, ...]:
        tokens: list[Token] = []
        index = 0
        i = 0
        line = 1
        column = 1
        length = len(source)

        while i < length:
            char = source[i]
            if char.isspace():
                i, line, column = self._advance_whitespace(source, i, line, column)
                continue

            start = i
            start_line = line
            start_column = column
            while i < length and not source[i].isspace():
                i += 1
                column += 1

            token_text = source[start:i]
            tokens.append(
                Token(
                    text=token_text,
                    index=index,
                    offset=start,
                    line=start_line,
                    column=start_column,
                )
            )
            index += 1

        return tuple(tokens)

    @staticmethod
    def _advance_whitespace(
        source: str, i: int, line: int, column: int
    ) -> tuple[int, int, int]:
        char = source[i]
        if char == "\r" and i + 1 < len(source) and source[i + 1] == "\n":
            return i + 2, line + 1, 1
        if char in "\r\n":
            return i + 1, line + 1, 1
        return i + 1, line, column + 1


def tokenize(source: str) -> tuple[Token, ...]:
    return Tokenizer().tokenize(source)


__all__ = ["Token", "Tokenizer", "tokenize"]