# ruff: noqa: E402, I001
"""Phase 7 regression tests for protocol rollback and budget handling."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import (
    DictionaryRepository,
    ExecutionBudget,
    FaifthAgentProtocol,
    InterpreterSession,
    ProtocolRequest,
)


def _request(
    action: str,
    session_id: str,
    request_id: str,
    arguments: dict | None = None,
) -> ProtocolRequest:
    return ProtocolRequest.from_dict(
        {
            "protocol": "faifth-agent",
            "version": "0.1",
            "request_id": request_id,
            "session_id": session_id,
            "action": action,
            "arguments": arguments or {},
        }
    )


def _protocol(tmp_path: Path) -> FaifthAgentProtocol:
    protocol = FaifthAgentProtocol()
    protocol.register_repository(
        "main", DictionaryRepository(tmp_path / "phase7-regression.sqlite3")
    )
    return protocol


def _create_session(protocol: FaifthAgentProtocol, session_id: str) -> None:
    response = protocol.handle(
        _request(
            "create_session",
            session_id,
            f"{session_id}-create",
            {
                "capabilities": [
                    "core.compute",
                    "core.stack",
                    "dictionary.define",
                    "dictionary.read",
                    "dictionary.restore",
                    "introspection.read",
                    "storage.read",
                    "storage.write",
                    "transaction.manage",
                ],
                "repository_ids": ["main"],
            },
        )
    )
    assert response.status == "ok"


def _publish_square(protocol: FaifthAgentProtocol, session_id: str) -> None:
    proposed = protocol.handle(
        _request(
            "propose_definition",
            session_id,
            f"{session_id}-propose-square",
            {"source": ": square ( int -- int ) dup * ;"},
        )
    )
    assert proposed.status == "ok"
    assert proposed.result is not None
    candidate_id = proposed.result["candidate_id"]
    content_hash = proposed.result["content_hash"]

    tested = protocol.handle(
        _request(
            "test_definition",
            session_id,
            f"{session_id}-test-square",
            {
                "candidate_id": candidate_id,
                "content_hash": content_hash,
                "tests": [{"source": "5 square", "expected_stack": [25]}],
            },
        )
    )
    assert tested.status == "ok"

    published = protocol.handle(
        _request(
            "publish_definition",
            session_id,
            f"{session_id}-publish-square",
            {
                "candidate_id": candidate_id,
                "content_hash": content_hash,
                "require_tests_passed": True,
            },
        )
    )
    assert published.status == "ok"


def canonical_session_state(protocol: FaifthAgentProtocol, session_id: str) -> dict:
    response = protocol.handle(
        _request("inspect_state", session_id, f"{session_id}-inspect")
    )
    assert response.status == "ok"
    assert response.result is not None
    result = response.result
    return {
        "stack": result["stack"],
        "stack_depth": result["stack_depth"],
        "user_word_count": result["user_word_count"],
        "active_versions": result["active_versions"],
        "candidate_count": result["candidate_count"],
        "transaction_active": result["transaction_active"],
        "repositories": result["repositories"],
        "capabilities": result["capabilities"],
        "default_budget": result["default_budget"],
    }


def test_bad_type_restores_stack_in_interpreter() -> None:
    session = InterpreterSession()
    session.execute(": square ( int -- int ) dup * ;")

    result = session.execute("true square")

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "faifth.contract_input_mismatch"
    assert [value.value for value in result.stack] == [True]
    assert result.transaction_rolled_back is False


def test_bad_type_restores_stack_in_protocol(tmp_path: Path) -> None:
    protocol = _protocol(tmp_path)
    session_id = "bad-type"
    _create_session(protocol, session_id)
    _publish_square(protocol, session_id)

    response = protocol.handle(
        _request(
            "execute",
            session_id,
            f"{session_id}-execute",
            {"source": "true square"},
        )
    )

    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "faifth.contract_input_mismatch"
    assert response.result is None
    snapshot = canonical_session_state(protocol, session_id)
    assert snapshot["stack"] == []
    assert snapshot["transaction_active"] is False


def test_budget_exceeded_restores_stack_in_interpreter() -> None:
    session = InterpreterSession()

    result = session.execute(
        "2 3 + dup *",
        budget=ExecutionBudget(max_steps=4, max_stack_depth=32, max_call_depth=16),
    )

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "faifth.step_budget_exceeded"
    assert [value.value for value in result.stack] == [5, 5]
    assert result.usage.steps_used == 4
    assert result.usage.limit_hit == "steps"


def test_budget_exceeded_restores_stack_in_protocol(tmp_path: Path) -> None:
    protocol = _protocol(tmp_path)
    session_id = "budget"
    response = protocol.handle(
        _request(
            "create_session",
            session_id,
            f"{session_id}-create",
            {
                "capabilities": [
                    "core.compute",
                    "core.stack",
                    "dictionary.define",
                    "dictionary.read",
                    "dictionary.restore",
                    "introspection.read",
                    "storage.read",
                    "storage.write",
                    "transaction.manage",
                ],
                "repository_ids": ["main"],
                "default_budget": {
                    "max_steps": 4,
                    "max_stack_depth": 32,
                    "max_call_depth": 16,
                },
            },
        )
    )
    assert response.status == "ok"
    _publish_square(protocol, session_id)

    executed = protocol.handle(
        _request(
            "execute",
            session_id,
            f"{session_id}-execute",
            {"source": "2 3 + dup *"},
        )
    )

    assert executed.status == "error"
    assert executed.error is not None
    assert executed.error.code == "faifth.step_budget_exceeded"
    assert executed.result is None
    snapshot = canonical_session_state(protocol, session_id)
    assert snapshot["stack"] == []
    assert snapshot["transaction_active"] is False


def test_budget_exceeded_inside_user_word_restores_call_stack() -> None:
    session = InterpreterSession()

    result = session.execute(
        ": explode dup dup dup ; 1 explode",
        budget=ExecutionBudget(max_steps=3, max_stack_depth=32, max_call_depth=16),
    )

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "faifth.step_budget_exceeded"
    assert [value.value for value in result.stack] == [1]


def test_mid_modification_error_rolls_back_protocol_state(tmp_path: Path) -> None:
    protocol = _protocol(tmp_path)
    session_id = "mid-modification"
    _create_session(protocol, session_id)
    before = canonical_session_state(protocol, session_id)

    begin = protocol.handle(
        _request("begin_transaction", session_id, f"{session_id}-begin")
    )
    assert begin.status == "ok"
    _publish_square(protocol, session_id)

    proposed = protocol.handle(
        _request(
            "propose_definition",
            session_id,
            f"{session_id}-temp-propose",
            {"source": ": temporary dup ;"},
        )
    )
    assert proposed.status == "ok"
    assert proposed.result is not None
    candidate_id = proposed.result["candidate_id"]
    content_hash = proposed.result["content_hash"]

    tested = protocol.handle(
        _request(
            "test_definition",
            session_id,
            f"{session_id}-temp-test",
            {
                "candidate_id": candidate_id,
                "content_hash": content_hash,
                "tests": [{"source": "1 temporary", "expected_stack": [1, 1]}],
            },
        )
    )
    assert tested.status == "ok"

    published = protocol.handle(
        _request(
            "publish_definition",
            session_id,
            f"{session_id}-temp-publish",
            {
                "candidate_id": candidate_id,
                "content_hash": content_hash,
                "require_tests_passed": True,
            },
        )
    )
    assert published.status == "ok"

    failed = protocol.handle(
        _request(
            "execute",
            session_id,
            f"{session_id}-fail",
            {"source": "1 missing-word"},
        )
    )

    assert failed.status == "error"
    assert failed.error is not None
    after = canonical_session_state(protocol, session_id)
    assert after == before


def test_rollback_exact_restores_canonical_protocol_state(tmp_path: Path) -> None:
    protocol = _protocol(tmp_path)
    session_id = "rollback-exact"
    _create_session(protocol, session_id)
    before = canonical_session_state(protocol, session_id)

    begin = protocol.handle(
        _request("begin_transaction", session_id, f"{session_id}-begin")
    )
    assert begin.status == "ok"
    _publish_square(protocol, session_id)

    proposed = protocol.handle(
        _request(
            "propose_definition",
            session_id,
            f"{session_id}-temp-propose",
            {"source": ": temporary dup ;"},
        )
    )
    assert proposed.status == "ok"
    assert proposed.result is not None
    candidate_id = proposed.result["candidate_id"]
    content_hash = proposed.result["content_hash"]

    tested = protocol.handle(
        _request(
            "test_definition",
            session_id,
            f"{session_id}-temp-test",
            {
                "candidate_id": candidate_id,
                "content_hash": content_hash,
                "tests": [{"source": "1 temporary", "expected_stack": [1, 1]}],
            },
        )
    )
    assert tested.status == "ok"

    published = protocol.handle(
        _request(
            "publish_definition",
            session_id,
            f"{session_id}-temp-publish",
            {
                "candidate_id": candidate_id,
                "content_hash": content_hash,
                "require_tests_passed": True,
            },
        )
    )
    assert published.status == "ok"

    rolled_back = protocol.handle(
        _request("rollback_transaction", session_id, f"{session_id}-rollback")
    )

    assert rolled_back.status == "ok"
    assert rolled_back.result is not None
    assert rolled_back.result["transaction"]["status"] == "rolled_back"
    after = canonical_session_state(protocol, session_id)
    assert after == before
