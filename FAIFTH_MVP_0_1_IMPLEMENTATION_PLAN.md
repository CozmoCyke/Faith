# FAIFTH MVP 0.1 Implementation Plan

## 1. Summary of decisions

Faifth 0.1 will be implemented as a **small agent runtime prototype** on top of an existing host OS, not as a bootable OS.

Key decisions:

- **Language for the prototype:** Python.
- **Execution model:** direct interpreter first, with a very small internal instruction model if needed later.
- **Core shape:** small stack machine with inspectable data and return stacks.
- **Safety model:** deny-by-default capabilities, runtime contract checks, explicit budgets, transactional mutations, and structured errors.
- **Persistence:** versioned, validated storage for the dictionary and metadata, not blind code execution on load.
- **AI interface:** structured request/response protocol, not free-form terminal text.
- **MVP priority:** observability and correctness over performance.

What is deliberately not part of MVP 0.1:

- booting hardware;
- OS kernel work;
- native compilation;
- unrestricted plugins;
- graphical UI;
- concurrency beyond the minimal host loop;
- physical robot control;
- free network access;
- a full filesystem abstraction inside the language core.

## 2. MVP perimeter

The MVP must prove this hypothesis:

> An AI can act more safely inside a small explicit machine than in a large implicit environment.

### Included

- tokenizer;
- interpreter;
- data stack;
- return stack;
- dictionary;
- primitives;
- user-defined words;
- stack contracts;
- execution journal;
- budgets;
- capabilities;
- structured errors;
- automated tests;
- controlled persistence of the dictionary;
- structured AI protocol;
- simple transactions and rollback.

### Excluded

- boot material;
- kernel or drivers;
- full GUI;
- open network access;
- unlimited self-modification;
- native compilation;
- complex multitasking;
- general scheduler;
- a first-class filesystem API in the core;
- autonomous physical robotics.

## 3. Prototype language choice

### Recommended host language: Python

Why Python is the right first prototype language:

- fastest iteration speed for an experimental runtime;
- readable implementation and easy review;
- strong support for tests and structured data;
- straightforward instrumentation and trace logging;
- easy to express the data model cleanly;
- portable to later ports in Rust, C, or WebAssembly-backed implementations.

### Why not Rust first

Rust would be a good later implementation target, but it is not the best first move for this phase because:

- iteration is slower for a design that is still moving;
- the prototype needs frequent semantic changes;
- the main risk is architectural ambiguity, not raw speed.

### Why not TypeScript first

TypeScript would work for tooling and UI, but it is weaker for a deterministic runtime core where the implementation should stay close to a precise execution model.

### Why not C first

C is too low-level for a first feasibility prototype:

- more manual safety work;
- slower experimentation;
- higher risk of memory bugs during design churn.

### Future path

If Faifth 0.1 proves valuable, the architecture should remain portable enough to later reimplement:

- the kernel/runtime core in Rust or C;
- the protocol and tooling in Python or TypeScript;
- a portability backend in WebAssembly.

## 4. Proposed repository shape

Minimal structure:

```text
Faifth/
├── README.md
├── pyproject.toml
├── faifth/
│   ├── __init__.py
│   ├── tokenizer.py
│   ├── values.py
│   ├── stacks.py
│   ├── errors.py
│   ├── state.py
│   ├── words.py
│   ├── dictionary.py
│   ├── contracts.py
│   ├── capabilities.py
│   ├── budgets.py
│   ├── transactions.py
│   ├── tracing.py
│   ├── persistence.py
│   ├── protocol.py
│   └── interpreter.py
├── tests/
│   ├── test_values.py
│   ├── test_stacks.py
│   ├── test_interpreter.py
│   ├── test_dictionary.py
│   ├── test_contracts.py
│   ├── test_capabilities.py
│   ├── test_budgets.py
│   ├── test_transactions.py
│   ├── test_persistence.py
│   └── test_protocol.py
├── examples/
│   └── basic_words.faifth
├── experiments/
│   ├── compare_python.py
│   ├── compare_tool_calling.py
│   └── stack_prediction_bench.py
└── docs/
    ├── runtime_state.md
    ├── word_metadata.md
    └── protocol.md
```

### Why each module exists

- `tokenizer.py`: turn source text into stable tokens.
- `values.py`: define the small value algebra used by the runtime.
- `stacks.py`: stack operations and bounded stack behavior.
- `errors.py`: structured error types and error serialization.
- `state.py`: explicit runtime state and execution result objects.
- `words.py`: word representation and metadata.
- `dictionary.py`: lookup, definition, versioning, and inspection.
- `contracts.py`: stack-effect and metadata validation.
- `capabilities.py`: deny-by-default effect authorization.
- `budgets.py`: deterministic resource accounting.
- `transactions.py`: snapshot, commit, rollback.
- `tracing.py`: execution journal and trace records.
- `persistence.py`: validated storage and restore.
- `protocol.py`: structured AI exchange.
- `interpreter.py`: execution loop and orchestration.

This is the smallest coherent split that still keeps the concerns separated.

## 5. Internal representations

### 5.1 Values

Keep the value system intentionally small.

Recommended variants:

- `Int`
- `Bool`
- `Str`
- `Symbol`
- `WordRef`
- `Handle`
- `ErrorValue`

Optional later additions:

- `List`
- `Bytes`
- `None` or `Unit`

Principles:

- values should be explicit and serializable;
- opaque handles should not expose host internals;
- no broad object system in the MVP;
- no heavy type inference in the MVP.

### 5.2 Word

Each word should contain at least:

- `name`
- `body`
- `signature`
- `description`
- `effects`
- `required_capabilities`
- `status`
- `version`
- `dependencies`
- `tests`
- `provenance`
- `confidence`

Recommended status values:

- `experimental`
- `tested`
- `approved`
- `critical`
- `primitive_protected`
- `disabled`
- `retired`

### 5.3 Runtime state

The runtime state must be explicit and serializable.

Recommended fields:

- `data_stack`
- `return_stack`
- `dictionary`
- `instruction_pointer`
- `current_word`
- `budget_remaining`
- `authorized_capabilities`
- `active_transaction`
- `trace`
- `last_error`

### 5.4 Execution result

Do not rely only on exceptions.

Every execution should return a structured result such as:

```text
ExecutionResult {
  status: ok | error | rollback | denied | budget_exceeded
  stack_before: [...]
  stack_after: [...]
  steps: N
  effects: [...]
  capabilities_used: [...]
  trace_id: ...
  error: ...
  transaction: ...
}
```

## 6. Minimal syntax

The MVP syntax should remain close to small postfix Forth-like code, but with explicit metadata.

### 6.1 Push a value

```text
1
true
"hello"
```

### 6.2 Call a word

```text
1 2 +
```

### 6.3 Define a word

```text
: square  ( int -- int )
  dup *
;
```

### 6.4 Declare a capability

```text
CAPABILITY core.compute
CAPABILITY dictionary.read
```

### 6.5 Declare an effect

```text
: read-clock  ( -- int )
  EFFECT host.clock
  clock.now
;
```

### 6.6 Run a test

```text
TEST add-works
  1 2 + ASSERT 3
;
```

### 6.7 Start a transaction

```text
BEGIN
  : tmp  ( -- int ) 41 1 + ;
  TEST tmp-works
    tmp ASSERT 42
  ;
COMMIT
```

### 6.8 Roll back

```text
ROLLBACK
```

### 6.9 Inspect the stack

```text
STACK
```

### 6.10 Inspect a word

```text
SEE square
```

### 6.11 Inspect the dictionary

```text
WORDS
```

### 6.12 Metadata strategy

Use a **hybrid approach**:

- syntax for local definition metadata such as contracts and effects;
- structured API for publishing, versioning, rollback, and protocol-level operations.

That keeps source readable while avoiding an overgrown grammar.

## 7. Initial primitives

Keep the primitive set small and auditable.

### 7.1 Stack primitives

| Primitive | Signature | Behavior | Errors | Needed |
|---|---|---|---|---|
| `dup` | `( a -- a a )` | duplicate top item | `StackUnderflow` | yes |
| `drop` | `( a -- )` | remove top item | `StackUnderflow` | yes |
| `swap` | `( a b -- b a )` | exchange top two | `StackUnderflow` | yes |
| `over` | `( a b -- a b a )` | copy second item | `StackUnderflow` | yes |
| `rot` | `( a b c -- b c a )` | rotate top three | `StackUnderflow` | yes |

### 7.2 Arithmetic primitives

| Primitive | Signature | Behavior | Errors | Needed |
|---|---|---|---|---|
| `+` | `( int int -- int )` | add integers | `TypeMismatch` | yes |
| `-` | `( int int -- int )` | subtract integers | `TypeMismatch` | yes |
| `*` | `( int int -- int )` | multiply integers | `TypeMismatch` | yes |
| `/` | `( int int -- int )` | integer division or error on zero | `TypeMismatch`, division error | yes |

### 7.3 Comparison primitives

| Primitive | Signature | Behavior | Errors | Needed |
|---|---|---|---|---|
| `=` | `( a b -- bool )` | equality check | `TypeMismatch` only if unsupported compare | yes |
| `<` | `( int int -- bool )` | less-than | `TypeMismatch` | yes |
| `>` | `( int int -- bool )` | greater-than | `TypeMismatch` | yes |

### 7.4 Control primitives

Prefer to keep control words minimal and interpreter-managed.

| Primitive | Signature | Behavior | Errors | Needed |
|---|---|---|---|---|
| `if` | `( bool -- )` | branch into compiled/parsed block | `ContractViolation` | yes |
| `else` | control marker | alternate branch marker | parse error if misused | yes |
| `then` | control marker | branch join marker | parse error if misused | yes |

If direct interpreter simplicity becomes too fragile, control flow can be lowered internally to a tiny bytecode-like representation while keeping the source syntax unchanged.

### 7.5 Dictionary and introspection primitives

| Primitive | Signature | Behavior | Errors | Needed |
|---|---|---|---|---|
| `WORDS` | `( -- list )` | list visible words | none | yes |
| `SEE` | `( word -- word_info )` | inspect one word | `UnknownWord` | yes |
| `STACK` | `( -- stack )` | inspect data stack | none | yes |
| `RSTACK` | `( -- stack )` | inspect return stack | none | yes |
| `META` | `( word -- metadata )` | inspect metadata | `UnknownWord` | yes |

### 7.6 Safety and execution primitives

| Primitive | Signature | Behavior | Errors | Needed |
|---|---|---|---|---|
| `ASSERT` | `( value expected -- )` | test equality and fail on mismatch | `ContractViolation` or test failure | yes |
| `TEST` | declaration | register a test word | `InvalidDefinition` | yes |
| `BEGIN` | control | start transaction | `TransactionFailure` | yes |
| `COMMIT` | control | commit transaction | `TransactionFailure` | yes |
| `ROLLBACK` | control | revert transaction | `TransactionFailure` | yes |
| `CAPABILITY` | declaration | declare allowed capability | `InvalidDefinition` | yes |
| `EFFECT` | declaration | declare effect usage | `InvalidDefinition` | yes |

### 7.7 Trace primitives

Tracing should mostly be automatic, not user-managed.

Suggested user-visible inspection:

| Primitive | Signature | Behavior | Errors | Needed |
|---|---|---|---|---|
| `TRACE` | `( -- trace )` | inspect recent trace | none | yes |
| `LAST-ERROR` | `( -- error )` | inspect last structured error | none | yes |

## 8. Error model

Errors must be structured, explicit, and inspectable.

Required error types:

- `UnknownWord`
- `StackUnderflow`
- `StackOverflow`
- `TypeMismatch`
- `ContractViolation`
- `CapabilityDenied`
- `BudgetExceeded`
- `TransactionFailure`
- `PersistenceFailure`
- `InvalidDefinition`

### 8.1 Error policy

- errors must never fail silently;
- every error produces a trace entry;
- every error is returned in the structured result;
- transaction-scoped failures trigger rollback automatically;
- the runtime should stop on the first fatal error rather than trying to continue in a corrupted state.

### 8.2 Immediate stop vs recoverable

Immediate stop:

- `UnknownWord`
- `StackUnderflow`
- `StackOverflow`
- `TypeMismatch`
- `ContractViolation`
- `BudgetExceeded`
- `InvalidDefinition`

Recoverable in host orchestration, not inside the same failed execution:

- `CapabilityDenied`
- `TransactionFailure`
- `PersistenceFailure`

Automatic rollback:

- any failure inside `BEGIN ... COMMIT`

Transmitted to the AI:

- all of them, with stack snapshot, word name, and trace id.

## 9. Contracts

### 9.1 Chosen MVP level

The realistic MVP choice is:

1. syntax validation of signatures;
2. runtime pre-check and post-check of stack effects;
3. limited static validation for simple composed words.

That is enough for the MVP without overbuilding a type system.

### 9.2 Why not document-only

Documentation-only contracts are not sufficient because:

- they do not prevent stack corruption;
- they do not help rollback safety;
- they do not give the AI hard constraints.

### 9.3 Why not a full proof system

A proof-grade type system would be too expensive for 0.1 and would distract from the core experiment.

### 9.4 Contract usage

Contracts should be used by:

- the runtime for enforcement;
- the test runner for validation;
- the AI planner for choosing safe compositions;
- the inspector for human review.

## 10. Capabilities

### 10.1 Minimal capability set

Suggested initial capability names:

- `core.compute`
- `dictionary.read`
- `dictionary.define`
- `storage.read`
- `storage.write`
- `host.clock`
- `host.random`

Possible later capabilities:

- `network.http`
- `filesystem.read`
- `filesystem.write`
- `robot.motor`

### 10.2 Declaration by primitive or word

Each primitive or word declares the capabilities it may require.

Example:

```text
: read-clock  ( -- int )
  CAPABILITY host.clock
  clock.now
;
```

### 10.3 Authorization model

- capabilities are deny-by-default;
- a session or transaction must explicitly authorize the capability;
- authorization is checked at execution time and at definition validation time for effectful words;
- a denied capability yields a structured `CapabilityDenied` error and a trace entry.

### 10.4 Preventing hidden capability use

Composite words must not be able to smuggle in undeclared effects.

Rules:

- transitive dependencies must be resolved during definition validation;
- effective capabilities are the union of all reachable dependencies;
- a word cannot be published if its transitive effects exceed its declared capabilities;
- primitive-protected words cannot be shadowed in a way that bypasses checks.

## 11. Budgets

Budgets must be deterministic and checked continuously.

Minimum budgets:

- instruction count;
- stack depth;
- call depth;
- dictionary size;
- definition size;
- optional wall-clock duration.

### 11.1 Priority order

The **instruction counter is primary**.

That means:

- every executed instruction decrements the budget;
- budget exhaustion must stop execution even if wall-clock time is still available;
- time is only a secondary safeguard.

### 11.2 Suggested default limits for early tests

Do not treat these as final production values.

- instruction budget: low thousands for unit tests;
- stack depth: small fixed upper bound;
- call depth: small fixed upper bound;
- dictionary size: dozens at first;
- definition size: bounded in tokens or operations.

These values should be configurable in tests, but always bounded.

## 12. Transactions and rollback

### 12.1 What is restorable in MVP 0.1

Restorable:

- data stack;
- return stack;
- dictionary;
- metadata;
- persistent storage state;
- recent trace window, if treated as journaled data;
- current execution cursor and instruction counts.

Not allowed in the MVP:

- irreversible external effects;
- uncontrolled filesystem writes;
- live network calls with side effects;
- physical device actions.

### 12.2 Transaction rule

```text
BEGIN
  temporary modifications
  validations
COMMIT
```

On failure:

```text
ROLLBACK
```

### 12.3 Implementation rule

Transactions should snapshot mutable internal state or use append-only change logs that can be rewound.

For the MVP, a snapshot-based approach is the simplest and safest.

### 12.4 Rollback semantics

- if a definition fails validation, it never becomes visible;
- if test execution fails inside a transaction, the pre-transaction state is restored exactly;
- rollback must restore both content and metadata, not just the visible dictionary entries;
- rollback must itself be traceable.

## 13. Persistence

### 13.1 Comparison

#### JSON

Pros:

- human-readable;
- easy to debug;
- easy to diff.

Cons:

- weak native transaction support;
- schema drift risk;
- less convenient for selective updates.

#### SQLite

Pros:

- transactional;
- built-in versioning and querying;
- good fit for metadata and dictionary storage;
- inspectable with standard tools.

Cons:

- slightly more complexity;
- schema design matters.

#### Text format Faifth

Pros:

- readable as source;
- close to the language model;
- good for exporting and hand inspection.

Cons:

- dangerous if treated as executable on load;
- not ideal as the sole persistence format.

#### Combination of code + metadata

Pros:

- keeps executable words and inspectable metadata aligned;
- allows a canonical runtime form and a human-readable export form.

Cons:

- needs careful synchronization.

### 13.2 Initial choice

Use **SQLite as the primary store**, with a canonical export/import format in JSON-like structured records.

Why:

- transaction support matters from day one;
- the dictionary needs versioning and safe restore;
- the data must remain inspectable;
- the store should not execute blindly on load.

### 13.3 Migration future

Plan for future migration to:

- a portable on-disk record format;
- a text export format for review;
- possible WASM-hosted persistence adapters.

Do **not** implement migrations in 0.1 unless a real storage incompatibility appears.

## 14. Protocol: AI ↔ Faifth

### 14.1 Transport

Use a structured protocol that is vendor-neutral and language-neutral.

Recommended shape:

- JSON over stdin/stdout for local tests;
- the same schema behind a function-call interface later if needed.

### 14.2 Commands

Minimum command set:

- `inspect_state`
- `list_words`
- `inspect_word`
- `propose_definition`
- `validate_definition`
- `execute_test`
- `execute_transaction`
- `run_tests`
- `publish_word`
- `rollback_version`

### 14.3 Response shape

Example:

```json
{
  "status": "ok",
  "stack_before": [],
  "stack_after": [25],
  "steps": 4,
  "effects": [],
  "capabilities_used": ["core.compute"],
  "trace_id": "..."
}
```

Mandatory response fields for most commands:

- `status`
- `trace_id`
- `errors`
- `steps`
- `capabilities_used`
- `state_before`
- `state_after`

Optional fields when relevant:

- `word`
- `dictionary_diff`
- `tests`
- `transaction`
- `confidence`

### 14.4 Protocol rules

- the AI must act on structured state, not just raw text;
- responses must be machine-readable;
- invalid proposals must return structured validation errors;
- publishing a word is a separate action from proposing it;
- rollback must be a first-class protocol operation.

## 15. Phases of implementation

### Phase 0 — Foundation

Goals:

- project skeleton;
- values;
- stacks;
- structured errors;
- tests;
- minimal state object.

Files:

- `faifth/values.py`
- `faifth/stacks.py`
- `faifth/errors.py`
- `faifth/state.py`
- `tests/test_values.py`
- `tests/test_stacks.py`
- `tests/test_errors.py`

Acceptance:

- stack push/pop works;
- values serialize cleanly;
- errors are structured;
- tests run from day one.

### Phase 1 — Minimal interpreter

Goals:

- tokenizer;
- literals;
- primitive execution;
- word lookup;
- stack inspection.

Files:

- `faifth/tokenizer.py`
- `faifth/interpreter.py`
- `faifth/dictionary.py`
- `tests/test_interpreter.py`

Acceptance:

- arithmetic words execute deterministically;
- unknown words fail structurally;
- stack is inspectable after every run.

### Phase 2 — Dictionary and definitions

Goals:

- define new words;
- inspect words;
- track dependencies;
- store metadata.

Files:

- `faifth/words.py`
- `faifth/dictionary.py`
- `faifth/tracing.py`
- `tests/test_dictionary.py`

Acceptance:

- a user-defined word can be created and called;
- metadata is visible;
- dependencies are recorded.

### Phase 3 — Contracts and budgets

Goals:

- signature parsing;
- runtime validation;
- limited static checks;
- instruction budgeting;
- depth limits.

Files:

- `faifth/contracts.py`
- `faifth/budgets.py`
- `tests/test_contracts.py`
- `tests/test_budgets.py`

Acceptance:

- invalid stack effects are rejected;
- budget overflow stops execution deterministically;
- errors are structured and logged.

### Phase 4 — Capabilities and transactions

Goals:

- deny-by-default capability model;
- transaction snapshots;
- rollback of internal state;
- capability refusal logging.

Files:

- `faifth/capabilities.py`
- `faifth/transactions.py`
- `tests/test_capabilities.py`
- `tests/test_transactions.py`

Acceptance:

- unauthorized effects are refused;
- rollback restores the pre-transaction state exactly;
- transaction failures are visible in traces.

### Phase 5 — Persistence

Goals:

- store dictionary and metadata;
- reload validated state;
- versioning;
- safe restore.

Files:

- `faifth/persistence.py`
- `tests/test_persistence.py`

Acceptance:

- approved words persist and reload;
- load does not execute unchecked code;
- persistence failures are structured.

### Phase 6 — Agent protocol

Goals:

- structured requests and responses;
- state inspection;
- definition proposal;
- test execution;
- publish and rollback operations.

Files:

- `faifth/protocol.py`
- `tests/test_protocol.py`

Acceptance:

- the model can query exact state;
- responses are machine-readable;
- invalid proposals are rejected without side effects.

### Phase 7 — Comparative experiments

Goals:

- compare Faifth to direct Python execution and JSON tool calling;
- measure stack prediction accuracy;
- measure rollback behavior;
- measure error rates and correction count.

Files:

- `experiments/compare_python.py`
- `experiments/compare_tool_calling.py`
- `experiments/stack_prediction_bench.py`

Acceptance:

- experiments produce measurable outputs;
- results can justify whether the next iteration is worthwhile.

## 16. Acceptance criteria

The MVP 0.1 is successful only if all of the following are true:

1. the runtime executes simple words deterministically;
2. the stack is always inspectable;
3. errors are never silent;
4. invalid definitions are rejected;
5. unauthorized capabilities are rejected;
6. budget overflow stops execution;
7. failed transactions restore the exact internal state;
8. a word can be persisted and reloaded;
9. the AI can receive structured runtime state;
10. a new skill can be created, tested, and reused;
11. traces are available for inspection and replay;
12. the runtime remains small enough to be understandable in full.

## 17. Decisive experiments

The experiments should test whether Faifth improves safety or reliability relative to Python and JSON tool calling.

Minimum experiment set:

1. simple arithmetic;
2. multi-word composition;
3. stack error correction;
4. skill creation;
5. skill reuse;
6. denied capability;
7. rollback of a failed transaction;
8. persistence round-trip;
9. stack state prediction by the model;
10. effect of longer programs on reliability.

Measured outputs:

- success rate;
- number of corrections;
- stack prediction accuracy;
- number of silent failures, which should be zero;
- trace length;
- token cost;
- rollback correctness;
- capability refusal correctness.

## 18. Risks

### Technical risks

- stack manipulation may become confusing too fast;
- contracts may be too weak if only documented;
- persistence may become overcomplicated;
- the dictionary may bloat;
- transaction boundaries may be leaky.

### Agentic risks

- the model may hallucinate the stack state;
- the model may overtrust unproven words;
- unsafe definitions may be promoted too early.

### Security risks

- hidden capability usage;
- accidental effect escalation;
- unsafe rollback assumptions;
- external data interpreted as code.

### Mitigations

- keep the core tiny;
- make state structured and inspectable;
- require runtime checks;
- stage promotions through tests;
- preserve deny-by-default capabilities;
- make rollback explicit;
- never let load-time data execute directly.

## 19. Exact recommended order

The recommended order is:

1. create the Python project skeleton;
2. implement value and error types;
3. implement bounded stacks;
4. add tests for the foundation;
5. implement tokenizer and literal parsing;
6. implement primitive execution;
7. expose runtime state inspection;
8. add word definitions and dictionary lookup;
9. add contract parsing and runtime checks;
10. add capability enforcement;
11. add budgets;
12. add transaction snapshots and rollback;
13. add persistence;
14. add structured protocol messages;
15. run the comparative experiments;
16. decide whether Phase 1 should continue, pivot, or stop.

## 20. First phase recommendation

The very first implementation phase should be **Phase 0 only**:

- values;
- stacks;
- structured errors;
- tests;
- explicit runtime state.

This is the smallest possible piece that can still prove the kernel is clean.

Files that would be created in Phase 0:

- `faifth/values.py`
- `faifth/stacks.py`
- `faifth/errors.py`
- `faifth/state.py`
- `tests/test_values.py`
- `tests/test_stacks.py`
- `tests/test_errors.py`

No AI model integration is required for Phase 0.
No tokenizer is required for Phase 0.
No persistence is required for Phase 0.
No transaction engine is required for Phase 0.