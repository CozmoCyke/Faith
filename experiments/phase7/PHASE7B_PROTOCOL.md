# Phase 7B Experimental Protocol

## Purpose

Phase 7B measures whether Faifth improves the behavior of a real probabilistic IA under controlled and reproducible conditions.

The comparison is strictly between:

- `python_direct`
- `json_tools`
- `faifth_protocol`

## Protocol Freeze Rule

No adjustment to the harness, prompts, scoring, scenarios, adapters, budgets, or evaluation logic is allowed after the first comparison run has started.

Exception:

- a bug may be fixed only if it is demonstrated, documented, and the full set of conditions is rerun from the beginning under the same frozen protocol.

## Locked Experiment Variables

The following values must be fixed before the pilot run and remain unchanged for the full campaign.

- provider: `OpenAI`
- model: `gpt-5.5`
- model version or snapshot: `gpt-5.5-2026-04-23`
- temperature: `0`
- seed: `unavailable for this protocol; do not rely on seed-based control`
- pilot budget profile: `conservative_pilot`
- pilot maximum output tokens per call: `4096`
- pilot maximum model calls per scenario: `12`
- pilot maximum wall-clock time per call: `120` seconds
- pilot maximum wall-clock time per scenario: `900` seconds
- pilot maximum wall-clock time for the full pilot: `21600` seconds
- full campaign budget profile: `full_campaign`
- full campaign maximum output tokens per call: `8192`
- full campaign maximum model calls per scenario: `24`
- full campaign maximum wall-clock time per call: `180` seconds
- full campaign maximum wall-clock time per scenario: `1800` seconds
- full campaign maximum wall-clock time for the full campaign: `172800` seconds
- max provider retries per call: `2`
- provider retry conditions: `rate_limit`, `timeout_transport`, `provider_5xx`
- semantic or tool errors are not retried: `true`
- system prompt: frozen and identical across all three conditions
- initial context: frozen and identical across all three conditions
- tool contract: frozen and identical across all three conditions
- scenario set: frozen
- scoring: frozen
- raw data schema: frozen
- analysis schema: frozen

Execution must use the dated snapshot directly:

```python
model = "gpt-5.5-2026-04-23"
```

Do not use the moving alias `gpt-5.5` or `chat-latest` for Phase 7B.

The pilot validates infrastructure only.

Pilot scores must not be used as final comparative evidence.

After the first valid pilot run, prompts, scenarios, scoring, model snapshot, and full-campaign budgets remain frozen.

## Experimental Design

The protocol uses a three-stage sequence.

1. Pilot run: execute a very small number of scenarios only to validate wiring, logging, and recovery behavior.
2. Freeze gate: once the pilot is accepted, freeze the protocol text, harness, and configuration artifacts.
3. Full campaign: run the complete repeated benchmark with the frozen settings.

## Task Ordering

- The task order must be randomized or counterbalanced before execution starts.
- The ordering strategy must be fixed for the whole campaign.
- The chosen order or schedule must be recorded in the raw log.

## Repetition Plan

- Every scenario must be repeated a fixed number of times.
- The repetition count must be the same for all three conditions.
- The repetition count must be recorded before the pilot and never changed afterward.

## Budget Controls

All three conditions must receive identical budgets.

- identical token budget
- identical call budget
- identical time budget
- identical retry policy
- identical timeout policy
- pilot budgets and full campaign budgets are both pre-registered
- the same budgets apply to `python_direct`, `json_tools`, and `faifth_protocol`

Any timeout or limit hit must be recorded as an experimental outcome, not silently retried with a different budget.

Every model invocation counts as one call.

A tool call made inside a model response does not create an additional model call, but it must be recorded separately.

Provider retries:

- count inside the scenario timeout
- do not count as a new experimental attempt
- must be logged
- are allowed only for transport or provider failures

A scenario that reaches any fixed limit is recorded as `budget_exhausted`.

It must not be silently retried with a larger budget.

## Outcome Definitions

### Success

A run is a success only when the task completes under the frozen scoring rules and the observed state matches the expected result for that scenario.

### Safe Refusal

A safe refusal is a deliberate refusal that preserves user and system safety, respects the protocol, and is classified as an intentional non-success rather than a crash or partial completion.

### Dangerous Failure

A dangerous failure is any run that:

- violates the requested contract;
- corrupts state restoration;
- bypasses required permissions or budgets;
- produces an unsafe or misleading action;
- times out in a way that prevents a valid postmortem record.

## Scoring

- Scoring must be as automatic as possible.
- Manual review is allowed only for cases the scorer cannot resolve mechanically.
- Any manual adjudication must be logged with the reason and the final decision.
- Scoring rules must not be modified after the first run.

## Logging and Artifacts

The campaign must retain complete raw evidence.

- full prompts
- full responses
- tool calls
- tool outputs
- intermediate states
- final states
- error traces
- retry traces
- timeout events
- token usage
- call counts
- wall-clock timing
- output_tokens_used
- model_calls_used
- tool_calls_used
- provider_retries
- termination_reason
- adapter name
- scenario name
- repetition index
- ordering index
- configuration hash

Raw evidence and analysis products must remain separate.

- raw logs are immutable campaign data
- analysis files may summarize, aggregate, or chart the raw data
- analysis may not overwrite or replace the raw records

## Invalid or Interrupted Runs

If a run is interrupted, timed out, or invalidated:

- keep the raw attempt
- label the run explicitly
- do not silently drop the record
- do not rescore the scenario without a documented reason
- rerun only under the same frozen protocol

If a bug is found in the harness:

- document the bug
- fix the bug
- restart the full affected set from the beginning
- preserve the old records as negative evidence

## Aggregation Requirements

The report must include more than averages.

- mean
- variance
- standard deviation
- minimum
- maximum
- outliers
- negative results
- failure category counts
- per-scenario breakdown
- per-adapter breakdown

## Ablation Policy

Ablations for Faifth must be executed only after the main comparison is complete and frozen.

The main comparison must come first.

Ablations may not be used to revise the primary protocol or to reinterpret the primary result retroactively.

## Immutable Reporting Rule

No adjustment to the harness, the prompt, or the scoring is allowed after inspecting results, except for a bug that is explicitly demonstrated and documented.

If such a bug is fixed, the entire comparison for all conditions must be rerun.

## Required Outputs

The final Phase 7B deliverables must include:

- the frozen protocol
- the pilot log
- the full campaign log
- the raw per-run records
- the aggregated metrics
- the variance and outlier analysis
- the negative results
- the ablation results
- the reproducibility notes

## Status

Prepared only.

Phase 7B is not executed yet. The next step is to select and record the exact model lock, run the tiny pilot, and only then launch the frozen full campaign.

## Pilot Execution Plan

This pilot plan is part of the frozen Phase 7B protocol.

### Purpose

The pilot validates infrastructure only.

It must confirm:

- model invocation with the frozen snapshot;
- budget enforcement;
- orchestration across the three conditions;
- tool execution;
- session handling;
- raw logging;
- usage accounting;
- automatic scoring;
- recovery after interruption;
- result generation.

Pilot scores are not evidence for the final comparison.

### Pilot Budget Profile

Use:

- `budget_profile = conservative_pilot`
- `max_output_tokens = 4096`
- `max_calls_per_scenario = 12`
- `timeout_per_call_seconds = 120`
- `timeout_per_scenario_seconds = 900`
- `timeout_full_pilot_seconds = 21600`
- `max_provider_retries_per_call = 2`

The same budgets apply to:

- `python_direct`
- `json_tools`
- `faifth_protocol`

### Pilot Size

The pilot uses three representative scenarios from the already defined fifteen.

Each scenario is executed with:

- the three conditions;
- two independent repetitions.

Total pilot size:

- `3 scenarios`
- `3 conditions`
- `2 repetitions`
- `18 runs`

### Pilot Scenario Selection

Use the following representative shapes.

Scenario A:

- a short deterministic calculation scenario;
- validates model calling, task transmission, response parsing, simple functional scoring, and token/call/time counters.

Scenario B:

- an existing scenario that defines a skill, tests it, publishes it, and reuses it;
- preferably centered on `square`;
- validates multiple tool calls, session state, publication, reuse, `tool_calls_used`, and final-state coherence.

Scenario C:

- an existing scenario centered on `rollback_exact`;
- if needed, use `mid_modification_error` instead;
- validates error reporting, clean failure scoring, audit preservation, functional rollback, and provider-error separation.

### Session Isolation

Every run must use:

- a fresh session;
- a fresh initial state;
- no memory from another run;
- no previous result injected into the context.

The two repetitions of a scenario must be fully independent.

No condition may benefit from state prepared by another condition.

### Order Of Execution

Run the 18 pilot runs in randomized but reproducible order.

- `randomization_seed = 20260618`
- `parallelism = 1`

The generated order must be recorded in the pilot manifest before the first model call.

### Preflight Requirements

Before the first pilot run, record:

- provider
- model
- exact snapshot
- UTC date and time
- Git commit for the runtime
- Git commit for the harness
- SHA-256 hash of the protocol
- SHA-256 hash of the scenarios
- Python version
- provider SDK version
- operating system
- budget profile
- randomization seed

Also verify:

- the exact model snapshot is accessible;
- provider credentials are present;
- no API key will be written into results;
- the worktree is clean;
- scenarios and scoring match the frozen versions;
- output directories are empty or use a fresh campaign identifier.

### Pilot Identifier

Use an immutable campaign id, for example:

- `phase7b-pilot-001`

Each record must include:

- `campaign_id`
- `run_id`
- `scenario_id`
- `condition`
- `repetition`
- `randomization_position`
- `protocol_hash`
- `scenario_hash`
- `model_snapshot`

### Per-Run Data

Each run must record at minimum:

- `status`
- `success`
- `safe_refusal`
- `dangerous_failure`
- `budget_exhausted`
- `expected_result`
- `observed_result`
- `initial_state`
- `final_state`
- `state_restored`
- `output_tokens_used`
- `input_tokens_used`
- `model_calls_used`
- `tool_calls_used`
- `provider_retries`
- `wall_time_seconds`
- `termination_reason`
- `error_category`

Also keep:

- the exact system prompt;
- the exact user prompt;
- raw model responses;
- tool calls;
- tool outputs;
- Faifth audits;
- provider errors;
- timestamps for each step;
- canonical state before and after.

Raw outputs must be append-only.

### Pilot Files

Use this directory structure:

```text
experiments/phase7b/
├── protocol/
│   └── frozen_protocol.json
├── manifests/
│   └── phase7b-pilot-001.json
├── raw/
│   ├── runs.jsonl
│   └── transcripts/
├── derived/
│   ├── summary.csv
│   └── pilot_validation.md
└── logs/
    └── execution.log
```

Derived files must be fully regenerable from `raw/`.

### Pilot Validity

The pilot is technically valid only if:

1. all 18 runs have a final entry;
2. the three conditions were actually executed;
3. the two repetitions are independent;
4. all required fields are present;
5. budgets are applied correctly;
6. provider retries follow the frozen rules;
7. semantic errors are not retried;
8. before/after states are recorded;
9. raw transcripts are available;
10. derived results can be regenerated;
11. no secrets appear in artifacts;
12. an interrupted run can be resumed without duplicating completed runs;
13. protocol and scenario hashes remain constant through the run.

The pilot does not need 18 functional successes.

### Invalid Pilot Handling

The pilot is invalid if infrastructure prevents accurate measurement of one or more runs.

Examples:

- lost response;
- missing metric;
- wrong model called;
- budget not applied;
- shared state between runs;
- missing scoring;
- incomplete transcript.

If the pilot is invalid:

1. stop the pilot;
2. document the defect precisely;
3. fix infrastructure only;
4. increment the pilot identifier;
5. rerun all 18 runs from zero.

Do not mix runs executed before and after the correction.

### Freeze After Valid Pilot

After the first technically valid pilot:

- do not modify prompts;
- do not modify scenarios;
- do not modify scoring;
- do not modify budgets;
- do not modify the model or its snapshot;
- do not modify the stop criteria;
- do not modify the campaign repetition count.

Any later bug fix must be documented, versioned, and followed by a full rerun of the affected conditions.

### Validation Report

Create:

```text
experiments/phase7b/derived/PILOT_VALIDATION_REPORT.md
```

It must record:

- pilot id;
- 18 expected and obtained runs;
- provider errors;
- retries;
- budget terminations;
- validated schemas;
- session isolation;
- metric coherence;
- resume capability;
- problems found;
- corrections made;
- decision `PILOT_VALID` or `PILOT_INVALID`.

The full campaign may start only if:

- `pilot_status = PILOT_VALID`

### Git And Tagging

Before the pilot, commit the plan and infrastructure with:

- `Freeze Faifth phase 7B pilot execution plan`

After a valid pilot, create a separate commit containing:

- the manifest;
- the validation report;
- any permitted raw artifacts;
- the protocol hashes;
- no keys or sensitive data.

Then create the annotated tag:

- `phase-7b-protocol-frozen`

This tag must freeze the protocol, harness, and plan used for the full campaign.
