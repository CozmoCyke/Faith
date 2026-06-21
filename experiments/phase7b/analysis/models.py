from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    BLOCKING = "BLOCKING"


class CampaignState(StrEnum):
    COMPLETE_VALID = "COMPLETE_VALID"
    COMPLETE_INVALID = "COMPLETE_INVALID"
    INCOMPLETE_VALIDLY_RECORDED = "INCOMPLETE_VALIDLY_RECORDED"
    CORRUPTED = "CORRUPTED"


@dataclass(frozen=True, slots=True)
class CampaignPaths:
    campaign_dir: Path
    preflight: Path
    runs: Path
    transcripts_dir: Path
    derived_dir: Path
    manifest: Path
    protocol: Path
    validation_report: Path
    pilot_validation_report: Path
    summary_csv: Path
    summary_json: Path
    summary_md: Path
    integrity_json: Path
    integrity_md: Path
    paired_csv: Path
    paired_md: Path
    reproducibility_json: Path


@dataclass(frozen=True, slots=True)
class CampaignArtifacts:
    paths: CampaignPaths
    preflight: dict[str, Any] | None
    manifest: dict[str, Any] | None
    protocol: dict[str, Any] | None
    runs: list[dict[str, Any]]
    transcripts: dict[str, list[dict[str, Any]]]
    derived_validation_report: str | None


@dataclass(frozen=True, slots=True)
class AnalysisIssue:
    severity: Severity
    code: str
    message: str
    path: str | None = None
    run_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
        }
        if self.path is not None:
            payload["path"] = self.path
        if self.run_id is not None:
            payload["run_id"] = self.run_id
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(frozen=True, slots=True)
class NumericSummary:
    total: float
    mean: float
    median: float
    minimum: float
    maximum: float
    standard_deviation: float

    def to_dict(self) -> dict[str, float]:
        return {
            "total": self.total,
            "mean": self.mean,
            "median": self.median,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "standard_deviation": self.standard_deviation,
        }


@dataclass(frozen=True, slots=True)
class CampaignAnalysis:
    state: CampaignState
    campaign_id: str
    issues: list[AnalysisIssue]
    complete_runs: int
    expected_runs: int
    provider_calls: int
    secret_leaks: int
    raw_artifacts_modified: int
    summary: dict[str, Any]
    comparison: dict[str, Any]
    reproducibility: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "campaign_id": self.campaign_id,
            "issues": [issue.to_dict() for issue in self.issues],
            "complete_runs": self.complete_runs,
            "expected_runs": self.expected_runs,
            "provider_calls": self.provider_calls,
            "secret_leaks": self.secret_leaks,
            "raw_artifacts_modified": self.raw_artifacts_modified,
            "summary": self.summary,
            "comparison": self.comparison,
            "reproducibility": self.reproducibility,
        }
