# ruff: noqa: E402, I001
"""Phase 6 session tests."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import FaifthAgentProtocol, ProtocolRequest


def _request(
    action: str,
    session_id: str,
    request_id: str,
    arguments: dict | None = None,
):
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


def test_create_inspect_and_close_session() -> None:
    protocol = FaifthAgentProtocol()
    created = protocol.handle(
        _request(
            "create_session",
            "session-1",
            "req-1",
            {
                "capabilities": [
                    "core.compute",
                    "core.stack",
                    "dictionary.read",
                    "introspection.read",
                ],
                "repository_ids": [],
            },
        )
    )
    inspected = protocol.handle(_request("inspect_state", "session-1", "req-2"))
    closed = protocol.handle(_request("close_session", "session-1", "req-3"))

    assert created.status == "ok"
    assert inspected.status == "ok"
    assert inspected.result is not None
    assert inspected.result["session_id"] == "session-1"
    assert closed.status == "ok"


def test_sessions_are_isolated() -> None:
    protocol = FaifthAgentProtocol()
    protocol.handle(
        _request(
            "create_session",
            "session-a",
            "req-1",
            {
                "capabilities": [
                    "core.compute",
                    "core.stack",
                    "dictionary.define",
                    "dictionary.read",
                    "introspection.read",
                ]
            },
        )
    )
    protocol.handle(
        _request(
            "create_session",
            "session-b",
            "req-2",
            {
                "capabilities": [
                    "core.compute",
                    "core.stack",
                    "dictionary.define",
                    "dictionary.read",
                    "introspection.read",
                ]
            },
        )
    )

    protocol.handle(
        _request(
            "propose_definition",
            "session-a",
            "req-3",
            {"source": ": square dup * ;"},
        )
    )

    inspected_a = protocol.handle(_request("inspect_state", "session-a", "req-4"))
    inspected_b = protocol.handle(_request("inspect_state", "session-b", "req-5"))

    assert inspected_a.result is not None
    assert inspected_b.result is not None
    assert inspected_a.result["candidate_count"] == 1
    assert inspected_b.result["candidate_count"] == 0
