from __future__ import annotations

from pathlib import Path

from experiments.phase7b.analysis.loader import load_campaign_artifacts
from experiments.phase7b.analysis.metrics import compute_campaign_metrics
from tests.phase7b_analysis_fixtures import build_campaign


def test_metrics_compute_descriptive_summaries(tmp_path: Path) -> None:
    campaign_dir = build_campaign(tmp_path, campaign_id="metrics-campaign")
    artifacts = load_campaign_artifacts(campaign_dir)

    metrics = compute_campaign_metrics(artifacts.runs)

    assert metrics["totals"]["run_count"] == 18
    assert metrics["totals"]["success_count"] == 18
    assert metrics["by_condition"]["python_direct"]["run_count"] == 6
    assert metrics["by_scenario"]["basic_calculation"]["run_count"] == 6
    assert metrics["by_repetition"]["1"]["run_count"] == 9
    assert "wall_time_seconds" in metrics["totals"]
    assert metrics["totals"]["wall_time_seconds"]["mean"] >= 0
