from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any


def _freeze_mapping(data: Mapping[str, Any] | None) -> Mapping[str, Any]:
    frozen = dict(sorted((data or {}).items()))
    return MappingProxyType(frozen)


class FaifthError(Exception):
    __slots__ = ("_code", "_message", "_metadata", "_context")

    default_code = "faifth.error"
    default_message = "Faifth error"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        actual_message = self.default_message if message is None else message
        super().__init__(actual_message)
        self._code = self.default_code if code is None else code
        self._message = actual_message
        self._metadata = _freeze_mapping(metadata)
        self._context = _freeze_mapping(context)

    @property
    def code(self) -> str:
        return self._code

    @property
    def message(self) -> str:
        return self._message

    @property
    def metadata(self) -> Mapping[str, Any]:
        return self._metadata

    @property
    def context(self) -> Mapping[str, Any]:
        return self._context

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.__class__.__name__,
            "code": self.code,
            "message": self.message,
            "metadata": dict(self.metadata),
            "context": dict(self.context),
        }

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r}, "
            f"metadata={dict(self.metadata)!r}, context={dict(self.context)!r})"
        )

    def __eq__(self, other: object) -> bool:
        if other.__class__ is not self.__class__:
            return False
        assert isinstance(other, FaifthError)
        return (
            self.code == other.code
            and self.message == other.message
            and dict(self.metadata) == dict(other.metadata)
            and dict(self.context) == dict(other.context)
        )


class StackUnderflow(FaifthError):
    default_code = "faifth.stack_underflow"
    default_message = "Stack underflow"


class StackOverflow(FaifthError):
    default_code = "faifth.stack_overflow"
    default_message = "Stack overflow"


class TypeMismatch(FaifthError):
    default_code = "faifth.type_mismatch"
    default_message = "Type mismatch"


class InvalidValue(FaifthError):
    default_code = "faifth.invalid_value"
    default_message = "Invalid value"


class InvalidSnapshot(FaifthError):
    default_code = "faifth.invalid_snapshot"
    default_message = "Invalid snapshot"


class UnknownWord(FaifthError):
    default_code = "faifth.unknown_word"
    default_message = "Unknown word"

    def __init__(
        self,
        word: str,
        *,
        index: int,
        line: int | None = None,
        column: int | None = None,
        offset: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        context: dict[str, Any] = {"word": word, "index": index}
        if line is not None:
            context["line"] = line
        if column is not None:
            context["column"] = column
        if offset is not None:
            context["offset"] = offset
        super().__init__(
            f"Unknown word: {word}",
            metadata=metadata,
            context=context,
        )


class InvalidDefinition(FaifthError):
    default_code = "faifth.invalid_definition"
    default_message = "Invalid definition"


class DuplicateWord(FaifthError):
    default_code = "faifth.duplicate_word"
    default_message = "Duplicate word"


class ProtectedWord(FaifthError):
    default_code = "faifth.protected_word"
    default_message = "Protected word"


class UnterminatedDefinition(FaifthError):
    default_code = "faifth.unterminated_definition"
    default_message = "Unterminated definition"


class UnexpectedTerminator(FaifthError):
    default_code = "faifth.unexpected_terminator"
    default_message = "Unexpected terminator"


class RecursiveDefinition(FaifthError):
    default_code = "faifth.recursive_definition"
    default_message = "Recursive definition"


class CallDepthExceeded(FaifthError):
    default_code = "faifth.call_depth_exceeded"
    default_message = "Call depth exceeded"


class InterpreterError(FaifthError):
    default_code = "faifth.interpreter_error"
    default_message = "Interpreter error"


__all__ = [
    "FaifthError",
    "StackUnderflow",
    "StackOverflow",
    "TypeMismatch",
    "InvalidValue",
    "InvalidSnapshot",
    "UnknownWord",
    "InvalidDefinition",
    "DuplicateWord",
    "ProtectedWord",
    "UnterminatedDefinition",
    "UnexpectedTerminator",
    "RecursiveDefinition",
    "CallDepthExceeded",
    "InterpreterError",
]
