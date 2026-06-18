# Faifth Phase 3 Implementation Report

## 1. Status

Phase 3 has been implemented successfully.

Faifth now supports:

- explicit stack contracts on primitives and user words;
- optional contract annotations after the word name;
- dynamic input verification before execution;
- dynamic output and depth verification after execution;
- deterministic execution budgets;
- observable step, stack, and call-depth usage.

No Phase 4 feature was started.

## 2. Documents consulted

Primary references:

- `C:\dev\Faifth\FAIFTH_MVP_0_1_IMPLEMENTATION_PLAN.md`
- `C:\dev\Faifth\FAIFTH_PHASE_2_IMPLEMENTATION_REPORT.md`
- `C:\dev\Faifth\FAIFTH_PHASES_0_1_GIT_CHECKPOINT_REPORT.md`
- `C:\dev\Faifth\README.md`

Runtime files read during implementation:

- `C:\dev\Faifth\src\faifth\values.py`
- `C:\dev\Faifth\src\faifth\stack.py`
- `C:\dev\Faifth\src\faifth\errors.py`
- `C:\dev\Faifth\src\faifth\results.py`
- `C:\dev\Faifth\src\faifth\primitives.py`
- `C:\dev\Faifth\src\faifth\dictionary.py`
- `C:\dev\Faifth\src\faifth\definitions.py`
- `C:\dev\Faifth\src\faifth\tracing.py`
- `C:\dev\Faifth\src\faifth\interpreter.py`

## 3. Git state at start

- Branch at start: `phase-3-contracts-budgets`
- Base commit: `97eca2374756164757236c30329456d64ca19fd8`
- Stable Phase 2 tag present and unchanged: `phase-2-stable`
- Prior stable tag unchanged: `phase-1-stable`
- Remote: `origin`
- Remote URL: `https://github.com/CozmoCyke/Faith.git`

## 4. Files added

- `src/faifth/budgets.py`
- `src/faifth/contracts.py`
- `tests/test_budgets.py`
- `tests/test_contracts.py`
- `tests/test_phase3_integration.py`

## 5. Files modified

- `README.md`
- `src/faifth/__init__.py`
- `src/faifth/definitions.py`
- `src/faifth/dictionary.py`
- `src/faifth/errors.py`
- `src/faifth/interpreter.py`
- `src/faifth/primitives.py`
- `tests/test_dictionary.py`

## 6. Architecture

The Phase 3 architecture adds two small modules:

- `contracts.py` defines contract types and parsing helpers.
- `budgets.py` defines execution budgets and usage tracking.

The existing interpreter remained the execution entry point, but now:

- user-word publication can carry an optional `StackContract`;
- primitives also expose explicit contracts;
- execution tracks step count, peak stack depth, and peak call depth;
- budgets are checked deterministically before a token runs;
- contract and budget failures are surfaced as structured errors.

No general type system, no compilation, and no persistence layer were added.

## 7. Contract syntax

Supported contract annotation:

```text
: square ( int -- int ) dup * ;
```

Supported types:

- `int`
- `bool`
- `any`

Examples:

```text
: is-zero ( int -- bool ) 0 = ;
: constant-five ( -- int ) 5 ;
: consume ( int -- ) drop ;
: duplicate ( any -- any any ) dup ;
```

The Phase 2 syntax without a contract remains valid:

```text
: square dup * ;
```

## 8. Contract model

`StackContract` is immutable and serializable.

It stores:

- `inputs`
- `outputs`

User words now expose:

- `contract: StackContract | None`

Primitives now expose:

- `contract`
- `behavior`
- `description`

## 9. Validation strategy

Dynamic validation:

- input stack segment is checked before execution;
- output stack segment is checked after execution;
- depth mismatches are checked explicitly;
- failed contract checks restore the stack to its pre-call state.

Static validation:

- contractful words are simulated abstractly before publication;
- literals, primitives, and prior contractful words are analyzed;
- contractless dependencies are rejected inside contractful words;
- contractful words that do not match their declared contract are rejected.

This deliberately avoids general inference.

## 10. Budget model

`ExecutionBudget` is immutable and configurable.

Fields:

- `max_steps`
- `max_stack_depth`
- `max_call_depth`

`BudgetUsage` is exposed in the result and tracks:

- `steps_used`
- `peak_stack_depth`
- `peak_call_depth`
- `limit_hit`

Default budget values:

- `max_steps = 10_000`
- `max_stack_depth = 1_024`
- `max_call_depth = 64`

## 11. Order of checks

Stable execution order:

1. check step budget before the next token;
2. resolve the token;
3. if a contract exists, check inputs;
4. execute atomically;
5. enforce stack depth;
6. check contract outputs;
7. record trace and usage.

This order is shared across primitives and user words as far as their semantics allow.

## 12. Atomicity and rollback

Atomicity remains local:

- failed literals restore the stack;
- failed primitives restore the stack;
- failed user-word calls restore the stack before the call;
- contract failures do not leak partial mutations;
- budget failures do not leak partial mutations.

The earlier Phase 2 rollback semantics remain intact.

## 13. Trace

Trace kinds now include:

- `literal`
- `primitive`
- `definition`
- `call`
- `return`
- `error`

Trace entries remain structured and serializable, with depth preserved.

## 14. API surface

New public surface:

- `ExecutionBudget`
- `BudgetUsage`
- `StackContract`
- `ValueKind`
- contract-related error types
- budget-related error types

Execution API:

```python
session.execute("2 3 + dup *", budget=ExecutionBudget(...))
```

## 15. Demonstrations executed

### Contracted word

```text
: square ( int -- int ) dup * ;
5 square
```

Observed:

- `square` definition: `ok`, `steps = 1`
- `5 square`: `ok`, stack `[25]`, `steps = 4`

### Contract violation

```text
true square
```

Observed:

- `status = error`
- error code: `faifth.contract_input_mismatch`
- stack restored: `[True]`

### Composition

```text
: fourth-power ( int -- int ) square square ;
2 fourth-power
```

Observed:

- `status = ok`
- stack `[16]`

### Budget exact

```text
2 3 + dup *
```

With `max_steps = 5`:

- `status = ok`
- stack `[25]`
- `steps_used = 5`

With `max_steps = 4`:

- `status = error`
- error code: `faifth.step_budget_exceeded`

### Stack budget

```text
1 dup dup
```

With `max_stack_depth = 2`:

- `status = error`
- error code: `faifth.stack_depth_budget_exceeded`
- stack restored to `[1, 1]`

## 16. Validation results

Total tests now passing: **72**

New tests added in Phase 3: **10**

- `tests/test_budgets.py`: 3 tests
- `tests/test_contracts.py`: 4 tests
- `tests/test_phase3_integration.py`: 3 tests

### `pytest`

Result:

- 72 passed

### `ruff check .`

Result:

- All checks passed

### `mypy src`

Result:

- Success: no issues found in 13 source files

### `compileall`

Result:

- all source files under `src/faifth` compiled successfully

## 17. Limits known after Phase 3

Still out of scope:

- capability enforcement;
- transactions;
- persistence;
- AI protocol;
- concurrency;
- branching;
- looping;
- recursion;
- generic type variables;
- native compilation;
- bytecode;
- I/O.

## 18. Content deferred to Phase 4

Phase 4 should focus on:

- capability control;
- transaction semantics beyond local rollback;
- persistence;
- richer protocol integration;
- additional observability if needed.

## 19. Git state

- Branch created for this work: `phase-3-contracts-budgets`
- Implementation commit hash: `d1503ff66ae6c775ee2fb13e73d40139125c8972`
- Commit message: `Implement Faifth phase 3 contracts and budgets`
- `phase-2-stable` remains unchanged
- `phase-1-stable` remains unchanged
- `git status --short` after the implementation commit was clean before this report was added

## 20. No external project modified

Only `C:\dev\Faifth` was modified.
