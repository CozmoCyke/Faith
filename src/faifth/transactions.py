from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .capabilities import CapabilitySet
from .errors import FaifthError

TransactionStatus = Literal["active", "committed", "rolled_back"]


@dataclass(frozen=True, slots=True)
class TransactionRecord:
    transaction_id: str
    status: TransactionStatus
    started_sequence: int
    ended_sequence: int | None = None
    committed: bool = False
    rolled_back: bool = False
    rollback_reason: str | None = None
    error: FaifthError | None = None
    words_added: tuple[str, ...] = ()
    words_removed: tuple[str, ...] = ()
    granted_capabilities: CapabilitySet = CapabilitySet.none()

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "started_sequence": self.started_sequence,
            "ended_sequence": self.ended_sequence,
            "committed": self.committed,
            "rolled_back": self.rolled_back,
            "rollback_reason": self.rollback_reason,
            "error": None if self.error is None else self.error.to_dict(),
            "words_added": list(self.words_added),
            "words_removed": list(self.words_removed),
            "granted_capabilities": self.granted_capabilities.to_dict(),
        }


__all__ = ["TransactionRecord", "TransactionStatus"]
