from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from .budgets import BudgetUsage, ExecutionBudget
from .contracts import (
    StackContract,
    ValueKind,
    check_input_segment,
    check_output_segment,
)
from .definitions import ParsedDefinition, parse_definition
from .dictionary import Dictionary, UserWord
from .errors import (
    CallDepthExceeded,
    ContractDepthMismatch,
    ContractInputMismatch,
    ContractOutputMismatch,
    FaifthError,
    InterpreterError,
    StackDepthBudgetExceeded,
    StepBudgetExceeded,
    UnexpectedTerminator,
    UnknownWord,
)
from .primitives import DEFAULT_PRIMITIVE_MAP, Primitive
from .stack import Stack, StackOverflow, StackSnapshot
from .tokenizer import Token, Tokenizer
from .tracing import TraceEntry
from .values import BoolValue, IntValue, StrValue, SymbolValue, Value

ResultStatus = Literal["ok", "error"]


def _clone_stack(
    initial_stack: Stack | Iterable[Value] | None,
    *,
    max_depth: int | None,
) -> Stack:
    if initial_stack is None:
        return Stack(max_depth=max_depth)
    if isinstance(initial_stack, Stack):
        snapshot = initial_stack.snapshot()
        merged_max_depth = _merge_max_depth(snapshot.max_depth, max_depth)
        return Stack(snapshot.items, max_depth=merged_max_depth)
    return Stack(initial_stack, max_depth=max_depth)


def _merge_max_depth(left: int | None, right: int | None) -> int | None:
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)


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


def _value_kind(value: Value) -> ValueKind:
    if isinstance(value, IntValue):
        return ValueKind.INT
    if isinstance(value, BoolValue):
        return ValueKind.BOOL
    return ValueKind.ANY


@dataclass(frozen=True, slots=True)
class InterpreterResult:
    status: ResultStatus
    value: Value | None = None
    error: FaifthError | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    stack: tuple[Value, ...] = ()
    trace: tuple[TraceEntry, ...] = ()
    steps: int = 0
    budget: ExecutionBudget | None = None
    usage: BudgetUsage = field(default_factory=BudgetUsage)

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
        if self.budget is not None and not isinstance(self.budget, ExecutionBudget):
            raise TypeError("budget must be an ExecutionBudget or None")
        if not isinstance(self.usage, BudgetUsage):
            raise TypeError("usage must be a BudgetUsage")
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
        budget: ExecutionBudget | None = None,
        usage: BudgetUsage | None = None,
    ) -> InterpreterResult:
        stack_values = tuple(stack)
        return cls(
            status="ok",
            value=stack_values[-1] if stack_values else None,
            metadata=metadata if metadata is not None else {},
            stack=stack_values,
            trace=tuple(trace),
            steps=steps,
            budget=budget,
            usage=usage if usage is not None else BudgetUsage(steps_used=steps),
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
        budget: ExecutionBudget | None = None,
        usage: BudgetUsage | None = None,
    ) -> InterpreterResult:
        stack_values = tuple(stack)
        return cls(
            status="error",
            error=error,
            metadata=metadata if metadata is not None else {},
            stack=stack_values,
            trace=tuple(trace),
            steps=steps,
            budget=budget,
            usage=usage if usage is not None else BudgetUsage(steps_used=steps),
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
            "budget": None if self.budget is None else self.budget.to_dict(),
            "usage": self.usage.to_dict(),
        }


@dataclass(slots=True)
class _RuntimeState:
    stack: Stack
    trace: list[TraceEntry]
    steps: int
    peak_stack_depth: int
    peak_call_depth: int
    budget: ExecutionBudget
    limit_hit: str | None = None

    @property
    def usage(self) -> BudgetUsage:
        return BudgetUsage(
            steps_used=self.steps,
            peak_stack_depth=self.peak_stack_depth,
            peak_call_depth=self.peak_call_depth,
            limit_hit=self.limit_hit,
        )


class InterpreterSession:
    def __init__(
        self,
        *,
        primitives: Mapping[str, Primitive] | None = None,
        tokenizer: Tokenizer | None = None,
        dictionary: Dictionary | None = None,
        default_budget: ExecutionBudget | None = None,
        max_call_depth: int = 64,
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
        self._default_budget = (
            default_budget
            if default_budget is not None
            else ExecutionBudget(max_call_depth=max_call_depth)
        )

    @property
    def primitives(self) -> Mapping[str, Primitive]:
        return self._dictionary.primitives

    @property
    def dictionary(self) -> Dictionary:
        return self._dictionary

    @property
    def default_budget(self) -> ExecutionBudget:
        return self._default_budget

    def execute(
        self,
        source: str,
        *,
        initial_stack: Stack | Iterable[Value] | None = None,
        budget: ExecutionBudget | None = None,
    ) -> InterpreterResult:
        effective_budget = budget if budget is not None else self._default_budget
        runtime = _RuntimeState(
            stack=_clone_stack(
                initial_stack,
                max_depth=effective_budget.max_stack_depth,
            ),
            trace=[],
            steps=0,
            peak_stack_depth=0,
            peak_call_depth=0,
            budget=effective_budget,
        )
        runtime.peak_stack_depth = runtime.stack.depth()
        tokens = self._tokenizer.tokenize(source)

        index = 0
        while index < len(tokens):
            token = tokens[index]
            step_error = self._check_step_budget(runtime, token)
            if step_error is not None:
                return self._fail(runtime, step_error, token, token_index=token.index)

            if token.text == ":":
                parsed_or_error = self._parse_definition(tokens, index, runtime.stack)
                if isinstance(parsed_or_error, FaifthError):
                    runtime.trace.append(
                        TraceEntry(
                            token=token.text,
                            token_index=token.index,
                            kind="error",
                            stack_before=runtime.stack.snapshot(),
                            stack_after=runtime.stack.snapshot(),
                            status="error",
                            error=parsed_or_error,
                            depth=0,
                            line=token.line,
                            column=token.column,
                            offset=token.offset,
                        )
                    )
                    return self._fail(
                        runtime,
                        parsed_or_error,
                        token,
                        token_index=token.index,
                    )
                parsed = parsed_or_error
                publish_error = self._publish_definition(parsed, runtime)
                if publish_error is not None:
                    return self._fail(
                        runtime,
                        publish_error,
                        token,
                        token_index=token.index,
                    )
                index = parsed.end_index
                continue

            error = self._execute_token(
                token=token,
                runtime=runtime,
                call_depth=0,
            )
            if error is not None:
                return self._fail(runtime, error, token, token_index=token.index)
            index += 1

        return InterpreterResult.success(
            stack=runtime.stack,
            trace=runtime.trace,
            steps=runtime.steps,
            metadata={
                "tokens": len(tokens),
                "definitions": len(self._dictionary.list_user_words()),
            },
            budget=effective_budget,
            usage=runtime.usage,
        )

    def _check_step_budget(
        self, runtime: _RuntimeState, token: Token
    ) -> FaifthError | None:
        max_steps = runtime.budget.max_steps
        if max_steps is not None and runtime.steps >= max_steps:
            runtime.limit_hit = "steps"
            return StepBudgetExceeded(
                "Step budget exceeded",
                context={
                    "limit": max_steps,
                    "steps_used": runtime.steps,
                    "token": token.text,
                    "index": token.index,
                },
            )
        return None

    def _publish_definition(
        self, parsed: ParsedDefinition, runtime: _RuntimeState
    ) -> FaifthError | None:
        stack_before = runtime.stack.snapshot()
        try:
            word = self._dictionary.validate_user_word(
                parsed.name,
                parsed.body_tokens,
                contract=parsed.contract,
                source=None,
                definition_index=parsed.start_index,
            )
            self._dictionary.define(word)
        except FaifthError as caught_error:
            runtime.stack.restore(stack_before)
            runtime.trace.append(
                TraceEntry(
                    token=parsed.name,
                    token_index=parsed.start_index,
                    kind="error",
                    stack_before=stack_before,
                    stack_after=runtime.stack.snapshot(),
                    status="error",
                    error=caught_error,
                    depth=0,
                )
            )
            return caught_error

        runtime.steps += 1
        runtime.peak_stack_depth = max(runtime.peak_stack_depth, runtime.stack.depth())
        runtime.trace.append(
            TraceEntry(
                token=parsed.name,
                token_index=parsed.start_index,
                kind="definition",
                stack_before=stack_before,
                stack_after=runtime.stack.snapshot(),
                status="ok",
                depth=0,
            )
        )
        return None

    def _parse_definition(
        self, tokens: Sequence[Token], index: int, stack: Stack
    ) -> ParsedDefinition | FaifthError:
        try:
            return parse_definition(tokens, index)
        except FaifthError as error:
            return error

    def _execute_token(
        self,
        *,
        token: Token,
        runtime: _RuntimeState,
        call_depth: int,
    ) -> FaifthError | None:
        runtime.steps += 1
        stack_before = runtime.stack.snapshot()
        literal = _literal_value(token.text)
        if literal is not None:
            try:
                runtime.stack.push(literal)
            except StackOverflow:
                runtime.stack.restore(stack_before)
                runtime.limit_hit = "stack"
                return StackDepthBudgetExceeded(
                    "Stack depth budget exceeded",
                    context={
                        "limit": runtime.budget.max_stack_depth,
                        "current_depth": len(stack_before.items),
                        "token": token.text,
                    },
                )
            runtime.peak_stack_depth = max(
                runtime.peak_stack_depth, runtime.stack.depth()
            )
            runtime.trace.append(
                TraceEntry(
                    token=token.text,
                    token_index=token.index,
                    kind="literal",
                    stack_before=stack_before,
                    stack_after=runtime.stack.snapshot(),
                    status="ok",
                    depth=call_depth,
                    line=token.line,
                    column=token.column,
                    offset=token.offset,
                )
            )
            return None

        if token.text == ";":
            terminator_error = UnexpectedTerminator(
                "Unexpected terminator",
                context={"token": token.text, "index": token.index},
            )
            runtime.trace.append(
                TraceEntry(
                    token=token.text,
                    token_index=token.index,
                    kind="error",
                    stack_before=stack_before,
                    stack_after=stack_before,
                    status="error",
                    error=terminator_error,
                    depth=call_depth,
                    line=token.line,
                    column=token.column,
                    offset=token.offset,
                )
            )
            return terminator_error

        resolved = self._dictionary.resolve(token.text)
        if resolved is None:
            unknown_error = UnknownWord(
                token.text,
                index=token.index,
                line=token.line,
                column=token.column,
                offset=token.offset,
            )
            runtime.trace.append(
                TraceEntry(
                    token=token.text,
                    token_index=token.index,
                    kind="error",
                    stack_before=stack_before,
                    stack_after=stack_before,
                    status="error",
                    error=unknown_error,
                    depth=call_depth,
                    line=token.line,
                    column=token.column,
                    offset=token.offset,
                )
            )
            return unknown_error

        if isinstance(resolved, Primitive):
            return self._execute_primitive(token, resolved, runtime, call_depth)

        return self._execute_user_word(token, resolved, runtime, call_depth)

    def _execute_primitive(
        self,
        token: Token,
        primitive: Primitive,
        runtime: _RuntimeState,
        call_depth: int,
    ) -> FaifthError | None:
        stack_before = runtime.stack.snapshot()
        contract_error = self._check_contract_inputs(
            primitive.contract, runtime.stack, token=token, word_name=primitive.name
        )
        if contract_error is not None:
            runtime.trace.append(
                TraceEntry(
                    token=token.text,
                    token_index=token.index,
                    kind="error",
                    stack_before=stack_before,
                    stack_after=stack_before,
                    status="error",
                    error=contract_error,
                    depth=call_depth,
                    line=token.line,
                    column=token.column,
                    offset=token.offset,
                )
            )
            return contract_error

        try:
            primitive.execute(runtime.stack)
        except StackOverflow:
            runtime.stack.restore(stack_before)
            runtime.limit_hit = "stack"
            error = StackDepthBudgetExceeded(
                "Stack depth budget exceeded",
                context={
                    "limit": runtime.budget.max_stack_depth,
                    "current_depth": len(stack_before.items),
                    "token": token.text,
                    "word": primitive.name,
                },
            )
            runtime.trace.append(
                TraceEntry(
                    token=token.text,
                    token_index=token.index,
                    kind="error",
                    stack_before=stack_before,
                    stack_after=runtime.stack.snapshot(),
                    status="error",
                    error=error,
                    depth=call_depth,
                    line=token.line,
                    column=token.column,
                    offset=token.offset,
                )
            )
            return error
        except FaifthError as caught_error:
            runtime.stack.restore(stack_before)
            runtime.trace.append(
                TraceEntry(
                    token=token.text,
                    token_index=token.index,
                    kind="error",
                    stack_before=stack_before,
                    stack_after=runtime.stack.snapshot(),
                    status="error",
                    error=caught_error,
                    depth=call_depth,
                    line=token.line,
                    column=token.column,
                    offset=token.offset,
                )
            )
            return caught_error
        except Exception as exc:  # pragma: no cover - defensive
            runtime.stack.restore(stack_before)
            internal_error = InterpreterError(
                "Unexpected interpreter failure",
                context={
                    "token": token.text,
                    "token_index": token.index,
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                },
            )
            runtime.trace.append(
                TraceEntry(
                    token=token.text,
                    token_index=token.index,
                    kind="error",
                    stack_before=stack_before,
                    stack_after=runtime.stack.snapshot(),
                    status="error",
                    error=internal_error,
                    depth=call_depth,
                    line=token.line,
                    column=token.column,
                    offset=token.offset,
                )
            )
            return internal_error

        contract_post_error = self._check_contract_outputs(
            primitive.contract,
            stack_before,
            runtime.stack,
            token=token,
            word_name=primitive.name,
        )
        if contract_post_error is not None:
            runtime.stack.restore(stack_before)
            runtime.trace.append(
                TraceEntry(
                    token=token.text,
                    token_index=token.index,
                    kind="error",
                    stack_before=stack_before,
                    stack_after=runtime.stack.snapshot(),
                    status="error",
                    error=contract_post_error,
                    depth=call_depth,
                    line=token.line,
                    column=token.column,
                    offset=token.offset,
                )
            )
            return contract_post_error

        runtime.peak_stack_depth = max(runtime.peak_stack_depth, runtime.stack.depth())
        runtime.trace.append(
            TraceEntry(
                token=token.text,
                token_index=token.index,
                kind="primitive",
                stack_before=stack_before,
                stack_after=runtime.stack.snapshot(),
                status="ok",
                depth=call_depth,
                line=token.line,
                column=token.column,
                offset=token.offset,
            )
        )
        return None

    def _execute_user_word(
        self,
        token: Token,
        word: UserWord,
        runtime: _RuntimeState,
        call_depth: int,
    ) -> FaifthError | None:
        stack_before = runtime.stack.snapshot()
        next_call_depth = call_depth + 1
        max_call_depth = runtime.budget.max_call_depth
        if max_call_depth is not None and next_call_depth > max_call_depth:
            runtime.limit_hit = "call"
            call_error = CallDepthExceeded(
                f"Call depth exceeded: {word.name}",
                context={
                    "word": word.name,
                    "depth": next_call_depth,
                    "limit": max_call_depth,
                },
            )
            runtime.trace.append(
                TraceEntry(
                    token=token.text,
                    token_index=token.index,
                    kind="error",
                    stack_before=stack_before,
                    stack_after=stack_before,
                    status="error",
                    error=call_error,
                    depth=call_depth,
                    line=token.line,
                    column=token.column,
                    offset=token.offset,
                )
            )
            return call_error

        contract_error = None
        if word.contract is not None:
            contract_error = self._check_contract_inputs(
                word.contract, runtime.stack, token=token, word_name=word.name
            )
        if contract_error is not None:
            runtime.trace.append(
                TraceEntry(
                    token=token.text,
                    token_index=token.index,
                    kind="error",
                    stack_before=stack_before,
                    stack_after=stack_before,
                    status="error",
                    error=contract_error,
                    depth=call_depth,
                    line=token.line,
                    column=token.column,
                    offset=token.offset,
                )
            )
            return contract_error

        runtime.peak_call_depth = max(runtime.peak_call_depth, next_call_depth)
        runtime.trace.append(
            TraceEntry(
                token=token.text,
                token_index=token.index,
                kind="call",
                stack_before=stack_before,
                stack_after=stack_before,
                status="ok",
                depth=call_depth,
                line=token.line,
                column=token.column,
                offset=token.offset,
            )
        )

        call_snapshot = runtime.stack.snapshot()
        for body_index, body_token_text in enumerate(word.body):
            body_token = Token(
                text=body_token_text,
                index=body_index,
                offset=0,
                line=token.line,
                column=token.column,
            )
            step_error = self._check_step_budget(runtime, body_token)
            if step_error is not None:
                runtime.stack.restore(call_snapshot)
                runtime.trace.append(
                    TraceEntry(
                        token=body_token.text,
                        token_index=body_token.index,
                        kind="error",
                        stack_before=call_snapshot,
                        stack_after=runtime.stack.snapshot(),
                        status="error",
                        error=step_error,
                        depth=next_call_depth,
                    )
                )
                return step_error
            body_error = self._execute_token(
                token=body_token,
                runtime=runtime,
                call_depth=next_call_depth,
            )
            if body_error is not None:
                runtime.stack.restore(call_snapshot)
                return body_error

        post_error = None
        if word.contract is not None:
            post_error = self._check_contract_outputs(
                word.contract,
                stack_before,
                runtime.stack,
                token=token,
                word_name=word.name,
            )
        if post_error is not None:
            runtime.stack.restore(stack_before)
            runtime.trace.append(
                TraceEntry(
                    token=token.text,
                    token_index=token.index,
                    kind="error",
                    stack_before=stack_before,
                    stack_after=runtime.stack.snapshot(),
                    status="error",
                    error=post_error,
                    depth=call_depth,
                    line=token.line,
                    column=token.column,
                    offset=token.offset,
                )
            )
            return post_error

        runtime.trace.append(
            TraceEntry(
                token=token.text,
                token_index=token.index,
                kind="return",
                stack_before=stack_before,
                stack_after=runtime.stack.snapshot(),
                status="ok",
                depth=call_depth,
                line=token.line,
                column=token.column,
                offset=token.offset,
            )
        )
        return None

    def _check_contract_inputs(
        self,
        contract: StackContract,
        stack: Stack,
        *,
        token: Token,
        word_name: str,
    ) -> FaifthError | None:
        observed = tuple(stack)[-contract.input_count :] if contract.input_count else ()
        if len(observed) < contract.input_count:
            return ContractDepthMismatch(
                f"Contract depth mismatch for {word_name}",
                context={
                    "word": word_name,
                    "expected": [kind.value for kind in contract.inputs],
                    "observed": [kind.value for kind in map(_value_kind, observed)],
                    "token": token.text,
                    "index": token.index,
                },
            )
        observed_kinds = tuple(_value_kind(value) for value in observed)
        if not check_input_segment(observed, contract.inputs)[0]:
            return ContractInputMismatch(
                f"Contract input mismatch for {word_name}",
                context={
                    "word": word_name,
                    "expected": [kind.value for kind in contract.inputs],
                    "observed": [kind.value for kind in observed_kinds],
                    "token": token.text,
                    "index": token.index,
                },
            )
        return None

    def _check_contract_outputs(
        self,
        contract: StackContract,
        stack_before: StackSnapshot,
        stack_after: Stack,
        *,
        token: Token,
        word_name: str,
    ) -> FaifthError | None:
        expected_depth = (
            len(stack_before.items) - contract.input_count + contract.output_count
        )
        actual_depth = stack_after.depth()
        if actual_depth != expected_depth:
            return ContractDepthMismatch(
                f"Contract depth mismatch for {word_name}",
                context={
                    "word": word_name,
                    "expected_depth": expected_depth,
                    "observed_depth": actual_depth,
                    "token": token.text,
                    "index": token.index,
                },
            )
        observed = (
            tuple(stack_after)[-contract.output_count :]
            if contract.output_count
            else ()
        )
        if contract.output_count and not check_output_segment(
            observed,
            contract.outputs,
        ):
            return ContractOutputMismatch(
                f"Contract output mismatch for {word_name}",
                context={
                    "word": word_name,
                    "expected": [kind.value for kind in contract.outputs],
                    "observed": [kind.value for kind in map(_value_kind, observed)],
                    "token": token.text,
                    "index": token.index,
                },
            )
        return None

    def _fail(
        self,
        runtime: _RuntimeState,
        error: FaifthError,
        token: Token,
        *,
        token_index: int,
    ) -> InterpreterResult:
        return InterpreterResult.failure(
            error=error,
            stack=runtime.stack,
            trace=runtime.trace,
            steps=runtime.steps,
            metadata={"token_index": token_index},
            budget=runtime.budget,
            usage=runtime.usage,
        )


Interpreter = InterpreterSession


def execute(
    source: str,
    *,
    initial_stack: Stack | Iterable[Value] | None = None,
    budget: ExecutionBudget | None = None,
) -> InterpreterResult:
    return InterpreterSession().execute(
        source,
        initial_stack=initial_stack,
        budget=budget,
    )


__all__ = [
    "InterpreterSession",
    "Interpreter",
    "InterpreterResult",
    "execute",
]
