from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from .errors import FaifthError, InterpreterError, UnknownWord
from .primitives import DEFAULT_PRIMITIVE_MAP, Primitive
from .stack import Stack
from .tokenizer import Token, Tokenizer
from .tracing import TraceEntry, TraceKind
from .values import BoolValue, IntValue, StrValue, SymbolValue, Value

ResultStatus = Literal["ok", "error"]


def _clone_stack(initial_stack: Stack | Iterable[Value] | None) -> Stack:
    if initial_stack is None:
        return Stack()
    if isinstance(initial_stack, Stack):
        snapshot = initial_stack.snapshot()
        return Stack(snapshot.items, max_depth=snapshot.max_depth)
    return Stack(initial_stack)


def _literal_value(token: Token) -> Value | None:
    text = token.text
    if text == "true":
        return BoolValue(True)
    if text == "false":
        return BoolValue(False)
    if _is_int_literal(text):
        return IntValue(int(text))
    return None


def _is_int_literal(text: str) -> bool:
    if text.startswith("-"):
        return len(text) > 1 and text[1:].isdigit()
    return text.isdigit()


@dataclass(frozen=True, slots=True)
class InterpreterResult:
    status: ResultStatus
    value: Value | None = None
    error: FaifthError | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    stack: tuple[Value, ...] = ()
    trace: tuple[TraceEntry, ...] = ()
    steps: int = 0

    def __post_init__(self) -> None:
        if self.status not in {"ok", "error"}:
            raise ValueError(f"Invalid result status: {self.status!r}")
        if self.error is not None and not isinstance(self.error, FaifthError):
            raise TypeError("error must be a FaifthError")
        if self.value is not None and not isinstance(
            self.value, IntValue | BoolValue | StrValue | SymbolValue
        ):
            raise TypeError("value must be a Phase 1 Faifth value or None")
        if self.status == "ok" and self.error is not None:
            raise ValueError("Success results cannot contain an error")
        if self.status == "error" and self.error is None:
            raise ValueError("Error results must contain an error")
        if self.status == "error" and self.value is not None:
            raise ValueError("Error results cannot contain a value")
        if self.steps < 0:
            raise ValueError("steps cannot be negative")
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(sorted((self.metadata or {}).items()))),
        )

    @classmethod
    def success(
        cls,
        *,
        stack: Stack,
        trace: Iterable[TraceEntry],
        steps: int,
        metadata: Mapping[str, Any] | None = None,
    ) -> InterpreterResult:
        stack_values = tuple(stack)
        return cls(
            status="ok",
            value=stack_values[-1] if stack_values else None,
            metadata=metadata if metadata is not None else {},
            stack=stack_values,
            trace=tuple(trace),
            steps=steps,
        )

    @classmethod
    def failure(
        cls,
        *,
        error: FaifthError,
        stack: Stack,
        trace: Iterable[TraceEntry],
        steps: int,
        metadata: Mapping[str, Any] | None = None,
    ) -> InterpreterResult:
        stack_values = tuple(stack)
        return cls(
            status="error",
            error=error,
            metadata=metadata if metadata is not None else {},
            stack=stack_values,
            trace=tuple(trace),
            steps=steps,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "value": None if self.value is None else self.value.to_dict(),
            "error": None if self.error is None else self.error.to_dict(),
            "metadata": dict(self.metadata),
            "stack": [value.to_dict() for value in self.stack],
            "trace": [entry.to_dict() for entry in self.trace],
            "steps": self.steps,
        }


class Interpreter:
    def __init__(
        self,
        *,
        primitives: Mapping[str, Primitive] | None = None,
        tokenizer: Tokenizer | None = None,
    ) -> None:
        self._primitives = (
            MappingProxyType(dict(primitives))
            if primitives is not None
            else DEFAULT_PRIMITIVE_MAP
        )
        self._tokenizer = tokenizer if tokenizer is not None else Tokenizer()

    @property
    def primitives(self) -> Mapping[str, Primitive]:
        return self._primitives

    def execute(
        self,
        source: str,
        *,
        initial_stack: Stack | Iterable[Value] | None = None,
    ) -> InterpreterResult:
        stack = _clone_stack(initial_stack)
        tokens = self._tokenizer.tokenize(source)
        trace: list[TraceEntry] = []
        steps = 0

        for token in tokens:
            steps += 1
            stack_before = stack.snapshot()
            literal = _literal_value(token)
            try:
                if literal is not None:
                    kind: TraceKind = "literal"
                    stack.push(literal)
                else:
                    primitive = self._primitives.get(token.text)
                    if primitive is None:
                        raise UnknownWord(
                            token.text,
                            index=token.index,
                            line=token.line,
                            column=token.column,
                            offset=token.offset,
                        )
                    kind = "primitive"
                    primitive.execute(stack)
                stack_after = stack.snapshot()
                trace.append(
                    TraceEntry(
                        token=token.text,
                        token_index=token.index,
                        kind=kind,
                        stack_before=stack_before,
                        stack_after=stack_after,
                        status="ok",
                        line=token.line,
                        column=token.column,
                        offset=token.offset,
                    )
                )
            except FaifthError as caught_error:
                stack.restore(stack_before)
                stack_after = stack.snapshot()
                trace.append(
                    TraceEntry(
                        token=token.text,
                        token_index=token.index,
                        kind="error",
                        stack_before=stack_before,
                        stack_after=stack_after,
                        status="error",
                        error=caught_error,
                        line=token.line,
                        column=token.column,
                        offset=token.offset,
                    )
                )
                return InterpreterResult.failure(
                    error=caught_error,
                    stack=stack,
                    trace=trace,
                    steps=steps,
                    metadata={
                        "tokens": len(tokens),
                        "token_index": token.index,
                    },
                )
            except Exception as exc:  # pragma: no cover - defensive
                stack.restore(stack_before)
                internal_error = InterpreterError(
                    "Unexpected interpreter failure",
                    context={
                        "token": token.text,
                        "token_index": token.index,
                        "exception_type": type(exc).__name__,
                        "exception_message": str(exc),
                    },
                )
                stack_after = stack.snapshot()
                trace.append(
                    TraceEntry(
                        token=token.text,
                        token_index=token.index,
                        kind="error",
                        stack_before=stack_before,
                        stack_after=stack_after,
                        status="error",
                        error=internal_error,
                        line=token.line,
                        column=token.column,
                        offset=token.offset,
                    )
                )
                return InterpreterResult.failure(
                    error=internal_error,
                    stack=stack,
                    trace=trace,
                    steps=steps,
                    metadata={
                        "tokens": len(tokens),
                        "token_index": token.index,
                    },
                )

        return InterpreterResult.success(
            stack=stack,
            trace=trace,
            steps=steps,
            metadata={"tokens": len(tokens)},
        )


def execute(
    source: str, *, initial_stack: Stack | Iterable[Value] | None = None
) -> InterpreterResult:
    return Interpreter().execute(source, initial_stack=initial_stack)


__all__ = ["Interpreter", "InterpreterResult", "execute"]
