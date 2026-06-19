# ruff: noqa: E402, I001
"""Phase 7B pilot workflow tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.phase7b.infra import build_pilot_manifest  # noqa: E402
from experiments.phase7b.pilot import prepare_campaign, validate_campaign  # noqa: E402


def test_prepare_campaign_writes_protocol_and_manifest(tmp_path: Path) -> None:
    manifest = prepare_campaign(tmp_path)

    assert manifest["campaign_id"] == "phase7b-pilot-001"
    assert (tmp_path / "protocol" / "frozen_protocol.json").exists()
    assert (tmp_path / "manifests" / "phase7b-pilot-001.json").exists()


def test_validate_campaign_writes_validation_report(tmp_path: Path) -> None:
    manifest = build_pilot_manifest()
    (tmp_path / "manifests").mkdir(parents=True)
    (tmp_path / "manifests" / "phase7b-pilot-001.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    records = []
    for run in manifest["runs"]:
        records.append(
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
        )
    (raw_dir / "runs.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    summary = validate_campaign(tmp_path)

    assert summary["decision"] == "PILOT_VALID"
    assert (tmp_path / "derived" / "PILOT_VALIDATION_REPORT.md").exists()
