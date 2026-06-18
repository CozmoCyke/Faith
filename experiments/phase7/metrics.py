from __future__ import annotations

import csv
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def canonical_json(payload: Any) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def json_bytes(payload: Any) -> int:
    return len(canonical_json(payload).encode("utf-8"))


def estimate_tokens(byte_count: int) -> int:
    return max(1, math.ceil(byte_count / 4))


def canonical_state(snapshot: Mapping[str, Any]) -> str:
    return canonical_json(snapshot)


def state_bytes(snapshot: Mapping[str, Any]) -> int:
    return json_bytes(snapshot)


def state_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return canonical_state(left) == canonical_state(right)


def response_audit_quality(audit: Sequence[Mapping[str, Any]]) -> str:
    if not audit:
        return "empty"
    required = {"kind", "status"}
    covered = sum(1 for item in audit if required.issubset(item))
    if covered == len(audit):
        return "complete"
    if covered:
        return "partial"
    return "missing"


def classify_error(error: Mapping[str, Any] | None) -> str:
    if error is None:
        return "none"
    code = str(error.get("code", "")).lower()
    message = str(error.get("message", "")).lower()
    if "budget" in code or "budget" in message:
        return "budget_exceeded"
    if "capability" in code or "permission" in code or "forbidden" in message:
        return "forbidden_action"
    if "underflow" in code or "type" in code or "mismatch" in code:
        return "state_error"
    if "version" in code or "persist" in code or "storage" in code:
        return "persistence_error"
    if "word" in code or "word" in message:
        return "state_error"
    return "error"


@dataclass(frozen=True, slots=True)
class ScenarioOutcome:
    adapter: str
    scenario: str
    status: str
    expected: str
    observed: str
    success: bool
    state_before: Mapping[str, Any]
    state_after: Mapping[str, Any]
    request_bytes: int
    response_bytes: int
    token_estimate: int
    request_count: int
    step_count: int
    steps_used: int
    corrections: int
    rollback_exact: bool | None
    action_blocked: bool
    audit_quality: str
    duration_ms: float
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "scenario": self.scenario,
            "variant": self.extra.get("variant"),
            "status": self.status,
            "outcome": self.status,
            "expected": self.expected,
            "observed": self.observed,
            "success": self.success,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "request_bytes": self.request_bytes,
            "response_bytes": self.response_bytes,
            "token_estimate": self.token_estimate,
            "request_count": self.request_count,
            "step_count": self.step_count,
            "steps_used": self.steps_used,
            "corrections": self.corrections,
            "rollback_exact": self.rollback_exact,
            "action_blocked": self.action_blocked,
            "audit_quality": self.audit_quality,
            "duration_ms": self.duration_ms,
            "extra": dict(self.extra),
        }


@dataclass(frozen=True, slots=True)
class BenchmarkRecord:
    adapter: str
    scenario: str
    variant: str
    request_json: str
    response_json: str
    request_bytes: int
    response_bytes: int
    token_estimate: int
    duration_ms: float
    outcome: str
    error_category: str
    audit_quality: str
    request_id: str
    step_index: int
    total_steps: int
    state_before: Mapping[str, Any]
    state_after: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "scenario": self.scenario,
            "variant": self.variant,
            "request_json": self.request_json,
            "response_json": self.response_json,
            "request_bytes": self.request_bytes,
            "response_bytes": self.response_bytes,
            "token_estimate": self.token_estimate,
            "duration_ms": self.duration_ms,
            "outcome": self.outcome,
            "error_category": self.error_category,
            "audit_quality": self.audit_quality,
            "request_id": self.request_id,
            "step_index": self.step_index,
            "total_steps": self.total_steps,
            "state_before": self.state_before,
            "state_after": self.state_after,
        }


def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(canonical_json(record))
            handle.write("\n")


def write_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    fieldnames = [
        "adapter",
        "scenario",
        "variant",
        "outcome",
        "error_category",
        "audit_quality",
        "request_bytes",
        "response_bytes",
        "token_estimate",
        "duration_ms",
        "request_id",
        "step_index",
        "total_steps",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({name: record.get(name, "") for name in fieldnames})


def render_summary(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for record in records:
        key = (str(record["adapter"]), str(record["variant"]))
        grouped.setdefault(key, []).append(record)

    lines: list[str] = [
        "# Phase 7A Benchmark Summary",
        "",
        "## Per Adapter",
        "",
    ]
    for (adapter, variant), items in sorted(grouped.items()):
        successes = sum(1 for item in items if item["outcome"] == "ok")
        failures = len(items) - successes
        avg_tokens = sum(int(item["token_estimate"]) for item in items) / len(items)
        avg_duration = sum(float(item["duration_ms"]) for item in items) / len(items)
        lines.extend(
            [
                f"### {adapter} / {variant}",
                "",
                f"- scenarios: {len(items)}",
                f"- successes: {successes}",
                f"- failures: {failures}",
                f"- mean token estimate: {avg_tokens:.1f}",
                f"- mean duration ms: {avg_duration:.2f}",
                "",
            ]
        )

    path.write_text("\n".join(lines), encoding="utf-8")
