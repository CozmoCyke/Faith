from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from experiments.phase7b.infra import (
    MODEL_SNAPSHOT,
    PILOT_BUDGETS,
    RANDOMIZATION_SEED,
)

from .loader import load_campaign_artifacts

SCHEMA_VERSION = 1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build_reproducibility_manifest(campaign_dir: Path) -> dict[str, Any]:
    artifacts = load_campaign_artifacts(campaign_dir)
    files = []
    for path in (
        artifacts.paths.preflight,
        artifacts.paths.runs,
        *sorted(artifacts.paths.transcripts_dir.glob("*.jsonl")),
    ):
        if path.exists():
            files.append(
                {
                    "path": path.relative_to(campaign_dir).as_posix(),
                    "sha256": _sha256_file(path),
                }
            )
    manifest = artifacts.manifest or {}
    preflight = artifacts.preflight or {}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": str(
            manifest.get("campaign_id")
            or preflight.get("campaign_id")
            or campaign_dir.name
        ),
        "git_head": _git_head(_repo_root()),
        "protocol_hash": str(
            manifest.get("protocol_hash") or preflight.get("protocol_hash") or ""
        ),
        "model_snapshot": str(
            manifest.get("model_snapshot")
            or preflight.get("model_snapshot")
            or MODEL_SNAPSHOT
        ),
        "seed": int(
            manifest.get("randomization_seed")
            or preflight.get("randomization_seed")
            or RANDOMIZATION_SEED
        ),
        "budgets": {
            "name": PILOT_BUDGETS.name,
            "max_output_tokens": PILOT_BUDGETS.max_output_tokens,
            "max_calls_per_scenario": PILOT_BUDGETS.max_calls_per_scenario,
            "timeout_per_call_seconds": PILOT_BUDGETS.timeout_per_call_seconds,
            "timeout_per_scenario_seconds": PILOT_BUDGETS.timeout_per_scenario_seconds,
            "timeout_full_seconds": PILOT_BUDGETS.timeout_full_seconds,
            "max_provider_retries_per_call": (
                PILOT_BUDGETS.max_provider_retries_per_call
            ),
        },
        "ordered_runs": list(manifest.get("runs", [])),
        "artifact_hashes": files,
    }
    payload["sha256"] = hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    return payload


def verify_reproducibility_manifest(campaign_dir: Path) -> dict[str, Any]:
    artifacts = load_campaign_artifacts(campaign_dir)
    manifest_path = artifacts.paths.reproducibility_json
    if not manifest_path.exists():
        return {
            "status": "MISSING",
            "verified": False,
            "missing": ["derived/reproducibility_manifest.json"],
            "mismatched": [],
        }
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    current = build_reproducibility_manifest(campaign_dir)
    expected_files = {
        entry["path"]: entry["sha256"] for entry in expected.get("artifact_hashes", [])
    }
    current_files = {
        entry["path"]: entry["sha256"] for entry in current.get("artifact_hashes", [])
    }
    mismatched = []
    missing = []
    for path, digest in expected_files.items():
        if path not in current_files:
            missing.append(path)
        elif current_files[path] != digest:
            mismatched.append(path)
    status = "MATCH" if not missing and not mismatched else "MISMATCH"
    return {
        "status": status,
        "verified": status == "MATCH",
        "missing": missing,
        "mismatched": mismatched,
        "expected_sha256": expected.get("sha256", ""),
        "current_sha256": current.get("sha256", ""),
    }
