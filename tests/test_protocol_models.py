# ruff: noqa: E402, I001
"""Phase 6 protocol model tests."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import (
    InvalidRequest,
    ProtocolRequest,
    ProtocolResponse,
    canonical_json,
)


def test_protocol_request_round_trips_to_canonical_json() -> None:
    request = ProtocolRequest.from_dict(
        {
            "protocol": "faifth-agent",
            "version": "0.1",
            "request_id": "req-1",
            "session_id": "session-1",
            "action": "inspect_state",
            "arguments": {},
        }
    )

    assert request.to_dict() == {
        "protocol": "faifth-agent",
        "version": "0.1",
        "request_id": "req-1",
        "session_id": "session-1",
        "action": "inspect_state",
        "arguments": {},
    }
    assert request.to_json() == canonical_json(request.to_dict())


def test_protocol_response_is_deterministic() -> None:
    request = ProtocolRequest.from_dict(
        {
            "protocol": "faifth-agent",
            "version": "0.1",
            "request_id": "req-1",
            "session_id": "session-1",
            "action": "inspect_state",
            "arguments": {},
        }
    )
    response = ProtocolResponse.success(
        request=request,
        result={"b": 2, "a": 1},
    )

    assert response.status == "ok"
    assert response.error is None
    assert response.to_json() == canonical_json(response.to_dict())


def test_protocol_request_rejects_missing_required_field() -> None:
    with pytest.raises(InvalidRequest):
        ProtocolRequest.from_dict(
            {
                "protocol": "faifth-agent",
                "version": "0.1",
                "session_id": "session-1",
                "action": "inspect_state",
                "arguments": {},
            }
        )
