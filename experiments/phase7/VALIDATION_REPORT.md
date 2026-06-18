# Phase 7 Validation Report

Validated on `phase-7-benchmark-harness`.

## Checks Run

- `python -m pytest`
- `python -m ruff check .`
- `python -m mypy src`
- `python -m compileall src`
- `python experiments\phase7\runner.py`

## Results

- Total benchmark records: `120`
- `python_direct`: `15/15`
- `json_tools`: `13/15`
- `faifth_protocol`: `15/15`

## Regression Coverage

- `bad_type`: passes
- `budget_exceeded`: passes
- `mid_modification_error`: passes
- `rollback_exact`: passes

## Notes

- The dedicated validation venv was created and removed locally.
- The benchmark outputs were regenerated without changing scenarios or scoring.
- The protocol keeps functional state restoration separate from error evidence.
