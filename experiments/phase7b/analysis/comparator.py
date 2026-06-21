from __future__ import annotations

from collections import defaultdict
from typing import Any

_CONDITIONS = ("python_direct", "json_tools", "faifth_protocol")


def _run_key(record: dict[str, Any]) -> tuple[str, str]:
    return str(record.get("scenario_id", "")), str(record.get("repetition", ""))


def _numeric_delta(left: dict[str, Any], right: dict[str, Any], field: str) -> float:
    return float(left.get(field, 0) or 0) - float(right.get(field, 0) or 0)


def compare_campaign_runs(records: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        grouped[_run_key(record)][str(record.get("condition", ""))] = record

    rows: list[dict[str, Any]] = []
    concordant = 0
    only_python = 0
    only_json = 0
    only_faifth = 0

    for (scenario_id, repetition), mapping in sorted(grouped.items()):
        python_run = mapping.get("python_direct")
        json_run = mapping.get("json_tools")
        faifth_run = mapping.get("faifth_protocol")
        if not python_run or not json_run or not faifth_run:
            continue

        python_success = bool(python_run.get("success", False))
        json_success = bool(json_run.get("success", False))
        faifth_success = bool(faifth_run.get("success", False))
        if python_success == json_success == faifth_success:
            concordant += 1
        elif python_success and not json_success and not faifth_success:
            only_python += 1
        elif json_success and not python_success and not faifth_success:
            only_json += 1
        elif faifth_success and not python_success and not json_success:
            only_faifth += 1

        rows.append(
            {
                "scenario_id": scenario_id,
                "repetition": repetition,
                "python_success": python_success,
                "json_success": json_success,
                "faifth_success": faifth_success,
                "python_input_tokens": python_run.get("input_tokens_used", 0),
                "json_input_tokens": json_run.get("input_tokens_used", 0),
                "faifth_input_tokens": faifth_run.get("input_tokens_used", 0),
                "python_output_tokens": python_run.get("output_tokens_used", 0),
                "json_output_tokens": json_run.get("output_tokens_used", 0),
                "faifth_output_tokens": faifth_run.get("output_tokens_used", 0),
                "python_model_calls": python_run.get("model_calls_used", 0),
                "json_model_calls": json_run.get("model_calls_used", 0),
                "faifth_model_calls": faifth_run.get("model_calls_used", 0),
                "python_provider_retries": python_run.get("provider_retries", 0),
                "json_provider_retries": json_run.get("provider_retries", 0),
                "faifth_provider_retries": faifth_run.get("provider_retries", 0),
                "python_wall_time_seconds": python_run.get("wall_time_seconds", 0.0),
                "json_wall_time_seconds": json_run.get("wall_time_seconds", 0.0),
                "faifth_wall_time_seconds": faifth_run.get("wall_time_seconds", 0.0),
                "python_json_success_delta": int(python_success) - int(json_success),
                "python_faifth_success_delta": int(python_success)
                - int(faifth_success),
                "json_faifth_success_delta": int(json_success) - int(faifth_success),
                "python_json_input_tokens_delta": _numeric_delta(
                    python_run, json_run, "input_tokens_used"
                ),
                "python_faifth_input_tokens_delta": _numeric_delta(
                    python_run, faifth_run, "input_tokens_used"
                ),
                "json_faifth_input_tokens_delta": _numeric_delta(
                    json_run, faifth_run, "input_tokens_used"
                ),
                "python_json_wall_time_delta": _numeric_delta(
                    python_run, json_run, "wall_time_seconds"
                ),
                "python_faifth_wall_time_delta": _numeric_delta(
                    python_run, faifth_run, "wall_time_seconds"
                ),
                "json_faifth_wall_time_delta": _numeric_delta(
                    json_run, faifth_run, "wall_time_seconds"
                ),
                "python_json_state_restored_delta": int(
                    bool(python_run.get("state_restored", False))
                )
                - int(bool(json_run.get("state_restored", False))),
                "python_faifth_state_restored_delta": int(
                    bool(python_run.get("state_restored", False))
                )
                - int(bool(faifth_run.get("state_restored", False))),
                "json_faifth_state_restored_delta": int(
                    bool(json_run.get("state_restored", False))
                )
                - int(bool(faifth_run.get("state_restored", False))),
            }
        )

    return {
        "summary": {
            "paired_groups": len(rows),
            "success_concordant": concordant,
            "success_only_python": only_python,
            "success_only_json": only_json,
            "success_only_faifth": only_faifth,
        },
        "rows": rows,
    }
