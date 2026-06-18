# Faifth

Faifth is an experimental runtime for AI-oriented execution experiments.

Current status:

- Phase 0 is complete.
- Phase 1 is complete: a minimal deterministic interpreter exists.
- Phase 2 is complete: user-defined words and an inspectable dictionary exist.
- Phase 3 is complete: stack contracts and deterministic execution budgets exist.
- Phase 4 is in progress: capabilities, permissions, and transactions are being added.
- Faifth is not an OS.
- Faifth is not a full agent framework.

## What is implemented

### Phase 0

- immutable value types;
- a bounded, testable stack;
- structured errors;
- structured execution results.

### Phase 1

- flat tokenization;
- literal recognition for integers and booleans;
- a fixed primitive registry;
- interpreter execution on top of the Phase 0 stack;
- structured run results;
- structured trace entries.

### Phase 2

- inspectable dictionary;
- user-defined words;
- `:` / `;` definitions;
- explicit sessions with local procedural memory;
- call traces for user words;
- atomic rollback on failed word execution.

### Phase 3

- stack contracts for primitives and user words;
- optional contract annotations after the word name;
- dynamic input and output verification;
- deterministic execution budgets;

### Phase 4

- immutable capability identifiers and sets;
- capability-gated primitives and user words;
- session permissions with execution-time restriction;
- explicit transactions on internal state;
- automatic rollback on failure;
- transaction audit records.

## Capability profiles

Faifth keeps a compatibility profile for the current prototype so the historical examples continue to run:

- `CapabilitySet.development_defaults()` for the current prototype profile;
- `CapabilitySet.strict_defaults()` for an empty capability set.

The default `InterpreterSession()` uses the compatibility profile so the existing phases remain runnable without boilerplate. For strict experiments, pass an explicit `CapabilitySet`.

## Example usage

```python
from faifth import CapabilitySet, InterpreterSession

session = InterpreterSession(
    capabilities=CapabilitySet.of("core.compute", "core.stack")
)

result = session.execute("2 3 +")
```

To allow definitions and transactions:

```python
session = InterpreterSession(
    capabilities=CapabilitySet.of(
        "core.compute",
        "core.stack",
        "dictionary.define",
        "transaction.manage",
    )
)

session.begin_transaction()
session.execute(": square ( int -- int ) dup * ;")
session.commit_transaction()
```
- observable step, stack, and call-depth usage.

## Syntax currently supported

Tokens are separated by whitespace.

Literals:

```text
0
42
-7
true
false
```

Primitives:

```text
+  -  *  dup  drop  swap  over  =  depth
```

Example:

```text
2 3 + dup *
```

Phase 2 definitions:

```text
: square dup * ;
5 square
```

Phase 3 contracts:

```text
: square ( int -- int ) dup * ;
: is-zero ( int -- bool ) 0 = ;
: constant-five ( -- int ) 5 ;
```

## Python API

```python
from faifth import Interpreter, execute

result = execute("2 3 + dup *")
print(result.status)
print(result.stack)
print(result.trace)
```

For Phase 2, use an explicit session when you want words to persist:

```python
from faifth import InterpreterSession

session = InterpreterSession()
session.execute(": square dup * ;")
result = session.execute("5 square")
print(result.stack)
print(session.dictionary.inspect("square"))
```

Phase 3 budgets are explicit:

```python
from faifth import ExecutionBudget, InterpreterSession

session = InterpreterSession()
result = session.execute(
    "2 3 + dup *",
    budget=ExecutionBudget(max_steps=5, max_stack_depth=32, max_call_depth=16),
)
print(result.usage.to_dict())
```

The returned object contains:

- `status`
- `value`
- `error`
- `stack`
- `trace`
- `steps`
- `metadata`

## Example trace

For `2 3 + dup *`, the stack trace is:

```text
[] -> [2] -> [2, 3] -> [5] -> [5, 5] -> [25]
```

## Development setup

Install the package in editable mode with local dev tools if they are available:

```text
python -m pip install -e .[dev]
```

## Validation commands

```text
python -m pytest
python -m ruff check .
python -m mypy src
python -m compileall src
```

## Limitations

Not yet implemented:

- tokenizer comments or strings;
- capabilities;
- transactions;
- persistence;
- AI protocol;
- CLI;
- host filesystem or network access;
- concurrency;
- branching and looping.

## Deferred to Phase 2

- dictionary and named words;
- user definitions;
- capabilities;
- transactions;
- persistence;
- AI protocol.

## Deferred to Phase 3 or later

- advanced contract inference;
- generic type variables;
- capability enforcement;
- transactions;
- persistence;
- AI protocol;
- concurrency;
- branching and looping.

## Phase 2 limitations

- recursion is still forbidden;
- redefining primitives is forbidden;
- redefining existing user words is forbidden;
- persistence is still in memory only;
- the procedural memory is minimal and experimental.

## Phase 3 limitations

- contracts are intentionally minimal (`int`, `bool`, `any`);
- budgets are deterministic counters, not wall-clock timers;
- contractless words remain usable but are not contract-verified;
- persistence is still in memory only;
- no branching, looping, or recursion has been added.
