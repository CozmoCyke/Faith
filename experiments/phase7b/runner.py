from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .infra import (
    CAMPAIGN_ID,
    MODEL_ALIAS,
    MODEL_SNAPSHOT,
    PILOT_BUDGETS,
    RANDOMIZATION_SEED,
    build_pilot_manifest,
    build_protocol_payload,
    build_validation_summary,
    redact_secrets,
    regenerate_derived_artifacts,
    write_json,
    write_jsonl,
)


def prepare_infrastructure(output_root: Path) -> dict[str, Any]:
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

    write_json(protocol_dir / "frozen_protocol.json", build_protocol_payload())
    manifest = build_pilot_manifest(seed=RANDOMIZATION_SEED)
    write_json(manifests_dir / f"{CAMPAIGN_ID}.json", manifest)
    return manifest


def validate_infrastructure(output_root: Path) -> dict[str, Any]:
    manifest_path = output_root / "manifests" / f"{CAMPAIGN_ID}.json"
    parsed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_dir = output_root / "raw"
    derived_dir = output_root / "derived"
    raw_records = []
    raw_runs = raw_dir / "runs.jsonl"
    if raw_runs.exists():
        raw_records = [
            json.loads(line)
            for line in raw_runs.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return build_validation_summary(
        parsed_manifest,
        raw_records=raw_records or None,
        raw_dir=raw_dir if raw_records else None,
        derived_dir=derived_dir if raw_records else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare Phase 7B pilot infrastructure.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Output directory for the prepared infrastructure.",
    )
    args = parser.parse_args(argv)
    manifest = prepare_infrastructure(args.output_root)
    summary = build_validation_summary(manifest)
    print(
        f"prepared {summary['manifest_runs']} runs for {MODEL_ALIAS} / {MODEL_SNAPSHOT} "
        f"with budget profile {PILOT_BUDGETS.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
