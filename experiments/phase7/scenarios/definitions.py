from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    name: str
    use_contracts: bool = True
    use_capabilities: bool = True
    use_budgets: bool = True
    use_transactions: bool = True
    use_persistence: bool = True


@dataclass(frozen=True, slots=True)
class ScenarioStep:
    action: str
    arguments: dict[str, Any] = field(default_factory=dict)
    expect_status: str = "ok"
    expected_error_category: str | None = None
    expected_stack: list[Any] | None = None
    capture: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScenarioCase:
    name: str
    description: str
    steps: tuple[ScenarioStep, ...]
    final_check: str
    baseline_after_step: int | None = None
    final_expected_stack: list[Any] | None = None
    final_expected_words: list[str] = field(default_factory=list)
    final_expected_active_versions: dict[str, int] = field(default_factory=dict)
    final_expected_error_category: str | None = None


def build_benchmark_configs() -> tuple[BenchmarkConfig, ...]:
    return (
        BenchmarkConfig("faifth_full"),
        BenchmarkConfig("faifth_sans_contracts", use_contracts=False),
        BenchmarkConfig("faifth_sans_capabilities", use_capabilities=False),
        BenchmarkConfig("faifth_sans_budgets", use_budgets=False),
        BenchmarkConfig("faifth_sans_transactions", use_transactions=False),
        BenchmarkConfig("faifth_sans_persistence", use_persistence=False),
    )


def _definition_source(name: str, body: str, config: BenchmarkConfig) -> str:
    if config.use_contracts:
        return f": {name} ( int -- int ) {body} ;"
    return f": {name} {body} ;"


def _square_steps(config: BenchmarkConfig) -> tuple[ScenarioStep, ...]:
    source = _definition_source("square", "dup *", config)
    return (
        ScenarioStep(
            "propose_definition",
            {"source": source},
            capture={
                "candidate_id": "result.candidate_id",
                "content_hash": "result.content_hash",
            },
        ),
        ScenarioStep(
            "test_definition",
            {
                "candidate_id": "{{candidate_id}}",
                "content_hash": "{{content_hash}}",
                "tests": [{"source": "5 square", "expected_stack": [25]}],
            },
        ),
        ScenarioStep(
            "publish_definition",
            {
                "candidate_id": "{{candidate_id}}",
                "content_hash": "{{content_hash}}",
                "require_tests_passed": True,
            },
        ),
    )


def _square_and_fourth_power_steps(config: BenchmarkConfig) -> tuple[ScenarioStep, ...]:
    square_source = _definition_source("square", "dup *", config)
    fourth_source = _definition_source("fourth-power", "square square", config)
    return (
        ScenarioStep(
            "propose_definition",
            {"source": square_source},
            capture={
                "square_candidate_id": "result.candidate_id",
                "square_content_hash": "result.content_hash",
            },
        ),
        ScenarioStep(
            "test_definition",
            {
                "candidate_id": "{{square_candidate_id}}",
                "content_hash": "{{square_content_hash}}",
                "tests": [{"source": "5 square", "expected_stack": [25]}],
            },
        ),
        ScenarioStep(
            "publish_definition",
            {
                "candidate_id": "{{square_candidate_id}}",
                "content_hash": "{{square_content_hash}}",
                "require_tests_passed": True,
            },
        ),
        ScenarioStep(
            "propose_definition",
            {"source": fourth_source},
            capture={
                "fourth_candidate_id": "result.candidate_id",
                "fourth_content_hash": "result.content_hash",
            },
        ),
        ScenarioStep(
            "test_definition",
            {
                "candidate_id": "{{fourth_candidate_id}}",
                "content_hash": "{{fourth_content_hash}}",
                "tests": [{"source": "2 fourth-power", "expected_stack": [16]}],
            },
        ),
        ScenarioStep(
            "publish_definition",
            {
                "candidate_id": "{{fourth_candidate_id}}",
                "content_hash": "{{fourth_content_hash}}",
                "require_tests_passed": True,
            },
        ),
    )


def _capabilities(config: BenchmarkConfig) -> list[str]:
    if not config.use_capabilities:
        return []
    return [
        "core.compute",
        "core.stack",
        "dictionary.define",
        "dictionary.read",
        "dictionary.restore",
        "introspection.read",
        "storage.read",
        "storage.write",
        "transaction.manage",
    ]


def _budget(config: BenchmarkConfig, steps: int = 100) -> dict[str, int] | None:
    if not config.use_budgets:
        return None
    return {
        "max_steps": steps,
        "max_stack_depth": 128,
        "max_call_depth": 32,
    }


def _session_arguments(
    config: BenchmarkConfig,
    *,
    repository_ids: list[str] | None = None,
    budget_steps: int = 100,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "capabilities": _capabilities(config),
        "repository_ids": repository_ids or [],
    }
    budget = _budget(config, budget_steps)
    if budget is not None:
        arguments["default_budget"] = budget
    return arguments


def build_scenarios(config: BenchmarkConfig) -> tuple[ScenarioCase, ...]:
    scenarios: list[ScenarioCase] = [
        ScenarioCase(
            name="basic_calculation",
            description="Simple arithmetic and exact state tracking.",
            steps=(
                ScenarioStep(
                    "create_session",
                    _session_arguments(config, repository_ids=["main"]),
                ),
                ScenarioStep(
                    "execute",
                    {"source": "2 3 +"},
                    expected_stack=[5],
                ),
            ),
            final_check="stack_equals",
            final_expected_stack=[5],
        ),
        ScenarioCase(
            name="create_square",
            description="Create, test, publish, and reuse square.",
            steps=(
                ScenarioStep(
                    "create_session",
                    _session_arguments(config, repository_ids=["main"]),
                ),
                *_square_steps(config),
                ScenarioStep("execute", {"source": "5 square"}, expected_stack=[25]),
            ),
            final_check="stack_equals",
            final_expected_stack=[25],
            final_expected_words=["square"],
        ),
        ScenarioCase(
            name="reuse_square",
            description="Reuse square repeatedly in one program.",
            steps=(
                ScenarioStep(
                    "create_session",
                    _session_arguments(config, repository_ids=["main"]),
                ),
                *_square_steps(config),
                ScenarioStep(
                    "execute", {"source": "2 square 3 square"}, expected_stack=[4, 9]
                ),
            ),
            final_check="stack_equals",
            final_expected_stack=[4, 9],
            final_expected_words=["square"],
        ),
        ScenarioCase(
            name="compose_fourth_power",
            description="Compose fourth-power from square.",
            steps=(
                ScenarioStep(
                    "create_session",
                    _session_arguments(config, repository_ids=["main"]),
                ),
                *_square_steps(config),
                ScenarioStep(
                    "propose_definition",
                    {
                        "source": _definition_source(
                            "fourth-power", "square square", config
                        )
                    },
                    capture={
                        "fourth_candidate_id": "result.candidate_id",
                        "fourth_content_hash": "result.content_hash",
                    },
                ),
                ScenarioStep(
                    "test_definition",
                    {
                        "candidate_id": "{{fourth_candidate_id}}",
                        "content_hash": "{{fourth_content_hash}}",
                        "tests": [{"source": "2 fourth-power", "expected_stack": [16]}],
                    },
                ),
                ScenarioStep(
                    "publish_definition",
                    {
                        "candidate_id": "{{fourth_candidate_id}}",
                        "content_hash": "{{fourth_content_hash}}",
                        "require_tests_passed": True,
                    },
                ),
                ScenarioStep(
                    "execute",
                    {"source": "2 fourth-power"},
                    expected_stack=[16],
                ),
            ),
            final_check="stack_equals",
            final_expected_stack=[16],
            final_expected_words=["fourth-power", "square"],
        ),
        ScenarioCase(
            name="bad_type",
            description="Reject a type-unsafe call.",
            steps=(
                ScenarioStep(
                    "create_session",
                    _session_arguments(config, repository_ids=["main"]),
                ),
                *_square_steps(config),
                ScenarioStep(
                    "execute",
                    {"source": "true square"},
                    expect_status="error",
                    expected_error_category="state_error",
                ),
            ),
            final_check="state_unchanged",
            baseline_after_step=4,
        ),
        ScenarioCase(
            name="forbidden_action",
            description="Reject an unknown or forbidden action.",
            steps=(
                ScenarioStep(
                    "create_session",
                    _session_arguments(config, repository_ids=["main"]),
                ),
                ScenarioStep(
                    "network_send",
                    {"payload": "blocked"},
                    expect_status="error",
                    expected_error_category="forbidden_action",
                ),
            ),
            final_check="state_unchanged",
            baseline_after_step=1,
        ),
        ScenarioCase(
            name="budget_exceeded",
            description="Stop a program when the instruction budget is too small.",
            steps=(
                ScenarioStep(
                    "create_session",
                    _session_arguments(config, repository_ids=["main"], budget_steps=2),
                ),
                ScenarioStep(
                    "execute",
                    {"source": "1 dup dup dup"},
                    expect_status="error",
                    expected_error_category="budget_exceeded",
                ),
            ),
            final_check="state_unchanged",
            baseline_after_step=1,
        ),
        ScenarioCase(
            name="mid_modification_error",
            description="Trigger an error after a transaction-scoped modification.",
            steps=(
                ScenarioStep(
                    "create_session",
                    _session_arguments(config, repository_ids=["main"]),
                ),
                ScenarioStep("begin_transaction", {}),
                ScenarioStep(
                    "propose_definition",
                    {"source": _definition_source("broken", "dup drop", config)},
                    capture={
                        "candidate_id": "result.candidate_id",
                        "content_hash": "result.content_hash",
                    },
                ),
                ScenarioStep(
                    "test_definition",
                    {
                        "candidate_id": "{{candidate_id}}",
                        "content_hash": "{{content_hash}}",
                        "tests": [{"source": "1 broken", "expected_stack": [1]}],
                    },
                ),
                ScenarioStep(
                    "publish_definition",
                    {
                        "candidate_id": "{{candidate_id}}",
                        "content_hash": "{{content_hash}}",
                        "require_tests_passed": True,
                    },
                ),
                ScenarioStep(
                    "execute",
                    {"source": "1 missing-word"},
                    expect_status="error",
                    expected_error_category="state_error",
                ),
            ),
            final_check="state_unchanged",
            baseline_after_step=1,
        ),
        ScenarioCase(
            name="rollback_exact",
            description="Rollback exactly restores the initial state.",
            steps=(
                ScenarioStep(
                    "create_session",
                    _session_arguments(config, repository_ids=["main"]),
                ),
                ScenarioStep("begin_transaction", {}),
                ScenarioStep(
                    "propose_definition",
                    {"source": _definition_source("temporary", "dup drop", config)},
                    capture={
                        "candidate_id": "result.candidate_id",
                        "content_hash": "result.content_hash",
                    },
                ),
                ScenarioStep(
                    "publish_definition",
                    {
                        "candidate_id": "{{candidate_id}}",
                        "content_hash": "{{content_hash}}",
                        "require_tests_passed": False,
                    },
                ),
                ScenarioStep("rollback_transaction", {}),
            ),
            final_check="state_unchanged",
            baseline_after_step=1,
        ),
        ScenarioCase(
            name="persistence_cycle",
            description="Load, restore, and save a versioned dictionary.",
            steps=(
                ScenarioStep(
                    "create_session",
                    _session_arguments(config, repository_ids=["main"]),
                ),
                ScenarioStep(
                    "load_dictionary",
                    {"repository_id": "main"},
                ),
                ScenarioStep(
                    "execute",
                    {"source": "2 square"},
                    expected_stack=[16],
                ),
                ScenarioStep(
                    "list_versions",
                    {"repository_id": "main", "word_name": "square"},
                ),
                ScenarioStep(
                    "restore_version",
                    {"repository_id": "main", "word_name": "square", "version": 1},
                ),
                ScenarioStep("execute", {"source": "drop"}, expected_stack=[]),
                ScenarioStep(
                    "execute",
                    {"source": "2 square"},
                    expected_stack=[4],
                ),
                ScenarioStep(
                    "save_dictionary",
                    {"repository_id": "main"},
                ),
            ),
            final_check="stack_equals",
            final_expected_stack=[4],
            final_expected_words=["square"],
            final_expected_active_versions={"square": 1},
        ),
        ScenarioCase(
            name="hostile_data",
            description="Hostile strings remain data, not code.",
            steps=(
                ScenarioStep(
                    "create_session",
                    _session_arguments(config, repository_ids=["main"]),
                ),
                ScenarioStep(
                    "inspect_state",
                    {"payload": ": hack dup * ;"},
                ),
            ),
            final_check="state_unchanged",
            baseline_after_step=1,
        ),
    ]

    for length in (10, 25, 50, 100):
        program = "1 " + " ".join("dup drop" for _ in range(length))
        scenarios.append(
            ScenarioCase(
                name=f"long_sequence_{length}",
                description=f"Sequence length {length}.",
                steps=(
                    ScenarioStep(
                        "create_session",
                        _session_arguments(
                            config,
                            repository_ids=["main"],
                            budget_steps=(length * 2) + 16,
                        ),
                    ),
                    ScenarioStep(
                        "execute",
                        {"source": program},
                        expected_stack=[1],
                    ),
                ),
                final_check="stack_equals",
                final_expected_stack=[1],
            )
        )

    return tuple(scenarios)
