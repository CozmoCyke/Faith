# FAIFTH Phase 0 Implementation Plan

## 1. Objective

Phase 0 establishes the smallest reliable foundation for Faifth:

- a Python project skeleton;
- deterministic value representations;
- a bounded, testable data stack;
- structured, serializable errors;
- structured execution results;
- first automated tests;
- validation commands and quality rules.

Phase 0 must prove only the kernel foundation is clean. It must not introduce interpreter logic, dictionary semantics, contracts, capabilities, transactions, persistence, or AI protocol machinery.

## 2. Phase 0 scope

### Included

- project layout;
- packaging metadata;
- public package entry point;
- value types;
- stack abstraction;
- error hierarchy;
- execution result model;
- unit tests for each of the above;
- linting, type-checking, and test commands.

### Explicitly excluded

- tokenizer;
- interpreter or VM;
- executable dictionary;
- word definitions;
- contracts beyond placeholder-level representation;
- capabilities;
- transactions;
- rollback engine;
- persistence;
- protocol with an AI model;
- CLI;
- networking;
- filesystem host effects;
- any external tool integration.

## 3. Decisions carried over from the general plan

The general MVP plan fixes several Phase 0-relevant decisions:

- Faifth is a Python prototype first.
- The core should be small and deterministic.
- State should be explicit and serializable.
- Errors should be structured, not text-only.
- The runtime should be designed for future expansion, but the first step must stay minimal.

### Phase 0-specific interpretation

For Phase 0, this means:

- no execution semantics beyond stack operations and data-model validation;
- no hidden global state;
- no dependence on the future interpreter layer;
- no promise that the final runtime structure is already known.

## 4. Ambiguities and resolved choices

### 4.1 `stack.py` vs `stacks.py`

The general plan used `stacks.py`; the Phase 0 proposal uses `stack.py`.

Decision: **use `stack.py`**.

Reason:

- Phase 0 needs only one stack abstraction;
- a singular module keeps the initial API compact;
- the plural name can be introduced later if separate data/return stack implementations diverge.

### 4.2 `state.py` vs `results.py`

The general plan included `state.py`; the Phase 0 proposal focuses on `results.py`.

Decision: **do not add a separate `state.py` in Phase 0**.

Reason:

- Phase 0 does not need a runtime state container yet;
- the only structured execution artifact required now is the result object;
- adding state too early would create a placeholder abstraction without behavior.

### 4.3 `src/` layout

Decision: **use a `src/` layout**.

Reason:

- it prevents accidental imports from the repository root;
- it makes packaging and tests cleaner;
- it remains small and conventional for Python projects.

## 5. Exact repository structure

```text
Faifth/
├── README.md
├── pyproject.toml
├── src/
│   └── faifth/
│       ├── __init__.py
│       ├── errors.py
│       ├── values.py
│       ├── stack.py
│       └── results.py
└── tests/
    ├── test_values.py
    ├── test_stack.py
    ├── test_errors.py
    └── test_results.py
```

### File count

- Python source files: 5
- Python test files: 4
- total Python files planned in Phase 0: 9
- non-Python project files: 2

## 6. Responsibility of each file

### `pyproject.toml`

Responsibilities:

- define the package build metadata;
- configure `pytest`, `ruff`, and `mypy` or `pyright`;
- pin Python version compatibility;
- keep the initial toolchain lightweight.

### `README.md`

Responsibilities:

- explain the purpose of Phase 0;
- document the package layout;
- list validation commands;
- state what is intentionally out of scope.

### `src/faifth/__init__.py`

Responsibilities:

- expose the minimal public API;
- re-export the few types that Phase 0 considers stable enough to import directly.

### `src/faifth/errors.py`

Responsibilities:

- define the base error class;
- define structured stack and value-related errors;
- provide deterministic serialization helpers;
- make error identity independent from free-form message text.

### `src/faifth/values.py`

Responsibilities:

- define the allowed value representations;
- validate value construction;
- preserve deterministic equality and display;
- prepare future serialization compatibility.

### `src/faifth/stack.py`

Responsibilities:

- implement a bounded, deterministic stack;
- support push, pop, peek, depth, clear, snapshot, restore;
- avoid global mutable state;
- validate items and snapshot shape.

### `src/faifth/results.py`

Responsibilities:

- define structured success and failure results;
- ensure result objects cannot represent contradictory states;
- provide serialization and inspection helpers;
- serve as the future execution result model even before execution exists.

### `tests/test_values.py`

Responsibilities:

- verify allowed value creation;
- verify equality and repr stability;
- verify invalid values are rejected;
- verify the representation is serialization-friendly.

### `tests/test_stack.py`

Responsibilities:

- verify stack behavior independently from any interpreter;
- verify empty-stack failure;
- verify snapshot and restore isolation;
- verify depth and overflow behavior.

### `tests/test_errors.py`

Responsibilities:

- verify stable error codes;
- verify serializable structure;
- verify deterministic formatting;
- verify metadata and optional context handling.

### `tests/test_results.py`

Responsibilities:

- verify success and failure result shapes;
- verify invariants such as "success cannot carry an active error";
- verify serialization and deterministic display;
- verify metadata round-trip behavior.

## 7. Value model

Phase 0 should keep the value space small and explicit.

### Allowed value kinds

- `Int`
- `Bool`
- `Str`
- `Symbol`
- `Handle` only if needed for future compatibility

### Recommendation

Use **small dataclasses or frozen classes**, not raw Python primitives alone.

Reason:

- raw primitives are easy to use, but they do not carry stable type identity;
- dedicated classes give deterministic repr, future serialization hooks, and explicit validation;
- frozen dataclasses are easy to compare and test.

### Proposed minimal shape

- immutable;
- hashable where sensible;
- deterministic `repr`;
- explicit type tag or concrete class identity;
- no implicit coercion between integers and booleans.

### Rule on booleans

`Bool` must remain distinct from `Int`.

Reason:

- Python's `bool` is a subclass of `int`;
- Faifth should not inherit that ambiguity in its own model;
- tests should enforce this distinction explicitly.

### Validation rule

Invalid values should be rejected at construction time, not deferred to later phases.

## 8. Stack design

### 8.1 Stack API

The Phase 0 stack API is:

- `push(value)`
- `pop()`
- `peek()`
- `depth()`
- `clear()`
- `snapshot()`
- `restore(snapshot)`

### 8.2 Behavior rules

- `push` appends to the top of the stack.
- `pop` removes and returns the top item.
- `peek` returns the top item without removal.
- `depth` returns the number of items currently stored.
- `clear` empties the stack.
- `snapshot` returns an independent copy of the stack contents.
- `restore` replaces the stack contents from a snapshot.

### 8.3 Empty stack behavior

- `pop` on an empty stack raises `StackUnderflow`.
- `peek` on an empty stack raises `StackUnderflow`.

### 8.4 Overflow behavior

Phase 0 should support an optional maximum depth.

Decision:

- the stack constructor may accept `max_depth`;
- if no limit is provided, it is unbounded for tests;
- if a limit is provided and exceeded, `StackOverflow` is raised.

### 8.5 Snapshot behavior

- snapshots must be independent copies;
- mutating the live stack must not mutate a prior snapshot;
- restoring from a snapshot must not retain hidden aliasing;
- invalid snapshot data must raise `InvalidSnapshot`.

### 8.6 Equality and debugging

Recommended rules:

- two stacks are equal when their ordered contents and configuration are equal;
- `repr` should be deterministic and readable;
- debug output should show top-of-stack direction clearly.

### 8.7 No global state

The stack implementation must be instance-based only.

No module-level singleton stack is allowed.

## 9. Error model

### 9.1 Base hierarchy

Required classes:

- `FaifthError`
- `StackUnderflow`
- `StackOverflow`
- `TypeMismatch`
- `InvalidValue`
- `InvalidSnapshot`

### 9.2 Shared fields

Each error should support:

- stable `code`
- human-readable `message`
- optional structured `metadata`
- optional structured `context`
- deterministic serialization to a dictionary

### 9.3 Stable codes

Codes should be simple, stable strings, for example:

- `faifth.error`
- `faifth.stack_underflow`
- `faifth.stack_overflow`
- `faifth.type_mismatch`
- `faifth.invalid_value`
- `faifth.invalid_snapshot`

The exact strings may vary, but the principle is fixed:

- tests must assert code stability;
- tests must not rely on message text alone.

### 9.4 Test behavior

- error instances should compare by structure where appropriate;
- serialization should preserve code and metadata;
- `str(error)` may be human-friendly, but is not the identity of the error;
- `repr(error)` should be deterministic.

## 10. Result model

### 10.1 Purpose

`results.py` defines a generic structured result object that can later represent execution, validation, or persistence outcomes.

### 10.2 Minimal result shape

Recommended fields:

- `status`
- `value`
- `error`
- `metadata`

### 10.3 Status values

Recommended statuses:

- `ok`
- `error`

Optional future statuses can be added later, but Phase 0 should keep the set small.

### 10.4 Invariants

- `status="ok"` must not carry an active error;
- `status="error"` must carry an error object;
- `value` may be `None` on error;
- metadata must always be a mapping or equivalent structured object.

### 10.5 Serialization

The result object must support conversion to a plain dictionary.

This is required so future interpreter and protocol work can reuse the same model without redesign.

## 11. Test plan

### 11.1 Expected test count

Approximate tests planned in Phase 0: **20 to 30 assertions/cases**, grouped into four test files.

That is enough to pin down the foundation without overbuilding the harness.

### 11.2 `tests/test_values.py`

Cases:

1. create an `Int`;
2. create a `Bool`;
3. create a `Str`;
4. create a `Symbol`;
5. create a `Handle` only if included;
6. equality for same-kind values;
7. inequality for different kinds;
8. `Bool` must not equal `Int(1)`;
9. deterministic `repr`;
10. serialization-friendly dictionary output;
11. invalid value construction is rejected.

### 11.3 `tests/test_stack.py`

Cases:

1. empty stack depth is zero;
2. `push` increases depth;
3. `pop` returns the last pushed item;
4. LIFO order is preserved;
5. `peek` does not remove item;
6. `clear` empties the stack;
7. `snapshot` produces independent copy;
8. `restore` restores exact contents;
9. restoring one stack does not mutate the snapshot source;
10. `pop` on empty stack raises `StackUnderflow`;
11. `peek` on empty stack raises `StackUnderflow`;
12. exceeding `max_depth` raises `StackOverflow`;
13. invalid snapshot raises `InvalidSnapshot`.

### 11.4 `tests/test_errors.py`

Cases:

1. base error has stable code;
2. specialized error code is stable;
3. message is present and human-readable;
4. metadata round-trips;
5. context round-trips;
6. `to_dict` produces deterministic structure;
7. `repr` is deterministic;
8. equality or comparison behaves structurally as expected.

### 11.5 `tests/test_results.py`

Cases:

1. create success result;
2. create error result;
3. success result has no active error;
4. error result carries an error;
5. metadata round-trips;
6. dictionary serialization is deterministic;
7. invalid contradictory construction is rejected.

## 12. Quality tools and commands

### 12.1 Tooling choice

Use a lightweight Python toolchain:

- Python 3.12
- `pytest`
- `ruff`
- `mypy`

### 12.2 Packaging

Use `pyproject.toml` only.

Do not add extra framework layers.

### 12.3 Validation commands

Recommended commands:

```text
python -m pytest
python -m ruff check src tests
python -m mypy src
python -m compileall src
```

If `pyright` is preferred over `mypy`, it can be swapped later, but Phase 0 should choose only one type checker.

## 13. Implementation order

Recommended order:

1. `pyproject.toml`
2. `README.md`
3. `src/faifth/__init__.py`
4. `src/faifth/errors.py`
5. `tests/test_errors.py`
6. `src/faifth/values.py`
7. `tests/test_values.py`
8. `src/faifth/stack.py`
9. `tests/test_stack.py`
10. `src/faifth/results.py`
11. `tests/test_results.py`
12. `python -m pytest`
13. `python -m ruff check src tests`
14. `python -m mypy src`
15. `python -m compileall src`

### Dependency notes

- `errors.py` should exist before the stack and value modules so validation failures have a stable shape.
- `values.py` should exist before the stack module so the stack can validate allowed items.
- `results.py` can be added after values and errors are stable.
- tests should be written alongside each module, not deferred to the end.

## 14. Acceptance criteria

Phase 0 is ready to implement only if all of the following are true:

1. every planned file has one clear responsibility;
2. no interpreter logic appears;
3. the stack has no global mutable state;
4. every error has a stable structured code;
5. snapshots are independent and restorable;
6. allowed values are explicitly defined;
7. result objects cannot represent contradictory states;
8. every planned behavior has at least one test case;
9. the validation commands are known in advance;
10. the Phase 1 boundary remains intact.

## 15. Risks

### Technical risks

- using raw Python values everywhere would blur type identity;
- letting `bool` collapse into `int` would create a bad precedent;
- overly clever snapshot handling could introduce aliasing bugs;
- a too-rich result model could preempt the interpreter design.

### Process risks

- trying to solve Phase 1 inside Phase 0;
- adding placeholder abstractions that have no behavior yet;
- introducing protocol or persistence concepts too early;
- overfitting the initial models to hypothetical future needs.

### Mitigations

- keep the model tiny;
- keep modules independent;
- test each module directly;
- prefer explicit validation over implicit coercion;
- avoid speculative abstractions unless the Phase 0 tests need them.

## 16. Explicit out-of-scope items

Phase 0 must not include:

- tokenizer;
- interpreter;
- dictionary;
- word definitions;
- contracts beyond a placeholder data field;
- capabilities;
- transactions;
- persistence;
- AI protocol;
- CLI;
- host I/O;
- network;
- filesystem integration;
- plugin or agent framework support.

## 17. Final implementation statement

Phase 0 should be treated as complete only when:

- the package imports cleanly;
- values are deterministic;
- the stack is isolated and testable;
- structured errors are stable;
- structured results are valid;
- the four test files fully pin the behavior;
- the codebase is still small enough that Phase 1 can be designed without rethinking the foundation.