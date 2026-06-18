from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import BudgetExceeded, InvalidBudget

_DEFAULT_MAX_STEPS = 10_000
_DEFAULT_MAX_STACK_DEPTH = 1_024
_DEFAULT_MAX_CALL_DEPTH = 64


@dataclass(frozen=True, slots=True)
class ExecutionBudget:
    max_steps: int | None = _DEFAULT_MAX_STEPS
    max_stack_depth: int | None = _DEFAULT_MAX_STACK_DEPTH
    max_call_depth: int | None = _DEFAULT_MAX_CALL_DEPTH

    def __post_init__(self) -> None:
        for field_name, value in (
            ("max_steps", self.max_steps),
            ("max_stack_depth", self.max_stack_depth),
            ("max_call_depth", self.max_call_depth),
        ):
            if value is not None and (type(value) is not int or value <= 0):
                raise InvalidBudget(
                    f"{field_name} must be a positive int or None",
                    context={"field": field_name, "received": value},
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_steps": self.max_steps,
            "max_stack_depth": self.max_stack_depth,
            "max_call_depth": self.max_call_depth,
        }


@dataclass(frozen=True, slots=True)
class BudgetUsage:
    steps_used: int = 0
    peak_stack_depth: int = 0
    peak_call_depth: int = 0
    limit_hit: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("steps_used", self.steps_used),
            ("peak_stack_depth", self.peak_stack_depth),
            ("peak_call_depth", self.peak_call_depth),
        ):
            if type(value) is not int or value < 0:
                raise InvalidBudget(
                    f"{field_name} must be a non-negative int",
                    context={"field": field_name, "received": value},
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps_used": self.steps_used,
            "peak_stack_depth": self.peak_stack_depth,
            "peak_call_depth": self.peak_call_depth,
            "limit_hit": self.limit_hit,
        }


def default_execution_budget() -> ExecutionBudget:
    return ExecutionBudget()


__all__ = [
    "ExecutionBudget",
    "BudgetUsage",
    "BudgetExceeded",
    "default_execution_budget",
]
