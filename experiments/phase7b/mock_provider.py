from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class MockProvider:
    """Local no-op provider used to validate the pilot harness."""

    def __init__(self) -> None:
        self.call_count = 0
        self.sessions: dict[str, dict[str, Any]] = {}

    def create_session(
        self, session_id: str, *, initial_state: Mapping[str, Any]
    ) -> None:
        self.sessions[session_id] = {"state": dict(initial_state), "runs": []}

    def record_run(self, session_id: str, run: Mapping[str, Any]) -> None:
        session = self.sessions.setdefault(session_id, {"state": {}, "runs": []})
        session["runs"].append(dict(run))

    def invoke(self, *_: Any, **__: Any) -> dict[str, Any]:
        self.call_count += 1
        return {"status": "ok", "result": None, "audit": []}

    def snapshot(self, session_id: str) -> dict[str, Any]:
        session = self.sessions.get(session_id, {"state": {}, "runs": []})
        return {
            "session_id": session_id,
            "state": dict(session["state"]),
            "run_count": len(session["runs"]),
        }
