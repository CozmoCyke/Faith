# Faifth Phase 7 Benchmark Harness

This directory contains the local deterministic benchmark used to compare:

- `python_direct`
- `json_tools`
- `faifth_protocol`

The benchmark is intentionally local and does not use an LLM.

## Layout

```text
experiments/phase7/
├── adapters/
│   ├── python_direct.py
│   ├── json_tools.py
│   └── faith_protocol.py
├── scenarios/
├── runner.py
├── metrics.py
├── results/
│   ├── runs.jsonl
│   ├── summary.csv
│   └── summary.md
└── README.md
```

## Run

From the repository root:

```powershell
python experiments\phase7\runner.py
```

To skip the Faifth ablation variants:

```powershell
python experiments\phase7\runner.py --no-ablations
```

## What it measures

- success or failure;
- expected and observed result;
- state errors;
- forbidden actions;
- rollback fidelity;
- state before and after;
- corrections needed;
- steps executed;
- created and reused skills;
- request and response sizes;
- approximate token count;
- execution time;
- audit quality.

## Notes

- `json_tools` is a generic JSON tool-calling baseline.
- `python_direct` is direct Python control of the runtime.
- `faifth_protocol` uses the structured `faifth-agent` protocol.
- Phase 7A is deterministic and local.
- Phase 7B can later add an LLM on top of this harness.

