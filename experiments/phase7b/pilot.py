from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from .infra import (
    CAMPAIGN_ID,
    RANDOMIZATION_SEED,
    build_pilot_manifest,
    build_protocol_payload,
    build_validation_summary,
    load_jsonl,
    render_validation_report,
    validate_pilot_records,
    write_json,
)


def prepare_campaign(output_root: Path) -> dict[str, Any]:
    protocol_dir = output_root / "protocol"
    manifests_dir = output_root / "manifests"
    raw_dir = output_root / "raw"
    derived_dir = output_root / "derived"
    logs_dir = output_root / "logs"
    transcripts_dir = raw_dir / "transcripts"
    for directory in (
        protocol_dir,
        manifests_dir,
        raw_dir,
        derived_dir,
        logs_dir,
        transcripts_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    manifest = build_pilot_manifest(seed=RANDOMIZATION_SEED)
    write_json(protocol_dir / "frozen_protocol.json", build_protocol_payload())
    write_json(manifests_dir / f"{CAMPAIGN_ID}.json", manifest)
    return manifest


def load_campaign_manifest(output_root: Path) -> dict[str, Any]:
    manifest_path = output_root / "manifests" / f"{CAMPAIGN_ID}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return cast(dict[str, Any], manifest)


def validate_campaign(output_root: Path) -> dict[str, Any]:
    manifest = load_campaign_manifest(output_root)
    raw_dir = output_root / "raw"
    derived_dir = output_root / "derived"
    raw_records = load_jsonl(raw_dir / "runs.jsonl")
    validation = validate_pilot_records(manifest, raw_records)
    report = render_validation_report(validation)
    derived_dir.mkdir(parents=True, exist_ok=True)
    (derived_dir / "pilot_validation.md").write_text(report, encoding="utf-8")
    (derived_dir / "PILOT_VALIDATION_REPORT.md").write_text(report, encoding="utf-8")
    return validation


def summarize_campaign(output_root: Path) -> dict[str, Any]:
    manifest = load_campaign_manifest(output_root)
    raw_dir = output_root / "raw"
    derived_dir = output_root / "derived"
    raw_records = load_jsonl(raw_dir / "runs.jsonl")
    return build_validation_summary(
        manifest,
        raw_records=raw_records or None,
        raw_dir=raw_dir if raw_records else None,
        derived_dir=derived_dir if raw_records else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare or validate the Phase 7B pilot."
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Pilot output directory.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate an existing pilot workspace instead of preparing one.",
    )
    args = parser.parse_args(argv)

    if args.validate:
        summary = validate_campaign(args.output_root)
        print(f"{summary['decision']} {summary['manifest_runs']} runs")
    else:
        manifest = prepare_campaign(args.output_root)
        print(f"prepared {len(manifest['runs'])} runs for {manifest['model_snapshot']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
