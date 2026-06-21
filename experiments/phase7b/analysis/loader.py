from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from .models import CampaignArtifacts, CampaignPaths

_TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".csv", ".txt"}


def build_campaign_paths(campaign_dir: Path) -> CampaignPaths:
    return CampaignPaths(
        campaign_dir=campaign_dir,
        preflight=campaign_dir / "logs" / "preflight.json",
        runs=campaign_dir / "raw" / "runs.jsonl",
        transcripts_dir=campaign_dir / "raw" / "transcripts",
        derived_dir=campaign_dir / "derived",
        manifest=campaign_dir
        / "manifests"
        / f"{campaign_dir.name.replace('-live', '')}.json",
        protocol=campaign_dir / "protocol" / "frozen_protocol.json",
        validation_report=campaign_dir / "derived" / "PILOT_VALIDATION_REPORT.md",
        pilot_validation_report=campaign_dir / "derived" / "pilot_validation.md",
        summary_csv=campaign_dir / "derived" / "summary.csv",
        summary_json=campaign_dir / "derived" / "summary.json",
        summary_md=campaign_dir / "derived" / "summary.md",
        integrity_json=campaign_dir / "derived" / "integrity_report.json",
        integrity_md=campaign_dir / "derived" / "integrity_report.md",
        paired_csv=campaign_dir / "derived" / "paired_comparison.csv",
        paired_md=campaign_dir / "derived" / "paired_comparison.md",
        reproducibility_json=campaign_dir / "derived" / "reproducibility_manifest.json",
    )


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(cast(dict[str, Any], json.loads(line)))
    return records


def _load_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _load_transcripts(transcripts_dir: Path) -> dict[str, list[dict[str, Any]]]:
    transcripts: dict[str, list[dict[str, Any]]] = {}
    if not transcripts_dir.exists():
        return transcripts
    for path in sorted(transcripts_dir.glob("*.jsonl")):
        transcripts[path.stem] = _load_jsonl(path)
    return transcripts


def load_campaign_artifacts(campaign_dir: Path) -> CampaignArtifacts:
    paths = build_campaign_paths(campaign_dir)
    return CampaignArtifacts(
        paths=paths,
        preflight=_load_json(paths.preflight),
        manifest=_load_json(paths.manifest),
        protocol=_load_json(paths.protocol),
        runs=_load_jsonl(paths.runs),
        transcripts=_load_transcripts(paths.transcripts_dir),
        derived_validation_report=_load_text(paths.validation_report),
    )


def iter_text_artifact_paths(campaign_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for path in campaign_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in _TEXT_SUFFIXES:
            paths.append(path)
    return sorted(paths)
