from __future__ import annotations

from pathlib import Path

from experiments.phase7b.analysis.loader import load_campaign_artifacts
from experiments.phase7b.analysis.validator import validate_campaign_artifacts
from tests.phase7b_analysis_fixtures import (
    build_campaign,
    make_duplicate_run_campaign,
    make_missing_run_campaign,
    make_secret_campaign,
)


def test_validator_marks_complete_campaign_valid(tmp_path: Path) -> None:
    campaign_dir = build_campaign(tmp_path, campaign_id="complete-campaign")
    artifacts = load_campaign_artifacts(campaign_dir)

    report = validate_campaign_artifacts(artifacts)

    assert report["state"] == "COMPLETE_VALID"
    assert report["complete_runs"] == 18
    assert report["secret_leaks"] == 0


def test_validator_marks_missing_run_campaign_incomplete(tmp_path: Path) -> None:
    campaign_dir = make_missing_run_campaign(tmp_path, campaign_id="missing-run")
    artifacts = load_campaign_artifacts(campaign_dir)

    report = validate_campaign_artifacts(artifacts)

    assert report["state"] == "INCOMPLETE_VALIDLY_RECORDED"
    assert report["expected_runs"] == 18
    assert any(issue["code"] == "missing_runs" for issue in report["issues"])


def test_validator_detects_duplicate_runs(tmp_path: Path) -> None:
    campaign_dir = make_duplicate_run_campaign(tmp_path, campaign_id="duplicate-run")
    artifacts = load_campaign_artifacts(campaign_dir)

    report = validate_campaign_artifacts(artifacts)

    assert any(issue["code"] == "duplicate_runs" for issue in report["issues"])
    assert report["state"] in {"COMPLETE_INVALID", "CORRUPTED"}


def test_validator_detects_secret_leak(tmp_path: Path) -> None:
    campaign_dir = make_secret_campaign(tmp_path, campaign_id="secret-campaign")
    artifacts = load_campaign_artifacts(campaign_dir)

    report = validate_campaign_artifacts(artifacts)

    assert report["secret_leaks"] > 0
    assert any(issue["code"] == "secret_leak" for issue in report["issues"])
    assert report["state"] == "CORRUPTED"
