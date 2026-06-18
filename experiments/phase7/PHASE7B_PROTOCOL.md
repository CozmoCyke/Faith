# Phase 7B Experimental Protocol

## Goal

Measure whether Faifth improves real agent behavior when the same probabilistic model is used across:

- `python_direct`
- `json_tools`
- `faifth_protocol`

## Frozen Variables

- same model
- same task set
- same scenario order
- same scoring rules
- same output schema
- same audit retention policy

## Experimental Design

1. Run the same benchmark tasks repeatedly.
2. Use the same model prompt and tool contract for each adapter.
3. Repeat each scenario multiple times to capture run-to-run variance.
4. Compare:
   - success rate;
   - state restoration fidelity;
   - audit completeness;
   - failure categories;
   - token and request cost;
   - variance across repetitions.

## Controls

- Do not change scenario text.
- Do not change scoring.
- Do not weaken rollback checks.
- Do not soften error classification.
- Do not collapse audit or trace data.

## Outputs To Capture

- per-run raw responses;
- per-scenario aggregated success rate;
- per-adapter score distribution;
- error-category counts;
- restoration fidelity summary;
- reproducibility notes.

## Acceptance Criteria

Phase 7B is valid only if:

- the same model is used across all adapters;
- the same tasks are replayed unchanged;
- repetitions are explicit and recorded;
- the protocol is frozen before execution begins;
- results remain directly comparable to Phase 7.

## Status

Prepared only.

Phase 7B is not executed yet. The next step is to wire the runner and experiment harness to this protocol, then execute it under the frozen design.
