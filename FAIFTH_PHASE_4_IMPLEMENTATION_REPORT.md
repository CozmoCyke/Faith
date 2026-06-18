# Faifth Phase 4 Implementation Report

## 1. Status

Phase 4 has been implemented successfully.

Faifth now supports:

- immutable capability identifiers and sets;
- session-level permissions and execution-time restriction;
- capability-gated primitives and user words;
- transitive capability calculation for user words;
- explicit transactions on internal state;
- commit and rollback;
- automatic rollback on execution failure while a transaction is active;
- structured security and transaction metadata in results and traces.

No Phase 5 feature was started.

## 2. Documents consulted

Primary references:

- `C:\dev\Faifth\FAIFTH_MVP_0_1_IMPLEMENTATION_PLAN.md`
- `C:\dev\Faifth\FAIFTH_PHASE_2_IMPLEMENTATION_REPORT.md`
- `C:\dev\Faifth\FAIFTH_PHASE_3_IMPLEMENTATION_REPORT.md`
- `C:\dev\Faifth\README.md`

Runtime files read during implementation:

- `C:\dev\Faifth\src\faifth\errors.py`
- `C:\dev\Faifth\src\faifth\results.py`
- `C:\dev\Faifth\src\faifth\primitives.py`
- `C:\dev\Faifth\src\faifth\dictionary.py`
- `C:\dev\Faifth\src\faifth\definitions.py`
- `C:\dev\Faifth\src\faifth\contracts.py`
- `C:\dev\Faifth\src\faifth\budgets.py`
- `C:\dev\Faifth\src\faifth\tracing.py`
- `C:\dev\Faifth\src\faifth\interpreter.py`

## 3. Git state at start

- Branch at start: `phase-3-contracts-budgets`
- Base commit: `b01f62a1ca23ce4e362805cd476a76367d102024`
- Stable Phase 3 tag created from that commit: `phase-3-stable`
- Prior stable tag unchanged: `phase-2-stable`
- Prior stable tag unchanged: `phase-1-stable`
- Remote: `origin`
- Remote URL: `https://github.com/CozmoCyke/Faith.git`

## 4. Files added in Phase 4

- `src/faifth/capabilities.py`
- `src/faifth/transactions.py`
- `tests/test_capabilities.py`
- `tests/test_permissions.py`
- `tests/test_transactions.py`
- `tests/test_phase4_integration.py`

## 5. Files modified in Phase 4

- `README.md`
- `src/faifth/__init__.py`
- `src/faifth/contracts.py`
- `src/faifth/dictionary.py`
- `src/faifth/errors.py`
- `src/faifth/interpreter.py`
- `src/faifth/primitives.py`
- `src/faifth/tracing.py`
- `tests/test_dictionary.py`

## 6. Architecture

The Phase 4 architecture adds two small, explicit modules:

- `capabilities.py` defines immutable capability identifiers and capability sets.
- `transactions.py` defines transaction records for auditability.

The interpreter remains the execution entry point, but now:

- execution can be restricted to a subset of the session capabilities;
- primitives expose the capabilities they require;
- user words expose transitive required capabilities computed from their bodies;
- permission failures stop execution before the body runs;
- active transactions snapshot the mutable dictionary state and can be rolled back exactly.

No OS features, I/O effects, native compilation, or concurrency were added.

## 7. Capability model

Stable capability identifiers:

- `core.compute`
- `core.stack`
- `dictionary.define`
- `dictionary.read`
- `introspection.read`
- `transaction.manage`

Representation:

- `Capability(name: str)`
- `CapabilitySet(granted=frozenset(...))`

Supported operations:

- `allows(required)`
- `missing(required)`
- `union(other)`
- `intersection(other)`
- `difference(other)`
- deterministic `to_dict()`

Compatibility profile:

- `CapabilitySet.development_defaults()` grants the prototype capabilities needed by the existing examples and tests.

Strict profile:

- `CapabilitySet.strict_defaults()` returns an empty capability set.

The default `InterpreterSession()` uses the compatibility profile so the older phases remain runnable without boilerplate. For strict experiments, a caller can pass an explicit `CapabilitySet`.

## 8. Permission policy

The policy implemented is:

> A required capability must be present before the action begins.

Priority rules:

- session capabilities define the upper bound;
- execution-time capabilities may only restrict that upper bound;
- if execution requests capabilities outside the session set, the request is rejected with `CapabilityEscalationDenied`;
- if a primitive, user word, or transaction action needs a missing capability, execution is rejected with `CapabilityDenied`.

Permission boundaries:

- primitives check their required capabilities before running;
- user words check their transitive required capabilities before entering the body;
- definitions require `dictionary.define`;
- transactions require `transaction.manage`;
- introspection wrappers on `InterpreterSession` require `dictionary.read` or `introspection.read` depending on the operation.

## 9. Primitive and word capabilities

Primitive capability mapping:

- arithmetic and equality primitives use `core.compute`;
- stack manipulation and `depth` use `core.stack`.

`UserWord` now stores:

- `required_capabilities`

Those capabilities are computed from the word body and the transitive requirements of referenced user words.

Example:

- `square` requires `core.compute` and `core.stack`;
- `fourth-power` inherits the same set transitively.

## 10. Permission verification order

Stable execution order:

1. check step budget;
2. resolve the token;
3. verify permissions;
4. verify contract input if present;
5. execute atomically;
6. verify contract output if present;
7. record trace and usage.

For definitions:

1. parse the definition;
2. check `dictionary.define`;
3. validate the body and transitive requirements;
4. publish atomically.

## 11. Transaction model

The transaction model is intentionally small.

Snapshot contents:

- user-word dictionary state;
- transaction record metadata;
- session-local transaction sequence number.

Not snapshotted:

- external files;
- network;
- system time;
- process state;
- physical effects.

Statuses:

- `active`
- `committed`
- `rolled_back`

Public API:

- `begin_transaction()`
- `commit_transaction()`
- `rollback_transaction()`

Behavior:

- nested transactions are rejected;
- commit preserves the changes made since the snapshot;
- manual rollback restores the exact prior dictionary state;
- any execution failure while a transaction is active triggers automatic rollback.

## 12. Trace and audit

Trace entries now carry security metadata:

- required capabilities;
- granted capabilities;
- missing capabilities;
- permission status;
- transaction id.

Transaction records expose:

- transaction id;
- status;
- rollback reason;
- error;
- words added;
- words removed;
- granted capabilities.

This keeps the audit observable without introducing external persistence.

## 13. Compatibility with earlier phases

Compatibility preserved:

- Phase 1 literals, primitives, and traces continue to work.
- Phase 2 user-defined words and sessions continue to work.
- Phase 3 contracts and deterministic budgets continue to work.

The default session still runs the historical examples because it uses the compatibility capability profile.

## 14. Demonstrations executed

### Authorized execution

Input:

```text
: square ( int -- int ) dup * ;
5 square
```

Observed:

```text
ok [25] 4
```

### Capability denial

Input:

```text
2 3 +
```

Session capabilities:

```text
core.stack
```

Observed:

```text
error faifth.capability_denied [2, 3] ('core.compute',)
```

### Transaction rollback

Input:

```text
begin transaction
: square ( int -- int ) dup * ;
true square
```

Observed:

```text
error faifth.contract_input_mismatch rolled_back False True
```

Meaning:

- the transaction was rolled back;
- `square` was removed from the dictionary;
- the failure remained visible in the result and the audit.

## 15. Validation results

Total tests passing: **88**

### `pytest`

Result:

- 88 passed

### `ruff check .`

Result:

- All checks passed

### `mypy src`

Result:

- Success: no issues found in 15 source files

### `compileall`

Result:

- all source files under `src/faifth` compiled successfully

## 16. Limitations still in force

Still out of scope:

- persistence on disk;
- external I/O;
- network;
- native compilation;
- bytecode VM work;
- OS boot or drivers;
- concurrency and scheduling;
- recursive or branching language features;
- physical robot autonomy.

## 17. Content deferred to Phase 5

Phase 5 should focus on:

- persistence;
- explicit save/restore of the dictionary across runs;
- richer structured protocol integration if needed;
- more exhaustive observability around external effects.

## 18. Git state

- Branch created for this work: `phase-4-capabilities-transactions`
- Implementation commit hash: `2fa6fe6`
- Commit message: `Implement Faifth phase 4 capabilities and transactions`
- `phase-3-stable` remains on `b01f62a1ca23ce4e362805cd476a76367d102024`
- `phase-2-stable` remains unchanged
- `phase-1-stable` remains unchanged

## 19. No external project modified

Only `C:\dev\Faifth` was modified.
