# Phase 7 Failure Triage

This note classifies the Phase 7A benchmark failures after the harness corrections
made during triage. It is intentionally conservative: a secure refusal is not
counted as a failure when the state is preserved.

## Current Full-Variant Result

- `python_direct`: 15/15
- `json_tools`: 13/15
- `faifth_protocol`: 11/15

The ablation variants are still useful for diagnosis, but the main comparison is
the `faifth_full` row set above.

## What Was Fixed In The Benchmark

- `faifth_protocol` wire protocol mismatch (`faifth_protocol` -> `faifth-agent`)
- `python_direct` session stack not persisted across executions
- default session budgets ignored by `python_direct`
- default session budgets ignored by `faifth_protocol`
- `json_tools` candidate test comparison used encoded stack snapshots instead of values
- secure refusals were treated as failures even when the state was unchanged
- transaction and persistence scenarios were adjusted to be executable

## Scenario-by-Scenario Triage

| Scenario | python_direct | json_tools | faifth_protocol | Triage | Action |
| --- | --- | --- | --- | --- | --- |
| `basic_calculation` | pass | pass | pass | Baseline witness. | Keep. |
| `create_square` | pass | pass | pass | Harness bug fixed in `json_tools` test comparison. | Keep. |
| `reuse_square` | pass | pass | pass | Same as above. | Keep. |
| `compose_fourth_power` | pass | pass | pass | Same as above. | Keep. |
| `bad_type` | pass | fail | fail | `json_tools` still leaks state on error; `faifth_protocol` still reports a state change after a type mismatch. | Keep as real failure signals. |
| `forbidden_action` | pass | pass | pass | Secure refusal now counts as success when state is unchanged. | Keep. |
| `budget_exceeded` | pass | fail | fail | `json_tools` does not recover cleanly from the budget hit; `faifth_protocol` still does not enforce/restorer budgets consistently in the benchmark path. | Keep as real failure signals. |
| `mid_modification_error` | pass | pass | fail | `faifth_protocol` still does not roll back the whole transaction-scoped state; candidate metadata survives rollback. | Keep as real runtime weakness. |
| `rollback_exact` | pass | pass | fail | Same rollback boundary issue as above. | Keep as real runtime weakness. |
| `persistence_cycle` | pass | pass | pass | The explicit stack reset made the cycle meaningful. | Keep. |
| `hostile_data` | pass | pass | pass | Data/code separation holds. | Keep. |
| `long_sequence_10` | pass | pass | pass | Budget and persistence are aligned for the benchmark. | Keep. |
| `long_sequence_25` | pass | pass | pass | Same. | Keep. |
| `long_sequence_50` | pass | pass | pass | Same. | Keep. |
| `long_sequence_100` | pass | pass | pass | Same. | Keep. |

## Remaining Failures

### `json_tools`

- `bad_type`
  - Likely baseline weakness: no atomic restoration of the execution stack on failure.
  - This is a valid negative result for the generic JSON baseline.
- `budget_exceeded`
  - Likely baseline weakness: the budget overrun does not unwind the partial stack cleanly.
  - Also a valid negative result for the generic JSON baseline.

### `faifth_protocol`

- `bad_type`
  - Real weakness: the protocol path still leaves the session snapshot inconsistent after a contract failure.
- `budget_exceeded`
  - Real weakness: the protocol path still does not behave like a clean budget gate in the benchmark path.
- `mid_modification_error`
  - Real weakness: transaction rollback does not fully restore the session-visible state.
- `rollback_exact`
  - Real weakness: rollback still leaves transaction metadata visible in the benchmark state, so the rollback is not exact enough.

## Conclusion

The initial `0/15` for Faifth was not a valid verdict. Most of that signal came from
benchmark and adapter issues.

After the corrections:

- `python_direct` is clean on the full variant.
- `json_tools` is mostly functional, but still exposes two baseline weaknesses.
- `faifth_protocol` still has four meaningful failures, and those are the current
  action items for the runtime/protocol path.

The benchmark is now useful as a triage tool, not yet as a final verdict.
