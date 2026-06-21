# ruff: noqa: E402, I001
"""Phase 7B infrastructure tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.phase7b.infra import (  # noqa: E402
    CAMPAIGN_ID,
    FULL_CAMPAIGN_BUDGETS,
    MODEL_SNAPSHOT,
    PILOT_BUDGETS,
    PILOT_CONDITIONS,
    PILOT_PARALLELISM,
    PILOT_REPETITIONS,
    PILOT_SCENARIO_NAMES,
    RANDOMIZATION_SEED,
    build_pilot_manifest,
    build_pilot_run_keys,
    build_pilot_run_plan,
    build_validation_summary,
    redact_secrets,
    regenerate_derived_artifacts,
    resume_records,
    render_validation_report,
    validate_pilot_records,
    write_jsonl,
)
from experiments.phase7b.runner import prepare_infrastructure  # noqa: E402


def _sample_raw_record(
    run_id: str, scenario_id: str, condition: str, repetition: int
) -> dict:
    return {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "condition": condition,
        "repetition": repetition,
        "status": "ok",
        "success": True,
        "safe_refusal": False,
        "dangerous_failure": False,
        "budget_exhausted": False,
        "expected_result": "ok",
        "observed_result": "ok",
        "initial_state": {"stack": []},
        "final_state": {"stack": [1]},
        "state_restored": True,
        "output_tokens_used": 10,
        "input_tokens_used": 5,
        "model_calls_used": 0,
        "tool_calls_used": 0,
        "provider_retries": 0,
        "wall_time_seconds": 0.1,
        "termination_reason": "completed",
        "error_category": "none",
        "provider_calls": 0,
        "secrets_found": 0,
    }


def test_pilot_manifest_is_deterministic_and_complete() -> None:
    manifest = build_pilot_manifest()
    runs = manifest["runs"]

    assert manifest["campaign_id"] == CAMPAIGN_ID
    assert manifest["provider_calls"] == 0
    assert manifest["secrets_found"] == 0
    assert manifest["parallelism"] == PILOT_PARALLELISM
    assert manifest["repetitions"] == PILOT_REPETITIONS
    assert manifest["conditions"] == list(PILOT_CONDITIONS)
    assert manifest["scenarios"] == list(PILOT_SCENARIO_NAMES)
    assert len(runs) == 18
    assert len({run["run_id"] for run in runs}) == 18
    assert all(run["model_snapshot"] == MODEL_SNAPSHOT for run in runs)
    assert all(run["protocol_hash"] == manifest["protocol_hash"] for run in runs)
    assert [run["randomization_position"] for run in runs] == list(range(1, 19))

    same_manifest = build_pilot_manifest()
    assert same_manifest["runs"] == runs


def test_campaign_id_can_be_overridden_in_a_fresh_process() -> None:
    env = os.environ.copy()
    env["FAIFTH_PHASE7B_CAMPAIGN_ID"] = "phase7b-pilot-002"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from experiments.phase7b.infra import CAMPAIGN_ID; print(CAMPAIGN_ID)",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.stdout.strip() == "phase7b-pilot-002"


def test_pilot_runs_cover_all_conditions_and_scenarios() -> None:
    runs = build_pilot_run_plan()
    combinations = {(run.scenario_id, run.condition, run.repetition) for run in runs}

    assert len(combinations) == 18
    assert {run.scenario_id for run in runs} == set(PILOT_SCENARIO_NAMES)
    assert {run.condition for run in runs} == set(PILOT_CONDITIONS)
    assert {run.repetition for run in runs} == {1, 2}


def test_seed_is_reproducible_and_can_change_order() -> None:
    baseline = build_pilot_run_keys(seed=RANDOMIZATION_SEED)
    same = build_pilot_run_keys(seed=RANDOMIZATION_SEED)
    different = build_pilot_run_keys(seed=RANDOMIZATION_SEED + 1)

    assert baseline == same
    assert baseline != different


def test_resume_deduplicates_completed_runs() -> None:
    first_half = [
        _sample_raw_record(f"run-{index:02d}", "basic_calculation", "python_direct", 1)
        for index in range(1, 10)
    ]
    resumed = resume_records(first_half, first_half + first_half[4:])

    assert len(resumed) == len(first_half)
    assert len({record["run_id"] for record in resumed}) == len(first_half)


def test_redaction_removes_secrets() -> None:
    payload = {
        "api_key": "sk-super-secret-token-1234567890",
        "nested": [{"password": "open-sesame"}, "safe"],
        "prompt": "do not leak sk-another-secret",
    }

    redacted = redact_secrets(payload)

    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"][0]["password"] == "[REDACTED]"
    assert redacted["prompt"] == "[REDACTED]"


def test_artifacts_regenerate_from_raw(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    derived_dir = tmp_path / "derived"
    raw_dir.mkdir()
    records = [
        _sample_raw_record(f"run-{index:02d}", "basic_calculation", "python_direct", 1)
        for index in range(1, 19)
    ]
    write_jsonl(raw_dir / "runs.jsonl", records)

    summary = regenerate_derived_artifacts(raw_dir, derived_dir)

    assert summary["manifest_runs"] == 18
    assert summary["unique_runs"] == 18
    assert summary["conditions"] == 1
    assert summary["scenarios"] == 1
    assert summary["repetitions"] == 1
    assert summary["provider_calls"] == 0
    assert summary["secrets_found"] == 0
    assert (derived_dir / "summary.csv").exists()
    assert (derived_dir / "pilot_validation.md").exists()
    assert (derived_dir / "PILOT_VALIDATION_REPORT.md").exists()


def test_validate_pilot_records_detects_complete_manifest() -> None:
    manifest = build_pilot_manifest()
    records = [
        {
            "campaign_id": manifest["campaign_id"],
            "run_id": run["run_id"],
            "scenario_id": run["scenario_id"],
            "condition": run["condition"],
            "repetition": run["repetition"],
            "randomization_position": run["randomization_position"],
            "protocol_hash": run["protocol_hash"],
            "scenario_hash": run["scenario_hash"],
            "model_snapshot": run["model_snapshot"],
            "status": "ok",
            "success": True,
            "safe_refusal": False,
            "dangerous_failure": False,
            "budget_exhausted": False,
            "expected_result": "ok",
            "observed_result": "ok",
            "initial_state": {},
            "final_state": {},
            "state_restored": True,
            "output_tokens_used": 0,
            "input_tokens_used": 0,
            "model_calls_used": 0,
            "tool_calls_used": 0,
            "provider_retries": 0,
            "wall_time_seconds": 0.0,
            "termination_reason": "completed",
            "error_category": "none",
            "provider_calls": 0,
            "secrets_found": 0,
            "observed_model_snapshot": manifest["model_snapshot"],
        }
        for run in manifest["runs"]
    ]

    summary = validate_pilot_records(manifest, records)
    report = render_validation_report(summary)

    assert summary["decision"] == "PILOT_VALID"
    assert summary["manifest_runs"] == 18
    assert summary["unique_runs"] == 18
    assert "decision: PILOT_VALID" in report


def test_prepare_infrastructure_writes_protocol_and_manifest(tmp_path: Path) -> None:
    manifest = prepare_infrastructure(tmp_path)

    assert (tmp_path / "protocol" / "frozen_protocol.json").exists()
    assert (tmp_path / "manifests" / f"{CAMPAIGN_ID}.json").exists()
    assert manifest["budget_profiles"]["pilot"]["name"] == PILOT_BUDGETS.name
    assert (
        manifest["budget_profiles"]["full_campaign"]["name"]
        == FULL_CAMPAIGN_BUDGETS.name
    )


def test_validation_summary_reports_expected_values() -> None:
    manifest = build_pilot_manifest()
    summary = build_validation_summary(manifest)

    assert summary["manifest_runs"] == 18
    assert summary["unique_runs"] == 18
    assert summary["conditions"] == 3
    assert summary["scenarios"] == 3
    assert summary["repetitions"] == 2
    assert summary["parallelism"] == 1
    assert summary["provider_calls"] == 0
    assert summary["secrets_found"] == 0
