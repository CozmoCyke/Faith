from __future__ import annotations

from pathlib import Path

from experiments.phase7b.analysis.cli import main as analysis_cli_main
from experiments.phase7b.analysis.reporter import rebuild_derived_artifacts
from experiments.phase7b.analysis.reproducibility import (
    build_reproducibility_manifest,
    verify_reproducibility_manifest,
)
from tests.phase7b_analysis_fixtures import build_campaign


def test_reproducibility_manifest_verifies_clean_campaign(tmp_path: Path) -> None:
    campaign_dir = build_campaign(tmp_path, campaign_id="repro-campaign")
    rebuild_derived_artifacts(campaign_dir, write=True)

    verification = verify_reproducibility_manifest(campaign_dir)

    assert verification["status"] == "MATCH"
    assert verification["verified"] is True


def test_reproducibility_manifest_detects_raw_changes(tmp_path: Path) -> None:
    campaign_dir = build_campaign(tmp_path, campaign_id="repro-mismatch")
    manifest = build_reproducibility_manifest(campaign_dir)
    (campaign_dir / "derived" / "reproducibility_manifest.json").write_text(
        __import__("json").dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (campaign_dir / "raw" / "runs.jsonl").write_text(
        (campaign_dir / "raw" / "runs.jsonl").read_text(encoding="utf-8") + "{}\n",
        encoding="utf-8",
    )

    verification = verify_reproducibility_manifest(campaign_dir)

    assert verification["status"] == "MISMATCH"
    assert verification["verified"] is False


def test_cli_validate_and_compare_no_write(tmp_path: Path, capsys) -> None:
    campaign_dir = build_campaign(tmp_path, campaign_id="cli-campaign")

    exit_code = analysis_cli_main(
        ["validate", str(campaign_dir), "--json", "--strict", "--no-write"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert '"state": "COMPLETE_VALID"' in output
