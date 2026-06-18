# Faifth Phase 7 Final Report

## Executive Summary

Phase 7 established a reproducible deterministic benchmark for Faifth and converged the protocol runtime to parity with direct Python execution on the fifteen studied scenarios.

Final validated result:

- `python_direct`: `15/15`
- `json_tools`: `13/15`
- `faifth_protocol`: `15/15`

The benchmark was regenerated to `120` records and the full local quality suite passed:

- `109` tests
- `ruff check .`
- `mypy src`
- `compileall src`

## Chronology

### Brute Baseline

The first experimental pass established the raw baseline at `0/15`.

This phase was intentionally unsmoothed and showed that the initial harness was not yet producing a trustworthy comparison.

### Harness-Corrected Baseline

After triage and harness corrections, the benchmark stabilized at:

- `python_direct`: `15/15`
- `json_tools`: `13/15`
- `faifth_protocol`: `11/15`

This stage was important because it separated harness issues from real runtime defects.

### Real Defects Discovered

Four remaining `faifth_protocol` failures were confirmed as real:

- `bad_type`
- `budget_exceeded`
- `mid_modification_error`
- `rollback_exact`

These failures were not solved by changing the scenarios or the scoring.

## Fixes Applied

The final correction set focused on restoring the proper functional state boundary.

Key changes:

- runtime error handling now preserves the error-time stack in returned results while restoring session state correctly;
- protocol state restoration now covers the functional state that is expected to roll back;
- transaction-visible state now restores candidates, active versions, and stack state on rollback;
- benchmark canonical state comparison now ignores historical evidence that should remain visible, such as audit and error traces.

## Final Validation

Validated locally in a dedicated environment:

- `python -m pytest`
- `python -m ruff check .`
- `python -m mypy src`
- `python -m compileall src`
- `python experiments\phase7\runner.py`

Benchmark result after regeneration:

- `120` records
- `python_direct`: `15/15`
- `json_tools`: `13/15`
- `faifth_protocol`: `15/15`

The four real failures now pass:

- `bad_type`
- `budget_exceeded`
- `mid_modification_error`
- `rollback_exact`

The ablations remained discriminative:

- `faifth_sans_capabilities` still diverged strongly as expected;
- `faifth_sans_budgets` still fails `budget_exceeded`;
- `faifth_sans_contracts`, `faifth_sans_transactions`, and `faifth_sans_persistence` preserved the intended distinctions in the regenerated benchmark.

## Limits

This benchmark is deliberately deterministic and local.

It demonstrates:

- reproducibility;
- protocol correctness;
- state restoration guarantees;
- comparative behavior against a generic JSON tool dispatcher.

It does not yet demonstrate:

- superiority over Python in a general sense;
- robustness under probabilistic model variation;
- end-to-end behavior with a real LLM repeated across multiple trials.

## Conclusion

Faifth reaches functional parity with Python direct on the fifteen deterministic scenarios studied, while providing additional guarantees for contracts, capabilities, budgets, audit preservation, versioned procedural memory, and exact state restoration.

This result validates the viability of the prototype, but it does not yet prove a general advantage over Python or over arbitrary tool-calling systems.

The next experimental step should be Phase 7B: the same model, the same tasks, and multiple repetitions across the three systems, so the effect of Faifth can be measured under real probabilistic agent conditions.
