from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .infra import (
    MODEL_ALIAS,
    MODEL_SNAPSHOT,
    PILOT_BUDGETS,
    build_validation_summary,
)
from .pilot import prepare_campaign, summarize_campaign


def prepare_infrastructure(output_root: Path) -> dict[str, Any]:
    return prepare_campaign(output_root)


def validate_infrastructure(output_root: Path) -> dict[str, Any]:
    return summarize_campaign(output_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare Phase 7B pilot infrastructure."
    )
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
        f"prepared {summary['manifest_runs']} runs for "
        f"{MODEL_ALIAS} / {MODEL_SNAPSHOT} with budget profile {PILOT_BUDGETS.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
