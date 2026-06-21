from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .infra import (
    CAMPAIGN_ID,
    MODEL_SNAPSHOT,
)
from .pilot import prepare_campaign, run_pilot_campaign, summarize_campaign


def prepare_infrastructure(output_root: Path) -> dict[str, Any]:
    return prepare_campaign(output_root)


def validate_infrastructure(output_root: Path) -> dict[str, Any]:
    return summarize_campaign(output_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare, dry-run, or live-run the Phase 7B pilot."
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Output directory for the pilot artifacts.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted pilot without replaying completed runs.",
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the 18 pilot runs with the mock provider only.",
    )
    mode_group.add_argument(
        "--live",
        action="store_true",
        help="Run the live OpenAI provider pilot.",
    )
    args = parser.parse_args(argv)

    summary = run_pilot_campaign(
        args.output_root,
        mode="live" if args.live else "dry-run",
        resume=args.resume,
    )
    dry_run = not args.live
    print(f"campaign_id: {CAMPAIGN_ID}")
    print(f"runs: {summary['manifest_runs']}")
    print(f"model snapshot: {MODEL_SNAPSHOT}")
    print(
        "protocol hash: unchanged"
        if dry_run
        else f"protocol hash: {summary['protocol_hash']}"
    )
    print(f"parallelism: {summary['parallelism']}")
    print(f"provider calls: {summary['provider_calls']}")
    print(f"secrets found: {summary['secrets_found']}")
    print(f"resume test: {summary['resume_test']}")
    print(f"validation report: {summary['decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
