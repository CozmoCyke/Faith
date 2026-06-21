# Phase 7B Offline Analysis Tooling Report

Branch: `phase-7b-analysis-tooling`

## Scope

This branch adds offline analysis tooling for Phase 7B campaign archives under
`experiments/phase7b/analysis/`.

The tooling is read-only with respect to campaign execution. It does not call
OpenAI, does not modify the live provider, and does not touch the frozen
protocol file or the pilot runner.

## Added CLI

The analysis module exposes:

- `python -m experiments.phase7b.analysis.cli validate <campaign-dir>`
- `python -m experiments.phase7b.analysis.cli summarize <campaign-dir>`
- `python -m experiments.phase7b.analysis.cli compare <campaign-dir>`
- `python -m experiments.phase7b.analysis.cli rebuild-derived <campaign-dir>`
- `python -m experiments.phase7b.analysis.cli verify-reproducibility <campaign-dir>`

Supported flags:

- `--json`
- `--strict`
- `--no-write`

## Derived Artifacts

The tooling can rebuild or verify the following derived files:

- `derived/integrity_report.json`
- `derived/integrity_report.md`
- `derived/summary.json`
- `derived/summary.csv`
- `derived/summary.md`
- `derived/paired_comparison.csv`
- `derived/paired_comparison.md`
- `derived/reproducibility_manifest.json`

## Validation Features

- campaign archive loading
- run integrity validation
- secret leak scanning across text artifacts
- incomplete campaign tolerance
- duplicate / missing / unexpected run detection
- paired comparison across the three Phase 7B conditions
- reproducibility manifest generation and verification

## Test Coverage

Added tests cover:

- loader behavior
- integrity validation
- metric computation
- paired comparison
- reproducibility manifest generation and verification

## Verification

Targeted validation on the new analysis test suite passed locally.

No OpenAI requests were made while building this tooling.
