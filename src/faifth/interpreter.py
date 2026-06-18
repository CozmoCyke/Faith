from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from .definitions import ParsedDefinition, parse_definition
from .dictionary import Dictionary, UserWord
from .errors import (
    CallDepthExceeded,
    FaifthError,
    InterpreterError,
    UnexpectedTerminator,
    UnknownWord,
)
from .primitives import DEFAULT_PRIMITIVE_MAP, Primitive
from .stack import Stack
from .tokenizer import Tokenizer
from .tracing import TraceEntry, TraceKind
from .values import BoolValue, IntValue, StrValue, SymbolValue, Value

ResultStatus = Literal["ok", "error"]

_DEFAULT_MAX_CALL_DEPTH = 64


def _clone_stack(initial_stack: Stack | Iterable[Value] | None) -> Stack:
    if initial_stack is None:
        return Stack()
    if isinstance(initial_stack, Stack):
        snapshot = initial_stack.snapshot()
        return Stack(snapshot.items, max_depth=snapshot.max_depth)
    return Stack(initial_stack)


def _literal_value(token_text: str) -> Value | None:
    if token_text == "true":
        return BoolValue(True)
    if token_text == "false":
        return BoolValue(False)
    if _is_int_literal(token_text):
        return IntValue(int(token_text))
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


class InterpreterSession:
    def __init__(
        self,
        *,
        primitives: Mapping[str, Primitive] | None = None,
        tokenizer: Tokenizer | None = None,
        dictionary: Dictionary | None = None,
        max_call_depth: int = _DEFAULT_MAX_CALL_DEPTH,
    ) -> None:
        self._tokenizer = tokenizer if tokenizer is not None else Tokenizer()
        self._dictionary = (
            dictionary
            if dictionary is not None
            else Dictionary(
                primitives=(
                    primitives if primitives is not None else DEFAULT_PRIMITIVE_MAP
                )
            )
        )
        self._max_call_depth = max_call_depth

    @property
    def primitives(self) -> Mapping[str, Primitive]:
        return self._dictionary.primitives

    @property
    def dictionary(self) -> Dictionary:
        return self._dictionary

    @property
    def max_call_depth(self) -> int:
        return self._max_call_depth

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

        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token.text == ":":
                try:
                    parsed = parse_definition(tokens, index)
                except FaifthError as error:
                    stack_before = stack.snapshot()
                    trace.append(
                        TraceEntry(
                            token=token.text,
                            token_index=token.index,
                            kind="error",
                            stack_before=stack_before,
                            stack_after=stack_before,
                            status="error",
                            error=error,
                            depth=0,
                            line=token.line,
                            column=token.column,
                            offset=token.offset,
                        )
                    )
                    return InterpreterResult.failure(
                        error=error,
                        stack=stack,
                        trace=trace,
                        steps=steps,
                        metadata={
                            "tokens": len(tokens),
                            "token_index": token.index,
                        },
                    )
                definition_result = self._publish_definition(
                    parsed,
                    source=source,
                    stack=stack,
                    trace=trace,
                    steps=steps,
                )
                steps = definition_result[0]
                definition_error = definition_result[1]
                index = definition_result[2]
                if definition_error is not None:
                    return InterpreterResult.failure(
                        error=definition_error,
                        stack=stack,
                        trace=trace,
                        steps=steps,
                        metadata={
                            "tokens": len(tokens),
                            "token_index": token.index,
                        },
                    )
                continue

            token_result = self._execute_token(
                token.text,
                token_index=token.index,
                stack=stack,
                trace=trace,
                steps=steps,
                depth=0,
                line=token.line,
                column=token.column,
                offset=token.offset,
            )
            steps = token_result[0]
            token_error = token_result[1]
            if token_error is not None:
                return InterpreterResult.failure(
                    error=token_error,
                    stack=stack,
                    trace=trace,
                    steps=steps,
                    metadata={
                        "tokens": len(tokens),
                        "token_index": token.index,
                    },
                )
            index += 1

        return InterpreterResult.success(
            stack=stack,
            trace=trace,
            steps=steps,
            metadata={
                "tokens": len(tokens),
                "definitions": len(self._dictionary.list_user_words()),
            },
        )

    def _publish_definition(
        self,
        parsed: ParsedDefinition,
        *,
        source: str,
        stack: Stack,
        trace: list[TraceEntry],
        steps: int,
    ) -> tuple[int, FaifthError | None, int]:
        stack_before = stack.snapshot()
        try:
            word = self._dictionary.validate_user_word(
                parsed.name,
                parsed.body_tokens,
                source=source,
                definition_index=parsed.start_index,
            )
            self._dictionary.define(word)
        except FaifthError as error:
            stack.restore(stack_before)
            trace.append(
                TraceEntry(
                    token=parsed.name,
                    token_index=parsed.start_index,
                    kind="error",
                    stack_before=stack_before,
                    stack_after=stack.snapshot(),
                    status="error",
                    error=error,
                    depth=0,
                )
            )
            return steps, error, parsed.end_index

        trace.append(
            TraceEntry(
                token=parsed.name,
                token_index=parsed.start_index,
                kind="definition",
                stack_before=stack_before,
                stack_after=stack.snapshot(),
                status="ok",
                depth=0,
            )
        )
        return steps + 1, None, parsed.end_index

    def _execute_token(
        self,
        token_text: str,
        *,
        token_index: int,
        stack: Stack,
        trace: list[TraceEntry],
        steps: int,
        depth: int,
        line: int | None = None,
        column: int | None = None,
        offset: int | None = None,
    ) -> tuple[int, FaifthError | None]:
        stack_before = stack.snapshot()
        literal = _literal_value(token_text)
        try:
            if literal is not None:
                kind: TraceKind = "literal"
                stack.push(literal)
                trace.append(
                    TraceEntry(
                        token=token_text,
                        token_index=token_index,
                        kind=kind,
                        stack_before=stack_before,
                        stack_after=stack.snapshot(),
                        status="ok",
                        depth=depth,
                        line=line,
                        column=column,
                        offset=offset,
                    )
                )
                return steps + 1, None

            if token_text == ";":
                terminator_error = UnexpectedTerminator(
                    "Unexpected terminator",
                    context={"token": token_text, "index": token_index},
                )
                trace.append(
                    TraceEntry(
                        token=token_text,
                        token_index=token_index,
                        kind="error",
                        stack_before=stack_before,
                        stack_after=stack_before,
                        status="error",
                        error=terminator_error,
                        depth=depth,
                        line=line,
                        column=column,
                        offset=offset,
                    )
                )
                return steps + 1, terminator_error

            resolved = self._dictionary.resolve(token_text)
            if resolved is None:
                unknown_error = UnknownWord(
                    token_text,
                    index=token_index,
                    line=line,
                    column=column,
                    offset=offset,
                )
                trace.append(
                    TraceEntry(
                        token=token_text,
                        token_index=token_index,
                        kind="error",
                        stack_before=stack_before,
                        stack_after=stack_before,
                        status="error",
                        error=unknown_error,
                        depth=depth,
                        line=line,
                        column=column,
                        offset=offset,
                    )
                )
                return steps + 1, unknown_error

            if isinstance(resolved, Primitive):
                resolved.execute(stack)
                trace.append(
                    TraceEntry(
                        token=token_text,
                        token_index=token_index,
                        kind="primitive",
                        stack_before=stack_before,
                        stack_after=stack.snapshot(),
                        status="ok",
                        depth=depth,
                        line=line,
                        column=column,
                        offset=offset,
                    )
                )
                return steps + 1, None

            return self._execute_user_word(
                resolved,
                stack=stack,
                trace=trace,
                steps=steps,
                depth=depth,
                token_index=token_index,
                line=line,
                column=column,
                offset=offset,
            )
        except FaifthError as error:
            stack.restore(stack_before)
            trace.append(
                TraceEntry(
                    token=token_text,
                    token_index=token_index,
                    kind="error",
                    stack_before=stack_before,
                    stack_after=stack.snapshot(),
                    status="error",
                    error=error,
                    depth=depth,
                    line=line,
                    column=column,
                    offset=offset,
                )
            )
            return steps + 1, error
        except Exception as exc:  # pragma: no cover - defensive
            stack.restore(stack_before)
            internal_error = InterpreterError(
                "Unexpected interpreter failure",
                context={
                    "token": token_text,
                    "token_index": token_index,
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                },
            )
            trace.append(
                TraceEntry(
                    token=token_text,
                    token_index=token_index,
                    kind="error",
                    stack_before=stack_before,
                    stack_after=stack.snapshot(),
                    status="error",
                    error=internal_error,
                    depth=depth,
                    line=line,
                    column=column,
                    offset=offset,
                )
            )
            return steps + 1, internal_error

    def _execute_user_word(
        self,
        word: UserWord,
        *,
        stack: Stack,
        trace: list[TraceEntry],
        steps: int,
        depth: int,
        token_index: int,
        line: int | None,
        column: int | None,
        offset: int | None,
    ) -> tuple[int, FaifthError | None]:
        if depth >= self._max_call_depth:
            call_error = CallDepthExceeded(
                f"Call depth exceeded: {word.name}",
                context={
                    "word": word.name,
                    "depth": depth,
                    "max_call_depth": self._max_call_depth,
                },
            )
            trace.append(
                TraceEntry(
                    token=word.name,
                    token_index=token_index,
                    kind="error",
                    stack_before=stack.snapshot(),
                    stack_after=stack.snapshot(),
                    status="error",
                    error=call_error,
                    depth=depth,
                    line=line,
                    column=column,
                    offset=offset,
                )
            )
            return steps + 1, call_error

        call_snapshot = stack.snapshot()
        trace.append(
            TraceEntry(
                token=word.name,
                token_index=token_index,
                kind="call",
                stack_before=call_snapshot,
                stack_after=call_snapshot,
                status="ok",
                depth=depth,
                line=line,
                column=column,
                offset=offset,
            )
        )
        steps += 1

        for body_index, body_token in enumerate(word.body):
            body_result = self._execute_token(
                body_token,
                token_index=body_index,
                stack=stack,
                trace=trace,
                steps=steps,
                depth=depth + 1,
            )
            steps = body_result[0]
            body_error = body_result[1]
            if body_error is not None:
                stack.restore(call_snapshot)
                return steps, body_error

        trace.append(
            TraceEntry(
                token=word.name,
                token_index=token_index,
                kind="return",
                stack_before=call_snapshot,
                stack_after=stack.snapshot(),
                status="ok",
                depth=depth,
                line=line,
                column=column,
                offset=offset,
            )
        )
        return steps + 1, None


Interpreter = InterpreterSession


def execute(
    source: str, *, initial_stack: Stack | Iterable[Value] | None = None
) -> InterpreterResult:
    return InterpreterSession().execute(source, initial_stack=initial_stack)


__all__ = [
    "InterpreterSession",
    "Interpreter",
    "InterpreterResult",
    "execute",
]
