# Faifth

Faifth is an experimental runtime for AI-oriented execution experiments.

Current status:

- Phase 0 is complete.
- Phase 1 is complete: a minimal deterministic interpreter exists.
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

## Python API

```python
from faifth import Interpreter, execute

result = execute("2 3 + dup *")
print(result.status)
print(result.stack)
print(result.trace)
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
- user-defined words;
- dictionary;
- `:` / `;` definitions;
- contracts;
- capabilities;
- budgets;
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
- contracts;
- capabilities;
- transactions;
- persistence;
- AI protocol.