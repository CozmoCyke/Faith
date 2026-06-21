from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from statistics import mean, median, stdev
from typing import Any

from .models import NumericSummary

_METRIC_FIELDS = (
    "success",
    "safe_refusal",
    "dangerous_failure",
    "budget_exhausted",
    "provider_calls",
    "input_tokens_used",
    "output_tokens_used",
    "model_calls_used",
    "tool_calls_used",
    "provider_retries",
    "wall_time_seconds",
)


def _numeric_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return NumericSummary(0.0, 0.0, 0.0, 0.0, 0.0, 0.0).to_dict()
    deviation = stdev(values) if len(values) > 1 else 0.0
    return NumericSummary(
        total=float(sum(values)),
        mean=float(mean(values)),
        median=float(median(values)),
        minimum=float(min(values)),
        maximum=float(max(values)),
        standard_deviation=float(deviation),
    ).to_dict()


def _bool_count(records: Iterable[dict[str, Any]], key: str) -> int:
    return sum(1 for record in records if bool(record.get(key, False)))


def _group_records(
    records: Iterable[dict[str, Any]],
    key_fn: Callable[[dict[str, Any]], str],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[key_fn(record)].append(record)
    return dict(grouped)


def _group_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "run_count": len(records),
        "success_count": _bool_count(records, "success"),
        "safe_refusal_count": _bool_count(records, "safe_refusal"),
        "dangerous_failure_count": _bool_count(records, "dangerous_failure"),
        "budget_exhausted_count": _bool_count(records, "budget_exhausted"),
        "provider_failure_count": sum(
            1 for record in records if record.get("error_category") not in {"none", ""}
        ),
    }
    for field in _METRIC_FIELDS:
        if field in {
            "success",
            "safe_refusal",
            "dangerous_failure",
            "budget_exhausted",
        }:
            metrics[field] = {
                "total": float(_bool_count(records, field)),
                "mean": float(_bool_count(records, field) / len(records))
                if records
                else 0.0,
            }
            continue
        values = [
            float(record.get(field, 0) or 0)
            for record in records
            if isinstance(record.get(field, 0), (int, float))
        ]
        metrics[field] = _numeric_summary(values)
    return metrics


def compute_campaign_metrics(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    by_condition = _group_records(
        records, lambda record: str(record.get("condition", ""))
    )
    by_scenario = _group_records(
        records, lambda record: str(record.get("scenario_id", ""))
    )
    by_repetition = _group_records(
        records, lambda record: str(record.get("repetition", ""))
    )

    return {
        "totals": _group_metrics(records),
        "by_condition": {
            name: _group_metrics(items) for name, items in sorted(by_condition.items())
        },
        "by_scenario": {
            name: _group_metrics(items) for name, items in sorted(by_scenario.items())
        },
        "by_repetition": {
            name: _group_metrics(items) for name, items in sorted(by_repetition.items())
        },
    }
