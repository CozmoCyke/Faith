# ruff: noqa: E402, I001
"""Phase 5 persistence tests."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import CapabilitySet, Dictionary, DictionaryRepository, InterpreterSession
from faifth import CorruptWordVersion, StoragePermissionDenied


def _stack_as_ints(result) -> list[int]:
    return [value.value for value in result.stack]


def _make_square_dictionary(body: list[str]) -> Dictionary:
    dictionary = Dictionary()
    word = dictionary.validate_user_word("square", body)
    dictionary.define(word)
    return dictionary


def test_repository_round_trips_dictionary_state(tmp_path: Path) -> None:
    repository = DictionaryRepository(tmp_path / "faifth.sqlite3")
    save_caps = CapabilitySet.of("storage.write")
    read_caps = CapabilitySet.of("storage.read", "dictionary.restore")

    save_result = repository.save_dictionary(
        _make_square_dictionary(["dup", "*"]),
        capabilities=save_caps,
    )
    assert save_result.status == "ok"
    assert save_result.created_versions == (("square", 1),)

    session = InterpreterSession()
    load_result = repository.load_active_dictionary(
        session=session,
        capabilities=read_caps,
    )

    assert load_result.status == "ok"
    assert load_result.loaded_words == ("square",)
    assert _stack_as_ints(session.execute("5 square")) == [25]


def test_repository_reuses_identical_content_without_spurious_versions(
    tmp_path: Path,
) -> None:
    repository = DictionaryRepository(tmp_path / "faifth.sqlite3")
    save_caps = CapabilitySet.of("storage.write")

    first = repository.save_dictionary(
        _make_square_dictionary(["dup", "*"]),
        capabilities=save_caps,
    )
    second = repository.save_dictionary(
        _make_square_dictionary(["dup", "*"]),
        capabilities=save_caps,
    )

    assert first.status == "ok"
    assert second.status == "ok"
    assert first.created_versions == (("square", 1),)
    assert second.created_versions == ()
    assert second.unchanged_versions == (("square", 1),)
    assert repository.list_versions(
        "square",
        capabilities=CapabilitySet.of("storage.read"),
    ) == (1,)


def test_repository_restores_previous_version(tmp_path: Path) -> None:
    repository = DictionaryRepository(tmp_path / "faifth.sqlite3")
    save_caps = CapabilitySet.of("storage.write")
    restore_caps = CapabilitySet.of(
        "storage.read",
        "storage.write",
        "dictionary.restore",
    )

    repository.save_dictionary(
        _make_square_dictionary(["dup", "*"]),
        capabilities=save_caps,
    )
    repository.save_dictionary(
        _make_square_dictionary(["dup", "*", "dup", "*"]),
        capabilities=save_caps,
    )

    session = InterpreterSession()
    loaded = repository.load_active_dictionary(
        session=session,
        capabilities=CapabilitySet.of("storage.read", "dictionary.restore"),
    )
    assert loaded.status == "ok"
    assert _stack_as_ints(session.execute("2 square")) == [16]

    restored = repository.restore_word(
        session=session,
        name="square",
        version=1,
        capabilities=restore_caps,
    )

    assert restored.status == "ok"
    assert repository.get_active_version(
        "square", capabilities=CapabilitySet.of("storage.read")
    ) == 1
    assert _stack_as_ints(session.execute("2 square")) == [4]


def test_repository_refuses_missing_capabilities(tmp_path: Path) -> None:
    repository = DictionaryRepository(tmp_path / "faifth.sqlite3")

    result = repository.save_dictionary(_make_square_dictionary(["dup", "*"]))

    assert result.status == "error"
    assert isinstance(result.error, StoragePermissionDenied)
    assert result.error.code == "faifth.storage_permission_denied"


def test_repository_detects_corrupt_word_version(tmp_path: Path) -> None:
    repository = DictionaryRepository(tmp_path / "faifth.sqlite3")
    save_caps = CapabilitySet.of("storage.write")
    read_caps = CapabilitySet.of("storage.read", "dictionary.restore")
    repository.save_dictionary(
        _make_square_dictionary(["dup", "*"]),
        capabilities=save_caps,
    )

    with sqlite3.connect(tmp_path / "faifth.sqlite3") as conn:
        conn.execute(
            """
            UPDATE word_versions
            SET content_hash = 'deadbeef'
            WHERE word_name = 'square' AND version = 1
            """
        )
        conn.commit()

    result = repository.load_active_dictionary(
        session=InterpreterSession(),
        capabilities=read_caps,
    )

    assert result.status == "error"
    assert isinstance(result.error, CorruptWordVersion)
    assert result.error.code == "faifth.corrupt_word_version"
