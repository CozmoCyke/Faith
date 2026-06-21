from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from experiments.phase7b.infra import (
    MODEL_SNAPSHOT,
    PILOT_BUDGETS,
    PILOT_CONDITIONS,
    PILOT_REPETITIONS,
    PILOT_SCENARIO_NAMES,
    RANDOMIZATION_SEED,
    build_protocol_hash,
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def _run_record(
    *,
    campaign_id: str,
    run_id: str,
    scenario_id: str,
    condition: str,
    repetition: int,
    randomization_position: int,
    protocol_hash: str,
    status: str = "ok",
    success: bool = True,
    provider_calls: int = 0,
    provider_retries: int = 0,
    error_category: str = "none",
    termination_reason: str = "completed",
    secret: bool = False,
    wall_time_seconds: float = 0.1,
) -> dict[str, Any]:
    prompt = "safe prompt"
    if secret:
        prompt = "sk-test-secret-token"
    return {
        "campaign_id": campaign_id,
        "run_id": run_id,
        "scenario_id": scenario_id,
        "condition": condition,
        "repetition": repetition,
        "randomization_position": randomization_position,
        "protocol_hash": protocol_hash,
        "scenario_hash": "scenario-hash",
        "model_snapshot": MODEL_SNAPSHOT,
        "status": status,
        "success": success,
        "safe_refusal": False,
        "dangerous_failure": False,
        "budget_exhausted": termination_reason == "budget_exhausted",
        "expected_result": "ok",
        "observed_result": "ok",
        "initial_state": {"stack": []},
        "final_state": {"stack": [1]},
        "state_restored": True,
        "output_tokens_used": 10,
        "input_tokens_used": 5,
        "model_calls_used": provider_calls,
        "tool_calls_used": 0,
        "provider_retries": provider_retries,
        "wall_time_seconds": wall_time_seconds,
        "termination_reason": termination_reason,
        "error_category": error_category,
        "provider_calls": provider_calls,
        "secrets_found": 1 if secret else 0,
        "observed_model_snapshot": MODEL_SNAPSHOT,
        "system_prompt": "system",
        "user_prompt": prompt,
        "response_text": "ok",
        "provider_error": "",
        "mode": "live",
    }


def build_complete_runs(
    campaign_id: str,
    *,
    protocol_hash: str | None = None,
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    resolved_protocol_hash = protocol_hash or build_protocol_hash()
    position = 1
    for repetition in range(1, PILOT_REPETITIONS + 1):
        for scenario_id in PILOT_SCENARIO_NAMES:
            for condition in PILOT_CONDITIONS:
                runs.append(
                    _run_record(
                        campaign_id=campaign_id,
                        run_id=f"{campaign_id}-run-{position:03d}",
                        scenario_id=scenario_id,
                        condition=condition,
                        repetition=repetition,
                        randomization_position=position,
                        protocol_hash=resolved_protocol_hash,
                    )
                )
                position += 1
    return runs


def build_campaign(
    root: Path,
    *,
    campaign_id: str,
    runs: list[dict[str, Any]] | None = None,
    include_transcripts: bool = True,
    include_manifest: bool = True,
    include_protocol: bool = True,
    include_preflight: bool = True,
    include_validation_report: bool = True,
    protocol_hash: str | None = None,
) -> Path:
    campaign_dir = root / campaign_id
    campaign_dir.mkdir(parents=True, exist_ok=True)
    resolved_protocol_hash = protocol_hash or build_protocol_hash()
    records = runs or build_complete_runs(
        campaign_id, protocol_hash=resolved_protocol_hash
    )
    if include_preflight:
        _write_json(
            campaign_dir / "logs" / "preflight.json",
            {
                "campaign_id": campaign_id,
                "protocol_hash": resolved_protocol_hash,
                "model_snapshot": MODEL_SNAPSHOT,
                "budget_profile": PILOT_BUDGETS.name,
                "randomization_seed": RANDOMIZATION_SEED,
                "run_count": len(records),
                "parallelism": 1,
            },
        )
    if include_manifest:
        _write_json(
            campaign_dir / "manifests" / f"{campaign_id}.json",
            {
                "campaign_id": campaign_id,
                "conditions": list(PILOT_CONDITIONS),
                "scenarios": list(PILOT_SCENARIO_NAMES),
                "repetitions": PILOT_REPETITIONS,
                "parallelism": 1,
                "model_snapshot": MODEL_SNAPSHOT,
                "protocol_hash": resolved_protocol_hash,
                "randomization_seed": RANDOMIZATION_SEED,
                "runs": records,
            },
        )
    if include_protocol:
        _write_json(
            campaign_dir / "protocol" / "frozen_protocol.json",
            {
                "campaign_id": campaign_id,
                "model_snapshot": MODEL_SNAPSHOT,
                "protocol_hash": resolved_protocol_hash,
                "temperature": "omitted",
            },
        )
    _write_jsonl(campaign_dir / "raw" / "runs.jsonl", records)
    if include_transcripts:
        transcripts_dir = campaign_dir / "raw" / "transcripts"
        for record in records:
            _write_jsonl(
                transcripts_dir / f"{record['run_id']}.jsonl",
                [
                    {
                        "run_id": record["run_id"],
                        "mode": record["mode"],
                        "request": {
                            "system_prompt": record["system_prompt"],
                            "user_prompt": record["user_prompt"],
                            "tools": [],
                        },
                        "response": {
                            "model": record["model_snapshot"],
                            "output_text": record["response_text"],
                            "tool_calls": [],
                        },
                        "error_category": record["error_category"],
                        "provider_calls": record["provider_calls"],
                        "provider_retries": record["provider_retries"],
                    }
                ],
            )
    if include_validation_report:
        _write_json(
            campaign_dir / "derived" / "integrity_report.json",
            {"note": "synthetic"},
        )
        (campaign_dir / "derived" / "PILOT_VALIDATION_REPORT.md").write_text(
            "# synthetic report\n",
            encoding="utf-8",
        )
    return campaign_dir


def make_missing_run_campaign(root: Path, *, campaign_id: str) -> Path:
    runs = build_complete_runs(campaign_id)
    return build_campaign(root, campaign_id=campaign_id, runs=runs[:-1])


def make_duplicate_run_campaign(root: Path, *, campaign_id: str) -> Path:
    runs = build_complete_runs(campaign_id)
    runs.append(runs[0])
    return build_campaign(root, campaign_id=campaign_id, runs=runs)


def make_secret_campaign(root: Path, *, campaign_id: str) -> Path:
    runs = build_complete_runs(campaign_id)
    runs[0] = _run_record(
        campaign_id=campaign_id,
        run_id=f"{campaign_id}-run-001",
        scenario_id=PILOT_SCENARIO_NAMES[0],
        condition=PILOT_CONDITIONS[0],
        repetition=1,
        randomization_position=1,
        protocol_hash=build_protocol_hash(),
        secret=True,
    )
    return build_campaign(root, campaign_id=campaign_id, runs=runs)
