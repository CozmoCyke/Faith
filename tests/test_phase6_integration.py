# ruff: noqa: E402, I001
"""Phase 6 protocol integration tests."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import (
    CapabilitySet,
    Dictionary,
    DictionaryRepository,
    FaifthAgentProtocol,
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


def _stack_values(result: dict) -> list[int | bool | str]:
    return [item["value"] for item in result["stack"]]


def _create_protocol_with_seeded_repository(tmp_path: Path) -> FaifthAgentProtocol:
    repository = DictionaryRepository(tmp_path / "faifth.sqlite3")
    permissions = CapabilitySet.of("storage.write")

    first_dictionary = Dictionary()
    first_dictionary.define(
        first_dictionary.validate_user_word("square", ("dup", "*"))
    )
    assert repository.save_dictionary(
        first_dictionary,
        capabilities=permissions,
    ).status == "ok"

    second_dictionary = Dictionary()
    second_dictionary.define(
        second_dictionary.validate_user_word(
            "square",
            ("dup", "*", "dup", "*"),
        )
    )
    assert repository.save_dictionary(
        second_dictionary,
        capabilities=permissions,
    ).status == "ok"

    protocol = FaifthAgentProtocol()
    protocol.register_repository("main", repository)
    return protocol


def test_protocol_load_restore_and_execute_cycle(tmp_path: Path) -> None:
    protocol = _create_protocol_with_seeded_repository(tmp_path)

    created = protocol.handle(
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
                    "dictionary.restore",
                    "introspection.read",
                    "storage.read",
                    "storage.write",
                ],
                "repository_ids": ["main"],
            },
        )
    )
    assert created.status == "ok"

    loaded = protocol.handle(
        _request(
            "load_dictionary",
            "session-1",
            "req-2",
            {"repository_id": "main"},
        )
    )
    assert loaded.status == "ok"
    assert loaded.result is not None
    assert loaded.result["loaded_words"] == ["square"]

    listed = protocol.handle(
        _request(
            "list_versions",
            "session-1",
            "req-3",
            {
                "repository_id": "main",
                "word_name": "square",
            },
        )
    )
    assert listed.status == "ok"
    assert listed.result is not None
    assert listed.result["active_version"] == 2
    assert [item["version"] for item in listed.result["versions"]] == [1, 2]

    executed_active = protocol.handle(
        _request("execute", "session-1", "req-4", {"source": "2 square"})
    )
    assert executed_active.status == "ok"
    assert executed_active.result is not None
    assert _stack_values(executed_active.result) == [16]

    restored = protocol.handle(
        _request(
            "restore_version",
            "session-1",
            "req-5",
            {
                "repository_id": "main",
                "word_name": "square",
                "version": 1,
            },
        )
    )
    assert restored.status == "ok"
    assert restored.result is not None
    assert restored.result["restored_word"] == "square"
    assert restored.result["restored_version"] == 1

    executed_restored = protocol.handle(
        _request("execute", "session-1", "req-6", {"source": "2 square"})
    )
    assert executed_restored.status == "ok"
    assert executed_restored.result is not None
    assert _stack_values(executed_restored.result) == [4]
