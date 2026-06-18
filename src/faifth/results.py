from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from .errors import FaifthError, InvalidValue
from .values import Value, is_value

ResultStatus = Literal["ok", "error"]


def _freeze_metadata(metadata: Mapping[str, Any] | None) -> Mapping[str, Any]:
    frozen = dict(sorted((metadata or {}).items()))
    return MappingProxyType(frozen)


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    status: ResultStatus
    value: Value | None = None
    error: FaifthError | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {"ok", "error"}:
            raise ValueError(f"Invalid result status: {self.status!r}")
        if self.value is not None and not is_value(self.value):
            raise InvalidValue(
                "ExecutionResult value must be a Phase 0 Faifth value",
                context={"received": type(self.value).__name__},
            )
        if self.status == "ok" and self.error is not None:
            raise ValueError("Success results cannot contain an error")
        if self.status == "error" and self.error is None:
            raise ValueError("Error results must contain an error")
        if self.status == "error" and self.value is not None:
            raise ValueError("Error results cannot contain a value")
        if self.error is not None and not isinstance(self.error, FaifthError):
            raise TypeError("error must be a FaifthError")
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    @classmethod
    def success(
        cls, value: Value | None = None, *, metadata: Mapping[str, Any] | None = None
    ) -> ExecutionResult:
        return cls(
            status="ok",
            value=value,
            error=None,
            metadata=metadata if metadata is not None else {},
        )

    @classmethod
    def failure(
        cls, error: FaifthError, *, metadata: Mapping[str, Any] | None = None
    ) -> ExecutionResult:
        return cls(
            status="error",
            value=None,
            error=error,
            metadata=metadata if metadata is not None else {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "value": None if self.value is None else self.value.to_dict(),
            "error": None if self.error is None else self.error.to_dict(),
            "metadata": dict(self.metadata),
        }


__all__ = ["ExecutionResult", "ResultStatus"]
