from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from .capabilities import CapabilitySet
from .dictionary import Dictionary, UserWord
from .errors import (
    CorruptWordVersion,
    DependencyCycle,
    FaifthError,
    MissingDependency,
    MissingWordVersion,
    RestoreValidationError,
    StorageIntegrityError,
    StoragePermissionDenied,
    UnsupportedSchemaVersion,
)
from .interpreter import InterpreterSession
from .versioning import WordVersion, canonical_json

_SCHEMA_VERSION = 1
_FORMAT_NAME = "faifth-dictionary"

ResultStatus = Literal["ok", "error"]


def _freeze_mapping(data: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(sorted((data or {}).items())))


@dataclass(frozen=True, slots=True)
class PersistenceAuditEvent:
    kind: str
    status: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", _freeze_mapping(self.details))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "status": self.status,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class PersistenceResult:
    status: ResultStatus
    error: FaifthError | None = None
    audit: tuple[PersistenceAuditEvent, ...] = ()
    path: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"ok", "error"}:
            raise ValueError(f"Invalid result status: {self.status!r}")
        if self.status == "ok" and self.error is not None:
            raise ValueError("Success results cannot contain an error")
        if self.status == "error" and self.error is None:
            raise ValueError("Error results must contain an error")
        if self.error is not None and not isinstance(self.error, FaifthError):
            raise TypeError("error must be a FaifthError")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "error": None if self.error is None else self.error.to_dict(),
            "audit": [event.to_dict() for event in self.audit],
            "path": self.path,
        }


@dataclass(frozen=True, slots=True)
class SaveResult(PersistenceResult):
    created_versions: tuple[tuple[str, int], ...] = ()
    unchanged_versions: tuple[tuple[str, int], ...] = ()
    active_versions: tuple[tuple[str, int], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "created_versions": [
                    {"name": name, "version": version}
                    for name, version in self.created_versions
                ],
                "unchanged_versions": [
                    {"name": name, "version": version}
                    for name, version in self.unchanged_versions
                ],
                "active_versions": [
                    {"name": name, "version": version}
                    for name, version in self.active_versions
                ],
            }
        )
        return data


@dataclass(frozen=True, slots=True)
class LoadResult(PersistenceResult):
    loaded_words: tuple[str, ...] = ()
    active_versions: tuple[tuple[str, int], ...] = ()
    dictionary: Dictionary | None = None

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "loaded_words": list(self.loaded_words),
                "active_versions": [
                    {"name": name, "version": version}
                    for name, version in self.active_versions
                ],
                "dictionary": (
                    None if self.dictionary is None else self.dictionary_to_dict()
                ),
            }
        )
        return data

    def dictionary_to_dict(self) -> dict[str, Any]:
        assert self.dictionary is not None
        return {
            "words": [
                self.dictionary.inspect(name)
                for name in self.dictionary.list_user_words()
            ],
        }


@dataclass(frozen=True, slots=True)
class RestoreResult(LoadResult):
    restored_word: str | None = None
    restored_version: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "restored_word": self.restored_word,
                "restored_version": self.restored_version,
            }
        )
        return data


class DictionaryRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def initialize(
        self,
        *,
        capabilities: CapabilitySet | None = None,
    ) -> SaveResult:
        granted = capabilities or CapabilitySet.none()
        permission_error = self._check_capabilities(
            granted, CapabilitySet.of("storage.write"), operation="initialize"
        )
        if permission_error is not None:
            return SaveResult(
                status="error",
                error=permission_error.error,
                path=permission_error.path,
                audit=permission_error.audit,
            )

        try:
            with self._connect(write=True) as conn:
                self._ensure_schema(conn)
                self._write_metadata(conn)
        except FaifthError as error:
            return SaveResult(
                status="error",
                error=error,
                path=str(self.path),
                audit=(PersistenceAuditEvent("storage_initialized", "error"),),
            )
        return SaveResult(
            status="ok",
            path=str(self.path),
            audit=(PersistenceAuditEvent("storage_initialized", "ok"),),
        )

    def save_dictionary(
        self,
        dictionary: Dictionary,
        *,
        capabilities: CapabilitySet | None = None,
    ) -> SaveResult:
        granted = capabilities or CapabilitySet.none()
        permission_error = self._check_capabilities(
            granted,
            CapabilitySet.of("storage.write"),
            operation="save_dictionary",
        )
        if permission_error is not None:
            return SaveResult(
                status="error",
                error=permission_error.error,
                path=permission_error.path,
                audit=permission_error.audit,
            )

        try:
            self._ensure_parent_directory()
            with self._connect(write=True) as conn:
                self._ensure_schema(conn)
                self._assert_schema(conn)
                return self._save_dictionary_locked(conn, dictionary)
        except FaifthError as error:
            return SaveResult(
                status="error",
                error=error,
                path=str(self.path),
                audit=(PersistenceAuditEvent("dictionary_saved", "error"),),
            )

    def list_versions(
        self,
        word_name: str,
        *,
        capabilities: CapabilitySet | None = None,
    ) -> tuple[int, ...] | PersistenceResult:
        granted = capabilities or CapabilitySet.none()
        permission_error = self._check_capabilities(
            granted,
            CapabilitySet.of("storage.read"),
            operation="list_versions",
        )
        if permission_error is not None:
            return LoadResult(
                status="error",
                error=permission_error.error,
                path=permission_error.path,
                audit=permission_error.audit,
            )

        try:
            with self._connect(write=False) as conn:
                self._assert_schema(conn)
                rows = conn.execute(
                    """
                    SELECT version
                    FROM word_versions
                    WHERE word_name = ?
                    ORDER BY version ASC
                    """,
                    (word_name,),
                ).fetchall()
        except FaifthError as error:
            return SaveResult(
                status="error",
                error=error,
                path=str(self.path),
                audit=(PersistenceAuditEvent("word_versions_listed", "error"),),
            )
        return tuple(int(row["version"]) for row in rows)

    def get_active_version(
        self,
        word_name: str,
        *,
        capabilities: CapabilitySet | None = None,
    ) -> int | None | PersistenceResult:
        granted = capabilities or CapabilitySet.none()
        permission_error = self._check_capabilities(
            granted,
            CapabilitySet.of("storage.read"),
            operation="get_active_version",
        )
        if permission_error is not None:
            return LoadResult(
                status="error",
                error=permission_error.error,
                path=permission_error.path,
                audit=permission_error.audit,
            )

        try:
            with self._connect(write=False) as conn:
                self._assert_schema(conn)
                row = conn.execute(
                    """
                    SELECT active_version
                    FROM active_words
                    WHERE word_name = ?
                    """,
                    (word_name,),
                ).fetchone()
        except FaifthError as error:
            return SaveResult(
                status="error",
                error=error,
                path=str(self.path),
                audit=(PersistenceAuditEvent("active_version_read", "error"),),
            )
        return None if row is None else int(row["active_version"])

    def get_version(
        self,
        word_name: str,
        version: int,
        *,
        capabilities: CapabilitySet | None = None,
    ) -> WordVersion | PersistenceResult:
        granted = capabilities or CapabilitySet.none()
        permission_error = self._check_capabilities(
            granted,
            CapabilitySet.of("storage.read"),
            operation="get_version",
        )
        if permission_error is not None:
            return LoadResult(
                status="error",
                error=permission_error.error,
                path=permission_error.path,
                audit=permission_error.audit,
            )

        try:
            with self._connect(write=False) as conn:
                self._assert_schema(conn)
                row = conn.execute(
                    """
                    SELECT *
                    FROM word_versions
                    WHERE word_name = ? AND version = ?
                    """,
                    (word_name, version),
                ).fetchone()
                if row is None:
                    raise MissingWordVersion(
                        "Word version not found",
                        context={"word": word_name, "version": version},
                    )
                record = self._row_to_word_version(row)
        except FaifthError as error:
            return SaveResult(
                status="error",
                error=error,
                path=str(self.path),
                audit=(PersistenceAuditEvent("word_version_read", "error"),),
            )
        return record

    def load_active_dictionary(
        self,
        *,
        session: InterpreterSession,
        capabilities: CapabilitySet | None = None,
    ) -> LoadResult:
        granted = capabilities or CapabilitySet.none()
        permission_error = self._check_capabilities(
            granted,
            CapabilitySet.of("storage.read", "dictionary.restore"),
            operation="load_active_dictionary",
        )
        if permission_error is not None:
            return LoadResult(
                status="error",
                error=permission_error.error,
                path=permission_error.path,
                audit=permission_error.audit,
            )

        try:
            with self._connect(write=False) as conn:
                self._quick_check(conn)
                self._assert_schema(conn)
                active_rows = self._read_active_versions(conn)
                records = {
                    name: self._get_word_version(conn, name, version)
                    for name, version in active_rows.items()
                }
                dictionary = self._rebuild_dictionary(
                    session=session,
                    records=records,
                )
        except FaifthError as error:
            return LoadResult(
                status="error",
                error=error,
                path=str(self.path),
                audit=(PersistenceAuditEvent("dictionary_loaded", "error"),),
            )

        session.activate_dictionary(dictionary)
        return LoadResult(
            status="ok",
            path=str(self.path),
            audit=(PersistenceAuditEvent("dictionary_loaded", "ok"),),
            loaded_words=tuple(dictionary.list_user_words()),
            active_versions=tuple(sorted(active_rows.items())),
            dictionary=dictionary,
        )

    def restore_word(
        self,
        *,
        session: InterpreterSession,
        name: str,
        version: int,
        capabilities: CapabilitySet | None = None,
    ) -> RestoreResult:
        granted = capabilities or CapabilitySet.none()
        permission_error = self._check_capabilities(
            granted,
            CapabilitySet.of("storage.read", "storage.write", "dictionary.restore"),
            operation="restore_word",
        )
        if permission_error is not None:
            return RestoreResult(
                status="error",
                error=permission_error.error,
                path=permission_error.path,
                audit=permission_error.audit,
            )

        try:
            with self._connect(write=True) as conn:
                self._ensure_schema(conn)
                self._assert_schema(conn)
                active_rows = self._read_active_versions(conn)
                updated_active_rows = dict(active_rows)
                dependency_versions = self._collect_versions(
                    conn,
                    {name: version},
                )
                updated_active_rows.update(dependency_versions)
                dictionary = self._rebuild_dictionary(
                    session=session,
                    records={
                        word_name: self._get_word_version(
                            conn, word_name, active_version
                        )
                        for word_name, active_version in updated_active_rows.items()
                    },
                )
                self._write_active_versions(conn, updated_active_rows)
        except FaifthError as error:
            return RestoreResult(
                status="error",
                error=error,
                path=str(self.path),
                audit=(PersistenceAuditEvent("version_restored", "error"),),
                restored_word=name,
                restored_version=version,
            )

        session.activate_dictionary(dictionary)
        return RestoreResult(
            status="ok",
            path=str(self.path),
            audit=(PersistenceAuditEvent("version_restored", "ok"),),
            loaded_words=tuple(dictionary.list_user_words()),
            active_versions=tuple(sorted(updated_active_rows.items())),
            dictionary=dictionary,
            restored_word=name,
            restored_version=version,
        )

    def save_word(
        self,
        word: UserWord,
        *,
        capabilities: CapabilitySet | None = None,
    ) -> SaveResult:
        dictionary = Dictionary(primitives=None)
        dictionary.define(word)
        return self.save_dictionary(dictionary, capabilities=capabilities)

    def set_active_version(
        self,
        word_name: str,
        version: int,
        *,
        capabilities: CapabilitySet | None = None,
    ) -> SaveResult:
        granted = capabilities or CapabilitySet.none()
        permission_error = self._check_capabilities(
            granted,
            CapabilitySet.of("storage.read", "storage.write"),
            operation="set_active_version",
        )
        if permission_error is not None:
            return SaveResult(
                status="error",
                error=permission_error.error,
                path=permission_error.path,
                audit=permission_error.audit,
            )

        try:
            with self._connect(write=True) as conn:
                self._ensure_schema(conn)
                self._assert_schema(conn)
                self._get_word_version(conn, word_name, version)
                current = self._read_active_versions(conn)
                current[word_name] = version
                self._write_active_versions(conn, current)
        except FaifthError as error:
            return SaveResult(
                status="error",
                error=error,
                path=str(self.path),
                audit=(PersistenceAuditEvent("active_version_set", "error"),),
            )
        return SaveResult(
            status="ok",
            path=str(self.path),
            active_versions=((word_name, version),),
            audit=(PersistenceAuditEvent("active_version_set", "ok"),),
        )

    def _save_dictionary_locked(
        self,
        conn: sqlite3.Connection,
        dictionary: Dictionary,
    ) -> SaveResult:
        user_words = self._topological_user_word_names(dictionary)
        existing_active = self._read_active_versions(conn)
        created: list[tuple[str, int]] = []
        unchanged: list[tuple[str, int]] = []
        active_versions: dict[str, int] = dict(existing_active)
        audit: list[PersistenceAuditEvent] = [
            PersistenceAuditEvent(
                "storage_initialized",
                "ok",
                details={"path": str(self.path)},
            )
        ]

        for sequence, name in enumerate(user_words, start=1):
            entry = dictionary.resolve(name)
            if not isinstance(entry, UserWord):
                continue
            dependency_versions = {
                dependency: active_versions.get(dependency)
                for dependency in entry.dependencies
            }
            if any(version is None for version in dependency_versions.values()):
                missing = next(
                    dependency
                    for dependency, version in dependency_versions.items()
                    if version is None
                )
                raise MissingDependency(
                    "Missing dependency version",
                    context={"word": name, "dependency": missing},
                )
            resolved_dependency_versions = {
                dependency: int(version)
                for dependency, version in dependency_versions.items()
                if version is not None
            }
            candidate = WordVersion.from_user_word(
                entry,
                version=self._next_version(conn, name),
                dependency_versions=resolved_dependency_versions,
                created_sequence=sequence,
            )
            matching = self._find_matching_version(conn, name, candidate.content_hash)
            if matching is not None:
                active_versions[name] = matching
                unchanged.append((name, matching))
                audit.append(
                    PersistenceAuditEvent(
                        "word_version_unchanged",
                        "ok",
                        details={"word": name, "version": matching},
                    )
                )
                continue
            self._insert_version(conn, candidate)
            active_versions[name] = candidate.version
            created.append((name, candidate.version))
            audit.append(
                PersistenceAuditEvent(
                    "word_version_created",
                    "ok",
                    details={"word": name, "version": candidate.version},
                )
            )

        self._write_active_versions(conn, active_versions)
        return SaveResult(
            status="ok",
            path=str(self.path),
            created_versions=tuple(created),
            unchanged_versions=tuple(unchanged),
            active_versions=tuple(sorted(active_versions.items())),
            audit=tuple(audit),
        )

    def _rebuild_dictionary(
        self,
        *,
        session: InterpreterSession,
        records: Mapping[str, WordVersion],
    ) -> Dictionary:
        graph: dict[str, set[str]] = {}
        for name, record in records.items():
            graph[name] = set(record.dependencies)

        ordered_names = self._toposort(graph)
        dictionary = Dictionary(primitives=session.primitives)
        for name in ordered_names:
            record = records[name]
            reconstructed = record.to_user_word()
            candidate = dictionary.validate_user_word(
                reconstructed.name,
                reconstructed.body,
                contract=reconstructed.contract,
                source=reconstructed.source,
                definition_index=reconstructed.definition_index,
            )
            if candidate.dependencies != reconstructed.dependencies:
                raise RestoreValidationError(
                    "Dependency mismatch during restore",
                    context={
                        "word": reconstructed.name,
                        "expected": list(reconstructed.dependencies),
                        "observed": list(candidate.dependencies),
                    },
                )
            if candidate.primitive_dependencies != reconstructed.primitive_dependencies:
                raise RestoreValidationError(
                    "Primitive dependency mismatch during restore",
                    context={
                        "word": reconstructed.name,
                        "expected": list(reconstructed.primitive_dependencies),
                        "observed": list(candidate.primitive_dependencies),
                    },
                )
            if candidate.required_capabilities != reconstructed.required_capabilities:
                raise RestoreValidationError(
                    "Capability mismatch during restore",
                    context={"word": reconstructed.name},
            )
            dictionary.define(candidate)
        return dictionary

    def _topological_user_word_names(self, dictionary: Dictionary) -> tuple[str, ...]:
        graph: dict[str, set[str]] = {}
        for name in dictionary.list_user_words():
            word = dictionary.resolve(name)
            if isinstance(word, UserWord):
                graph[name] = set(word.dependencies)
        ordered: list[str] = []
        ready = sorted(name for name, deps in graph.items() if not deps)
        graph = {name: set(deps) for name, deps in graph.items()}
        while ready:
            name = ready.pop(0)
            ordered.append(name)
            for other_name, deps in graph.items():
                if name in deps:
                    deps.remove(name)
                    if (
                        not deps
                        and other_name not in ordered
                        and other_name not in ready
                    ):
                        ready.append(other_name)
                        ready.sort()
        if len(ordered) != len(graph):
            raise DependencyCycle(
                "User-word dependency cycle",
                context={"words": sorted(graph)},
            )
        return tuple(ordered)

    def _toposort(self, graph: Mapping[str, set[str]]) -> tuple[str, ...]:
        working = {key: set(deps) for key, deps in graph.items()}
        ordered: list[str] = []
        ready = sorted(name for name, deps in working.items() if not deps)
        while ready:
            name = ready.pop(0)
            ordered.append(name)
            for other_name, deps in working.items():
                if name in deps:
                    deps.remove(name)
                    if (
                        not deps
                        and other_name not in ordered
                        and other_name not in ready
                    ):
                        ready.append(other_name)
                        ready.sort()
        if len(ordered) != len(working):
            raise DependencyCycle(
                "Stored dependency cycle",
                context={"words": sorted(working)},
            )
        return tuple(ordered)

    def _collect_versions(
        self,
        conn: sqlite3.Connection,
        roots: Mapping[str, int],
    ) -> dict[str, int]:
        versions: dict[str, int] = {}
        stack: list[tuple[str, int]] = [*(tuple(sorted(roots.items())))]
        while stack:
            word_name, version = stack.pop()
            if word_name in versions:
                continue
            record = self._get_word_version(conn, word_name, version)
            versions[word_name] = record.version
            for dependency_name, dependency_version in record.dependency_versions:
                stack.append((dependency_name, dependency_version))
        return versions

    def _get_word_version(
        self, conn: sqlite3.Connection, word_name: str, version: int
    ) -> WordVersion:
        row = conn.execute(
            """
            SELECT *
            FROM word_versions
            WHERE word_name = ? AND version = ?
            """,
            (word_name, version),
        ).fetchone()
        if row is None:
            raise MissingWordVersion(
                "Word version not found",
                context={"word": word_name, "version": version},
            )
        record = self._row_to_word_version(row)
        if record.content_hash != record.compute_hash():
            raise CorruptWordVersion(
                "Word version hash mismatch",
                context={"word": word_name, "version": version},
            )
        return record

    def _insert_version(self, conn: sqlite3.Connection, record: WordVersion) -> None:
        conn.execute(
            """
            INSERT INTO word_versions (
                word_name,
                version,
                body_json,
                contract_json,
                dependencies_json,
                dependency_versions_json,
                primitive_dependencies_json,
                required_capabilities_json,
                metadata_json,
                created_sequence,
                content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.name,
                record.version,
                canonical_json({"body": list(record.body)}),
                None
                if record.contract is None
                else canonical_json(record.contract.to_dict()),
                canonical_json({"dependencies": list(record.dependencies)}),
                canonical_json(
                    {
                        "dependency_versions": [
                            {"name": name, "version": version}
                            for name, version in record.dependency_versions
                        ]
                    }
                ),
                canonical_json(
                    {"primitive_dependencies": list(record.primitive_dependencies)}
                ),
                canonical_json(record.required_capabilities.to_dict()),
                canonical_json({"metadata": dict(record.metadata)}),
                record.created_sequence,
                record.content_hash or record.compute_hash(),
            ),
        )

    def _find_matching_version(
        self, conn: sqlite3.Connection, word_name: str, content_hash: str
    ) -> int | None:
        row = conn.execute(
            """
            SELECT version
            FROM word_versions
            WHERE word_name = ? AND content_hash = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (word_name, content_hash),
        ).fetchone()
        return None if row is None else int(row["version"])

    def _next_version(self, conn: sqlite3.Connection, word_name: str) -> int:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(version), 0) AS max_version
            FROM word_versions
            WHERE word_name = ?
            """,
            (word_name,),
        ).fetchone()
        return int(row["max_version"]) + 1

    def _read_active_versions(self, conn: sqlite3.Connection) -> dict[str, int]:
        rows = conn.execute(
            """
            SELECT word_name, active_version
            FROM active_words
            ORDER BY word_name ASC
            """
        ).fetchall()
        return {str(row["word_name"]): int(row["active_version"]) for row in rows}

    def _write_active_versions(
        self, conn: sqlite3.Connection, active_versions: Mapping[str, int]
    ) -> None:
        conn.executemany(
            """
            INSERT INTO active_words (word_name, active_version)
            VALUES (?, ?)
            ON CONFLICT(word_name) DO UPDATE SET
                active_version = excluded.active_version
            """,
            sorted(active_versions.items()),
        )

    def _row_to_word_version(self, row: sqlite3.Row) -> WordVersion:
        record = WordVersion.from_dict(
            {
                "name": row["word_name"],
                "version": row["version"],
                "body": json.loads(row["body_json"]).get("body", []),
                "contract": (
                    json.loads(row["contract_json"])
                    if row["contract_json"]
                    else None
                ),
                "dependencies": json.loads(row["dependencies_json"]).get(
                    "dependencies", []
                ),
                "dependency_versions": json.loads(row["dependency_versions_json"]).get(
                    "dependency_versions", []
                ),
                "primitive_dependencies": json.loads(
                    row["primitive_dependencies_json"]
                ).get("primitive_dependencies", []),
                "required_capabilities": json.loads(
                    row["required_capabilities_json"]
                ),
                "metadata": json.loads(row["metadata_json"]).get("metadata", {}),
                "created_sequence": row["created_sequence"],
                "content_hash": row["content_hash"],
            }
        )
        if record.content_hash != record.compute_hash():
            raise CorruptWordVersion(
                "Stored word version hash mismatch",
                context={"word": record.name, "version": record.version},
            )
        return record

    def _ensure_parent_directory(self) -> None:
        if self.path.parent and not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self, *, write: bool) -> sqlite3.Connection:
        if self.path.exists() is False and not write:
            raise StorageIntegrityError(
                "Database file does not exist",
                context={"path": str(self.path)},
            )
        self._ensure_parent_directory()
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS word_versions (
                word_name TEXT NOT NULL,
                version INTEGER NOT NULL,
                body_json TEXT NOT NULL,
                contract_json TEXT,
                dependencies_json TEXT NOT NULL,
                dependency_versions_json TEXT NOT NULL,
                primitive_dependencies_json TEXT NOT NULL,
                required_capabilities_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_sequence INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                PRIMARY KEY (word_name, version)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS active_words (
                word_name TEXT PRIMARY KEY,
                active_version INTEGER NOT NULL,
                FOREIGN KEY(word_name, active_version)
                    REFERENCES word_versions(word_name, version)
                    ON UPDATE CASCADE
                    ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO metadata(key, value)
            VALUES ('schema_version', ?), ('format', ?)
            """,
            (str(_SCHEMA_VERSION), _FORMAT_NAME),
        )

    def _write_metadata(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT INTO metadata(key, value)
            VALUES ('schema_version', ?), ('format', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (str(_SCHEMA_VERSION), _FORMAT_NAME),
        )

    def _assert_schema(self, conn: sqlite3.Connection) -> None:
        self._quick_check(conn)
        rows = {
            str(row["key"]): str(row["value"])
            for row in conn.execute("SELECT key, value FROM metadata").fetchall()
        }
        if not rows:
            raise StorageIntegrityError(
                "Missing storage metadata",
                context={"path": str(self.path)},
            )
        if rows.get("format") != _FORMAT_NAME:
            raise StorageIntegrityError(
                "Invalid storage format",
                context={"expected": _FORMAT_NAME, "observed": rows.get("format")},
            )
        schema_value = rows.get("schema_version")
        if schema_value is None:
            raise StorageIntegrityError(
                "Missing schema version",
                context={"path": str(self.path)},
            )
        if int(schema_value) != _SCHEMA_VERSION:
            raise UnsupportedSchemaVersion(
                "Unsupported storage schema",
                context={"expected": _SCHEMA_VERSION, "observed": schema_value},
            )

    def _quick_check(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("PRAGMA quick_check").fetchone()
        if row is None or str(row[0]).lower() != "ok":
            raise StorageIntegrityError(
                "SQLite quick_check failed",
                context={
                    "path": str(self.path),
                    "result": None if row is None else row[0],
                },
            )

    def _check_capabilities(
        self,
        granted: CapabilitySet,
        required: CapabilitySet,
        *,
        operation: str,
    ) -> SaveResult | None:
        if granted.allows(required):
            return None
        missing = granted.missing(required)
        return SaveResult(
            status="error",
            error=StoragePermissionDenied(
                f"Storage permission denied for {operation}",
                context={
                    "operation": operation,
                    "required": list(required.to_tuple()),
                    "granted": list(granted.to_tuple()),
                    "missing": list(missing.to_tuple()),
                    "path": str(self.path),
                },
            ),
            path=str(self.path),
            audit=(
                PersistenceAuditEvent(
                    "permission_denied",
                    "error",
                    details={
                        "operation": operation,
                        "required": list(required.to_tuple()),
                        "granted": list(granted.to_tuple()),
                        "missing": list(missing.to_tuple()),
                    },
                ),
            ),
        )


def _save_result_from_error(error: FaifthError, path: Path, kind: str) -> SaveResult:
    return SaveResult(
        status="error",
        error=error,
        path=str(path),
        audit=(PersistenceAuditEvent(kind, "error"),),
    )


__all__ = [
    "DictionaryRepository",
    "PersistenceAuditEvent",
    "PersistenceResult",
    "SaveResult",
    "LoadResult",
    "RestoreResult",
]
