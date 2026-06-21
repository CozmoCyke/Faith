from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .comparator import compare_campaign_runs
from .loader import load_campaign_artifacts
from .metrics import compute_campaign_metrics
from .reproducibility import build_reproducibility_manifest
from .validator import validate_campaign_artifacts


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not rows:
            handle.write("")
            return
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _render_summary_md(summary: dict[str, Any]) -> str:
    lines = [
        "# Phase 7B Offline Summary",
        "",
        f"- campaign id: {summary['campaign_id']}",
        f"- state: {summary['state']}",
        f"- run count: {summary['run_count']}",
        f"- provider calls: {summary['provider_calls']}",
        f"- secret leaks: {summary['secret_leaks']}",
        "",
        "## Conditions",
        "",
    ]
    for name, data in summary["metrics"]["by_condition"].items():
        lines.append(
            f"- {name}: success={data['success_count']} run_count={data['run_count']}"
        )
    lines += ["", "## Issues", ""]
    lines.extend(
        [
            f"- {issue['severity']}: {issue['code']} - {issue['message']}"
            for issue in summary["integrity"]["issues"]
        ]
        or ["- none"]
    )
    return "\n".join(lines).rstrip() + "\n"


def _render_integrity_md(integrity: dict[str, Any]) -> str:
    lines = [
        "# Phase 7B Integrity Report",
        "",
        f"- campaign id: {integrity['campaign_id']}",
        f"- state: {integrity['state']}",
        f"- complete runs: {integrity['complete_runs']}",
        f"- expected runs: {integrity['expected_runs']}",
        f"- provider calls: {integrity['provider_calls']}",
        f"- secret leaks: {integrity['secret_leaks']}",
        "",
        "## Issues",
        "",
    ]
    lines.extend(
        [
            f"- {issue['severity']}: {issue['code']} - {issue['message']}"
            for issue in integrity["issues"]
        ]
        or ["- none"]
    )
    return "\n".join(lines).rstrip() + "\n"


def _flatten_metric_rows(
    section: str, name: str, metrics: dict[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for field, value in metrics.items():
        if isinstance(value, dict) and {
            "total",
            "mean",
            "median",
            "minimum",
            "maximum",
            "standard_deviation",
        } <= set(value):
            row = {"section": section, "group": name, "metric": field}
            row.update(value)
            rows.append(row)
    return rows


def rebuild_derived_artifacts(
    campaign_dir: Path, *, write: bool = True
) -> dict[str, Any]:
    artifacts = load_campaign_artifacts(campaign_dir)
    integrity = validate_campaign_artifacts(artifacts)
    metrics = compute_campaign_metrics(artifacts.runs)
    comparison = compare_campaign_runs(artifacts.runs)
    reproducibility = build_reproducibility_manifest(campaign_dir)

    summary = {
        "campaign_id": integrity["campaign_id"],
        "state": integrity["state"],
        "run_count": len(artifacts.runs),
        "provider_calls": integrity["provider_calls"],
        "secret_leaks": integrity["secret_leaks"],
        "integrity": integrity,
        "metrics": metrics,
        "comparison": comparison,
        "reproducibility": reproducibility,
    }

    if write:
        _write_json(artifacts.paths.integrity_json, integrity)
        artifacts.paths.integrity_md.write_text(
            _render_integrity_md(integrity), encoding="utf-8"
        )
        _write_json(artifacts.paths.summary_json, summary)
        artifacts.paths.summary_md.write_text(
            _render_summary_md(summary), encoding="utf-8"
        )
        rows = []
        for section, groups in (
            ("condition", metrics["by_condition"]),
            ("scenario", metrics["by_scenario"]),
            ("repetition", metrics["by_repetition"]),
        ):
            for name, group_metrics in groups.items():
                rows.extend(_flatten_metric_rows(section, name, group_metrics))
        _write_csv(artifacts.paths.summary_csv, rows)
        _write_csv(artifacts.paths.paired_csv, comparison["rows"])
        artifacts.paths.paired_md.write_text(
            "# Phase 7B Paired Comparison\n\n"
            "concordant success groups: "
            f"{comparison['summary']['success_concordant']}\n"
            f"- only python: {comparison['summary']['success_only_python']}\n"
            f"- only json: {comparison['summary']['success_only_json']}\n"
            f"- only faifth: {comparison['summary']['success_only_faifth']}\n",
            encoding="utf-8",
        )
        _write_json(artifacts.paths.reproducibility_json, reproducibility)

    return summary
