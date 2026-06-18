from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from faifth import CapabilitySet, Dictionary, DictionaryRepository, FaifthAgentProtocol

PROTOCOL_NAME = "faifth_protocol"
PROTOCOL_VERSION = "0.1"


class FaithProtocolAdapter:
    protocol_name = PROTOCOL_NAME
    protocol_version = PROTOCOL_VERSION
    wire_protocol_name = "faifth-agent"

    def __init__(self, *, workdir: Path, variant: str) -> None:
        self.variant = variant
        self.workdir = workdir
        self.protocol = FaifthAgentProtocol()
        self._repositories: dict[str, DictionaryRepository] = {}
        self._snapshot_sequence = 0
        self._seed_repository()

    def _seed_repository(self) -> None:
        repository = DictionaryRepository(self.workdir / "faifth-protocol.sqlite3")
        permissions = CapabilitySet.of("storage.write")
        first = Dictionary()
        first.define(first.validate_user_word("square", ("dup", "*")))
        second = Dictionary()
        second.define(second.validate_user_word("square", ("dup", "*", "dup", "*")))
        repository.save_dictionary(first, capabilities=permissions)
        repository.save_dictionary(second, capabilities=permissions)
        self.protocol.register_repository("main", repository)
        self._repositories["main"] = repository

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        response = self.protocol.handle_dict(dict(request))
        return response.to_dict()

    def snapshot(self, session_id: str) -> dict[str, Any]:
        self._snapshot_sequence += 1
        request_id = f"snapshot-{session_id}-{self._snapshot_sequence}"
        request = {
            "protocol": "faifth-agent",
            "version": "0.1",
            "request_id": request_id,
            "session_id": session_id,
            "action": "inspect_state",
            "arguments": {},
        }
        response = self.protocol.handle_dict(request)
        if response.status != "ok" or response.result is None:
            return {
                "session_id": session_id,
                "error": response.error.to_dict() if response.error else None,
            }
        snapshot = dict(response.result)
        words = self.protocol.handle_dict(
            {
                "protocol": "faifth-agent",
                "version": "0.1",
                "request_id": f"words-{session_id}-{self._snapshot_sequence}",
                "session_id": session_id,
                "action": "list_words",
                "arguments": {"kind": "user"},
            }
        )
        if words.status == "ok" and words.result is not None:
            snapshot["words"] = [item["name"] for item in words.result.get("words", [])]
        return snapshot

    def close(self) -> None:
        self._repositories.clear()
        self._snapshot_sequence = 0
