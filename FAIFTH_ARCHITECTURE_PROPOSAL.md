# FAIFTH Architecture Proposal

## 1. Design goals

Faifth should optimize for:

- small core size;
- complete observability;
- capability-limited execution;
- transaction safety;
- persistent procedural memory;
- machine-readable contracts;
- replay and rollback.

It should not optimize first for:

- human convenience alone;
- maximal language expressiveness;
- unrestricted self-modification;
- being a full OS on day one.

## 2. Architectural layers

### 2.1 Core runtime

Responsibilities:

- execute words;
- manage data stack and return stack;
- resolve dictionary entries;
- enforce stack contracts;
- stop on budget overflow;
- emit execution traces.

Must exist in MVP: yes.

Complexity: low to medium.

Risks:

- stack corruption;
- ambiguous semantics;
- hidden side effects.

Can fit in AI context: yes, if kept small.

### 2.2 Dictionary manager

Responsibilities:

- store word definitions;
- store metadata;
- version words;
- mark status;
- resolve namespaces;
- support promotion and rollback.

Must exist in MVP: yes.

Complexity: medium.

Risks:

- bloat;
- duplicate skills;
- unsafe updates.

Can fit in AI context: partially, for a reduced dictionary view.

### 2.3 Contract verifier

Responsibilities:

- validate stack effects;
- validate declared types;
- validate capabilities;
- validate selected preconditions.

Must exist in MVP: yes.

Complexity: medium.

Risks:

- false confidence if treated as proof;
- mismatch between declared and actual behavior.

Can fit in AI context: yes, if represented as compact metadata.

### 2.4 Capability manager

Responsibilities:

- grant, revoke, and inspect capabilities;
- enforce effect boundaries;
- bind permissions to transactions or sessions.

Must exist in MVP: yes.

Complexity: medium.

Risks:

- privilege escalation;
- capability leakage;
- confused-deputy behavior.

Can fit in AI context: yes, as a structured list.

### 2.5 Transaction engine

Responsibilities:

- begin / commit / rollback;
- isolate dictionary and storage changes;
- attach validation hooks;
- retain audit data.

Must exist in MVP: yes, at least for dictionary and storage mutations.

Complexity: medium to high.

Risks:

- partial commit;
- rollback gaps;
- side effects outside transaction scope.

Can fit in AI context: yes conceptually, but state should be summarized.

### 2.6 Execution journal

Responsibilities:

- append trace records;
- keep before/after snapshots;
- record effects, errors, and timings;
- support replay.

Must exist in MVP: yes.

Complexity: low to medium.

Risks:

- log growth;
- sensitive data leakage;
- incompleteness.

Can fit in AI context: partially, via recent window and summary.

### 2.7 Test manager

Responsibilities:

- run word-specific tests;
- run contract checks;
- store pass/fail history;
- compute confidence scores.

Must exist in MVP: yes.

Complexity: medium.

Risks:

- weak tests creating false trust;
- context-specific validity.

Can fit in AI context: yes.

### 2.8 Storage layer

Responsibilities:

- persist dictionary;
- persist traces or trace indexes;
- persist test history;
- support versioned restore.

Must exist in MVP: yes.

Complexity: medium.

Risks:

- corruption;
- schema drift;
- unbounded growth.

Can fit in AI context: only summarized metadata.

### 2.9 AI exchange protocol

Responsibilities:

- expose structured runtime state;
- accept candidate plans or code;
- return validation feedback;
- request clarification when needed.

Must exist in MVP: yes.

Complexity: medium.

Risks:

- prompt injection;
- state loss;
- unstructured tool abuse.

Can fit in AI context: yes, but state should be compact and canonical.

### 2.10 Host adapters

Responsibilities:

- filesystem;
- network;
- subprocesses;
- sensors;
- actuators;
- browser or GUI if needed.

Must exist in MVP: minimal file adapter only, maybe network later.

Complexity: high.

Risks:

- platform-specific bugs;
- unsafe effects;
- nondeterminism.

Can fit in AI context: no, only summaries and contracts.

### 2.11 Sandbox

Responsibilities:

- isolate runtime from host;
- restrict effects;
- enforce budgets;
- limit imported adapters.

Must exist in MVP: yes.

Complexity: medium to high.

Risks:

- incomplete isolation;
- bypass via host integration.

Can fit in AI context: only as a policy model.

## 3. Proposed flow

1. AI receives structured state.
2. AI selects relevant words and capabilities.
3. AI proposes a plan or a short program.
4. Runtime checks contracts and budgets.
5. Runtime executes inside a transaction if state can change.
6. Journal records before/after and effects.
7. Tests run automatically if available.
8. If success confidence rises, the procedure can be promoted to a named word.
9. If failure occurs, rollback or quarantine applies.

## 4. State model

Recommended runtime state object:

```text
State {
  data_stack: [...]
  return_stack: [...]
  dictionary_view: [...]
  capabilities: [...]
  contracts: [...]
  budgets: {...}
  recent_trace: [...]
  errors: [...]
  objectives: [...]
  tests: [...]
  confidence: {...}
}
```

The AI should not receive raw internal memory dumps unless explicitly requested. It should receive a stable, structured projection.

## 5. Dictionary model

Each word entry should contain:

- name;
- body;
- stack signature;
- effects;
- capabilities;
- version;
- status;
- provenance;
- tests;
- confidence;
- dependencies;
- notes.

Suggested statuses:

- experimental;
- tested;
- approved;
- critical;
- primitive-protected;
- disabled;
- retired.

Rules:

- primitives are immutable by default;
- experimental words may mutate only inside transaction scope;
- approved words require passing tests and contract checks;
- critical words require explicit review;
- retired words remain in history but cannot execute.

## 6. Transactions

### 6.1 Scope

Transactions should cover:

- dictionary writes;
- persistent storage writes;
- effectful host calls that can be staged or compensated.

### 6.2 Semantics

- begin creates a snapshot or log boundary;
- commit publishes changes atomically;
- rollback restores prior state;
- failed validation blocks commit.

### 6.3 Limitations

Not all effects are rollbackable.

For irreversibly effectful actions:

- require explicit capability;
- use dry-run or preflight validation when possible;
- record compensation strategy if one exists;
- classify the action as non-transactional if rollback cannot be guaranteed.

## 7. Contract and type strategy

Recommended progression:

1. document-only contracts for visibility;
2. runtime-checked stack effects;
3. capability declarations;
4. optional type annotations;
5. selected static checks for common words;
6. richer unit and resource types if the prototype proves valuable.

Do not start with a full static type system. That would likely exceed the value of the first prototype.

## 8. Proposed module boundaries

### 8.1 Core

- parser;
- evaluator;
- stack operations;
- dictionary lookup;
- error handling.

### 8.2 Safety

- capabilities;
- contracts;
- budgets;
- transactions;
- sandbox.

### 8.3 Memory

- dictionary persistence;
- trace index;
- test history;
- version history.

### 8.4 AI interface

- state projection;
- plan ingestion;
- execution result output;
- confidence feedback.

### 8.5 Host integration

- files;
- network;
- devices;
- scheduler hooks.

## 9. MVP architecture choice

Recommended choice for 0.1:

- direct interpreter or very small bytecode VM;
- persistent dictionary in a simple local store;
- append-only journal;
- capability checks on every effectful word;
- transaction wrapper around mutating operations;
- structured JSON-like exchange with the model.

Rejected for MVP:

- native compilation;
- full OS boot chain;
- unrestricted plugin loading;
- general concurrency;
- kernel-level drivers.

## 10. Why this architecture fits the hypothesis

It lets Faifth test the central claim:

- can an AI be more reliable when the entire runtime is small enough to model explicitly?

The architecture answers that claim by making the runtime:

- tiny enough to inspect;
- rich enough to be useful;
- safe enough to measure;
- extensible enough to learn from success.