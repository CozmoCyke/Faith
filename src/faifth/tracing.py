from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .capabilities import CapabilitySet
from .errors import FaifthError
from .stack import StackSnapshot

TraceKind = Literal["literal", "primitive", "definition", "call", "return", "error"]
TraceStatus = Literal["ok", "error"]


@dataclass(frozen=True, slots=True)
class TraceEntry:
    token: str
    token_index: int
    kind: TraceKind
    stack_before: StackSnapshot
    stack_after: StackSnapshot
    status: TraceStatus
    error: FaifthError | None = None
    depth: int | None = None
    line: int | None = None
    column: int | None = None
    offset: int | None = None
    required_capabilities: CapabilitySet | None = None
    granted_capabilities: CapabilitySet | None = None
    missing_capabilities: CapabilitySet | None = None
    permission_status: str | None = None
    transaction_id: str | None = None

    def __post_init__(self) -> None:
        if self.status == "ok" and self.error is not None:
            raise ValueError("ok trace entries cannot include an error")
        if self.status == "error" and self.error is None:
            raise ValueError("error trace entries must include an error")

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "token_index": self.token_index,
            "kind": self.kind,
            "stack_before": self.stack_before.to_dict(),
            "stack_after": self.stack_after.to_dict(),
            "status": self.status,
            "error": None if self.error is None else self.error.to_dict(),
            "depth": self.depth,
            "line": self.line,
            "column": self.column,
            "offset": self.offset,
            "required_capabilities": (
                None
                if self.required_capabilities is None
                else self.required_capabilities.to_dict()
            ),
            "granted_capabilities": (
                None
                if self.granted_capabilities is None
                else self.granted_capabilities.to_dict()
            ),
            "missing_capabilities": (
                None
                if self.missing_capabilities is None
                else self.missing_capabilities.to_dict()
            ),
            "permission_status": self.permission_status,
            "transaction_id": self.transaction_id,
        }


__all__ = ["TraceEntry", "TraceKind", "TraceStatus"]
