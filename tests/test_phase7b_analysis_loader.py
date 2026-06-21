from __future__ import annotations

from pathlib import Path

from experiments.phase7b.analysis.loader import load_campaign_artifacts
from tests.phase7b_analysis_fixtures import build_campaign


def test_loader_reads_complete_campaign(tmp_path: Path) -> None:
    campaign_dir = build_campaign(tmp_path, campaign_id="synthetic-campaign")

    artifacts = load_campaign_artifacts(campaign_dir)

    assert artifacts.preflight is not None
    assert artifacts.manifest is not None
    assert artifacts.protocol is not None
    assert len(artifacts.runs) == 18
    assert len(artifacts.transcripts) == 18
    assert artifacts.derived_validation_report is not None


def test_loader_tolerates_missing_optional_files(tmp_path: Path) -> None:
    campaign_dir = build_campaign(
        tmp_path,
        campaign_id="partial-campaign",
        include_manifest=False,
        include_protocol=False,
        include_preflight=False,
        include_transcripts=False,
        include_validation_report=False,
    )

    artifacts = load_campaign_artifacts(campaign_dir)

    assert artifacts.preflight is None
    assert artifacts.manifest is None
    assert artifacts.protocol is None
    assert artifacts.runs
    assert artifacts.transcripts == {}
    assert artifacts.derived_validation_report is None
