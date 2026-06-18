from __future__ import annotations

import argparse
import sys
import tempfile
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from experiments.phase7.adapters import (  # noqa: E402
    FaithProtocolAdapter,
    JsonToolsAdapter,
    PythonDirectAdapter,
)
from experiments.phase7.metrics import (  # noqa: E402
    ScenarioOutcome,
    canonical_json,
    classify_error,
    estimate_tokens,
    render_summary,
    response_audit_quality,
    state_equal,
    write_csv,
    write_jsonl,
)
from experiments.phase7.scenarios.definitions import (  # noqa: E402
    BenchmarkConfig,
    ScenarioCase,
    ScenarioStep,
    build_benchmark_configs,
    build_scenarios,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def _initial_state() -> dict[str, Any]:
    return {
        "session_id": None,
        "stack": [],
        "words": {},
        "active_versions": {},
        "candidate_count": 0,
        "transaction_active": False,
        "capabilities": [],
        "default_budget": {},
        "repositories": [],
        "user_word_count": 0,
    }


def _stack_from_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        if value and isinstance(value[0], dict) and "value" in value[0]:
            return [item["value"] for item in value]
        return list(value)
    return []


def _normalize_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    words = snapshot.get("words")
    if isinstance(words, Mapping):
        word_names = sorted(str(name) for name in words.keys())
        user_word_count = len(word_names)
    elif isinstance(words, list):
        if words and isinstance(words[0], dict) and "name" in words[0]:
            word_names = sorted(str(item["name"]) for item in words)
        else:
            word_names = sorted(str(item) for item in words)
        user_word_count = len(word_names)
    else:
        dictionary = snapshot.get("dictionary")
        if isinstance(dictionary, Mapping):
            nested_words = dictionary.get("words", [])
            if isinstance(nested_words, list):
                word_names = sorted(
                    str(item.get("name", ""))
                    for item in nested_words
                    if isinstance(item, Mapping)
                )
                user_word_count = len(word_names)
            else:
                word_names = []
                user_word_count = int(snapshot.get("user_word_count", 0))
        else:
            word_names = []
            user_word_count = int(snapshot.get("user_word_count", 0))

    stack = snapshot.get("stack", [])
    stack_values = _stack_from_value(stack)
    active_versions = snapshot.get("active_versions", {})
    if not isinstance(active_versions, Mapping):
        active_versions = {}
    repositories = snapshot.get("repositories", [])
    if isinstance(repositories, tuple):
        repositories = list(repositories)
    if not isinstance(repositories, list):
        repositories = []

    return {
        "stack": stack_values,
        "stack_depth": int(snapshot.get("stack_depth", len(stack_values))),
        "words": word_names,
        "user_word_count": user_word_count,
        "active_versions": {
            str(name): int(version) for name, version in sorted(active_versions.items())
        },
        "candidate_count": int(snapshot.get("candidate_count", 0)),
        "transaction_active": bool(snapshot.get("transaction_active", False)),
        "repositories": [str(item) for item in repositories],
        "capabilities": snapshot.get("capabilities", []),
        "default_budget": snapshot.get("default_budget", {}),
    }


def _extract_stack(payload: Mapping[str, Any]) -> list[Any]:
    if "stack" in payload and isinstance(payload["stack"], list):
        return _stack_from_value(payload["stack"])
    result = payload.get("result")
    if isinstance(result, Mapping) and "stack" in result:
        return _stack_from_value(result["stack"])
    return []


def _request_value(value: Any, context: Mapping[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
        return context.get(value[2:-2], value)
    if isinstance(value, Mapping):
        return {key: _request_value(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_request_value(item, context) for item in value]
    return value


def _resolve_request(
    step: ScenarioStep,
    session_id: str,
    request_id: str,
    context: Mapping[str, Any],
    protocol: str,
) -> dict[str, Any]:
    return {
        "protocol": protocol,
        "version": "0.1",
        "request_id": request_id,
        "session_id": session_id,
        "action": step.action,
        "arguments": _request_value(step.arguments, context),
    }


def _extract_path(payload: Mapping[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _capture_context(
    response: Mapping[str, Any], capture: Mapping[str, str], context: dict[str, Any]
) -> None:
    for name, path in capture.items():
        context[name] = _extract_path(response, path)


def _scenario_adapter_factory(name: str, variant: str, workdir: Path):
    if name == "python_direct":
        return PythonDirectAdapter(workdir=workdir, variant=variant)
    if name == "json_tools":
        return JsonToolsAdapter(workdir=workdir, variant=variant)
    if name == "faifth_protocol":
        return FaithProtocolAdapter(workdir=workdir, variant=variant)
    raise ValueError(name)


def _adapter_protocol_name(adapter: Any) -> str:
    protocol_name = getattr(adapter, "wire_protocol_name", None)
    if protocol_name is None:
        protocol_name = getattr(
            adapter, "protocol_name", getattr(adapter, "PROTOCOL_NAME", "benchmark")
        )
    return str(protocol_name)


def _run_scenario(
    *,
    adapter_name: str,
    variant: str,
    config: BenchmarkConfig,
    scenario: ScenarioCase,
) -> tuple[dict[str, Any], ScenarioOutcome]:
    with tempfile.TemporaryDirectory(
        prefix=f"phase7-{adapter_name}-{variant}-",
        dir=str(ROOT),
        ignore_cleanup_errors=True,
    ) as tempdir:
        adapter = _scenario_adapter_factory(adapter_name, variant, Path(tempdir))
        session_id = f"{adapter_name}-{variant}-{scenario.name}"
        context: dict[str, Any] = {}
        step_records: list[dict[str, Any]] = []
        request_count = 0
        request_bytes = 0
        response_bytes = 0
        steps_used = 0
        action_blocked = False
        current_snapshot = _initial_state()
        baseline_snapshot = None
        session_created = False
        start = time.perf_counter()
        final_response: dict[str, Any] | None = None

        try:
            for index, step in enumerate(scenario.steps, start=1):
                request_count += 1
                request_id = f"{session_id}-{index}"
                request = _resolve_request(
                    step,
                    session_id,
                    request_id,
                    context,
                    _adapter_protocol_name(adapter),
                )
                before_snapshot = (
                    _normalize_snapshot(adapter.snapshot(session_id))
                    if session_created
                    else current_snapshot
                )
                request_json = canonical_json(request)
                request_bytes += len(request_json.encode("utf-8"))
                started = time.perf_counter()
                response = adapter.handle(request)
                duration_ms = (time.perf_counter() - started) * 1000.0
                response_json = canonical_json(response)
                response_bytes += len(response_json.encode("utf-8"))
                steps_used += int(_extract_path(response, "result.steps") or 0)
                status = str(response.get("status"))
                error_category = classify_error(response.get("error"))
                step_stack = _extract_stack(response)
                if (
                    step.expected_stack is not None
                    and step_stack != step.expected_stack
                ):
                    status = "error"
                    error_category = "state_error"
                if status != step.expect_status:
                    error_category = (
                        "state_error" if step.expect_status == "ok" else error_category
                    )
                if (
                    step.expected_error_category is not None
                    and error_category != step.expected_error_category
                ):
                    status = "error"
                _capture_context(response, step.capture, context)
                if step.action == "create_session" and status == "ok":
                    session_created = True
                step_after_snapshot = (
                    _normalize_snapshot(adapter.snapshot(session_id))
                    if session_created
                    else before_snapshot
                )
                secure_refusal = (
                    step.expected_error_category == "forbidden_action"
                    and status == "error"
                    and state_equal(before_snapshot, step_after_snapshot)
                )
                if (
                    scenario.baseline_after_step is not None
                    and index == scenario.baseline_after_step
                ):
                    baseline_snapshot = step_after_snapshot
                step_records.append(
                    {
                        "step_index": index,
                        "action": step.action,
                        "request": request,
                        "response": response,
                        "request_json": request_json,
                        "response_json": response_json,
                        "request_bytes": len(request_json.encode("utf-8")),
                        "response_bytes": len(response_json.encode("utf-8")),
                        "duration_ms": duration_ms,
                        "status": status,
                        "error_category": error_category,
                        "stack_before": before_snapshot["stack"],
                        "stack_after": step_after_snapshot["stack"],
                        "audit_quality": response_audit_quality(
                            response.get("audit", [])
                        ),
                        "passed": (
                            status == step.expect_status
                            and (
                                step.expected_error_category is None
                                or error_category == step.expected_error_category
                                or secure_refusal
                            )
                            and (
                                step.expected_stack is None
                                or step_stack == step.expected_stack
                            )
                        ),
                    }
                )
                if (
                    step.expect_status == "error"
                    and error_category == "forbidden_action"
                ):
                    action_blocked = True
                if not step_records[-1]["passed"]:
                    final_response = response
                    break
                final_response = response
                current_snapshot = step_after_snapshot

            end_snapshot = (
                _normalize_snapshot(adapter.snapshot(session_id))
                if session_created
                else current_snapshot
            )
            baseline = (
                baseline_snapshot
                if baseline_snapshot is not None
                else (
                    current_snapshot
                    if not session_created
                    else _normalize_snapshot(adapter.snapshot(session_id))
                )
            )
            duration_ms = (time.perf_counter() - start) * 1000.0
            success = all(record["passed"] for record in step_records) and len(
                step_records
            ) == len(scenario.steps)
            observed = "ok" if success else "error"
            expected = scenario.final_check
            rollback_exact = None
            if scenario.final_check == "state_unchanged":
                rollback_exact = state_equal(baseline, end_snapshot)
                success = success and rollback_exact
                observed = "state_equal" if rollback_exact else "state_changed"
        finally:
            close = getattr(adapter, "close", None)
            if callable(close):
                close()
        if scenario.final_check == "stack_equals":
            success = success and end_snapshot["stack"] == (
                scenario.final_expected_stack or []
            )
            observed = str(end_snapshot["stack"])
        if scenario.final_expected_words:
            success = success and end_snapshot["words"] == sorted(
                scenario.final_expected_words
            )
        if scenario.final_expected_active_versions:
            success = success and end_snapshot["active_versions"] == dict(
                sorted(scenario.final_expected_active_versions.items())
            )

        total_audit = []
        for record in step_records:
            audit = record["response"].get("audit", [])
            if isinstance(audit, list):
                total_audit.extend(audit)

        outcome = ScenarioOutcome(
            adapter=adapter_name,
            scenario=scenario.name,
            status="ok" if success else "error",
            expected=expected,
            observed=observed,
            success=success,
            state_before=_initial_state(),
            state_after=end_snapshot,
            request_bytes=request_bytes,
            response_bytes=response_bytes,
            token_estimate=estimate_tokens(request_bytes + response_bytes),
            request_count=request_count,
            step_count=len(scenario.steps),
            steps_used=steps_used,
            corrections=0,
            rollback_exact=rollback_exact,
            action_blocked=action_blocked,
            audit_quality=response_audit_quality(total_audit),
            duration_ms=duration_ms,
            extra={
                "variant": variant,
                "baseline_state": baseline,
                "steps": step_records,
                "final_response": final_response,
                "config": config.name,
            },
        )
        return {
            "scenario": scenario.name,
            "adapter": adapter_name,
            "variant": variant,
            "success": success,
        }, outcome


def run_benchmark(*, include_ablations: bool = True) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    full_config = BenchmarkConfig("faifth_full")
    full_scenarios = build_scenarios(full_config)
    for adapter_name in ("python_direct", "json_tools", "faifth_protocol"):
        for scenario in full_scenarios:
            _, outcome = _run_scenario(
                adapter_name=adapter_name,
                variant=full_config.name,
                config=full_config,
                scenario=scenario,
            )
            records.append(outcome.to_dict())

    if include_ablations:
        for config in build_benchmark_configs()[1:]:
            for scenario in build_scenarios(config):
                _, outcome = _run_scenario(
                    adapter_name="faifth_protocol",
                    variant=config.name,
                    config=config,
                    scenario=scenario,
                )
                records.append(outcome.to_dict())
    return records


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Faifth Phase 7 benchmark harness."
    )
    parser.add_argument(
        "--no-ablations",
        action="store_true",
        help="Skip the Faifth ablation variants.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    records = run_benchmark(include_ablations=not args.no_ablations)
    write_jsonl(RESULTS_DIR / "runs.jsonl", records)
    write_csv(RESULTS_DIR / "summary.csv", records)
    render_summary(RESULTS_DIR / "summary.md", records)
    print(f"wrote {len(records)} benchmark records to {RESULTS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
