from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, cast

from .capabilities import CapabilitySet
from .errors import (
    FaifthError,
    InvalidArguments,
    InvalidRequest,
    ProtocolLimitExceeded,
)

PROTOCOL_NAME = "faifth-agent"
PROTOCOL_VERSION = "0.1"

ActionName = Literal[
    "create_session",
    "close_session",
    "inspect_state",
    "inspect_session",
    "list_words",
    "inspect_word",
    "propose_definition",
    "test_definition",
    "publish_definition",
    "execute",
    "begin_transaction",
    "commit_transaction",
    "rollback_transaction",
    "save_dictionary",
    "load_dictionary",
    "list_versions",
    "restore_version",
]

ResponseStatus = Literal["ok", "error"]
CandidateStatus = Literal["proposed", "tested", "published", "stale", "rejected"]
TraceMode = Literal["none", "summary", "full"]
WordKind = Literal["primitive", "user"]
SessionSource = Literal["session", "storage"]


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _freeze_mapping(data: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(sorted((data or {}).items())))


def _serialize(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(key): _serialize(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple | list):
        return [_serialize(item) for item in value]
    return value


def _json_depth(value: Any, *, current: int = 0) -> int:
    if isinstance(value, Mapping):
        if not value:
            return current + 1
        return max(_json_depth(item, current=current + 1) for item in value.values())
    if isinstance(value, list | tuple):
        if not value:
            return current + 1
        return max(_json_depth(item, current=current + 1) for item in value)
    return current + 1


def validate_json_depth(value: Any, *, limit: int, label: str) -> None:
    if _json_depth(value) > limit:
        raise ProtocolLimitExceeded(
            f"{label} exceeds the maximum nesting depth",
            context={"label": label, "limit": limit},
        )


@dataclass(frozen=True, slots=True)
class ProtocolAuditEvent:
    kind: str
    status: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", _freeze_mapping(self.details))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "status": self.status,
            "details": _serialize(dict(self.details)),
        }


@dataclass(frozen=True, slots=True)
class ProtocolRequest:
    protocol: str
    version: str
    request_id: str
    session_id: str
    action: ActionName
    arguments: Mapping[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _freeze_mapping(self.arguments))

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        max_depth: int = 16,
    ) -> ProtocolRequest:
        if not isinstance(data, Mapping):
            raise InvalidRequest(
                "Request payload must be a mapping",
                context={"received": type(data).__name__},
            )
        validate_json_depth(data, limit=max_depth, label="request")

        try:
            protocol = str(data["protocol"])
            version = str(data["version"])
            request_id = str(data["request_id"])
            session_id = str(data["session_id"])
            action = str(data["action"])
        except KeyError as exc:
            raise InvalidRequest(
                "Request is missing a required field",
                context={"field": exc.args[0]},
            ) from exc

        if not protocol:
            raise InvalidRequest("Protocol identifier cannot be empty")
        if not version:
            raise InvalidRequest("Protocol version cannot be empty")
        if not request_id:
            raise InvalidRequest("request_id cannot be empty")
        if not session_id:
            raise InvalidRequest("session_id cannot be empty")
        if action not in _ACTION_NAMES:
            raise InvalidRequest(
                "Unknown protocol action",
                context={"action": action},
            )

        arguments = data.get("arguments", {})
        if not isinstance(arguments, Mapping):
            raise InvalidArguments(
                "arguments must be a mapping",
                context={"received": type(arguments).__name__},
            )
        validate_json_depth(arguments, limit=max_depth, label="arguments")

        idempotency_key = data.get("idempotency_key")
        if idempotency_key is not None:
            idempotency_key = str(idempotency_key)
            if not idempotency_key:
                raise InvalidRequest("idempotency_key cannot be empty")

        return cls(
            protocol=protocol,
            version=version,
            request_id=request_id,
            session_id=session_id,
            action=cast(ActionName, action),
            arguments=arguments,
            idempotency_key=idempotency_key,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "protocol": self.protocol,
            "version": self.version,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "action": self.action,
            "arguments": _serialize(dict(self.arguments)),
        }
        if self.idempotency_key is not None:
            payload["idempotency_key"] = self.idempotency_key
        return payload

    def to_json(self) -> str:
        return canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class ProtocolResponse:
    protocol: str
    version: str
    request_id: str
    session_id: str
    status: ResponseStatus
    result: Mapping[str, Any] | None = None
    error: FaifthError | None = None
    audit: tuple[ProtocolAuditEvent, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"ok", "error"}:
            raise InvalidArguments(
                "Invalid response status",
                context={"status": self.status},
            )
        if self.status == "ok" and self.error is not None:
            raise InvalidArguments("Success responses cannot include an error")
        if self.status == "error" and self.error is None:
            raise InvalidArguments("Error responses must include an error")
        if self.result is not None:
            object.__setattr__(self, "result", _freeze_mapping(self.result))

    @classmethod
    def success(
        cls,
        *,
        request: ProtocolRequest,
        result: Mapping[str, Any] | None = None,
        audit: Sequence[ProtocolAuditEvent] = (),
    ) -> ProtocolResponse:
        return cls(
            protocol=request.protocol,
            version=request.version,
            request_id=request.request_id,
            session_id=request.session_id,
            status="ok",
            result=result if result is not None else {},
            error=None,
            audit=tuple(audit),
        )

    @classmethod
    def failure(
        cls,
        *,
        request: ProtocolRequest,
        error: FaifthError,
        audit: Sequence[ProtocolAuditEvent] = (),
    ) -> ProtocolResponse:
        return cls(
            protocol=request.protocol,
            version=request.version,
            request_id=request.request_id,
            session_id=request.session_id,
            status="error",
            result=None,
            error=error,
            audit=tuple(audit),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "version": self.version,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "status": self.status,
            "result": None if self.result is None else _serialize(dict(self.result)),
            "error": None if self.error is None else self.error.to_dict(),
            "audit": [event.to_dict() for event in self.audit],
        }

    def to_json(self) -> str:
        return canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class ProtocolTestCase:
    source: str
    expected_stack: tuple[Any, ...] = ()
    expected_status: str = "ok"
    expected_error_code: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ProtocolTestCase:
        if not isinstance(data, Mapping):
            raise InvalidArguments(
                "Test case must be a mapping",
                context={"received": type(data).__name__},
            )
        source = data.get("source")
        if not isinstance(source, str) or not source:
            raise InvalidArguments(
                "Test case source must be a non-empty string",
                context={"received": type(source).__name__},
            )
        expected_stack = tuple(data.get("expected_stack", ()))
        expected_status = str(data.get("expected_status", "ok"))
        expected_error_code = data.get("expected_error_code")
        if expected_error_code is not None:
            expected_error_code = str(expected_error_code)
        return cls(
            source=source,
            expected_stack=expected_stack,
            expected_status=expected_status,
            expected_error_code=expected_error_code,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "source": self.source,
            "expected_stack": list(self.expected_stack),
            "expected_status": self.expected_status,
        }
        if self.expected_error_code is not None:
            payload["expected_error_code"] = self.expected_error_code
        return payload


@dataclass(frozen=True, slots=True)
class ProtocolCandidate:
    candidate_id: str
    request_id: str
    sequence: int
    source: str
    word: Any
    content_hash: str
    dependency_fingerprint: tuple[tuple[str, str], ...]
    status: CandidateStatus = "proposed"
    tests_passed: bool = False
    tests_total: int = 0
    tests_passed_count: int = 0
    test_results: tuple[Mapping[str, Any], ...] = ()
    published_version: int | None = None
    last_error: FaifthError | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "request_id": self.request_id,
            "sequence": self.sequence,
            "source": self.source,
            "word": _serialize(self.word),
            "content_hash": self.content_hash,
            "dependency_fingerprint": [
                {"name": name, "fingerprint": fingerprint}
                for name, fingerprint in self.dependency_fingerprint
            ],
            "status": self.status,
            "tests_passed": self.tests_passed,
            "tests_total": self.tests_total,
            "tests_passed_count": self.tests_passed_count,
            "test_results": [_serialize(dict(item)) for item in self.test_results],
            "published_version": self.published_version,
            "last_error": (
                None if self.last_error is None else self.last_error.to_dict()
            ),
        }


@dataclass(slots=True)
class ProtocolSessionState:
    session_id: str
    interpreter: Any
    capabilities: CapabilitySet
    default_budget: Any
    stack: list[Any] = field(default_factory=list)
    repository_ids: tuple[str, ...] = ()
    candidate_sequence: int = 0
    active_versions: dict[str, int] = field(default_factory=dict)
    candidates: dict[str, ProtocolCandidate] = field(default_factory=dict)
    transaction_snapshot: Any = None
    request_cache: dict[str, tuple[str, ProtocolResponse]] = field(default_factory=dict)
    last_result: Any = None
    last_audit: tuple[ProtocolAuditEvent, ...] = ()
    sequence: int = 0

    def next_sequence(self) -> int:
        self.sequence += 1
        return self.sequence

    def next_candidate_id(self) -> str:
        self.candidate_sequence += 1
        return f"candidate-{self.candidate_sequence}"


_ACTION_NAMES = {
    "create_session",
    "close_session",
    "inspect_state",
    "inspect_session",
    "list_words",
    "inspect_word",
    "propose_definition",
    "test_definition",
    "publish_definition",
    "execute",
    "begin_transaction",
    "commit_transaction",
    "rollback_transaction",
    "save_dictionary",
    "load_dictionary",
    "list_versions",
    "restore_version",
}


__all__ = [
    "PROTOCOL_NAME",
    "PROTOCOL_VERSION",
    "ActionName",
    "CandidateStatus",
    "ProtocolAuditEvent",
    "ProtocolCandidate",
    "ProtocolRequest",
    "ProtocolResponse",
    "ProtocolSessionState",
    "ProtocolTestCase",
    "ResponseStatus",
    "SessionSource",
    "TraceMode",
    "WordKind",
    "canonical_json",
    "validate_json_depth",
]
