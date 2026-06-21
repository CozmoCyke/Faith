from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from experiments.phase7b.infra import (
    MODEL_SNAPSHOT,
    PILOT_CONDITIONS,
    PILOT_PARALLELISM,
    PILOT_REPETITIONS,
    PILOT_SCENARIO_NAMES,
)

from .models import (
    AnalysisIssue,
    CampaignAnalysis,
    CampaignArtifacts,
    CampaignState,
    Severity,
)

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"(?i)\b(openai[_-]?api[_-]?key|api[_-]?key|secret|password|token)\b"),
)

_EXPECTED_RUN_COUNT = (
    len(PILOT_CONDITIONS) * len(PILOT_SCENARIO_NAMES) * PILOT_REPETITIONS
)


def _issue(
    severity: Severity,
    code: str,
    message: str,
    *,
    path: str | None = None,
    run_id: str | None = None,
    **details: Any,
) -> AnalysisIssue:
    return AnalysisIssue(
        severity=severity,
        code=code,
        message=message,
        path=path,
        run_id=run_id,
        details=dict(details),
    )


def _scan_text(text: str) -> bool:
    lowered = text.lower()
    if "sk-" in lowered:
        return True
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS[1:])


def _manifest_runs(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    return list(manifest.get("runs", [])) if manifest else []


def _campaign_id(artifacts: CampaignArtifacts) -> str:
    if artifacts.manifest and artifacts.manifest.get("campaign_id"):
        return str(artifacts.manifest.get("campaign_id"))
    if artifacts.preflight and artifacts.preflight.get("campaign_id"):
        return str(artifacts.preflight.get("campaign_id"))
    return artifacts.paths.campaign_dir.name


def _load_expected_run_ids(campaign_id: str) -> list[str]:
    return [
        f"{campaign_id}-run-{position:03d}"
        for position in range(1, _EXPECTED_RUN_COUNT + 1)
    ]


def _raw_runs_by_id(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record.get("run_id", ""))].append(record)
    return grouped


def _secret_leak_count(artifacts: CampaignArtifacts) -> int:
    count = 0
    for path in artifacts.paths.campaign_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in {
            ".json",
            ".jsonl",
            ".md",
            ".csv",
            ".txt",
        }:
            if _scan_text(path.read_text(encoding="utf-8")):
                count += 1
    return count


def _classify_state(
    *,
    expected_run_ids: list[str],
    raw_run_ids: list[str],
    issues: list[AnalysisIssue],
) -> CampaignState:
    if any(issue.severity == Severity.BLOCKING for issue in issues):
        return CampaignState.CORRUPTED
    observed_expected = {run_id for run_id in raw_run_ids if run_id in expected_run_ids}
    if (
        len(observed_expected) == _EXPECTED_RUN_COUNT
        and len(raw_run_ids) >= _EXPECTED_RUN_COUNT
        and not issues
    ):
        return CampaignState.COMPLETE_VALID
    if len(observed_expected) == _EXPECTED_RUN_COUNT:
        return CampaignState.COMPLETE_INVALID
    return CampaignState.INCOMPLETE_VALIDLY_RECORDED


def validate_campaign_artifacts(artifacts: CampaignArtifacts) -> dict[str, Any]:
    issues: list[AnalysisIssue] = []
    campaign_id = _campaign_id(artifacts)
    expected_run_ids = _load_expected_run_ids(campaign_id)
    raw_run_ids = [str(record.get("run_id", "")) for record in artifacts.runs]
    raw_by_id = _raw_runs_by_id(artifacts.runs)

    if artifacts.preflight is None:
        issues.append(
            _issue(Severity.BLOCKING, "preflight_missing", "preflight.json is missing")
        )
    if artifacts.manifest is None:
        issues.append(
            _issue(Severity.BLOCKING, "manifest_missing", "manifest is missing")
        )
    if artifacts.protocol is None:
        issues.append(
            _issue(Severity.BLOCKING, "protocol_missing", "frozen protocol is missing")
        )
    if artifacts.derived_validation_report is None:
        issues.append(
            _issue(
                Severity.WARNING,
                "validation_report_missing",
                "PILOT validation report is missing",
            )
        )

    if artifacts.manifest:
        manifest = artifacts.manifest
        if str(manifest.get("model_snapshot", "")) != MODEL_SNAPSHOT:
            issues.append(
                _issue(
                    Severity.BLOCKING,
                    "model_snapshot_mismatch",
                    "manifest model snapshot differs from frozen snapshot",
                    expected=MODEL_SNAPSHOT,
                    observed=manifest.get("model_snapshot"),
                )
            )
        if int(manifest.get("parallelism", 0)) != PILOT_PARALLELISM:
            issues.append(
                _issue(
                    Severity.BLOCKING,
                    "parallelism_mismatch",
                    "manifest parallelism differs from frozen value",
                    expected=PILOT_PARALLELISM,
                    observed=manifest.get("parallelism"),
                )
            )
        if sorted(manifest.get("conditions", [])) != sorted(PILOT_CONDITIONS):
            issues.append(
                _issue(
                    Severity.ERROR,
                    "condition_set_mismatch",
                    "manifest conditions differ from the frozen set",
                )
            )
        if sorted(manifest.get("scenarios", [])) != sorted(PILOT_SCENARIO_NAMES):
            issues.append(
                _issue(
                    Severity.ERROR,
                    "scenario_set_mismatch",
                    "manifest scenarios differ from the frozen set",
                )
            )
        if int(manifest.get("repetitions", 0)) != PILOT_REPETITIONS:
            issues.append(
                _issue(
                    Severity.ERROR,
                    "repetition_mismatch",
                    "manifest repetitions differ from the frozen plan",
                )
            )
        if (
            manifest.get("protocol_hash")
            and artifacts.preflight
            and str(artifacts.preflight.get("protocol_hash", ""))
            != str(manifest.get("protocol_hash", ""))
        ):
            issues.append(
                _issue(
                    Severity.BLOCKING,
                    "protocol_hash_mismatch",
                    "preflight protocol hash differs from manifest protocol hash",
                    expected=manifest.get("protocol_hash"),
                    observed=artifacts.preflight.get("protocol_hash"),
                )
            )
        if artifacts.preflight and str(
            artifacts.preflight.get("campaign_id", "")
        ) != str(manifest.get("campaign_id", "")):
            issues.append(
                _issue(
                    Severity.BLOCKING,
                    "campaign_id_mismatch",
                    "preflight campaign id differs from manifest campaign id",
                    expected=manifest.get("campaign_id"),
                    observed=artifacts.preflight.get("campaign_id"),
                )
            )

    duplicates = [
        run_id for run_id, count in Counter(raw_run_ids).items() if run_id and count > 1
    ]
    if duplicates:
        issues.append(
            _issue(
                Severity.ERROR,
                "duplicate_runs",
                "duplicate run ids found",
                run_ids=duplicates,
            )
        )
    missing = [run_id for run_id in expected_run_ids if run_id not in raw_by_id]
    unexpected = [run_id for run_id in raw_run_ids if run_id not in expected_run_ids]
    if missing:
        issues.append(
            _issue(
                Severity.ERROR,
                "missing_runs",
                "expected run ids are missing",
                run_ids=missing,
            )
        )
    if unexpected:
        issues.append(
            _issue(
                Severity.ERROR,
                "unexpected_runs",
                "unexpected run ids are present",
                run_ids=unexpected,
            )
        )

    for run_id, records in raw_by_id.items():
        if not run_id:
            issues.append(
                _issue(
                    Severity.BLOCKING,
                    "missing_run_id",
                    "a raw record is missing run_id",
                )
            )
            continue
        if len(records) > 1:
            continue
        record = records[0]
        if expected_run_ids and run_id not in expected_run_ids:
            continue

        for field in (
            "campaign_id",
            "scenario_id",
            "condition",
            "repetition",
            "randomization_position",
            "protocol_hash",
            "scenario_hash",
            "model_snapshot",
            "status",
            "success",
            "safe_refusal",
            "dangerous_failure",
            "budget_exhausted",
            "expected_result",
            "observed_result",
            "initial_state",
            "final_state",
            "state_restored",
            "output_tokens_used",
            "input_tokens_used",
            "model_calls_used",
            "tool_calls_used",
            "provider_retries",
            "wall_time_seconds",
            "termination_reason",
            "error_category",
            "provider_calls",
            "secrets_found",
        ):
            if field not in record:
                issues.append(
                    _issue(
                        Severity.ERROR,
                        "metric_missing",
                        f"{run_id} is missing required field {field}",
                        run_id=run_id,
                    )
                )

        if (
            record.get("campaign_id")
            and artifacts.manifest
            and str(record.get("campaign_id"))
            != str(artifacts.manifest.get("campaign_id", ""))
        ):
            issues.append(
                _issue(
                    Severity.BLOCKING,
                    "campaign_id_divergent",
                    "raw record campaign id diverges from manifest",
                    run_id=run_id,
                )
            )
        if (
            record.get("model_snapshot")
            and str(record.get("model_snapshot")) != MODEL_SNAPSHOT
        ):
            issues.append(
                _issue(
                    Severity.BLOCKING,
                    "model_snapshot_divergent",
                    "raw record model snapshot diverges from frozen snapshot",
                    run_id=run_id,
                )
            )
        if (
            record.get("protocol_hash")
            and artifacts.manifest
            and str(record.get("protocol_hash"))
            != str(artifacts.manifest.get("protocol_hash", ""))
        ):
            issues.append(
                _issue(
                    Severity.WARNING,
                    "protocol_hash_divergent",
                    "raw record protocol hash diverges from manifest",
                    run_id=run_id,
                )
            )
        if (
            record.get("condition")
            and str(record.get("condition")) not in PILOT_CONDITIONS
        ):
            issues.append(
                _issue(
                    Severity.ERROR,
                    "unknown_condition",
                    "unknown condition in raw record",
                    run_id=run_id,
                )
            )
        if (
            record.get("scenario_id")
            and str(record.get("scenario_id")) not in PILOT_SCENARIO_NAMES
        ):
            issues.append(
                _issue(
                    Severity.ERROR,
                    "unknown_scenario",
                    "unknown scenario in raw record",
                    run_id=run_id,
                )
            )
        if record.get("repetition") and int(record.get("repetition", 0)) not in range(
            1, PILOT_REPETITIONS + 1
        ):
            issues.append(
                _issue(
                    Severity.ERROR,
                    "repetition_out_of_range",
                    "repetition is out of range",
                    run_id=run_id,
                )
            )

        if record.get("termination_reason") == "budget_exhausted" and not record.get(
            "budget_exhausted", False
        ):
            issues.append(
                _issue(
                    Severity.WARNING,
                    "budget_status_mismatch",
                    "budget exhausted run missing budget_exhausted flag",
                    run_id=run_id,
                )
            )

        provider_error = str(record.get("provider_error", "")).lower()
        error_category = str(record.get("error_category", ""))
        if (
            "insufficient_quota" in provider_error
            and int(record.get("provider_retries", 0)) > 0
        ):
            issues.append(
                _issue(
                    Severity.WARNING,
                    "quota_retry_policy_mismatch",
                    "insufficient_quota should not be retried",
                    run_id=run_id,
                )
            )
        if "temperature" in provider_error and error_category != "provider_error":
            issues.append(
                _issue(
                    Severity.ERROR,
                    "temperature_request_mismatch",
                    (
                        "unsupported temperature request should be treated as "
                        "a non-retryable provider error"
                    ),
                    run_id=run_id,
                )
            )

        transcript_path = artifacts.paths.transcripts_dir / f"{run_id}.jsonl"
        if not transcript_path.exists():
            issues.append(
                _issue(
                    Severity.ERROR,
                    "transcript_missing",
                    "transcript is missing",
                    run_id=run_id,
                    path=str(transcript_path),
                )
            )
        elif not artifacts.transcripts.get(run_id):
            issues.append(
                _issue(
                    Severity.WARNING,
                    "transcript_empty",
                    "transcript file contains no entries",
                    run_id=run_id,
                    path=str(transcript_path),
                )
            )

        if (
            record.get("wall_time_seconds") is not None
            and float(record.get("wall_time_seconds", 0.0)) < 0
        ):
            issues.append(
                _issue(
                    Severity.ERROR,
                    "timestamp_invalid",
                    "wall time is negative",
                    run_id=run_id,
                )
            )

    secret_leaks = _secret_leak_count(artifacts)
    if secret_leaks:
        issues.append(
            _issue(
                Severity.BLOCKING,
                "secret_leak",
                "text artifacts contain potential secrets",
                leaks=secret_leaks,
            )
        )

    state = _classify_state(
        expected_run_ids=expected_run_ids,
        raw_run_ids=raw_run_ids,
        issues=issues,
    )
    if state == CampaignState.COMPLETE_VALID and issues:
        state = CampaignState.COMPLETE_INVALID
    provider_calls = (
        int(sum(int(record.get("provider_calls", 0)) for record in artifacts.runs))
        if state == CampaignState.COMPLETE_VALID
        else 0
    )

    return {
        "campaign_id": campaign_id,
        "state": state.value,
        "issues": [issue.to_dict() for issue in issues],
        "issue_counts": dict(Counter(issue.severity.value for issue in issues)),
        "complete_runs": len(artifacts.runs),
        "expected_runs": _EXPECTED_RUN_COUNT,
        "provider_calls": provider_calls,
        "secret_leaks": secret_leaks,
        "raw_artifacts_modified": 0,
        "run_ids_expected": expected_run_ids,
        "run_ids_observed": raw_run_ids,
        "conditions_observed": sorted(
            {str(record.get("condition", "")) for record in artifacts.runs}
        ),
        "scenarios_observed": sorted(
            {str(record.get("scenario_id", "")) for record in artifacts.runs}
        ),
        "repetitions_observed": sorted(
            {int(record.get("repetition", 0)) for record in artifacts.runs}
        ),
    }


def analyze_campaign(artifacts: CampaignArtifacts) -> CampaignAnalysis:
    integrity = validate_campaign_artifacts(artifacts)
    return CampaignAnalysis(
        state=CampaignState(integrity["state"]),
        campaign_id=integrity["campaign_id"],
        issues=[
            AnalysisIssue(
                severity=Severity(issue["severity"]),
                code=issue["code"],
                message=issue["message"],
                path=issue.get("path"),
                run_id=issue.get("run_id"),
                details=dict(issue.get("details", {})),
            )
            for issue in integrity["issues"]
        ],
        complete_runs=int(integrity["complete_runs"]),
        expected_runs=int(integrity["expected_runs"]),
        provider_calls=int(integrity["provider_calls"]),
        secret_leaks=int(integrity["secret_leaks"]),
        raw_artifacts_modified=int(integrity["raw_artifacts_modified"]),
        summary={},
        comparison={},
        reproducibility={},
    )
