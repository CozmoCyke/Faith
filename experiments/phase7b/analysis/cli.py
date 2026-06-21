from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .comparator import compare_campaign_runs
from .loader import load_campaign_artifacts
from .reporter import rebuild_derived_artifacts
from .reproducibility import verify_reproducibility_manifest
from .validator import validate_campaign_artifacts


def _emit(payload: Any, *, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
        return
    if isinstance(payload, str):
        print(payload)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="Emit JSON only.")
    common.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on warnings or invalid states.",
    )
    common.add_argument(
        "--no-write", action="store_true", help="Analyze without writing derived files."
    )

    parser = argparse.ArgumentParser(
        description="Phase 7B offline analysis tooling",
        parents=[common],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in (
        "validate",
        "summarize",
        "compare",
        "rebuild-derived",
        "verify-reproducibility",
    ):
        cmd = subparsers.add_parser(command, parents=[common], add_help=True)
        cmd.add_argument("campaign_dir", type=Path)

    args = parser.parse_args(argv)
    campaign_dir: Path = args.campaign_dir
    artifacts = load_campaign_artifacts(campaign_dir)

    if args.command == "validate":
        report = validate_campaign_artifacts(artifacts)
        if not args.no_write:
            rebuild_derived_artifacts(campaign_dir, write=True)
        _emit(report, json_mode=args.json)
        if args.strict and report["state"] not in {
            "COMPLETE_VALID",
            "INCOMPLETE_VALIDLY_RECORDED",
        }:
            return 1
        return 0
    if args.command == "summarize":
        summary = rebuild_derived_artifacts(campaign_dir, write=not args.no_write)
        _emit(summary, json_mode=args.json)
        if args.strict and summary["state"] not in {
            "COMPLETE_VALID",
            "INCOMPLETE_VALIDLY_RECORDED",
        }:
            return 1
        return 0
    if args.command == "compare":
        comparison = compare_campaign_runs(artifacts.runs)
        _emit(comparison, json_mode=args.json)
        return 0
    if args.command == "rebuild-derived":
        summary = rebuild_derived_artifacts(campaign_dir, write=not args.no_write)
        _emit(summary, json_mode=args.json)
        return 0
    if args.command == "verify-reproducibility":
        verification = verify_reproducibility_manifest(campaign_dir)
        _emit(verification, json_mode=args.json)
        if args.strict and verification["status"] != "MATCH":
            return 1
        return 0
    raise RuntimeError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
