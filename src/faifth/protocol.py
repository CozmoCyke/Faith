from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, cast

from .budgets import ExecutionBudget
from .capabilities import Capability, CapabilitySet
from .dictionary import Dictionary, UserWord
from .errors import (
    CandidateHashMismatch,
    CandidateNotTested,
    CandidateStale,
    CandidateTestsFailed,
    CapabilityDenied,
    CapabilityEscalationDenied,
    FaifthError,
    InvalidArguments,
    InvalidDefinition,
    InvalidRequest,
    ProtocolLimitExceeded,
    RequestIdConflict,
    SessionAlreadyExists,
    UnknownAction,
    UnknownCandidate,
    UnknownRepository,
    UnknownSession,
    UnknownWord,
    UnsupportedProtocolVersion,
)
from .interpreter import InterpreterResult, InterpreterSession
from .persistence import DictionaryRepository, PersistenceResult
from .primitives import Primitive
from .protocol_models import (
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    ProtocolAuditEvent,
    ProtocolCandidate,
    ProtocolRequest,
    ProtocolResponse,
    ProtocolSessionState,
    ProtocolTestCase,
    TraceMode,
    canonical_json,
)
from .tokenizer import Tokenizer, tokenize
from .versioning import WordVersion

_DEFAULT_ALLOWED_CAPABILITIES = CapabilitySet.of(
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


def _coerce_capability_set(
    value: CapabilitySet | Iterable[str | Capability] | None,
) -> CapabilitySet:
    if value is None:
        return CapabilitySet.none()
    if isinstance(value, CapabilitySet):
        return value
    return CapabilitySet.of(*tuple(value))


def _clone_dictionary(dictionary: Dictionary) -> Dictionary:
    clone = Dictionary(primitives=dictionary.primitives)
    clone.restore_user_words(dictionary.snapshot_user_words())
    return clone


def _clone_interpreter_session(
    session: InterpreterSession,
    *,
    capabilities: CapabilitySet | None = None,
    default_budget: ExecutionBudget | None = None,
) -> InterpreterSession:
    clone = InterpreterSession(
        dictionary=_clone_dictionary(session.dictionary),
        capabilities=capabilities if capabilities is not None else session.capabilities,
        default_budget=(
            default_budget if default_budget is not None else session.default_budget
        ),
    )
    return clone


def _stack_to_python(stack: Sequence[Any]) -> list[Any]:
    return [value.value for value in stack]


@dataclass(slots=True)
class _TransactionSnapshot:
    stack: list[Any]
    active_versions: dict[str, int]
    candidates: dict[str, ProtocolCandidate]
    candidate_sequence: int


def _trace_mode_value(value: Any) -> TraceMode:
    if value is None:
        return "none"
    mode = str(value)
    if mode not in {"none", "summary", "full"}:
        raise InvalidArguments(
            "Invalid trace_mode",
            context={"trace_mode": mode},
        )
    return cast(TraceMode, mode)


class FaifthAgentProtocol:
    def __init__(
        self,
        *,
        allowed_capabilities: CapabilitySet | None = None,
        default_budget: ExecutionBudget | None = None,
        allow_inline_definitions: bool = False,
        max_request_depth: int = 16,
        max_source_length: int = 8_192,
        max_tests_per_request: int = 32,
        max_candidates_per_session: int = 64,
        max_trace_entries: int = 2_000,
    ) -> None:
        self.allowed_capabilities = (
            allowed_capabilities
            if allowed_capabilities is not None
            else _DEFAULT_ALLOWED_CAPABILITIES
        )
        self.default_budget = (
            default_budget if default_budget is not None else ExecutionBudget()
        )
        self.allow_inline_definitions = allow_inline_definitions
        self.max_request_depth = max_request_depth
        self.max_source_length = max_source_length
        self.max_tests_per_request = max_tests_per_request
        self.max_candidates_per_session = max_candidates_per_session
        self.max_trace_entries = max_trace_entries
        self._tokenizer = Tokenizer()
        self._sessions: dict[str, ProtocolSessionState] = {}
        self._repositories: dict[str, DictionaryRepository] = {}
        self._request_cache: dict[str, tuple[str, ProtocolResponse]] = {}
        self._sequence = 0

    def register_repository(
        self, repository_id: str, repository: DictionaryRepository
    ) -> None:
        if not repository_id:
            raise InvalidArguments(
                "repository_id cannot be empty",
                context={"repository_id": repository_id},
            )
        self._repositories[repository_id] = repository

    def handle(
        self, request: ProtocolRequest | Mapping[str, Any] | str
    ) -> ProtocolResponse:
        if isinstance(request, ProtocolRequest):
            return self._handle_request(request)
        if isinstance(request, str):
            try:
                parsed = json.loads(request)
                return self._handle_request(
                    ProtocolRequest.from_dict(
                        parsed,
                        max_depth=self.max_request_depth,
                    )
                )
            except ValueError:
                return self._failure_response_from_raw(
                    error=InvalidRequest("Invalid JSON payload"),
                    request_id="",
                    session_id="",
                )
            except FaifthError as error:
                return self._failure_response_from_raw(
                    error=error,
                    request_id="",
                    session_id="",
                )
        try:
            parsed = ProtocolRequest.from_dict(
                request,
                max_depth=self.max_request_depth,
            )
        except FaifthError as error:
            return self._failure_response_from_raw(
                error=error,
                request_id=str(request.get("request_id", "")),
                session_id=str(request.get("session_id", "")),
                protocol=str(request.get("protocol", PROTOCOL_NAME)),
                version=str(request.get("version", PROTOCOL_VERSION)),
            )
        return self._handle_request(parsed)

    def handle_dict(self, request: Mapping[str, Any]) -> ProtocolResponse:
        return self.handle(request)

    def handle_json(self, request_json: str) -> ProtocolResponse:
        return self.handle(request_json)

    def _handle_request(self, request: ProtocolRequest) -> ProtocolResponse:
        canonical_request = request.to_json()
        try:
            if request.protocol != PROTOCOL_NAME:
                raise UnsupportedProtocolVersion(
                    "Unsupported protocol identifier",
                    context={"protocol": request.protocol},
                )
            if request.version != PROTOCOL_VERSION:
                raise UnsupportedProtocolVersion(
                    "Unsupported protocol version",
                    context={"expected": PROTOCOL_VERSION, "observed": request.version},
                )

            canonical_request = request.to_json()
            cached = self._request_cache.get(request.request_id)
            if cached is not None:
                cached_request, cached_response = cached
                if cached_request != canonical_request:
                    raise RequestIdConflict(
                        "Request id reused with different content",
                        context={"request_id": request.request_id},
                    )
                return cached_response

            response = self._dispatch(request)
        except FaifthError as error:
            response = ProtocolResponse.failure(request=request, error=error, audit=())
        self._request_cache[request.request_id] = (canonical_request, response)
        return response

    def _dispatch(self, request: ProtocolRequest) -> ProtocolResponse:
        handlers = {
            "create_session": self._create_session,
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
        handler = handlers.get(request.action)
        if handler is None:  # pragma: no cover - guarded by parser
            raise UnknownAction(
                "Unknown action",
                context={"action": request.action},
            )
        return handler(request)

    def _create_session(self, request: ProtocolRequest) -> ProtocolResponse:
        if request.session_id in self._sessions:
            raise SessionAlreadyExists(
                "Session already exists",
                context={"session_id": request.session_id},
            )
        arguments = request.arguments
        capabilities = _coerce_capability_set(arguments.get("capabilities"))
        if not capabilities.issubset(self.allowed_capabilities):
            raise CapabilityEscalationDenied(
                "Requested capabilities exceed the host policy",
                context={
                    "requested": list(capabilities.to_tuple()),
                    "allowed": list(self.allowed_capabilities.to_tuple()),
                },
            )
        default_budget = self._parse_budget(arguments.get("default_budget"))
        repository_ids = tuple(
            str(item) for item in arguments.get("repository_ids", ())
        )
        for repository_id in repository_ids:
            if repository_id not in self._repositories:
                raise UnknownRepository(
                    "Unknown repository",
                    context={"repository_id": repository_id},
                )

        interpreter = InterpreterSession(
            capabilities=capabilities,
            default_budget=default_budget,
        )
        session = ProtocolSessionState(
            session_id=request.session_id,
            interpreter=interpreter,
            capabilities=capabilities,
            default_budget=default_budget,
            stack=[],
            repository_ids=repository_ids,
        )
        self._sessions[request.session_id] = session
        audit = (
            ProtocolAuditEvent(
                "session_created",
                "ok",
                details={
                    "session_id": request.session_id,
                    "capabilities": list(capabilities.to_tuple()),
                },
            ),
        )
        session.last_audit = audit
        return ProtocolResponse.success(
            request=request,
            result={
                "session_id": request.session_id,
                "capabilities": capabilities.to_dict(),
                "default_budget": default_budget.to_dict(),
                "repository_ids": list(repository_ids),
                "candidate_count": 0,
            },
            audit=audit,
        )

    def _close_session(self, request: ProtocolRequest) -> ProtocolResponse:
        session = self._require_session(request.session_id)
        del self._sessions[request.session_id]
        audit = (
            ProtocolAuditEvent(
                "session_closed",
                "ok",
                details={"session_id": request.session_id},
            ),
        )
        session.last_audit = audit
        return ProtocolResponse.success(
            request=request,
            result={"session_id": request.session_id, "closed": True},
            audit=audit,
        )

    def _inspect_state(self, request: ProtocolRequest) -> ProtocolResponse:
        session = self._require_session(request.session_id)
        self._require_capabilities(session, CapabilitySet.of("introspection.read"))
        summary = self._session_summary(session)
        return ProtocolResponse.success(request=request, result=summary, audit=())

    def _list_words(self, request: ProtocolRequest) -> ProtocolResponse:
        session = self._require_session(request.session_id)
        self._require_any_capability(
            session, CapabilitySet.of("dictionary.read", "introspection.read")
        )
        kind = str(request.arguments.get("kind", "all"))
        if kind not in {"all", "primitive", "user"}:
            raise InvalidArguments(
                "Invalid kind filter",
                context={"kind": kind},
            )
        words: list[dict[str, Any]] = []
        for name in session.interpreter.dictionary.list_words():
            entry = session.interpreter.dictionary.resolve(name)
            if entry is None:
                continue
            if kind == "primitive" and not isinstance(entry, Primitive):
                continue
            if kind == "user" and isinstance(entry, Primitive):
                continue
            words.append(self._summarize_word(session, name, entry))
        return ProtocolResponse.success(
            request=request,
            result={"words": words},
            audit=(),
        )

    def _inspect_word(self, request: ProtocolRequest) -> ProtocolResponse:
        session = self._require_session(request.session_id)
        self._require_capabilities(session, CapabilitySet.of("introspection.read"))
        name = self._require_string_argument(request, "name")
        entry = session.interpreter.dictionary.resolve(name)
        if entry is None:
            raise UnknownWord(
                "Unknown word",
                index=-1,
                metadata={"session_id": request.session_id},
            )
        result = self._summarize_word(session, name, entry, include_body=True)
        if isinstance(entry, UserWord):
            result["available_versions"] = self._available_versions(session, name)
        return ProtocolResponse.success(request=request, result=result, audit=())

    def _propose_definition(self, request: ProtocolRequest) -> ProtocolResponse:
        session = self._require_session(request.session_id)
        self._require_capabilities(session, CapabilitySet.of("dictionary.read"))
        source = self._require_string_argument(request, "source")
        if len(source) > self.max_source_length:
            raise ProtocolLimitExceeded(
                "Definition source exceeds the maximum length",
                context={"limit": self.max_source_length},
            )
        parsed = self._parse_definition_source(source)
        word = session.interpreter.dictionary.validate_user_word(
            parsed.name,
            parsed.body_tokens,
            contract=parsed.contract,
            source=source,
            definition_index=parsed.start_index,
        )
        dependency_fingerprint = self._dependency_fingerprint(
            session,
            word.dependencies,
        )
        content_hash = self._candidate_hash(
            word,
            dependency_fingerprint=dependency_fingerprint,
        )
        candidate = ProtocolCandidate(
            candidate_id=session.next_candidate_id(),
            request_id=request.request_id,
            sequence=session.next_sequence(),
            source=source,
            word=word,
            content_hash=content_hash,
            dependency_fingerprint=dependency_fingerprint,
            status="proposed",
        )
        self._store_candidate(session, candidate)
        audit = (
            ProtocolAuditEvent(
                "candidate_proposed",
                "ok",
                details={
                    "session_id": request.session_id,
                    "candidate_id": candidate.candidate_id,
                    "word": word.name,
                },
            ),
        )
        session.last_audit = audit
        return ProtocolResponse.success(
            request=request,
            result={
                "candidate_id": candidate.candidate_id,
                "content_hash": candidate.content_hash,
                "word": self._summarize_user_word(word),
                "status": candidate.status,
            },
            audit=audit,
        )

    def _test_definition(self, request: ProtocolRequest) -> ProtocolResponse:
        session = self._require_session(request.session_id)
        self._require_capabilities(session, CapabilitySet.of("dictionary.read"))
        candidate = self._candidate_for_request(session, request)
        tests = self._parse_tests(request.arguments.get("tests", ()))
        if len(tests) > self.max_tests_per_request:
            raise ProtocolLimitExceeded(
                "Too many tests",
                context={"limit": self.max_tests_per_request},
            )
        budget_data = request.arguments.get("budget")
        budget = (
            session.default_budget
            if budget_data is None
            else self._parse_budget(budget_data)
        )
        exec_caps = self._request_capabilities(session, request)
        temp_session = _clone_interpreter_session(
            session.interpreter,
            capabilities=exec_caps,
            default_budget=budget,
        )
        temp_session.dictionary.define(candidate.word)

        results: list[dict[str, Any]] = []
        passed = 0
        for case in tests:
            outcome = temp_session.execute(
                case.source,
                budget=budget,
                capabilities=exec_caps,
            )
            record = self._record_test_case(case, outcome)
            results.append(record)
            if record["passed"]:
                passed += 1

        all_passed = passed == len(tests)
        updated = replace(
            candidate,
            status="tested" if all_passed else "rejected",
            tests_passed=all_passed,
            tests_total=len(tests),
            tests_passed_count=passed,
            test_results=tuple(results),
            last_error=(
                None
                if all_passed
                else CandidateTestsFailed("Candidate tests failed")
            ),
        )
        self._store_candidate(session, updated)
        audit = (
            ProtocolAuditEvent(
                "candidate_tested",
                "ok" if all_passed else "error",
                details={
                    "session_id": request.session_id,
                    "candidate_id": candidate.candidate_id,
                    "passed": passed,
                    "total": len(tests),
                },
            ),
        )
        session.last_audit = audit
        if not all_passed:
            raise CandidateTestsFailed(
                "Candidate tests failed",
                metadata={"results": results},
                context={
                    "candidate_id": candidate.candidate_id,
                    "passed": passed,
                    "total": len(tests),
                },
            )
        return ProtocolResponse.success(
            request=request,
            result={
                "candidate_id": candidate.candidate_id,
                "status": updated.status,
                "passed": passed,
                "total": len(tests),
                "tests": results,
            },
            audit=audit,
        )

    def _publish_definition(self, request: ProtocolRequest) -> ProtocolResponse:
        session = self._require_session(request.session_id)
        self._require_capabilities(session, CapabilitySet.of("dictionary.define"))
        candidate = self._candidate_for_request(session, request)
        require_tests_passed = bool(request.arguments.get("require_tests_passed", True))
        if require_tests_passed and not candidate.tests_passed:
            raise CandidateNotTested(
                "Candidate has not passed tests",
                context={"candidate_id": candidate.candidate_id},
            )
        if (
            candidate.tests_total
            and candidate.tests_passed_count < candidate.tests_total
        ):
            raise CandidateTestsFailed(
                "Candidate tests failed",
                context={"candidate_id": candidate.candidate_id},
            )
        self._ensure_candidate_fresh(session, candidate)
        try:
            published = session.interpreter.dictionary.define(candidate.word)
        except FaifthError as error:
            raise CandidateStale(
                "Candidate is stale",
                context={
                    "candidate_id": candidate.candidate_id,
                    "word": candidate.word.name,
                },
            ) from error
        updated = replace(
            candidate,
            status="published",
            published_version=None,
            last_error=None,
        )
        self._store_candidate(session, updated)
        audit = (
            ProtocolAuditEvent(
                "candidate_published",
                "ok",
                details={
                    "session_id": request.session_id,
                    "candidate_id": candidate.candidate_id,
                    "word": published.name,
                },
            ),
        )
        session.last_audit = audit
        return ProtocolResponse.success(
            request=request,
            result={
                "candidate_id": candidate.candidate_id,
                "status": updated.status,
                "word": self._summarize_user_word(published),
            },
            audit=audit,
        )

    def _execute(self, request: ProtocolRequest) -> ProtocolResponse:
        session = self._require_session(request.session_id)
        source = self._require_string_argument(request, "source")
        if len(source) > self.max_source_length:
            raise ProtocolLimitExceeded(
                "Execution source exceeds the maximum length",
                context={"limit": self.max_source_length},
            )
        mode = str(request.arguments.get("mode", "normal"))
        if mode not in {"normal", "test"}:
            raise InvalidArguments(
                "Invalid execution mode",
                context={"mode": mode},
            )
        trace_mode = _trace_mode_value(request.arguments.get("trace_mode", "summary"))
        if (
            not self.allow_inline_definitions
            and self._contains_inline_definition(source)
        ):
            raise InvalidArguments(
                "Inline definitions are disabled",
                context={"allow_inline_definitions": self.allow_inline_definitions},
            )
        budget_data = request.arguments.get("budget")
        budget = (
            session.default_budget
            if budget_data is None
            else self._parse_budget(budget_data)
        )
        exec_caps = self._request_capabilities(session, request)
        target_session = (
            _clone_interpreter_session(
                session.interpreter,
                capabilities=exec_caps,
                default_budget=budget,
            )
            if mode == "test"
            else session.interpreter
        )
        result = target_session.execute(
            source,
            initial_stack=session.stack,
            budget=budget,
            capabilities=exec_caps,
        )
        self._update_session_after_execution(session, result, request.request_id)
        payload = self._execution_payload(result, mode=mode, trace_mode=trace_mode)
        audit = (
            ProtocolAuditEvent(
                "execution_completed" if result.status == "ok" else "execution_failed",
                result.status,
                details={
                    "session_id": request.session_id,
                    "request_id": request.request_id,
                    "steps": result.steps,
                },
            ),
        )
        session.last_audit = audit
        if result.status == "ok":
            return ProtocolResponse.success(
                request=request, result=payload, audit=audit
            )
        assert result.error is not None
        return ProtocolResponse.failure(
            request=request, error=result.error, audit=audit
        )

    def _begin_transaction(self, request: ProtocolRequest) -> ProtocolResponse:
        session = self._require_session(request.session_id)
        self._require_capabilities(session, CapabilitySet.of("transaction.manage"))
        record = session.interpreter.begin_transaction()
        session.transaction_snapshot = _TransactionSnapshot(
            stack=list(session.stack),
            active_versions=dict(session.active_versions),
            candidates=dict(session.candidates),
            candidate_sequence=session.candidate_sequence,
        )
        audit = (
            ProtocolAuditEvent(
                "transaction_started",
                "ok",
                details={
                    "session_id": request.session_id,
                    "transaction_id": record.transaction_id,
                },
            ),
        )
        session.last_audit = audit
        return ProtocolResponse.success(
            request=request,
            result={"transaction": record.to_dict()},
            audit=audit,
        )

    def _commit_transaction(self, request: ProtocolRequest) -> ProtocolResponse:
        session = self._require_session(request.session_id)
        self._require_capabilities(session, CapabilitySet.of("transaction.manage"))
        record = session.interpreter.commit_transaction()
        session.transaction_snapshot = None
        audit = (
            ProtocolAuditEvent(
                "transaction_committed",
                "ok",
                details={
                    "session_id": request.session_id,
                    "transaction_id": record.transaction_id,
                },
            ),
        )
        session.last_audit = audit
        return ProtocolResponse.success(
            request=request,
            result={"transaction": record.to_dict()},
            audit=audit,
        )

    def _rollback_transaction(self, request: ProtocolRequest) -> ProtocolResponse:
        session = self._require_session(request.session_id)
        self._require_capabilities(session, CapabilitySet.of("transaction.manage"))
        reason = request.arguments.get("reason")
        record = session.interpreter.rollback_transaction(
            reason=None if reason is None else str(reason)
        )
        self._restore_transaction_snapshot(session)
        audit = (
            ProtocolAuditEvent(
                "transaction_rolled_back",
                "ok",
                details={
                    "session_id": request.session_id,
                    "transaction_id": record.transaction_id,
                },
            ),
        )
        session.last_audit = audit
        return ProtocolResponse.success(
            request=request,
            result={"transaction": record.to_dict()},
            audit=audit,
        )

    def _save_dictionary(self, request: ProtocolRequest) -> ProtocolResponse:
        session = self._require_session(request.session_id)
        repository = self._repository_for_session(session, request)
        self._require_capabilities(session, CapabilitySet.of("storage.write"))
        result = repository.save_dictionary(
            session.interpreter.dictionary,
            capabilities=session.capabilities,
        )
        self._raise_if_persistence_error(result)
        session.active_versions.update(dict(result.active_versions))
        audit = (
            ProtocolAuditEvent(
                "dictionary_saved",
                "ok",
                details={
                    "session_id": request.session_id,
                    "repository_id": request.arguments.get("repository_id"),
                },
            ),
        )
        session.last_audit = audit
        return ProtocolResponse.success(
            request=request,
            result=result.to_dict(),
            audit=audit,
        )

    def _load_dictionary(self, request: ProtocolRequest) -> ProtocolResponse:
        session = self._require_session(request.session_id)
        repository = self._repository_for_session(session, request)
        self._require_capabilities(
            session, CapabilitySet.of("storage.read", "dictionary.restore")
        )
        result = repository.load_active_dictionary(
            session=session.interpreter,
            capabilities=session.capabilities,
        )
        self._raise_if_persistence_error(result)
        session.active_versions.update(dict(result.active_versions))
        audit = (
            ProtocolAuditEvent(
                "dictionary_loaded",
                "ok",
                details={
                    "session_id": request.session_id,
                    "repository_id": request.arguments.get("repository_id"),
                },
            ),
        )
        session.last_audit = audit
        return ProtocolResponse.success(
            request=request,
            result=result.to_dict(),
            audit=audit,
        )

    def _list_versions(self, request: ProtocolRequest) -> ProtocolResponse:
        session = self._require_session(request.session_id)
        repository = self._repository_for_session(session, request)
        self._require_capabilities(session, CapabilitySet.of("storage.read"))
        word_name = self._require_string_argument(request, "word_name")
        versions = repository.list_versions(
            word_name,
            capabilities=session.capabilities,
        )
        if not isinstance(versions, tuple):
            self._raise_if_persistence_error(versions)
        versions = cast(tuple[int, ...], versions)
        active_version = repository.get_active_version(
            word_name,
            capabilities=session.capabilities,
        )
        if isinstance(active_version, PersistenceResult):
            self._raise_if_persistence_error(active_version)
        active_version = cast(int | None, active_version)
        version_items = []
        for version in versions:
            record = repository.get_version(
                word_name,
                version,
                capabilities=session.capabilities,
            )
            if isinstance(record, PersistenceResult):
                self._raise_if_persistence_error(record)
            record = cast(WordVersion, record)
            version_items.append(
                {
                    "version": record.version,
                    "content_hash": record.content_hash,
                    "metadata": dict(record.metadata),
                }
            )
        return ProtocolResponse.success(
            request=request,
            result={
                "word_name": word_name,
                "active_version": active_version,
                "versions": version_items,
            },
            audit=(),
        )

    def _restore_version(self, request: ProtocolRequest) -> ProtocolResponse:
        session = self._require_session(request.session_id)
        repository = self._repository_for_session(session, request)
        self._require_capabilities(
            session,
            CapabilitySet.of("storage.read", "storage.write", "dictionary.restore"),
        )
        word_name = self._require_string_argument(request, "word_name")
        version = int(request.arguments.get("version", 0))
        if version <= 0:
            raise InvalidArguments(
                "version must be a positive integer",
                context={"version": version},
            )
        result = repository.restore_word(
            session=session.interpreter,
            name=word_name,
            version=version,
            capabilities=session.capabilities,
        )
        self._raise_if_persistence_error(result)
        session.active_versions.update(dict(result.active_versions))
        audit = (
            ProtocolAuditEvent(
                "version_restored",
                "ok",
                details={
                    "session_id": request.session_id,
                    "repository_id": request.arguments.get("repository_id"),
                    "word_name": word_name,
                    "version": version,
                },
            ),
        )
        session.last_audit = audit
        return ProtocolResponse.success(
            request=request,
            result=result.to_dict(),
            audit=audit,
        )

    def _require_session(self, session_id: str) -> ProtocolSessionState:
        session = self._sessions.get(session_id)
        if session is None:
            raise UnknownSession(
                "Unknown session",
                context={"session_id": session_id},
            )
        return session

    def _require_capabilities(
        self,
        session: ProtocolSessionState,
        required: CapabilitySet,
    ) -> None:
        if not session.capabilities.allows(required):
            raise CapabilityDenied(
                "Session lacks required capabilities",
                context={
                    "required": list(required.to_tuple()),
                    "granted": list(session.capabilities.to_tuple()),
                },
            )

    def _require_any_capability(
        self, session: ProtocolSessionState, required: CapabilitySet
    ) -> None:
        if not any(
            session.capabilities.allows(CapabilitySet.of(name))
            for name in required.to_tuple()
        ):
            raise CapabilityDenied(
                "Session lacks required capabilities",
                context={
                    "required": list(required.to_tuple()),
                    "granted": list(session.capabilities.to_tuple()),
                },
            )

    def _request_capabilities(
        self, session: ProtocolSessionState, request: ProtocolRequest
    ) -> CapabilitySet:
        requested = _coerce_capability_set(request.arguments.get("capabilities"))
        if not requested:
            return session.capabilities
        if not requested.issubset(session.capabilities):
            raise CapabilityEscalationDenied(
                "Request attempted to add capabilities",
                context={
                    "requested": list(requested.to_tuple()),
                    "session": list(session.capabilities.to_tuple()),
                },
            )
        return requested

    def _repository_for_session(
        self, session: ProtocolSessionState, request: ProtocolRequest
    ) -> DictionaryRepository:
        repository_id = self._require_string_argument(request, "repository_id")
        if repository_id not in session.repository_ids:
            raise UnknownRepository(
                "Repository is not authorized for this session",
                context={
                    "repository_id": repository_id,
                    "session_id": session.session_id,
                },
            )
        repository = self._repositories.get(repository_id)
        if repository is None:
            raise UnknownRepository(
                "Unknown repository",
                context={"repository_id": repository_id},
            )
        return repository

    def _require_string_argument(self, request: ProtocolRequest, name: str) -> str:
        value = request.arguments.get(name)
        if not isinstance(value, str) or not value:
            raise InvalidArguments(
                f"{name} must be a non-empty string",
                context={"argument": name, "received": type(value).__name__},
            )
        return value

    def _parse_budget(self, data: Any) -> ExecutionBudget:
        if data is None:
            return self.default_budget
        if not isinstance(data, Mapping):
            raise InvalidArguments(
                "budget must be a mapping",
                context={"received": type(data).__name__},
            )
        return ExecutionBudget(
            max_steps=data.get("max_steps", self.default_budget.max_steps),
            max_stack_depth=data.get(
                "max_stack_depth",
                self.default_budget.max_stack_depth,
            ),
            max_call_depth=data.get(
                "max_call_depth",
                self.default_budget.max_call_depth,
            ),
        )

    def _parse_definition_source(self, source: str) -> Any:
        tokens = tokenize(source)
        if not tokens:
            raise InvalidDefinition("Definition source cannot be empty")
        from .definitions import parse_definition

        parsed = parse_definition(tokens, 0)
        if parsed.end_index != len(tokens):
            raise InvalidArguments(
                "Definition source must contain a single definition",
                context={"remaining_tokens": len(tokens) - parsed.end_index},
            )
        return parsed

    def _parse_tests(self, data: Any) -> tuple[ProtocolTestCase, ...]:
        if data is None:
            return ()
        if not isinstance(data, Sequence) or isinstance(
            data, str | bytes | bytearray
        ):
            raise InvalidArguments(
                "tests must be a sequence",
                context={"received": type(data).__name__},
            )
        return tuple(ProtocolTestCase.from_dict(item) for item in data)

    def _record_test_case(
        self, case: ProtocolTestCase, outcome: InterpreterResult
    ) -> dict[str, Any]:
        stack_values = _stack_to_python(outcome.stack)
        passed = outcome.status == case.expected_status
        if passed and case.expected_status == "ok":
            passed = stack_values == list(case.expected_stack)
        if passed and case.expected_status == "error":
            passed = (
                outcome.error is not None
                and outcome.error.code == case.expected_error_code
            )
        return {
            "source": case.source,
            "expected_stack": list(case.expected_stack),
            "expected_status": case.expected_status,
            "expected_error_code": case.expected_error_code,
            "status": outcome.status,
            "stack": stack_values,
            "error": None if outcome.error is None else outcome.error.to_dict(),
            "trace": [entry.to_dict() for entry in outcome.trace],
            "steps": outcome.steps,
            "passed": passed,
        }

    def _candidate_for_request(
        self, session: ProtocolSessionState, request: ProtocolRequest
    ) -> ProtocolCandidate:
        candidate_id = request.arguments.get("candidate_id")
        content_hash = request.arguments.get("content_hash")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise InvalidArguments(
                "candidate_id must be a non-empty string",
                context={"received": type(candidate_id).__name__},
            )
        if not isinstance(content_hash, str) or not content_hash:
            raise InvalidArguments(
                "content_hash must be a non-empty string",
                context={"received": type(content_hash).__name__},
            )
        candidate = session.candidates.get(candidate_id)
        if candidate is None:
            raise UnknownCandidate(
                "Unknown candidate",
                context={"candidate_id": candidate_id},
            )
        if candidate.content_hash != content_hash:
            raise CandidateHashMismatch(
                "Candidate hash mismatch",
                context={
                    "candidate_id": candidate_id,
                    "expected": candidate.content_hash,
                    "observed": content_hash,
                },
            )
        return candidate

    def _store_candidate(
        self, session: ProtocolSessionState, candidate: ProtocolCandidate
    ) -> None:
        if (
            len(session.candidates) >= self.max_candidates_per_session
            and candidate.candidate_id not in session.candidates
        ):
            raise ProtocolLimitExceeded(
                "Too many candidates in session",
                context={"limit": self.max_candidates_per_session},
            )
        session.candidates[candidate.candidate_id] = candidate

    def _dependency_fingerprint(
        self, session: ProtocolSessionState, dependencies: Sequence[str]
    ) -> tuple[tuple[str, str], ...]:
        fingerprints: list[tuple[str, str]] = []
        for dependency in dependencies:
            resolved = session.interpreter.dictionary.inspect(dependency)
            fingerprints.append((dependency, canonical_json(resolved)))
        return tuple(sorted(fingerprints))

    def _candidate_hash(
        self,
        word: UserWord,
        *,
        dependency_fingerprint: tuple[tuple[str, str], ...],
    ) -> str:
        from .versioning import WordVersion

        dependency_versions = {
            name: 0 for name, _ in dependency_fingerprint
        }
        candidate = WordVersion.from_user_word(
            word,
            version=1,
            dependency_versions=dependency_versions,
            created_sequence=0,
        )
        return candidate.content_hash

    def _summarize_word(
        self,
        session: ProtocolSessionState,
        name: str,
        entry: Primitive | UserWord,
        *,
        include_body: bool = False,
    ) -> dict[str, Any]:
        if isinstance(entry, Primitive):
            summary = entry.to_dict()
            summary["version"] = None
            summary["origin"] = "primitive"
            summary["persistent"] = False
            return summary
        summary = {
            "kind": "user",
            "name": entry.name,
            "contract": None if entry.contract is None else entry.contract.to_dict(),
            "dependencies": list(entry.dependencies),
            "primitive_dependencies": list(entry.primitive_dependencies),
            "required_capabilities": entry.required_capabilities.to_dict(),
            "version": session.active_versions.get(name),
            "origin": "storage" if name in session.active_versions else "session",
            "persistent": name in session.active_versions,
        }
        if include_body:
            summary["body"] = list(entry.body)
        return summary

    def _summarize_user_word(self, word: UserWord) -> dict[str, Any]:
        return {
            "kind": "user",
            "name": word.name,
            "body": list(word.body),
            "dependencies": list(word.dependencies),
            "primitive_dependencies": list(word.primitive_dependencies),
            "required_capabilities": word.required_capabilities.to_dict(),
            "contract": None if word.contract is None else word.contract.to_dict(),
            "source": word.source,
            "definition_index": word.definition_index,
            "metadata": dict(word.metadata),
        }

    def _available_versions(
        self, session: ProtocolSessionState, word_name: str
    ) -> list[dict[str, Any]]:
        versions: list[dict[str, Any]] = []
        for repository_id in session.repository_ids:
            repository = self._repositories.get(repository_id)
            if repository is None:
                continue
            version_list = repository.list_versions(
                word_name,
                capabilities=session.capabilities,
            )
            if isinstance(version_list, PersistenceResult):
                continue
            version_list = cast(tuple[int, ...], version_list)
            for version in version_list:
                record = repository.get_version(
                    word_name,
                    version,
                    capabilities=session.capabilities,
                )
                if isinstance(record, PersistenceResult):
                    continue
                record = cast(WordVersion, record)
                versions.append(
                    {
                        "repository_id": repository_id,
                        "version": record.version,
                        "content_hash": record.content_hash,
                    }
                )
        versions.sort(key=lambda item: (item["repository_id"], item["version"]))
        return versions

    def _ensure_candidate_fresh(
        self, session: ProtocolSessionState, candidate: ProtocolCandidate
    ) -> None:
        current = session.interpreter.dictionary.resolve(candidate.word.name)
        if current is not None and current != candidate.word:
            raise CandidateStale(
                "Candidate name is no longer available",
                context={
                    "candidate_id": candidate.candidate_id,
                    "word": candidate.word.name,
                },
            )
        fingerprint = self._dependency_fingerprint(
            session,
            candidate.word.dependencies,
        )
        if fingerprint != candidate.dependency_fingerprint:
            raise CandidateStale(
                "Candidate dependencies changed",
                context={
                    "candidate_id": candidate.candidate_id,
                    "word": candidate.word.name,
                },
            )

    def _contains_inline_definition(self, source: str) -> bool:
        tokens = self._tokenizer.tokenize(source)
        return any(token.text == ":" for token in tokens)

    def _execution_payload(
        self,
        result: InterpreterResult,
        *,
        mode: str,
        trace_mode: TraceMode,
    ) -> dict[str, Any]:
        payload = result.to_dict()
        payload["mode"] = mode
        payload["trace_mode"] = trace_mode
        if trace_mode == "none":
            payload["trace"] = []
            payload["trace_truncated"] = False
            return payload
        trace = payload.get("trace", [])
        if trace_mode == "summary":
            payload["trace"] = trace[: min(len(trace), self.max_trace_entries)]
            payload["trace_truncated"] = len(trace) > self.max_trace_entries
            return payload
        payload["trace_truncated"] = len(trace) > self.max_trace_entries
        if payload["trace_truncated"]:
            payload["trace"] = trace[: self.max_trace_entries]
        return payload

    def _raise_if_persistence_error(self, result: Any) -> None:
        if isinstance(result, PersistenceResult) and result.status == "error":
            assert result.error is not None
            raise result.error

    def _failure_response_from_raw(
        self,
        *,
        error: FaifthError,
        request_id: str,
        session_id: str,
        protocol: str = PROTOCOL_NAME,
        version: str = PROTOCOL_VERSION,
    ) -> ProtocolResponse:
        request = ProtocolRequest(
            protocol=protocol,
            version=version,
            request_id=request_id,
            session_id=session_id,
            action="inspect_state",
            arguments={},
        )
        return ProtocolResponse.failure(request=request, error=error, audit=())

    def _update_session_after_execution(
        self,
        session: ProtocolSessionState,
        result: InterpreterResult,
        request_id: str,
    ) -> None:
        session.last_result = result
        if result.status == "ok":
            session.stack = list(result.stack)
        elif result.transaction_rolled_back:
            self._restore_transaction_snapshot(session)
        session.last_audit = (
            ProtocolAuditEvent(
                "execution_completed" if result.status == "ok" else "execution_failed",
                result.status,
                details={"request_id": request_id, "steps": result.steps},
            ),
        )

    def _session_summary(self, session: ProtocolSessionState) -> dict[str, Any]:
        last_result = (
            None
            if session.last_result is None
            else self._execution_payload(
                session.last_result,
                mode="normal",
                trace_mode="summary",
            )
        )
        return {
            "session_id": session.session_id,
            "capabilities": session.capabilities.to_dict(),
            "default_budget": session.default_budget.to_dict(),
            "user_word_count": len(session.interpreter.dictionary.list_user_words()),
            "stack": _stack_to_python(session.stack),
            "stack_depth": len(session.stack),
            "transaction_status": session.interpreter.transaction_status,
            "transaction_active": session.interpreter.transaction_status == "active",
            "repositories": list(session.repository_ids),
            "candidate_count": len(session.candidates),
            "sequence": session.sequence,
            "last_result": last_result,
            "last_audit": [event.to_dict() for event in session.last_audit],
            "active_versions": dict(sorted(session.active_versions.items())),
        }

    def _restore_transaction_snapshot(self, session: ProtocolSessionState) -> None:
        snapshot = session.transaction_snapshot
        if snapshot is None:
            return
        session.stack = list(snapshot.stack)
        session.active_versions = dict(snapshot.active_versions)
        session.candidates = dict(snapshot.candidates)
        session.candidate_sequence = snapshot.candidate_sequence
        session.transaction_snapshot = None


__all__ = ["FaifthAgentProtocol"]
