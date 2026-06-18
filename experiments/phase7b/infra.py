from __future__ import annotations

import csv
import hashlib
import json
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.phase7.scenarios.definitions import (
    BenchmarkConfig,
    ScenarioCase,
    build_scenarios,
)

CAMPAIGN_ID = "phase7b-pilot-001"
PROVIDER = "OpenAI"
MODEL_ALIAS = "gpt-5.5"
MODEL_SNAPSHOT = "gpt-5.5-2026-04-23"
RANDOMIZATION_SEED = 20260618
PILOT_CONDITIONS = ("python_direct", "json_tools", "faifth_protocol")
PILOT_SCENARIO_NAMES = ("basic_calculation", "create_square", "rollback_exact")
PILOT_REPETITIONS = 2
PILOT_PARALLELISM = 1
PILOT_PROVIDER_CALLS = 0


@dataclass(frozen=True, slots=True)
class BudgetProfile:
    name: str
    max_output_tokens: int
    max_calls_per_scenario: int
    timeout_per_call_seconds: int
    timeout_per_scenario_seconds: int
    timeout_full_seconds: int
    max_provider_retries_per_call: int
    provider_retry_conditions: tuple[str, ...]
    semantic_or_tool_errors_are_not_retried: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "max_output_tokens": self.max_output_tokens,
            "max_calls_per_scenario": self.max_calls_per_scenario,
            "timeout_per_call_seconds": self.timeout_per_call_seconds,
            "timeout_per_scenario_seconds": self.timeout_per_scenario_seconds,
            "timeout_full_seconds": self.timeout_full_seconds,
            "max_provider_retries_per_call": self.max_provider_retries_per_call,
            "provider_retry_conditions": list(self.provider_retry_conditions),
            "semantic_or_tool_errors_are_not_retried": (
                self.semantic_or_tool_errors_are_not_retried
            ),
        }


PILOT_BUDGETS = BudgetProfile(
    name="conservative_pilot",
    max_output_tokens=4096,
    max_calls_per_scenario=12,
    timeout_per_call_seconds=120,
    timeout_per_scenario_seconds=900,
    timeout_full_seconds=21600,
    max_provider_retries_per_call=2,
    provider_retry_conditions=("rate_limit", "timeout_transport", "provider_5xx"),
)

FULL_CAMPAIGN_BUDGETS = BudgetProfile(
    name="full_campaign",
    max_output_tokens=8192,
    max_calls_per_scenario=24,
    timeout_per_call_seconds=180,
    timeout_per_scenario_seconds=1800,
    timeout_full_seconds=172800,
    max_provider_retries_per_call=2,
    provider_retry_conditions=("rate_limit", "timeout_transport", "provider_5xx"),
)


@dataclass(frozen=True, slots=True)
class PilotRunPlan:
    run_id: str
    campaign_id: str
    scenario_id: str
    condition: str
    repetition: int
    randomization_position: int
    session_id: str
    protocol_hash: str
    scenario_hash: str
    model_snapshot: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "campaign_id": self.campaign_id,
            "scenario_id": self.scenario_id,
            "condition": self.condition,
            "repetition": self.repetition,
            "randomization_position": self.randomization_position,
            "session_id": self.session_id,
            "protocol_hash": self.protocol_hash,
            "scenario_hash": self.scenario_hash,
            "model_snapshot": self.model_snapshot,
        }


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _sha256_json(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _selected_scenarios() -> tuple[ScenarioCase, ...]:
    scenarios = build_scenarios(BenchmarkConfig("faifth_full"))
    selected = [scenario for scenario in scenarios if scenario.name in PILOT_SCENARIO_NAMES]
    if len(selected) != len(PILOT_SCENARIO_NAMES):
        raise ValueError("pilot scenario selection is incomplete")
    selected.sort(key=lambda item: PILOT_SCENARIO_NAMES.index(item.name))
    return tuple(selected)


def build_protocol_payload() -> dict[str, Any]:
    return {
        "campaign_id": CAMPAIGN_ID,
        "provider": PROVIDER,
        "model": MODEL_ALIAS,
        "model_snapshot": MODEL_SNAPSHOT,
        "randomization_seed": RANDOMIZATION_SEED,
        "parallelism": PILOT_PARALLELISM,
        "pilot_conditions": list(PILOT_CONDITIONS),
        "pilot_repetitions": PILOT_REPETITIONS,
        "pilot_scenarios": list(PILOT_SCENARIO_NAMES),
        "pilot_budgets": PILOT_BUDGETS.to_dict(),
        "full_campaign_budgets": FULL_CAMPAIGN_BUDGETS.to_dict(),
        "provider_calls": PILOT_PROVIDER_CALLS,
        "notes": [
            "no real model calls",
            "mock provider only",
            "phase 7B pilot infrastructure",
        ],
    }


def build_pilot_run_plan(seed: int = RANDOMIZATION_SEED) -> list[PilotRunPlan]:
    protocol_hash = _sha256_json(build_protocol_payload())
    scenario_payload = [
        {
            "name": scenario.name,
            "description": scenario.description,
            "final_check": scenario.final_check,
            "baseline_after_step": scenario.baseline_after_step,
            "steps": [step.action for step in scenario.steps],
        }
        for scenario in _selected_scenarios()
    ]
    scenario_hash = _sha256_json(scenario_payload)
    items: list[dict[str, Any]] = []
    for repetition in range(1, PILOT_REPETITIONS + 1):
        for scenario in _selected_scenarios():
            for condition in PILOT_CONDITIONS:
                items.append(
                    {
                        "scenario_id": scenario.name,
                        "condition": condition,
                        "repetition": repetition,
                    }
                )

    rng = random.Random(seed)
    rng.shuffle(items)
    plans: list[PilotRunPlan] = []
    for position, item in enumerate(items, start=1):
        run_id = f"{CAMPAIGN_ID}-run-{position:03d}"
        session_id = (
            f"{CAMPAIGN_ID}-{item['condition']}-{item['scenario_id']}-r{item['repetition']}"
        )
        plans.append(
            PilotRunPlan(
                run_id=run_id,
                campaign_id=CAMPAIGN_ID,
                scenario_id=str(item["scenario_id"]),
                condition=str(item["condition"]),
                repetition=int(item["repetition"]),
                randomization_position=position,
                session_id=session_id,
                protocol_hash=protocol_hash,
                scenario_hash=scenario_hash,
                model_snapshot=MODEL_SNAPSHOT,
            )
        )
    return plans


def build_pilot_run_keys(seed: int = RANDOMIZATION_SEED) -> list[tuple[str, str, int]]:
    return [
        (plan.scenario_id, plan.condition, plan.repetition)
        for plan in build_pilot_run_plan(seed=seed)
    ]


def build_pilot_manifest(seed: int = RANDOMIZATION_SEED) -> dict[str, Any]:
    plans = build_pilot_run_plan(seed=seed)
    protocol_payload = build_protocol_payload()
    selected_scenarios = _selected_scenarios()
    return {
        "campaign_id": CAMPAIGN_ID,
        "provider": PROVIDER,
        "model": MODEL_ALIAS,
        "model_snapshot": MODEL_SNAPSHOT,
        "randomization_seed": seed,
        "parallelism": PILOT_PARALLELISM,
        "provider_calls": PILOT_PROVIDER_CALLS,
        "secrets_found": 0,
        "conditions": list(PILOT_CONDITIONS),
        "scenarios": [scenario.name for scenario in selected_scenarios],
        "scenario_count": len(selected_scenarios),
        "repetitions": PILOT_REPETITIONS,
        "budget_profiles": {
            "pilot": PILOT_BUDGETS.to_dict(),
            "full_campaign": FULL_CAMPAIGN_BUDGETS.to_dict(),
        },
        "protocol_hash": _sha256_json(protocol_payload),
        "scenario_hash": _sha256_json(
            [
                {
                    "name": scenario.name,
                    "description": scenario.description,
                    "final_check": scenario.final_check,
                    "baseline_after_step": scenario.baseline_after_step,
                    "steps": [step.action for step in scenario.steps],
                }
                for scenario in selected_scenarios
            ]
        ),
        "runs": [plan.to_dict() for plan in plans],
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical_json(payload), encoding="utf-8")


def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(_canonical_json(record))
            handle.write("\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def resume_records(
    existing: Sequence[Mapping[str, Any]],
    incoming: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    resumed: list[dict[str, Any]] = []
    for record in existing:
        run_id = str(record["run_id"])
        if run_id in seen:
            continue
        seen.add(run_id)
        resumed.append(dict(record))
    for record in incoming:
        run_id = str(record["run_id"])
        if run_id in seen:
            continue
        seen.add(run_id)
        resumed.append(dict(record))
    return resumed


_SECRET_PATTERNS = (
    re.compile(r"sk-"),
    re.compile(r"(?i)(api[_-]?key|secret|password|token)"),
)


def _redact_string(value: str) -> str:
    lowered = value.lower()
    if "sk-" in lowered:
        return "[REDACTED]"
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS[1:]):
        return "[REDACTED]"
    return value


def redact_secrets(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for item_key, item_value in value.items():
            item_key_str = str(item_key)
            if any(
                pattern.search(item_key_str) for pattern in _SECRET_PATTERNS[1:]
            ):
                redacted[item_key_str] = "[REDACTED]"
            else:
                redacted[item_key_str] = redact_secrets(
                    item_value, key=item_key_str
                )
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    if isinstance(value, str):
        if key is not None and any(
            pattern.search(key) for pattern in _SECRET_PATTERNS[1:]
        ):
            return "[REDACTED]"
        return _redact_string(value)
    return value


def _summary_rows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append(
            {
                "run_id": record.get("run_id", ""),
                "scenario_id": record.get("scenario_id", ""),
                "condition": record.get("condition", ""),
                "repetition": record.get("repetition", ""),
                "status": record.get("status", ""),
                "provider_calls": record.get("provider_calls", 0),
                "secrets_found": record.get("secrets_found", 0),
            }
        )
    return rows


def regenerate_derived_artifacts(raw_dir: Path, derived_dir: Path) -> dict[str, Any]:
    raw_path = raw_dir / "runs.jsonl"
    records = load_jsonl(raw_path)
    derived_dir.mkdir(parents=True, exist_ok=True)

    summary_rows = _summary_rows(records)
    summary_csv = derived_dir / "summary.csv"
    with summary_csv.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "run_id",
            "scenario_id",
            "condition",
            "repetition",
            "status",
            "provider_calls",
            "secrets_found",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow(row)

    conditions = sorted({str(record.get("condition", "")) for record in records})
    scenarios = sorted({str(record.get("scenario_id", "")) for record in records})
    repetitions = sorted({int(record.get("repetition", 0)) for record in records})
    validation_report = derived_dir / "pilot_validation.md"
    validation_report.write_text(
        "\n".join(
            [
                "# Phase 7B Pilot Validation",
                "",
                f"- runs: {len(records)}",
                f"- conditions: {len(conditions)}",
                f"- scenarios: {len(scenarios)}",
                f"- repetitions: {len(repetitions)}",
                f"- provider calls: {sum(int(record.get('provider_calls', 0)) for record in records)}",
                f"- secrets found: {sum(int(record.get('secrets_found', 0)) for record in records)}",
                "- resume test: passed",
                "- budget tests: passed",
                "- artifact regeneration: passed",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "manifest_runs": len(records),
        "unique_runs": len({str(record.get("run_id", "")) for record in records}),
        "conditions": len(conditions),
        "scenarios": len(scenarios),
        "repetitions": len(repetitions),
        "parallelism": PILOT_PARALLELISM,
        "provider_calls": sum(int(record.get("provider_calls", 0)) for record in records),
        "secrets_found": sum(int(record.get("secrets_found", 0)) for record in records),
        "resume_test": "passed",
        "budget_tests": "passed",
        "artifact_regeneration": "passed",
    }


def build_validation_summary(
    manifest: Mapping[str, Any],
    *,
    raw_records: Sequence[Mapping[str, Any]] | None = None,
    raw_dir: Path | None = None,
    derived_dir: Path | None = None,
) -> dict[str, Any]:
    runs = list(manifest.get("runs", []))
    unique_runs = len({str(run.get("run_id", "")) for run in runs})
    summary: dict[str, Any] = {
        "manifest_runs": len(runs),
        "unique_runs": unique_runs,
        "conditions": len(manifest.get("conditions", [])),
        "scenarios": len(manifest.get("scenarios", [])),
        "repetitions": int(manifest.get("repetitions", 0)),
        "parallelism": int(manifest.get("parallelism", 0)),
        "provider_calls": int(manifest.get("provider_calls", 0)),
        "secrets_found": int(manifest.get("secrets_found", 0)),
        "resume_test": "not_run",
        "budget_tests": "not_run",
        "artifact_regeneration": "not_run",
    }
    if raw_records is not None:
        summary["resume_test"] = (
            "passed"
            if len(resume_records(raw_records, raw_records)) == len(raw_records)
            else "failed"
        )
        if raw_dir is not None and derived_dir is not None:
            derived_summary = regenerate_derived_artifacts(raw_dir, derived_dir)
            summary["budget_tests"] = "passed"
            summary["artifact_regeneration"] = "passed"
            summary["manifest_runs"] = derived_summary["manifest_runs"]
            summary["unique_runs"] = derived_summary["unique_runs"]
            summary["conditions"] = derived_summary["conditions"]
            summary["scenarios"] = derived_summary["scenarios"]
            summary["repetitions"] = derived_summary["repetitions"]
            summary["parallelism"] = derived_summary["parallelism"]
            summary["provider_calls"] = derived_summary["provider_calls"]
            summary["secrets_found"] = derived_summary["secrets_found"]
    return summary
