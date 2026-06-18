# Faifth Phase 5 Implementation Report

## Summary

Phase 5 is implemented: Faifth now persists user words in SQLite with version tracking, loads an active dictionary into a fresh session, and restores an older version of a word with explicit storage permissions.

The implementation stays conservative:

- persistence is explicit and repository-based;
- the runtime remains session-oriented;
- versioned words are inspectable and hash-checked;
- storage access is refused by default;
- corruption is detected on load;
- no OS, network, or native compilation work was added.

## Documents Consulted

- `FAIFTH_MVP_0_1_IMPLEMENTATION_PLAN.md`
- `FAIFTH_PHASE_4_IMPLEMENTATION_REPORT.md`
- `src/faifth/dictionary.py`
- `src/faifth/interpreter.py`
- `src/faifth/errors.py`
- `src/faifth/results.py`
- `src/faifth/transactions.py`
- `src/faifth/capabilities.py`
- `README.md`

## Git State at Start

- Branch: `phase-5-persistence-versioning`
- HEAD before Phase 5 work: `04e1c5418ddd8581d32e44740721dd6aecb0ed5d`
- Stable tags remained unchanged during the implementation work.

## Files Added

- `src/faifth/versioning.py`
- `src/faifth/persistence.py`
- `tests/test_persistence.py`

## Files Modified

- `src/faifth/errors.py`
- `src/faifth/interpreter.py`
- `src/faifth/__init__.py`
- `README.md`

## Architecture

Phase 5 is built from three cooperating pieces:

1. `WordVersion` in `src/faifth/versioning.py`
   - stores immutable version metadata for a user word;
   - computes a canonical content hash;
   - serializes contract, dependencies, capabilities, and metadata deterministically.

2. `DictionaryRepository` in `src/faifth/persistence.py`
   - owns the SQLite file;
   - saves dictionaries and individual words;
   - lists stored versions;
   - loads the active dictionary into an `InterpreterSession`;
   - restores a selected version into the active dictionary.

3. `InterpreterSession.activate_dictionary(...)` in `src/faifth/interpreter.py`
   - replaces the current dictionary only when no transaction is active;
   - keeps restoration explicit instead of hidden behind global state.

## Persistence Model

SQLite schema:

- `metadata`
- `word_versions`
- `active_words`

Each stored word version includes:

- name;
- version number;
- body tokens;
- dependency names;
- dependency versions;
- primitive dependencies;
- required capabilities;
- optional contract;
- metadata;
- content hash.

The content hash excludes the version number, so resaving identical content reuses the existing stored version instead of creating a duplicate.

## Validation Strategy

Validation is done in layers:

- permission check first;
- storage schema and `PRAGMA quick_check`;
- content hash verification for each loaded word version;
- dependency ordering before reconstruction;
- session activation only after the dictionary is rebuilt successfully;
- explicit error objects for refusal and corruption.

## Behavior Confirmed

- save a first version of `square`;
- load it into a new session and execute `5 square`;
- save a second version of `square`;
- confirm the active version advances to `2`;
- restore version `1`;
- confirm the active version returns to `1`;
- confirm the restored session executes the older behavior.

Observed demo output:

```text
save1 ok (('square', 1),)
load ok [25]
save2 ok (('square', 2),) ()
active_before_restore 2
restore ok [4] 1
```

## Tests

Full validation run:

- `pytest`: 93 passed
- `ruff`: passed
- `mypy`: passed
- `compileall`: passed

Targeted persistence coverage includes:

- round-trip dictionary save/load;
- identical-content version reuse;
- restore to an older version;
- permission refusal;
- corruption detection.

## Limits and Deferred Work

Still out of scope for Phase 5:

- free-form filesystem access;
- network access;
- concurrency;
- native compilation;
- OS boot or hardware drivers;
- graphical UI;
- automatic migration tooling;
- distributed synchronization.

The persistence layer is intentionally narrow: it gives Faifth durable procedural memory without turning the runtime into a general-purpose storage subsystem.

## Final Notes

- No other project was modified.
- `phase-4-stable` was left unchanged.
- Phase 6 has not started.
- The Phase 5 worktree remains focused on persistence, versioning, and restoration only.
