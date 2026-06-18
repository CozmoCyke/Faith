# FAIFTH MVP 0.1 Specification

## 1. Purpose

Faifth 0.1 is a minimal agent runtime used to test whether an AI can reason more reliably inside a small, explicit, capability-constrained machine than in a large opaque environment.

## 2. Scope

### 2.1 Included

- integer and string literals;
- a small stack machine;
- inspectable data stack;
- inspectable return stack;
- named words;
- word metadata;
- stack contracts;
- basic capability checks;
- execution journal;
- simple tests;
- transactional updates to the dictionary;
- persistent dictionary storage;
- structured AI state exchange;
- budget enforcement;
- sandboxed host effects.

### 2.2 Excluded

- bootable OS features;
- graphics;
- unrestricted filesystem access;
- unrestricted network access;
- direct hardware control;
- concurrency primitives beyond the minimal host loop;
- unbounded self-modification;
- advanced optimization;
- full static typing.

## 3. Syntax proposal

Faifth should stay close to a small postfix language, but with explicit metadata.

Example:

```text
: distance  ( -- millimeters )
  capteur-distance
;
```

Contract notation:

```text
( input1 input2 -- output1 output2 )
```

Capability declaration:

```text
CAPABILITY filesystem.read
CAPABILITY robot.motor
```

Effect declaration:

```text
: prendre-photo  ( camera -- image )
  EFFECT camera.capture
  camera.capture
;
```

## 4. Primitive set

### 4.1 Stack

- `dup`
- `drop`
- `swap`
- `over`
- `rot`
- `nip`
- `tuck`

### 4.2 Arithmetic and comparison

- `+`
- `-`
- `*`
- `/`
- `=`
- `<`
- `>`

### 4.3 Dictionary

- `:`
- `;`
- `see`
- `words`
- `meta`
- `forget` only if explicitly allowed and not for primitives

### 4.4 Control

- `if`
- `else`
- `then`
- `begin`
- `again`
- `until`
- `for`
- `return`

### 4.5 Safety

- `CAPABILITY`
- `EFFECT`
- `TEST`
- `BEGIN-TRANSACTION`
- `COMMIT`
- `ROLLBACK`
- `ASSERT`
- `BUDGET`

## 5. Contracts

### 5.1 Contract form

Each word should carry a stack signature and optional semantic annotations.

Example:

```text
: distance  ( -- mm )
  capteur-distance
;
```

### 5.2 Enforcement

MVP rule:

- runtime checks are mandatory for effectful words;
- contract mismatches fail execution and produce a trace record;
- the AI may use contracts during planning but cannot bypass them.

## 6. Capabilities

The MVP should implement a deny-by-default model.

Example:

```text
CAPABILITY filesystem.read
CAPABILITY filesystem.write
CAPABILITY network.http
```

Rules:

- a word must declare the capabilities it may use;
- a session must hold the capability before execution;
- capability grants may be scoped to a transaction;
- primitive words that touch the host are protected.

## 7. Transactions

### 7.1 Required semantics

- dictionary update is atomic;
- test failure can trigger rollback;
- failed validation blocks commit;
- journal always keeps the attempt record.

### 7.2 Example

```text
BEGIN-TRANSACTION
  define-word
  run-tests
  validate
COMMIT
```

If any step fails:

```text
ROLLBACK
```

## 8. Testing

### 8.1 Test format

```text
TEST add-works
  1 2 + ASSERT 3
;
```

### 8.2 Required test classes

- pure arithmetic;
- stack contract validation;
- dictionary inspection;
- capability refusal;
- rollback correctness;
- persistence round-trip;
- budget overflow handling.

### 8.3 Confidence

Each word should carry:

- number of passing tests;
- number of failing tests;
- last failure;
- confidence score.

## 9. Required behaviors

Faifth 0.1 must:

- expose the current stack;
- expose dictionary metadata;
- stop on budget overflow;
- refuse undeclared capabilities;
- log each important execution;
- restore state after rollback;
- persist approved dictionary entries.

## 10. Experiments

### 10.1 Functional experiments

1. run simple arithmetic;
2. compose three or four words;
3. intentionally underflow the stack and inspect the error;
4. define a new word;
5. promote a validated procedure to a named skill;
6. reuse that skill in a second task;
7. force a rollback and verify state restoration;
8. request a denied capability;
9. compare the model's predicted stack state with the actual stack state.

### 10.2 Comparative experiments

Measure against:

- Python;
- Lua;
- JSON tool calling.

Metrics:

- task success rate;
- number of corrective steps;
- trace clarity;
- rollback correctness;
- prediction accuracy for stack state;
- execution overhead.

### 10.3 Reliability experiments

Measure how reliability changes as:

- program length increases;
- dictionary size increases;
- number of tools increases;
- number of side effects increases.

## 11. Success criteria

Faifth 0.1 is successful if:

- an AI can inspect and reason about the runtime state without ambiguity;
- stack errors are detectable and recoverable;
- capabilities are enforced;
- dictionary updates are safe and reversible;
- the runtime remains small enough to be fully representable in context.

## 12. Failure criteria

Faifth 0.1 fails if:

- state cannot be represented compactly;
- stack reasoning remains error-prone despite contracts;
- safety requires too much host complexity;
- the dictionary becomes unbounded and ungovernable;
- the AI still behaves more reliably with ordinary tool calling.

## 13. Implementation guidance

Do not implement:

- full OS services;
- unrestricted plugins;
- advanced type inference;
- hardware abstraction layers beyond the minimum needed for tests.

Start with:

- a tiny interpreter or VM;
- a simple persistent store;
- a clear JSON-compatible protocol for state and trace;
- an append-only journal;
- explicit tests and contracts.