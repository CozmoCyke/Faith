# ruff: noqa: E402, I001
"""Phase 6 protocol action tests."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import DictionaryRepository, FaifthAgentProtocol, ProtocolRequest


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


def _stack_values(result) -> list[int | bool | str]:
    return [item["value"] for item in result["stack"]]


def _protocol_with_repository(tmp_path: Path) -> FaifthAgentProtocol:
    protocol = FaifthAgentProtocol()
    repository = DictionaryRepository(tmp_path / "faifth.sqlite3")
    protocol.register_repository("main", repository)
    return protocol


def test_propose_test_publish_and_execute_cycle(tmp_path: Path) -> None:
    protocol = _protocol_with_repository(tmp_path)
    protocol.handle(
        _request(
            "create_session",
            "session-1",
            "req-1",
            {
                "capabilities": [
                    "core.compute",
                    "core.stack",
                    "dictionary.define",
                    "dictionary.read",
                    "introspection.read",
                ],
            },
        )
    )

    proposed = protocol.handle(
        _request(
            "propose_definition",
            "session-1",
            "req-2",
            {"source": ": square dup * ;"},
        )
    )
    assert proposed.status == "ok"
    assert proposed.result is not None
    candidate_id = proposed.result["candidate_id"]
    content_hash = proposed.result["content_hash"]

    tested = protocol.handle(
        _request(
            "test_definition",
            "session-1",
            "req-3",
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
            "session-1",
            "req-4",
            {
                "candidate_id": candidate_id,
                "content_hash": content_hash,
                "require_tests_passed": True,
            },
        )
    )
    assert published.status == "ok"

    executed = protocol.handle(
        _request("execute", "session-1", "req-5", {"source": "5 square"})
    )

    assert executed.status == "ok"
    assert executed.result is not None
    assert _stack_values(executed.result) == [25]


def test_request_id_replay_is_idempotent(tmp_path: Path) -> None:
    protocol = _protocol_with_repository(tmp_path)
    first = _request(
        "create_session",
        "session-1",
        "req-1",
        {"capabilities": ["core.compute", "core.stack"]},
    )

    response1 = protocol.handle(first)
    response2 = protocol.handle(first)

    assert response1.to_json() == response2.to_json()


def test_invalid_protocol_version_is_rejected() -> None:
    protocol = FaifthAgentProtocol()
    response = protocol.handle_dict(
        {
            "protocol": "faifth-agent",
            "version": "9.9",
            "request_id": "req-1",
            "session_id": "session-1",
            "action": "inspect_state",
            "arguments": {},
        }
    )

    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "faifth.unsupported_protocol_version"
