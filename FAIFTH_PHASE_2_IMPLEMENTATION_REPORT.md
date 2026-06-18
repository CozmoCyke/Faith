# Faifth Phase 2 Implementation Report

## 1. Status

Phase 2 has been implemented successfully.

Faifth now supports:

- an inspectable dictionary;
- user-defined words;
- `:` / `;` definitions;
- sequential publication of definitions in one source;
- session-scoped procedural memory;
- nested calls to user words;
- atomic rollback when a user word fails;
- structured traces that expose definitions, calls, returns, primitives, and errors.

No Phase 3 feature was started.

## 2. Documents consulted

Primary references:

- `C:\dev\Faifth\FAIFTH_MVP_0_1_IMPLEMENTATION_PLAN.md`
- `C:\dev\Faifth\FAIFTH_PHASE_1_IMPLEMENTATION_REPORT.md`
- `C:\dev\Faifth\FAIFTH_PHASES_0_1_GIT_CHECKPOINT_REPORT.md`
- `C:\dev\Faifth\README.md`

Runtime files read during implementation:

- `C:\dev\Faifth\src\faifth\tokenizer.py`
- `C:\dev\Faifth\src\faifth\primitives.py`
- `C:\dev\Faifth\src\faifth\tracing.py`
- `C:\dev\Faifth\src\faifth\interpreter.py`
- `C:\dev\Faifth\src\faifth\errors.py`
- `C:\dev\Faifth\src\faifth\results.py`
- `C:\dev\Faifth\src\faifth\values.py`
- `C:\dev\Faifth\src\faifth\stack.py`

## 3. Git state at start

- Local branch before work: `main`
- Commit at start: `f346fc3a4f185c068f8bc739a73d697df4df297b`
- Remote: `origin`
- Remote URL: `https://github.com/CozmoCyke/Faith.git`
- Stable tag present and unchanged: `phase-1-stable`

The branch `phase-2-user-words` was created for this work.

## 4. Files added

- `src/faifth/definitions.py`
- `src/faifth/dictionary.py`
- `tests/test_definitions.py`
- `tests/test_dictionary.py`
- `tests/test_user_words.py`

## 5. Files modified

- `README.md`
- `src/faifth/__init__.py`
- `src/faifth/errors.py`
- `src/faifth/interpreter.py`
- `src/faifth/tracing.py`

## 6. Architecture

The Phase 2 architecture stays small and explicit:

- `definitions.py` parses `:` / `;` blocks into a minimal `ParsedDefinition`.
- `dictionary.py` stores primitives and user words in a deterministic registry.
- `UserWord` is an immutable dataclass with the validated body and dependencies.
- `InterpreterSession` keeps a session-local dictionary and executes sources against it.
- `execute(source)` remains a convenience entry point that creates a fresh session, preserving Phase 1 isolation semantics.

No AST, bytecode, persistence, contracts, capacities, or transaction system was added.

## 7. Syntax

Supported Phase 2 syntax:

```text
: square dup * ;
5 square
```

Multiple definitions can appear in one source:

```text
: square dup * ;
: fourth-power square square ;
2 fourth-power
```

Rules enforced:

- `:` starts a definition;
- the next token is the name;
- `;` ends the definition;
- empty bodies are rejected;
- stray `;` is rejected;
- recursion is rejected;
- redefining a primitive is rejected;
- redefining an existing user word is rejected.

## 8. Dictionary model

The dictionary is session-local and deterministic.

Public behavior:

- `has(name)`
- `resolve(name)`
- `define(word)`
- `inspect(name)`
- `list_words()`
- `list_user_words()`
- `validate_user_word(name, body, ...)`

User words store:

- `name`
- `body`
- `dependencies`
- `primitive_dependencies`
- optional `source`
- optional `definition_index`
- optional `metadata`

Inspection is structured and returns a machine-readable dictionary.

## 9. User-word model

`UserWord` is immutable and validated on creation.

For:

```text
: square dup * ;
```

the inspected word is conceptually:

```json
{
  "kind": "user",
  "name": "square",
  "body": ["dup", "*"],
  "dependencies": [],
  "primitive_dependencies": ["dup", "*"]
}
```

For:

```text
: fourth-power square square ;
```

the direct dependency list is:

```text
["square"]
```

## 10. Validation strategy

Validation happens before publication.

Sequence:

1. tokenize source;
2. parse a definition block if `:` is encountered;
3. validate the name;
4. validate the body token-by-token;
5. resolve dependencies against the live dictionary;
6. reject recursion and duplicates;
7. publish only if the word is fully valid.

Definitions are atomic: a failed definition does not partially mutate the dictionary.

## 11. Anti-recursion strategy

Phase 2 forbids recursion entirely.

The implementation rejects:

- direct self-reference;
- indirect recursion through already defined words;
- forward references;
- redefinition-based cycles.

This keeps the dependency graph acyclic without adding a general graph solver.

## 12. Atomicity strategy

Atomicity is implemented at the user-word call level.

Behavior:

- snapshot the stack before entering a user word;
- execute the body token by token;
- if any token fails, restore the snapshot taken before the call;
- preserve the detailed error trace;
- stop execution immediately.

This is stronger than token-local rollback and matches the Phase 2 goal of safe, observable skill reuse.

## 13. Session API

Phase 2 adds explicit sessions:

```python
from faifth import InterpreterSession

session = InterpreterSession()
session.execute(": square dup * ;")
result = session.execute("5 square")
```

The session keeps the dictionary in memory.

Separate sessions do not share words.

## 14. Inspection

The dictionary is inspectable from Python, without adding a new language keyword.

Examples:

```python
session.dictionary.list_user_words()
session.dictionary.inspect("square")
```

This keeps introspection simple and avoids widening the language surface too early.

## 15. Errors added

Added in Phase 2:

- `InvalidDefinition`
- `DuplicateWord`
- `ProtectedWord`
- `UnterminatedDefinition`
- `UnexpectedTerminator`
- `RecursiveDefinition`
- `CallDepthExceeded`

Existing errors remain active:

- `UnknownWord`
- `StackUnderflow`
- `StackOverflow`
- `TypeMismatch`

## 16. Trace

Trace entries were extended to include:

- `definition`
- `call`
- `return`
- `literal`
- `primitive`
- `error`

User-word calls now appear explicitly in the trace, and the internal primitives remain visible.

## 17. Validation strategy

New tests added in Phase 2: **14**

- `tests/test_dictionary.py`: 3 tests
- `tests/test_definitions.py`: 3 tests
- `tests/test_user_words.py`: 8 tests

Total tests now passing: **62**

## 18. Validation results

### `pytest`

Result:

- 62 passed

### `ruff check .`

Result:

- All checks passed

### `mypy src`

Result:

- Success: no issues found in 11 source files

### `compileall`

Result:

- all source files under `src/faifth` compiled successfully

## 19. Demonstrations executed

### `square`

Session:

```text
: square dup * ;
5 square
```

Observed result:

- status: `ok`
- stack: `[25]`

### `fourth-power`

Session:

```text
: fourth-power square square ;
2 fourth-power
```

Observed result:

- status: `ok`
- stack: `[16]`

## 20. Limits

Still out of scope:

- contracts;
- capacities;
- budgets;
- transactions;
- persistence;
- AI protocol;
- branching;
- looping;
- recursion;
- anonymous definitions;
- native compilation;
- modules;
- namespaces;
- concurrency;
- I/O.

## 21. Content deferred to Phase 3

Phase 3 should focus on:

- contracts of stack usage;
- capability control;
- execution budgets;
- transaction and rollback semantics beyond local stack restore;
- optional persistence;
- richer trace metadata;
- structured AI protocol integration.

## 22. Git state

- Branch created for this work: `phase-2-user-words`
- Implementation commit hash: `00473dc97a000635b10ab811eea1f6d4eeecf996`
- Commit message: `Implement Faifth phase 2 user-defined words`
- `git status --short` after the implementation commit was clean

## 23. No external project modified

Only `C:\dev\Faifth` was modified.
