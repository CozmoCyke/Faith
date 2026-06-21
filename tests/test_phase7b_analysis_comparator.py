from __future__ import annotations

from pathlib import Path

from experiments.phase7b.analysis.comparator import compare_campaign_runs
from experiments.phase7b.analysis.loader import load_campaign_artifacts
from tests.phase7b_analysis_fixtures import build_campaign


def test_comparator_pairs_runs_by_scenario_and_repetition(tmp_path: Path) -> None:
    campaign_dir = build_campaign(tmp_path, campaign_id="compare-campaign")
    artifacts = load_campaign_artifacts(campaign_dir)

    comparison = compare_campaign_runs(artifacts.runs)

    assert comparison["summary"]["paired_groups"] == 6
    assert comparison["summary"]["success_concordant"] == 6
    assert len(comparison["rows"]) == 6
    assert comparison["rows"][0]["python_success"] is True
