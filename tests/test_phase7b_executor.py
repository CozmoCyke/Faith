# ruff: noqa: E402, I001
"""Phase 7B executor tests."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import experiments.phase7b.pilot as pilot_module  # noqa: E402
import experiments.phase7b.runner as runner_module  # noqa: E402
from experiments.phase7.scenarios.definitions import (  # noqa: E402
    BenchmarkConfig,
    build_scenarios,
)
from experiments.phase7b.infra import (  # noqa: E402
    CAMPAIGN_ID,
    MODEL_SNAPSHOT,
    build_pilot_manifest,
    validate_pilot_records,
)
from experiments.phase7b.pilot import (  # noqa: E402
    SIMULATION_DECISION,
    OpenAIProviderConfiguration,
    PilotRunResult,
    _execute_live_run,
    load_openai_api_key,
    run_pilot_campaign,
    validate_campaign,
)


def _completed_record(run: dict[str, object]) -> dict[str, object]:
    return {
        "campaign_id": run["campaign_id"],
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
        "initial_state": {"stack": []},
        "final_state": {"stack": []},
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
        "observed_model_snapshot": run["model_snapshot"],
    }


def test_env_local_loader_reads_only_openai_api_key(tmp_path: Path) -> None:
    (tmp_path / ".env.local").write_text(
        "OPENAI_API_KEY=test-key\nOPENAI_ORG_ID=org-123\n", encoding="utf-8"
    )

    assert load_openai_api_key(tmp_path) == "test-key"


def test_env_local_is_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-q", ".env.local"],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_dirty_worktree_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_result = SimpleNamespace(stdout=" M experiments/phase7b/pilot.py\n")

    def fake_run(*_: object, **__: object) -> SimpleNamespace:
        return fake_result

    monkeypatch.setattr(pilot_module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="worktree must be clean"):
        pilot_module._ensure_clean_worktree(Path.cwd())


def test_dry_run_executes_all_runs_and_redacts_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "sk-test-secret-7b"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.setattr(pilot_module, "_ensure_clean_worktree", lambda _: None)

    summary = run_pilot_campaign(tmp_path, mode="dry-run")

    assert summary["manifest_runs"] == 18
    assert summary["provider_calls"] == 0
    assert summary["resume_test"] == "passed"
    assert summary["parallelism"] == 1
    assert summary["secrets_found"] == 0
    assert summary["decision"] == SIMULATION_DECISION
    assert (tmp_path / "derived" / "PILOT_VALIDATION_REPORT.md").exists()
    assert SIMULATION_DECISION in (
        tmp_path / "derived" / "PILOT_VALIDATION_REPORT.md"
    ).read_text(encoding="utf-8")

    raw_text = (tmp_path / "raw" / "runs.jsonl").read_text(encoding="utf-8")
    assert secret not in raw_text
    assert "sk-" not in raw_text
    assert "sk-" not in (tmp_path / "logs" / "preflight.json").read_text(
        encoding="utf-8"
    )
    assert CAMPAIGN_ID in (tmp_path / "logs" / "execution.log").read_text(
        encoding="utf-8"
    )


def test_dry_run_cli_prints_expected_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(pilot_module, "_ensure_clean_worktree", lambda _: None)
    runner_module.main(["--output-root", str(tmp_path), "--dry-run"])
    output = capsys.readouterr().out

    assert "campaign_id: phase7b-pilot-001" in output
    assert "runs: 18" in output
    assert "model snapshot: gpt-5.5-2026-04-23" in output
    assert "protocol hash: unchanged" in output
    assert "parallelism: 1" in output
    assert "provider calls: 0" in output
    assert "secrets found: 0" in output
    assert "resume test: passed" in output
    assert "validation report: PILOT_VALID_SIMULATION" in output


def test_resume_skips_completed_runs_without_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pilot_module, "_ensure_clean_worktree", lambda _: None)
    original = cast(Callable[..., PilotRunResult], pilot_module._execute_mock_run)
    call_count = {"value": 0}

    def interrupted(*args: object, **kwargs: object) -> PilotRunResult:
        call_count["value"] += 1
        result = original(*args, **kwargs)
        if call_count["value"] == 1:
            return replace(result, halt_after=True)
        return result

    monkeypatch.setattr(pilot_module, "_execute_mock_run", interrupted)
    summary = run_pilot_campaign(tmp_path, mode="dry-run")
    assert summary["manifest_runs"] == 1

    monkeypatch.setattr(pilot_module, "_execute_mock_run", original)
    summary = run_pilot_campaign(tmp_path, mode="dry-run", resume=True)
    assert summary["manifest_runs"] == 18

    raw_lines = (
        (tmp_path / "raw" / "runs.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(raw_lines) == 18
    run_ids = {json.loads(line)["run_id"] for line in raw_lines if line.strip()}
    assert len(run_ids) == 18


def test_validate_campaign_is_invalid_when_a_run_is_missing(
    tmp_path: Path,
) -> None:
    manifest = build_pilot_manifest()
    (tmp_path / "manifests").mkdir(parents=True)
    (tmp_path / "manifests" / f"{CAMPAIGN_ID}.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (tmp_path / "raw").mkdir()
    records = [_completed_record(run) for run in manifest["runs"][:-1]]
    (tmp_path / "raw" / "runs.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    validation = validate_pilot_records(manifest, records)
    report = validate_campaign(tmp_path)["decision"]

    assert validation["decision"] == "PILOT_INVALID"
    assert report == "PILOT_INVALID"


def test_live_run_retries_provider_errors(tmp_path: Path) -> None:
    manifest = build_pilot_manifest()
    run = manifest["runs"][0]
    scenario = build_scenarios(BenchmarkConfig("faifth_full"))[0]

    class RetryableError(RuntimeError):
        status_code = 429

    class FlakyResponses:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, **_: object) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                raise RetryableError("too many requests")
            return {
                "model": MODEL_SNAPSHOT,
                "output_text": "ok",
                "usage": {"input_tokens": 3, "output_tokens": 7},
                "tool_calls": [],
            }

    class FlakyClient:
        def __init__(self) -> None:
            self.responses = FlakyResponses()

    result = _execute_live_run(
        run=run,
        scenario=scenario,
        client=FlakyClient(),
        configuration=OpenAIProviderConfiguration(),
    )

    assert result.record["provider_retries"] == 1
    assert result.record["provider_calls"] == 2
    assert result.record["status"] == "ok"
    assert result.record["error_category"] == "none"
    assert result.record["output_tokens_used"] == 7
    assert result.record["input_tokens_used"] == 3


def test_live_mode_requires_openai_api_key_before_first_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pilot_module, "_ensure_clean_worktree", lambda _: None)
    monkeypatch.setattr(
        pilot_module,
        "LIVE_PROTOCOL_HASH",
        build_pilot_manifest()["protocol_hash"],
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        run_pilot_campaign(tmp_path, mode="live")


def test_live_mode_refuses_protocol_or_snapshot_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_prepare = pilot_module.prepare_campaign
    monkeypatch.setattr(pilot_module, "_ensure_clean_worktree", lambda _: None)
    monkeypatch.setattr(
        pilot_module,
        "LIVE_PROTOCOL_HASH",
        build_pilot_manifest()["protocol_hash"],
    )

    def bad_prepare(
        output_root: Path, *, protocol_hash: str | None = None
    ) -> dict[str, object]:
        return original_prepare(
            output_root, protocol_hash="wrong-protocol-hash"
        )

    monkeypatch.setattr(pilot_module, "prepare_campaign", bad_prepare)

    with pytest.raises(RuntimeError, match="protocol hash mismatch"):
        run_pilot_campaign(tmp_path / "protocol-check", mode="live")

    monkeypatch.setattr(pilot_module, "prepare_campaign", original_prepare)
    monkeypatch.setattr(
        pilot_module,
        "MODEL_SNAPSHOT",
        "gpt-5.5-override",
    )

    with pytest.raises(RuntimeError, match="model snapshot mismatch"):
        run_pilot_campaign(tmp_path / "snapshot-check", mode="live")
