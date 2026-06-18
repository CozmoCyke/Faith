from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from faifth import (
    CapabilitySet,
    Dictionary,
    DictionaryRepository,
    ExecutionBudget,
    FaifthError,
    InterpreterSession,
    ProtocolTestCase,
    UserWord,
    WordVersion,
    tokenize,
)
from faifth.definitions import parse_definition

from .common import make_error, make_response

PROTOCOL_NAME = "python-direct"
PROTOCOL_VERSION = "0.1"

_ALLOWED_CAPABILITIES = CapabilitySet.of(
    "core.compute",
    "core.stack",
    "dictionary.define",
    "dictionary.read",
    "dictionary.restore",
    "introspection.read",
    "storage.read",
    "storage.write",
    "transaction.manage",
)


@dataclass(slots=True)
class DirectCandidate:
    candidate_id: str
    request_id: str
    source: str
    word: UserWord
    content_hash: str
    dependency_fingerprint: tuple[tuple[str, str], ...]
    status: str = "proposed"
    tests_passed: bool = False
    tests_total: int = 0
    tests_passed_count: int = 0
    test_results: tuple[dict[str, Any], ...] = ()
    last_error: FaifthError | None = None


@dataclass(slots=True)
class DirectSession:
    session_id: str
    interpreter: InterpreterSession
    capabilities: CapabilitySet
    default_budget: ExecutionBudget
    repository_ids: tuple[str, ...]
    candidates: dict[str, DirectCandidate]
    request_cache: dict[str, tuple[str, dict[str, Any]]]
    last_result: dict[str, Any] | None
    last_audit: tuple[dict[str, Any], ...]
    stack: list[Any]
    sequence: int = 0
    candidate_sequence: int = 0
    active_versions: dict[str, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.active_versions is None:
            self.active_versions = {}

    def next_sequence(self) -> int:
        self.sequence += 1
        return self.sequence

    def next_candidate_id(self) -> str:
        self.candidate_sequence += 1
        return f"candidate-{self.candidate_sequence}"


def _clone_dictionary(dictionary: Dictionary) -> Dictionary:
    clone = Dictionary(primitives=dictionary.primitives)
    clone.restore_user_words(dictionary.snapshot_user_words())
    return clone


def _clone_session(
    session: InterpreterSession,
    *,
    capabilities: CapabilitySet | None = None,
    default_budget: ExecutionBudget | None = None,
) -> InterpreterSession:
    return InterpreterSession(
        dictionary=_clone_dictionary(session.dictionary),
        capabilities=capabilities if capabilities is not None else session.capabilities,
        default_budget=(
            default_budget if default_budget is not None else session.default_budget
        ),
    )


def _stack_values(stack: list[Any]) -> list[Any]:
    return [item.value for item in stack]


def _error_response(
    request: Mapping[str, Any],
    error: FaifthError | Exception,
) -> dict[str, Any]:
    if isinstance(error, FaifthError):
        error_payload = error.to_dict()
    else:
        error_payload = make_error(
            "python_direct.unhandled_error",
            str(error),
            metadata={"type": type(error).__name__},
        )
    return make_response(
        protocol=PROTOCOL_NAME,
        version=PROTOCOL_VERSION,
        request_id=str(request["request_id"]),
        session_id=str(request["session_id"]),
        status="error",
        error=error_payload,
    )


class PythonDirectAdapter:
    protocol_name = PROTOCOL_NAME
    protocol_version = PROTOCOL_VERSION

    def __init__(self, *, workdir: Path, variant: str) -> None:
        self.variant = variant
        self.workdir = workdir
        self.allowed_capabilities = _ALLOWED_CAPABILITIES
        self._repositories: dict[str, DictionaryRepository] = {}
        self._sessions: dict[str, DirectSession] = {}
        self._seed_repository()

    def _seed_repository(self) -> None:
        repository = DictionaryRepository(self.workdir / "faifth-direct.sqlite3")
        permissions = CapabilitySet.of("storage.write")
        first = Dictionary()
        first.define(first.validate_user_word("square", ("dup", "*")))
        second = Dictionary()
        second.define(second.validate_user_word("square", ("dup", "*", "dup", "*")))
        repository.save_dictionary(first, capabilities=permissions)
        repository.save_dictionary(second, capabilities=permissions)
        self._repositories["main"] = repository

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        try:
            str(request["request_id"])
            session_id = str(request["session_id"])
            action = str(request["action"])
            arguments = request.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be a mapping")
            session = self._sessions.get(session_id)
            if action == "create_session":
                response = self._create_session(request, arguments)
            else:
                if session is None:
                    raise KeyError("unknown session")
                response = self._dispatch(request, session, action, arguments)
        except FaifthError as error:
            response = _error_response(request, error)
        except Exception as error:  # pragma: no cover - safety net
            response = _error_response(request, error)
        return response

    def snapshot(self, session_id: str) -> dict[str, Any]:
        session = self._sessions[session_id]
        return {
            "session_id": session.session_id,
            "stack": [value.to_dict() for value in session.stack],
            "words": list(session.interpreter.dictionary.list_user_words()),
            "active_versions": dict(sorted(session.active_versions.items())),
            "candidates": len(session.candidates),
            "capabilities": session.capabilities.to_dict(),
            "default_budget": session.default_budget.to_dict(),
            "last_error": (
                None
                if session.last_result is None
                or session.last_result.get("error") is None
                else session.last_result["error"]
            ),
            "transaction_active": session.interpreter.transaction_status == "active",
        }

    def _create_session(
        self,
        request: Mapping[str, Any],
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        session_id = str(request["session_id"])
        if session_id in self._sessions:
            raise ValueError("session already exists")
        capabilities = CapabilitySet.of(
            *tuple(str(item) for item in arguments.get("capabilities", ()))
        )
        if not capabilities.issubset(self.allowed_capabilities):
            raise ValueError("capability escalation denied")
        default_budget = self._parse_budget(arguments.get("default_budget"))
        repository_ids = tuple(
            str(item) for item in arguments.get("repository_ids", ())
        )
        interpreter = InterpreterSession(
            capabilities=capabilities,
            default_budget=default_budget,
        )
        session = DirectSession(
            session_id=session_id,
            interpreter=interpreter,
            capabilities=capabilities,
            default_budget=default_budget,
            repository_ids=repository_ids,
            candidates={},
            request_cache={},
            last_result=None,
            last_audit=(),
            stack=[],
        )
        self._sessions[session_id] = session
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session_id,
            status="ok",
            result={
                "session_id": session_id,
                "capabilities": capabilities.to_dict(),
                "default_budget": default_budget.to_dict(),
                "repository_ids": list(repository_ids),
            },
            audit=[
                {
                    "kind": "session_created",
                    "status": "ok",
                    "details": {"session_id": session_id},
                }
            ],
        )

    def _dispatch(
        self,
        request: Mapping[str, Any],
        session: DirectSession,
        action: str,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        handlers = {
            "close_session": self._close_session,
            "inspect_state": self._inspect_state,
            "inspect_session": self._inspect_state,
            "list_words": self._list_words,
            "inspect_word": self._inspect_word,
            "propose_definition": self._propose_definition,
            "test_definition": self._test_definition,
            "publish_definition": self._publish_definition,
            "execute": self._execute,
            "begin_transaction": self._begin_transaction,
            "commit_transaction": self._commit_transaction,
            "rollback_transaction": self._rollback_transaction,
            "save_dictionary": self._save_dictionary,
            "load_dictionary": self._load_dictionary,
            "list_versions": self._list_versions,
            "restore_version": self._restore_version,
        }
        handler = handlers.get(action)
        if handler is None:
            raise ValueError(f"unknown action: {action}")
        return handler(request, session, arguments)

    def _close_session(
        self,
        request: Mapping[str, Any],
        session: DirectSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        del self._sessions[session.session_id]
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result={"session_id": session.session_id, "closed": True},
            audit=[{"kind": "session_closed", "status": "ok", "details": {}}],
        )

    def _inspect_state(
        self,
        request: Mapping[str, Any],
        session: DirectSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not session.capabilities.allows(CapabilitySet.of("introspection.read")):
            if not session.capabilities.allows(CapabilitySet.of("dictionary.read")):
                raise ValueError("insufficient capabilities")
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result=self.snapshot(session.session_id),
            audit=[],
        )

    def _list_words(
        self,
        request: Mapping[str, Any],
        session: DirectSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        words = []
        for name in session.interpreter.dictionary.list_words():
            words.append(session.interpreter.dictionary.inspect(name))
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result={"words": words},
            audit=[],
        )

    def _inspect_word(
        self,
        request: Mapping[str, Any],
        session: DirectSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        name = str(arguments.get("name", ""))
        if not name:
            raise ValueError("name is required")
        entry = session.interpreter.dictionary.resolve(name)
        if entry is None:
            raise ValueError("unknown word")
        payload = entry.to_dict() if hasattr(entry, "to_dict") else {"name": name}
        if name in session.active_versions:
            payload["version"] = session.active_versions[name]
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result=payload,
            audit=[],
        )

    def _propose_definition(
        self,
        request: Mapping[str, Any],
        session: DirectSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        source = str(arguments.get("source", ""))
        parsed = parse_definition(tokenize(source), 0)
        word = session.interpreter.dictionary.validate_user_word(
            parsed.name,
            parsed.body_tokens,
            contract=parsed.contract,
            source=source,
            definition_index=parsed.start_index,
        )
        content_hash = WordVersion.from_user_word(
            word,
            version=1,
            dependency_versions={},
            created_sequence=0,
        ).content_hash
        candidate = DirectCandidate(
            candidate_id=session.next_candidate_id(),
            request_id=str(request["request_id"]),
            source=source,
            word=word,
            content_hash=content_hash,
            dependency_fingerprint=(),
        )
        session.candidates[candidate.candidate_id] = candidate
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result={
                "candidate_id": candidate.candidate_id,
                "content_hash": candidate.content_hash,
                "word": candidate.word.to_dict(),
                "status": candidate.status,
            },
            audit=[
                {
                    "kind": "candidate_proposed",
                    "status": "ok",
                    "details": {"candidate_id": candidate.candidate_id},
                }
            ],
        )

    def _candidate(
        self, session: DirectSession, candidate_id: str, content_hash: str
    ) -> DirectCandidate:
        candidate = session.candidates.get(candidate_id)
        if candidate is None:
            raise ValueError("unknown candidate")
        if candidate.content_hash != content_hash:
            raise ValueError("candidate hash mismatch")
        return candidate

    def _test_definition(
        self,
        request: Mapping[str, Any],
        session: DirectSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        candidate_id = str(arguments.get("candidate_id", ""))
        content_hash = str(arguments.get("content_hash", ""))
        candidate = self._candidate(session, candidate_id, content_hash)
        tests = tuple(
            ProtocolTestCase.from_dict(item) for item in arguments.get("tests", ())
        )
        budget = self._parse_budget(arguments.get("budget"))
        exec_caps = session.capabilities
        temp = _clone_session(
            session.interpreter, capabilities=exec_caps, default_budget=budget
        )
        temp.dictionary.define(candidate.word)
        results: list[dict[str, Any]] = []
        passed = 0
        for case in tests:
            outcome = temp.execute(case.source, budget=budget, capabilities=exec_caps)
            stack = _stack_values(outcome.stack)
            record = {
                "source": case.source,
                "expected_stack": list(case.expected_stack),
                "expected_status": case.expected_status,
                "expected_error_code": case.expected_error_code,
                "status": outcome.status,
                "stack": stack,
                "error": None if outcome.error is None else outcome.error.to_dict(),
                "trace": [entry.to_dict() for entry in outcome.trace],
                "steps": outcome.steps,
            }
            if case.expected_status == "ok":
                record["passed"] = stack == list(case.expected_stack)
            else:
                record["passed"] = (
                    outcome.status == "error"
                    and outcome.error is not None
                    and outcome.error.code == case.expected_error_code
                )
            if record["passed"]:
                passed += 1
            results.append(record)
        candidate = replace(
            candidate,
            status="tested" if passed == len(tests) else "rejected",
            tests_passed=passed == len(tests),
            tests_total=len(tests),
            tests_passed_count=passed,
            test_results=tuple(results),
        )
        session.candidates[candidate_id] = candidate
        if passed != len(tests):
            raise ValueError("candidate tests failed")
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result={
                "candidate_id": candidate.candidate_id,
                "status": candidate.status,
                "passed": passed,
                "total": len(tests),
                "tests": results,
            },
            audit=[
                {
                    "kind": "candidate_tested",
                    "status": "ok",
                    "details": {"candidate_id": candidate.candidate_id},
                }
            ],
        )

    def _publish_definition(
        self,
        request: Mapping[str, Any],
        session: DirectSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        candidate_id = str(arguments.get("candidate_id", ""))
        content_hash = str(arguments.get("content_hash", ""))
        candidate = self._candidate(session, candidate_id, content_hash)
        if not candidate.tests_passed and bool(
            arguments.get("require_tests_passed", True)
        ):
            raise ValueError("candidate not tested")
        published = session.interpreter.dictionary.define(candidate.word)
        session.candidates[candidate_id] = replace(candidate, status="published")
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result={"candidate_id": candidate_id, "word": published.to_dict()},
            audit=[
                {
                    "kind": "candidate_published",
                    "status": "ok",
                    "details": {"candidate_id": candidate_id},
                }
            ],
        )

    def _execute(
        self,
        request: Mapping[str, Any],
        session: DirectSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        source = str(arguments.get("source", ""))
        budget_data = arguments.get("budget")
        budget = (
            session.default_budget
            if budget_data is None
            else self._parse_budget(budget_data)
        )
        mode = str(arguments.get("mode", "normal"))
        target = (
            _clone_session(
                session.interpreter,
                capabilities=session.capabilities,
                default_budget=budget,
            )
            if mode == "test"
            else session.interpreter
        )
        result = target.execute(
            source,
            initial_stack=session.stack,
            budget=budget,
            capabilities=session.capabilities,
        )
        payload = result.to_dict()
        session.last_result = payload
        if mode != "test" and result.status == "ok":
            session.stack = list(result.stack)
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status=result.status,
            result=payload,
            error=None if result.error is None else result.error.to_dict(),
            audit=[
                {
                    "kind": "execution_completed",
                    "status": result.status,
                    "details": {"steps": result.steps},
                }
            ],
        )

    def _begin_transaction(
        self,
        request: Mapping[str, Any],
        session: DirectSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        record = session.interpreter.begin_transaction()
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result={"transaction": record.to_dict()},
            audit=[
                {
                    "kind": "transaction_started",
                    "status": "ok",
                    "details": {"transaction_id": record.transaction_id},
                }
            ],
        )

    def _commit_transaction(
        self,
        request: Mapping[str, Any],
        session: DirectSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        record = session.interpreter.commit_transaction()
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result={"transaction": record.to_dict()},
            audit=[
                {
                    "kind": "transaction_committed",
                    "status": "ok",
                    "details": {"transaction_id": record.transaction_id},
                }
            ],
        )

    def _rollback_transaction(
        self,
        request: Mapping[str, Any],
        session: DirectSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        record = session.interpreter.rollback_transaction(
            reason=str(arguments.get("reason"))
            if arguments.get("reason") is not None
            else None
        )
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result={"transaction": record.to_dict()},
            audit=[
                {
                    "kind": "transaction_rolled_back",
                    "status": "ok",
                    "details": {"transaction_id": record.transaction_id},
                }
            ],
        )

    def _save_dictionary(
        self,
        request: Mapping[str, Any],
        session: DirectSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        repository = self._repository(session, arguments)
        result = repository.save_dictionary(
            session.interpreter.dictionary, capabilities=session.capabilities
        )
        if result.status == "error":
            assert result.error is not None
            raise result.error
        session.active_versions.update(dict(result.active_versions))
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result=result.to_dict(),
            audit=[
                {
                    "kind": "dictionary_saved",
                    "status": "ok",
                    "details": {"repository_id": arguments.get("repository_id")},
                }
            ],
        )

    def _load_dictionary(
        self,
        request: Mapping[str, Any],
        session: DirectSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        repository = self._repository(session, arguments)
        result = repository.load_active_dictionary(
            session=session.interpreter, capabilities=session.capabilities
        )
        if result.status == "error":
            assert result.error is not None
            raise result.error
        session.active_versions.update(dict(result.active_versions))
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result=result.to_dict(),
            audit=[
                {
                    "kind": "dictionary_loaded",
                    "status": "ok",
                    "details": {"repository_id": arguments.get("repository_id")},
                }
            ],
        )

    def _list_versions(
        self,
        request: Mapping[str, Any],
        session: DirectSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        repository = self._repository(session, arguments)
        word_name = str(arguments.get("word_name", ""))
        versions = repository.list_versions(
            word_name, capabilities=session.capabilities
        )
        if not isinstance(versions, tuple):
            assert versions.error is not None
            raise versions.error
        active_version = repository.get_active_version(
            word_name, capabilities=session.capabilities
        )
        if hasattr(active_version, "status") and active_version.status == "error":
            assert active_version.error is not None
            raise active_version.error
        version_items = []
        for version in versions:
            record = repository.get_version(
                word_name, version, capabilities=session.capabilities
            )
            if hasattr(record, "status") and record.status == "error":
                assert record.error is not None
                raise record.error
            version_items.append(
                {
                    "version": record.version,
                    "content_hash": record.content_hash,
                    "metadata": dict(record.metadata),
                }
            )
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result={
                "word_name": word_name,
                "active_version": active_version,
                "versions": version_items,
            },
            audit=[],
        )

    def _restore_version(
        self,
        request: Mapping[str, Any],
        session: DirectSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        repository = self._repository(session, arguments)
        word_name = str(arguments.get("word_name", ""))
        version = int(arguments.get("version", 0))
        result = repository.restore_word(
            session=session.interpreter,
            name=word_name,
            version=version,
            capabilities=session.capabilities,
        )
        if result.status == "error":
            assert result.error is not None
            raise result.error
        session.active_versions.update(dict(result.active_versions))
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result=result.to_dict(),
            audit=[
                {
                    "kind": "version_restored",
                    "status": "ok",
                    "details": {"word_name": word_name, "version": version},
                }
            ],
        )

    def _repository(
        self,
        session: DirectSession,
        arguments: Mapping[str, Any],
    ) -> DictionaryRepository:
        repository_id = str(arguments.get("repository_id", "main"))
        if repository_id not in session.repository_ids:
            raise ValueError("repository not authorized")
        repository = self._repositories.get(repository_id)
        if repository is None:
            raise ValueError("unknown repository")
        return repository

    def close(self) -> None:
        self._sessions.clear()
        self._repositories.clear()

    def _parse_budget(self, data: Any) -> ExecutionBudget:
        if data is None:
            return ExecutionBudget(
                max_steps=10000, max_stack_depth=1024, max_call_depth=64
            )
        return ExecutionBudget(
            max_steps=data.get("max_steps", 10000),
            max_stack_depth=data.get("max_stack_depth", 1024),
            max_call_depth=data.get("max_call_depth", 64),
        )
