from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from experiments.phase7.scenarios.definitions import (  # noqa: E402
    BenchmarkConfig,
    ScenarioCase,
    build_scenarios,
)

from .infra import (  # noqa: E402
    CAMPAIGN_ID,
    MODEL_ALIAS,
    MODEL_SNAPSHOT,
    PILOT_BUDGETS,
    PILOT_PARALLELISM,
    RANDOMIZATION_SEED,
    append_jsonl,
    build_pilot_manifest,
    build_protocol_hash,
    build_protocol_payload,
    build_validation_summary,
    load_jsonl,
    redact_secrets,
    render_validation_report,
    validate_pilot_records,
    write_json,
)
from .mock_provider import MockProvider  # noqa: E402
from .provider import (  # noqa: E402
    OpenAIProviderConfiguration,
    build_response_request,
    classify_provider_error,
    create_openai_client,
    invoke_response,
    validate_configuration,
)

LIVE_PROTOCOL_HASH = build_protocol_hash()
SIMULATION_DECISION = "PILOT_VALID_SIMULATION"


@dataclass(frozen=True, slots=True)
class PilotRunResult:
    record: dict[str, Any]
    transcript: dict[str, Any]
    halt_after: bool = False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _sha256_json(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _read_env_value(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, raw_value = stripped.split("=", 1)
        if name.strip() != key:
            continue
        value = raw_value.strip().strip("'").strip('"')
        return value
    return ""


def load_openai_api_key(output_root: Path) -> str:
    env_key = str(os.environ.get("OPENAI_API_KEY", "")).strip()
    if env_key:
        return env_key
    for candidate in (output_root / ".env.local", output_root / ".env"):
        value = _read_env_value(candidate, "OPENAI_API_KEY")
        if value:
            return value
    return ""


def _git_head(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _ensure_clean_worktree(repo_root: Path) -> None:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        raise RuntimeError("worktree must be clean before running the pilot")


def _campaign_artifacts_exist(output_root: Path) -> bool:
    candidates = [
        output_root / "protocol" / "frozen_protocol.json",
        output_root / "manifests" / f"{CAMPAIGN_ID}.json",
        output_root / "raw" / "runs.jsonl",
        output_root / "derived" / "PILOT_VALIDATION_REPORT.md",
        output_root / "logs" / "execution.log",
        output_root / "logs" / "preflight.json",
    ]
    return any(path.exists() for path in candidates)


def _expected_protocol_hash(mode: str) -> str:
    if mode == "live":
        return LIVE_PROTOCOL_HASH
    return _sha256_json(build_protocol_payload())


def _ensure_campaign_root(output_root: Path, *, resume: bool) -> None:
    if resume:
        return
    if _campaign_artifacts_exist(output_root):
        raise RuntimeError(
            "campaign output directory already contains Phase 7B artifacts"
        )


def _scenario_map() -> dict[str, ScenarioCase]:
    scenarios = build_scenarios(BenchmarkConfig("faifth_full"))
    return {scenario.name: scenario for scenario in scenarios}


def _system_prompt() -> str:
    return (
        "You are the Phase 7B pilot runner for Faifth. "
        "Follow the frozen protocol exactly, do not improvise, "
        "and return only the requested structured summary."
    )


def _user_prompt(run: Mapping[str, Any], scenario: ScenarioCase) -> str:
    payload = {
        "campaign_id": run["campaign_id"],
        "run_id": run["run_id"],
        "scenario_id": scenario.name,
        "condition": run["condition"],
        "repetition": run["repetition"],
        "randomization_position": run["randomization_position"],
        "scenario_description": scenario.description,
        "expected_final_check": scenario.final_check,
        "expected_stack": scenario.final_expected_stack,
        "steps": [
            {
                "action": step.action,
                "arguments": step.arguments,
                "expect_status": step.expect_status,
            }
            for step in scenario.steps
        ],
    }
    return _canonical_json(payload)


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return cast(dict[str, Any], value.model_dump())
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return cast(dict[str, Any], value.to_dict())
    return {"repr": repr(value)}


def _extract_text_response(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        for key in ("output_text", "text", "content"):
            value = response.get(key)
            if isinstance(value, str):
                return value
    value = getattr(response, "output_text", None)
    if isinstance(value, str):
        return value
    value = getattr(response, "text", None)
    if isinstance(value, str):
        return value
    return ""


def _extract_usage(response: Any) -> tuple[int, int]:
    usage = None
    if isinstance(response, dict):
        usage = response.get("usage")
    else:
        usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    if isinstance(usage, dict):
        return (
            int(usage.get("input_tokens", 0)),
            int(usage.get("output_tokens", 0)),
        )
    return (
        int(getattr(usage, "input_tokens", 0) or 0),
        int(getattr(usage, "output_tokens", 0) or 0),
    )


def _extract_tool_calls(response: Any) -> int:
    if isinstance(response, dict):
        tool_calls = response.get("tool_calls")
        if isinstance(tool_calls, list):
            return len(tool_calls)
        output = response.get("output")
        if isinstance(output, list):
            return sum(
                1
                for item in output
                if isinstance(item, dict) and item.get("type") == "tool_call"
            )
    output = getattr(response, "output", None)
    if isinstance(output, list):
        return sum(
            1
            for item in output
            if getattr(item, "type", None) == "tool_call"
        )
    tool_calls = getattr(response, "tool_calls", None)
    if isinstance(tool_calls, list):
        return len(tool_calls)
    return 0


def _session_state(run: Mapping[str, Any], scenario: ScenarioCase) -> dict[str, Any]:
    return {
        "campaign_id": run["campaign_id"],
        "run_id": run["run_id"],
        "session_id": run["session_id"],
        "scenario_id": scenario.name,
        "condition": run["condition"],
        "repetition": run["repetition"],
        "stack": [],
        "words": [],
        "active_versions": {},
        "budget": {
            "profile": PILOT_BUDGETS.name,
            "max_output_tokens": PILOT_BUDGETS.max_output_tokens,
            "max_calls_per_scenario": PILOT_BUDGETS.max_calls_per_scenario,
            "timeout_per_call_seconds": PILOT_BUDGETS.timeout_per_call_seconds,
        },
    }


def _mock_response(run: Mapping[str, Any], scenario: ScenarioCase) -> dict[str, Any]:
    return {
        "model": run["model_snapshot"],
        "output_text": (
            f"simulation complete for {scenario.name} "
            f"under {run['condition']}"
        ),
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "tool_calls": [],
    }


def _preflight_payload(
    *,
    mode: str,
    manifest: Mapping[str, Any],
    git_head: str,
    sdk_version: str,
    output_root: Path,
) -> dict[str, Any]:
    return {
        "campaign_id": manifest["campaign_id"],
        "git_head": git_head,
        "protocol_hash": manifest["protocol_hash"],
        "model_snapshot": manifest["model_snapshot"],
        "budget_profile": PILOT_BUDGETS.name,
        "run_count": len(manifest.get("runs", [])),
        "randomization_seed": manifest["randomization_seed"],
        "parallelism": manifest["parallelism"],
        "output_directory": str(output_root),
        "provider": manifest["provider"],
        "model": manifest["model"],
        "provider_sdk_version": sdk_version,
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "mode": mode,
        "openai_key_present": bool(load_openai_api_key(output_root)),
    }


def _write_execution_log(output_root: Path, line: str) -> None:
    log_path = output_root / "logs" / "execution.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line.rstrip())
        handle.write("\n")


def _write_preflight(output_root: Path, preflight: Mapping[str, Any]) -> None:
    write_json(output_root / "logs" / "preflight.json", dict(preflight))
    for key in (
        "campaign_id",
        "git_head",
        "protocol_hash",
        "model_snapshot",
        "budget_profile",
        "run_count",
        "randomization_seed",
        "parallelism",
        "output_directory",
    ):
        _write_execution_log(output_root, f"{key}: {preflight[key]}")


def _assert_preflight(preflight: Mapping[str, Any]) -> None:
    expected = {
        "campaign_id": CAMPAIGN_ID,
        "run_count": 18,
        "randomization_seed": RANDOMIZATION_SEED,
        "parallelism": PILOT_PARALLELISM,
        "budget_profile": PILOT_BUDGETS.name,
    }
    for key, value in expected.items():
        if preflight[key] != value:
            raise RuntimeError(f"preflight mismatch for {key}")


def _load_manifest(output_root: Path) -> dict[str, Any]:
    manifest_path = output_root / "manifests" / f"{CAMPAIGN_ID}.json"
    return _read_json(manifest_path)


def _prepare_or_load_campaign(
    output_root: Path,
    *,
    mode: str,
    resume: bool,
) -> dict[str, Any]:
    manifest_path = output_root / "manifests" / f"{CAMPAIGN_ID}.json"
    if manifest_path.exists():
        return _load_manifest(output_root)
    protocol_hash = _expected_protocol_hash(mode)
    return prepare_campaign(output_root, protocol_hash=protocol_hash)


def _validate_protocol_hash(manifest: Mapping[str, Any], *, mode: str) -> None:
    expected = _expected_protocol_hash(mode)
    if str(manifest.get("protocol_hash", "")) != expected:
        raise RuntimeError("protocol hash mismatch")


def _ensure_mode_guardrails(manifest: Mapping[str, Any], *, mode: str) -> None:
    if str(manifest.get("campaign_id", "")) != CAMPAIGN_ID:
        raise RuntimeError("campaign id mismatch")
    if str(manifest.get("model_snapshot", "")) != MODEL_SNAPSHOT:
        raise RuntimeError("model snapshot mismatch")
    if int(manifest.get("parallelism", 0)) != PILOT_PARALLELISM:
        raise RuntimeError("parallelism mismatch")
    if int(manifest.get("repetitions", 0)) != 2:
        raise RuntimeError("repetition count mismatch")
    _validate_protocol_hash(manifest, mode=mode)


def _record_result(
    *,
    run: Mapping[str, Any],
    scenario: ScenarioCase,
    mode: str,
    provider_calls: int,
    provider_retries: int,
    response: Any,
    response_error: str,
    initial_state: Mapping[str, Any],
    final_state: Mapping[str, Any],
    observed_model_snapshot: str,
    wall_time_seconds: float,
    status: str,
    success: bool,
    termination_reason: str,
    error_category: str,
    state_restored: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    input_tokens, output_tokens = _extract_usage(response)
    observed_result = _extract_text_response(response)
    record = {
        "campaign_id": run["campaign_id"],
        "run_id": run["run_id"],
        "scenario_id": run["scenario_id"],
        "condition": run["condition"],
        "repetition": run["repetition"],
        "randomization_position": run["randomization_position"],
        "protocol_hash": run["protocol_hash"],
        "scenario_hash": run["scenario_hash"],
        "model_snapshot": run["model_snapshot"],
        "status": status,
        "success": success,
        "safe_refusal": error_category == "forbidden_action",
        "dangerous_failure": error_category not in {"none", "forbidden_action"},
        "budget_exhausted": termination_reason == "budget_exhausted",
        "expected_result": scenario.final_check,
        "observed_result": observed_result,
        "initial_state": initial_state,
        "final_state": final_state,
        "state_restored": state_restored,
        "output_tokens_used": output_tokens,
        "input_tokens_used": input_tokens,
        "model_calls_used": provider_calls,
        "tool_calls_used": _extract_tool_calls(response),
        "provider_retries": provider_retries,
        "wall_time_seconds": wall_time_seconds,
        "termination_reason": termination_reason,
        "error_category": error_category,
        "provider_calls": provider_calls,
        "secrets_found": 0,
        "observed_model_snapshot": observed_model_snapshot,
        "system_prompt": _system_prompt(),
        "user_prompt": _user_prompt(run, scenario),
        "response_text": observed_result,
        "provider_error": response_error,
        "mode": mode,
    }
    transcript = {
        "run_id": run["run_id"],
        "mode": mode,
        "request": {
            "system_prompt": _system_prompt(),
            "user_prompt": _user_prompt(run, scenario),
            "tools": [],
        },
        "response": redact_secrets(_coerce_mapping(response)),
        "initial_state": initial_state,
        "final_state": final_state,
        "provider_retries": provider_retries,
        "provider_calls": provider_calls,
        "error_category": error_category,
        "response_error": response_error,
    }
    return record, transcript


def _execute_mock_run(
    *,
    run: Mapping[str, Any],
    scenario: ScenarioCase,
    provider: MockProvider,
) -> PilotRunResult:
    session_id = str(run["session_id"])
    initial_state = _session_state(run, scenario)
    provider.create_session(session_id, initial_state=initial_state)
    start = time.perf_counter()
    response = _mock_response(run, scenario)
    provider.record_run(
        session_id,
        {
            "run_id": run["run_id"],
            "scenario_id": run["scenario_id"],
            "condition": run["condition"],
            "repetition": run["repetition"],
            "status": "ok",
            "response": response,
        },
    )
    final_state = _session_state(run, scenario)
    final_state["last_response"] = response["output_text"]
    wall_time_seconds = time.perf_counter() - start
    record, transcript = _record_result(
        run=run,
        scenario=scenario,
        mode="dry-run",
        provider_calls=0,
        provider_retries=0,
        response=response,
        response_error="",
        initial_state=initial_state,
        final_state=final_state,
        observed_model_snapshot=str(response["model"]),
        wall_time_seconds=wall_time_seconds,
        status="ok",
        success=True,
        termination_reason="completed",
        error_category="none",
        state_restored=True,
    )
    return PilotRunResult(record=record, transcript=transcript)


def _execute_live_run(
    *,
    run: Mapping[str, Any],
    scenario: ScenarioCase,
    client: Any,
    configuration: OpenAIProviderConfiguration,
) -> PilotRunResult:
    system_prompt = _system_prompt()
    user_prompt = _user_prompt(run, scenario)
    request = build_response_request(
        configuration,
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        tools=(),
    )
    initial_state = _session_state(run, scenario)
    provider_calls = 0
    provider_retries = 0
    response: Any = {
        "model": configuration.model_snapshot,
        "output_text": "",
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "tool_calls": [],
    }
    response_error = ""
    error_category = "none"
    status = "ok"
    success = True
    termination_reason = "completed"
    observed_model_snapshot = configuration.model_snapshot
    start = time.perf_counter()

    while True:
        provider_calls += 1
        try:
            response = invoke_response(client, request)
            response_mapping = _coerce_mapping(response)
            observed_model_snapshot = str(
                response_mapping.get("model", configuration.model_snapshot)
            )
            status = "ok"
            success = True
            error_category = "none"
            response_error = ""
            termination_reason = "completed"
            if observed_model_snapshot != configuration.model_snapshot:
                error_category = "model_mismatch"
                status = "error"
                success = False
                termination_reason = "model_mismatch"
                response_error = (
                    "expected "
                    f"{configuration.model_snapshot!r}, got {observed_model_snapshot!r}"
                )
            break
        except BaseException as exc:  # pragma: no cover - exercised in tests
            error_category = classify_provider_error(exc)
            response_error = f"{type(exc).__name__}: {exc}"
            status = "error"
            success = False
            if (
                error_category in PILOT_BUDGETS.provider_retry_conditions
                and provider_retries < PILOT_BUDGETS.max_provider_retries_per_call
                and provider_calls < PILOT_BUDGETS.max_calls_per_scenario
            ):
                provider_retries += 1
                continue
            if provider_calls >= PILOT_BUDGETS.max_calls_per_scenario:
                termination_reason = "budget_exhausted"
            else:
                termination_reason = error_category
            break

    final_state = _session_state(run, scenario)
    if status == "ok":
        final_state["last_response"] = _extract_text_response(response)
    wall_time_seconds = time.perf_counter() - start
    record, transcript = _record_result(
        run=run,
        scenario=scenario,
        mode="live",
        provider_calls=provider_calls,
        provider_retries=provider_retries,
        response=response,
        response_error=response_error,
        initial_state=initial_state,
        final_state=final_state,
        observed_model_snapshot=observed_model_snapshot,
        wall_time_seconds=wall_time_seconds,
        status=status,
        success=success,
        termination_reason=termination_reason,
        error_category=error_category,
        state_restored=True,
    )
    halt_after = termination_reason != "completed" or not success
    return PilotRunResult(record=record, transcript=transcript, halt_after=halt_after)


def _records_by_run_id(records: Sequence[Mapping[str, Any]]) -> set[str]:
    return {str(record.get("run_id", "")) for record in records}


def prepare_campaign(
    output_root: Path,
    *,
    protocol_hash: str | None = None,
) -> dict[str, Any]:
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
    manifest = build_pilot_manifest(
        seed=RANDOMIZATION_SEED,
        protocol_hash=protocol_hash,
    )
    write_json(protocol_dir / "frozen_protocol.json", build_protocol_payload())
    write_json(manifests_dir / f"{CAMPAIGN_ID}.json", manifest)
    return manifest


def load_campaign_manifest(output_root: Path) -> dict[str, Any]:
    manifest_path = output_root / "manifests" / f"{CAMPAIGN_ID}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return cast(dict[str, Any], manifest)


def validate_campaign(
    output_root: Path,
    *,
    decision_label: str | None = None,
) -> dict[str, Any]:
    manifest = load_campaign_manifest(output_root)
    raw_dir = output_root / "raw"
    derived_dir = output_root / "derived"
    raw_records = load_jsonl(raw_dir / "runs.jsonl")
    validation = validate_pilot_records(manifest, raw_records)
    if decision_label and validation["decision"] == "PILOT_VALID":
        validation = dict(validation)
        validation["decision"] = decision_label
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


def run_pilot_campaign(
    output_root: Path,
    *,
    mode: str,
    resume: bool = False,
) -> dict[str, Any]:
    if mode not in {"dry-run", "live"}:
        raise ValueError("mode must be 'dry-run' or 'live'")
    repo_root = _repo_root()
    _ensure_clean_worktree(repo_root)
    _ensure_campaign_root(output_root, resume=resume)
    manifest = _prepare_or_load_campaign(output_root, mode=mode, resume=resume)
    _ensure_mode_guardrails(manifest, mode=mode)

    raw_dir = output_root / "raw"
    transcripts_dir = raw_dir / "transcripts"
    completed_records = load_jsonl(raw_dir / "runs.jsonl") if resume else []
    completed_run_ids = _records_by_run_id(completed_records)

    if mode == "dry-run":
        provider: Any = MockProvider()
        sdk_version = "mock"
        validation_env = {"OPENAI_API_KEY": ""}
        client = None
    else:
        api_key = load_openai_api_key(output_root)
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required before the first live pilot run"
            )
        validation_env = {"OPENAI_API_KEY": api_key}
        configuration = OpenAIProviderConfiguration(
            model_alias=MODEL_ALIAS,
            model_snapshot=MODEL_SNAPSHOT,
            max_output_tokens=PILOT_BUDGETS.max_output_tokens,
            timeout_seconds=PILOT_BUDGETS.timeout_per_call_seconds,
            max_retries=PILOT_BUDGETS.max_provider_retries_per_call,
        )
        provider_validation = validate_configuration(
            configuration, env=validation_env, tools=()
        )
        sdk_version = provider_validation.sdk_version
        client = create_openai_client(configuration, env=validation_env)
        provider = None

    preflight = _preflight_payload(
        mode=mode,
        manifest=manifest,
        git_head=_git_head(repo_root),
        sdk_version=sdk_version,
        output_root=output_root,
    )
    _assert_preflight(preflight)
    _write_preflight(output_root, preflight)

    scenario_map = _scenario_map()
    for run in manifest["runs"]:
        run_id = str(run["run_id"])
        if run_id in completed_run_ids:
            continue
        scenario = scenario_map[str(run["scenario_id"])]
        if mode == "dry-run":
            result = _execute_mock_run(
                run=run,
                scenario=scenario,
                provider=cast(MockProvider, provider),
            )
        else:
            configuration = OpenAIProviderConfiguration(
                model_alias=MODEL_ALIAS,
                model_snapshot=MODEL_SNAPSHOT,
                max_output_tokens=PILOT_BUDGETS.max_output_tokens,
                timeout_seconds=PILOT_BUDGETS.timeout_per_call_seconds,
                max_retries=PILOT_BUDGETS.max_provider_retries_per_call,
            )
            result = _execute_live_run(
                run=run,
                scenario=scenario,
                client=client,
                configuration=configuration,
            )

        append_jsonl(raw_dir / "runs.jsonl", redact_secrets(result.record))
        append_jsonl(
            transcripts_dir / f"{run_id}.jsonl",
            redact_secrets(result.transcript),
        )
        _write_execution_log(
            output_root,
            (
                f"{run_id}: {result.record['status']} "
                f"{result.record['termination_reason']}"
            ),
        )
        if result.halt_after:
            break

    raw_records = load_jsonl(raw_dir / "runs.jsonl")
    summary = build_validation_summary(
        manifest,
        raw_records=raw_records or None,
        raw_dir=raw_dir if raw_records else None,
        derived_dir=output_root / "derived" if raw_records else None,
    )
    report_validation = validate_campaign(
        output_root,
        decision_label=SIMULATION_DECISION if mode == "dry-run" else None,
    )
    summary["decision"] = report_validation["decision"]
    summary["protocol_hash"] = manifest["protocol_hash"]
    summary["validation_report"] = (
        output_root / "derived" / "PILOT_VALIDATION_REPORT.md"
    ).as_posix()
    summary["resume_test"] = report_validation["resume_test"]
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare, dry-run, or live-run the Phase 7B pilot."
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Pilot output directory.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted pilot without rerunning completed runs.",
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate all 18 runs with the mock provider only.",
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
    print(f"campaign_id: {CAMPAIGN_ID}")
    print(f"runs: {summary['manifest_runs']}")
    print(f"model snapshot: {MODEL_SNAPSHOT}")
    print(f"protocol hash: {summary['protocol_hash']}")
    print(f"parallelism: {summary['parallelism']}")
    print(f"provider calls: {summary['provider_calls']}")
    print(f"secrets found: {summary['secrets_found']}")
    print(f"resume test: {summary['resume_test']}")
    print(f"validation report: {summary['decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
