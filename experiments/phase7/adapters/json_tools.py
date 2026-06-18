from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .common import make_error, make_response, parse_definition_source, tokenize_source

PROTOCOL_NAME = "json-tools"
PROTOCOL_VERSION = "0.1"

_PRIMITIVES = {"+", "*", "dup", "drop", "swap", "over", "=", "depth"}


def _is_int(text: str) -> bool:
    if text.startswith("-"):
        return text[1:].isdigit()
    return text.isdigit()


def _is_bool(text: str) -> bool:
    return text in {"true", "false"}


def _literal_value(text: str) -> Any:
    if _is_int(text):
        return int(text)
    if _is_bool(text):
        return text == "true"
    raise ValueError(text)


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _stack_snapshot(stack: list[Any]) -> list[dict[str, Any]]:
    result = []
    for item in stack:
        if isinstance(item, bool):
            result.append({"type": "bool", "value": item})
        elif isinstance(item, int):
            result.append({"type": "int", "value": item})
        else:
            result.append({"type": "str", "value": item})
    return result


def _stack_values(stack: list[Any]) -> list[Any]:
    values: list[Any] = []
    for item in stack:
        if isinstance(item, Mapping):
            values.append(item.get("value"))
        else:
            values.append(item)
    return values


@dataclass(slots=True)
class JsonCandidate:
    candidate_id: str
    request_id: str
    source: str
    name: str
    body_tokens: tuple[str, ...]
    content_hash: str
    status: str = "proposed"
    tests_passed: bool = False
    tests_total: int = 0
    tests_passed_count: int = 0
    test_results: tuple[dict[str, Any], ...] = ()


@dataclass(slots=True)
class JsonSession:
    session_id: str
    capabilities: list[str]
    default_budget: dict[str, int]
    repository_ids: tuple[str, ...]
    stack: list[Any] = field(default_factory=list)
    words: dict[str, list[str]] = field(default_factory=dict)
    active_versions: dict[str, int] = field(default_factory=dict)
    candidates: dict[str, JsonCandidate] = field(default_factory=dict)
    transaction_snapshot: dict[str, Any] | None = None
    transaction_active: bool = False
    candidate_sequence: int = 0
    request_cache: dict[str, tuple[str, dict[str, Any]]] = field(default_factory=dict)
    last_result: dict[str, Any] | None = None

    def next_candidate_id(self) -> str:
        self.candidate_sequence += 1
        return f"candidate-{self.candidate_sequence}"

    def snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "stack": _stack_snapshot(self.stack),
            "words": {name: list(body) for name, body in sorted(self.words.items())},
            "active_versions": dict(sorted(self.active_versions.items())),
            "candidates": len(self.candidates),
            "transaction_active": self.transaction_active,
            "default_budget": dict(self.default_budget),
            "capabilities": list(self.capabilities),
        }


class JsonRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._state = {
            "versions": {},
            "active_versions": {},
        }

    def seed(self) -> None:
        self._state["versions"] = {
            "square": [
                {
                    "version": 1,
                    "body": ["dup", "*"],
                    "content_hash": self._hash_word("square", ["dup", "*"]),
                },
                {
                    "version": 2,
                    "body": ["dup", "*", "dup", "*"],
                    "content_hash": self._hash_word("square", ["dup", "*", "dup", "*"]),
                },
            ]
        }
        self._state["active_versions"] = {"square": 2}
        self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(_canonical_json(self._state), encoding="utf-8")

    def _read(self) -> None:
        if self.path.exists():
            self._state = json.loads(self.path.read_text(encoding="utf-8"))

    def _hash_word(self, name: str, body: list[str]) -> str:
        digest = hashlib.sha256(
            _canonical_json({"name": name, "body": body}).encode("utf-8")
        )
        return digest.hexdigest()

    def save_dictionary(self, session: JsonSession) -> dict[str, Any]:
        self._read()
        versions = self._state.setdefault("versions", {})
        active = self._state.setdefault("active_versions", {})
        created: list[dict[str, Any]] = []
        unchanged: list[dict[str, Any]] = []
        for name, body in sorted(session.words.items()):
            records = versions.setdefault(name, [])
            content_hash = self._hash_word(name, body)
            match = next(
                (
                    record
                    for record in records
                    if record["content_hash"] == content_hash
                ),
                None,
            )
            if match is not None:
                active[name] = match["version"]
                unchanged.append({"name": name, "version": match["version"]})
                continue
            version = (
                1 if not records else max(record["version"] for record in records) + 1
            )
            record = {
                "version": version,
                "body": list(body),
                "content_hash": content_hash,
            }
            records.append(record)
            active[name] = version
            created.append({"name": name, "version": version})
        self._write()
        return {
            "status": "ok",
            "path": str(self.path),
            "created_versions": created,
            "unchanged_versions": unchanged,
            "active_versions": [
                {"name": name, "version": version}
                for name, version in sorted(active.items())
            ],
        }

    def load_dictionary(self, session: JsonSession) -> dict[str, Any]:
        self._read()
        active = self._state.get("active_versions", {})
        versions = self._state.get("versions", {})
        session.words.clear()
        session.active_versions.clear()
        for name, version in sorted(active.items()):
            record = next(
                (
                    record
                    for record in versions.get(name, [])
                    if record["version"] == version
                ),
                None,
            )
            if record is None:
                raise ValueError("missing word version")
            session.words[name] = list(record["body"])
            session.active_versions[name] = version
        return {
            "status": "ok",
            "path": str(self.path),
            "loaded_words": list(session.words.keys()),
            "active_versions": [
                {"name": name, "version": version}
                for name, version in sorted(session.active_versions.items())
            ],
            "dictionary": {
                "words": [
                    {"kind": "user", "name": name, "body": body}
                    for name, body in sorted(session.words.items())
                ]
            },
        }

    def list_versions(self, word_name: str) -> dict[str, Any]:
        self._read()
        versions = self._state.get("versions", {}).get(word_name, [])
        return {
            "status": "ok",
            "word_name": word_name,
            "active_version": self._state.get("active_versions", {}).get(word_name),
            "versions": [
                {
                    "version": record["version"],
                    "content_hash": record["content_hash"],
                    "metadata": {},
                }
                for record in versions
            ],
        }

    def restore_version(
        self, session: JsonSession, word_name: str, version: int
    ) -> dict[str, Any]:
        self._read()
        records = self._state.get("versions", {}).get(word_name, [])
        record = next((item for item in records if item["version"] == version), None)
        if record is None:
            raise ValueError("missing word version")
        session.words[word_name] = list(record["body"])
        session.active_versions[word_name] = version
        self._state.setdefault("active_versions", {})[word_name] = version
        self._write()
        return {
            "status": "ok",
            "path": str(self.path),
            "loaded_words": list(session.words.keys()),
            "active_versions": [
                {"name": name, "version": version}
                for name, version in sorted(session.active_versions.items())
            ],
            "dictionary": {
                "words": [
                    {"kind": "user", "name": name, "body": body}
                    for name, body in sorted(session.words.items())
                ]
            },
            "restored_word": word_name,
            "restored_version": version,
        }


def _execute_tokens(
    tokens: list[str],
    *,
    stack: list[Any],
    words: Mapping[str, list[str]],
    budget: dict[str, int],
    step_counter: list[int],
    call_depth: int = 0,
) -> None:
    if call_depth > int(budget["max_call_depth"]):
        raise RuntimeError("call depth exceeded")
    i = 0
    while i < len(tokens):
        step_counter[0] += 1
        if step_counter[0] > int(budget["max_steps"]):
            raise RuntimeError("budget exceeded")
        token = tokens[i]
        if _is_int(token) or _is_bool(token):
            stack.append(_literal_value(token))
        elif token == "+":
            if len(stack) < 2:
                raise RuntimeError("stack underflow")
            b = stack.pop()
            a = stack.pop()
            if (
                not isinstance(a, int)
                or not isinstance(b, int)
                or isinstance(a, bool)
                or isinstance(b, bool)
            ):
                raise RuntimeError("type mismatch")
            stack.append(a + b)
        elif token == "*":
            if len(stack) < 2:
                raise RuntimeError("stack underflow")
            b = stack.pop()
            a = stack.pop()
            if (
                not isinstance(a, int)
                or not isinstance(b, int)
                or isinstance(a, bool)
                or isinstance(b, bool)
            ):
                raise RuntimeError("type mismatch")
            stack.append(a * b)
        elif token == "dup":
            if not stack:
                raise RuntimeError("stack underflow")
            stack.append(copy.deepcopy(stack[-1]))
        elif token == "drop":
            if not stack:
                raise RuntimeError("stack underflow")
            stack.pop()
        elif token == "swap":
            if len(stack) < 2:
                raise RuntimeError("stack underflow")
            stack[-1], stack[-2] = stack[-2], stack[-1]
        elif token == "over":
            if len(stack) < 2:
                raise RuntimeError("stack underflow")
            stack.append(copy.deepcopy(stack[-2]))
        elif token == "=":
            if len(stack) < 2:
                raise RuntimeError("stack underflow")
            b = stack.pop()
            a = stack.pop()
            stack.append(a == b)
        elif token == "depth":
            stack.append(len(stack))
        else:
            body = words.get(token)
            if body is None:
                raise RuntimeError("unknown word")
            _execute_tokens(
                body,
                stack=stack,
                words=words,
                budget=budget,
                step_counter=step_counter,
                call_depth=call_depth + 1,
            )
        i += 1


class JsonToolsAdapter:
    protocol_name = PROTOCOL_NAME
    protocol_version = PROTOCOL_VERSION

    def __init__(self, *, workdir: Path, variant: str) -> None:
        self.variant = variant
        self.workdir = workdir
        self._repositories: dict[str, JsonRepository] = {}
        self._sessions: dict[str, JsonSession] = {}
        self._seed_repository()

    def _seed_repository(self) -> None:
        repository = JsonRepository(self.workdir / "json-tools.json")
        repository.seed()
        self._repositories["main"] = repository

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        try:
            session_id = str(request["session_id"])
            action = str(request["action"])
            arguments = request.get("arguments", {})
            if not isinstance(arguments, Mapping):
                raise ValueError("arguments must be a mapping")
            if action == "create_session":
                response = self._create_session(request, arguments)
            else:
                session = self._sessions.get(session_id)
                if session is None:
                    raise ValueError("unknown session")
                response = self._dispatch(request, session, action, arguments)
        except Exception as error:
            response = make_response(
                protocol=PROTOCOL_NAME,
                version=PROTOCOL_VERSION,
                request_id=str(request.get("request_id", "")),
                session_id=str(request.get("session_id", "")),
                status="error",
                error=make_error(
                    "json_tools.error",
                    str(error),
                    metadata={"type": type(error).__name__},
                ),
            )
        return response

    def snapshot(self, session_id: str) -> dict[str, Any]:
        session = self._sessions[session_id]
        return session.snapshot()

    def close(self) -> None:
        self._sessions.clear()
        self._repositories.clear()

    def _create_session(
        self, request: Mapping[str, Any], arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        session_id = str(request["session_id"])
        if session_id in self._sessions:
            raise ValueError("session already exists")
        capabilities = [str(item) for item in arguments.get("capabilities", [])]
        repository_ids = tuple(
            str(item) for item in arguments.get("repository_ids", ())
        )
        budget = arguments.get("default_budget") or {
            "max_steps": 10000,
            "max_stack_depth": 128,
            "max_call_depth": 64,
        }
        session = JsonSession(
            session_id=session_id,
            capabilities=capabilities,
            default_budget={
                "max_steps": int(budget.get("max_steps", 10000)),
                "max_stack_depth": int(budget.get("max_stack_depth", 128)),
                "max_call_depth": int(budget.get("max_call_depth", 64)),
            },
            repository_ids=repository_ids,
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
                "capabilities": list(capabilities),
                "default_budget": dict(session.default_budget),
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
        session: JsonSession,
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
            raise ValueError("unknown action")
        return handler(request, session, arguments)

    def _close_session(
        self,
        request: Mapping[str, Any],
        session: JsonSession,
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
        session: JsonSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result=session.snapshot(),
            audit=[],
        )

    def _list_words(
        self,
        request: Mapping[str, Any],
        session: JsonSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        words = []
        for name in sorted(session.words):
            words.append(
                {"kind": "user", "name": name, "body": list(session.words[name])}
            )
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
        session: JsonSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        name = str(arguments.get("name", ""))
        if name not in session.words:
            raise ValueError("unknown word")
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result={
                "kind": "user",
                "name": name,
                "body": list(session.words[name]),
                "version": session.active_versions.get(name),
                "dependencies": [],
                "primitive_dependencies": [
                    token for token in session.words[name] if token in _PRIMITIVES
                ],
            },
            audit=[],
        )

    def _propose_definition(
        self,
        request: Mapping[str, Any],
        session: JsonSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        source = str(arguments.get("source", ""))
        parsed = parse_definition_source(source)
        content_hash = hashlib.sha256(
            _canonical_json(parsed).encode("utf-8")
        ).hexdigest()
        candidate = JsonCandidate(
            candidate_id=session.next_candidate_id(),
            request_id=str(request["request_id"]),
            source=source,
            name=parsed["name"],
            body_tokens=tuple(parsed["body_tokens"]),
            content_hash=content_hash,
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
                "word": {"name": candidate.name, "body": list(candidate.body_tokens)},
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
        self, session: JsonSession, candidate_id: str, content_hash: str
    ) -> JsonCandidate:
        candidate = session.candidates.get(candidate_id)
        if candidate is None:
            raise ValueError("unknown candidate")
        if candidate.content_hash != content_hash:
            raise ValueError("candidate hash mismatch")
        return candidate

    def _test_definition(
        self,
        request: Mapping[str, Any],
        session: JsonSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        candidate = self._candidate(
            session,
            str(arguments.get("candidate_id", "")),
            str(arguments.get("content_hash", "")),
        )
        tests = tuple(arguments.get("tests", ()))
        budget = arguments.get("budget") or session.default_budget
        temp = copy.deepcopy(session)
        temp.words[candidate.name] = list(candidate.body_tokens)
        results: list[dict[str, Any]] = []
        passed = 0
        for case in tests:
            source = str(case.get("source", ""))
            expected_stack = list(case.get("expected_stack", []))
            expected_status = str(case.get("expected_status", "ok"))
            expected_error_code = case.get("expected_error_code")
            outcome = self._execute_source(temp, source, budget)
            record = {
                "source": source,
                "expected_stack": expected_stack,
                "expected_status": expected_status,
                "expected_error_code": expected_error_code,
                "status": outcome["status"],
                "stack": outcome["stack"],
                "error": outcome["error"],
                "trace": outcome["trace"],
                "steps": outcome["steps"],
            }
            if expected_status == "ok":
                record["passed"] = (
                    outcome["status"] == "ok"
                    and _stack_values(outcome["stack"]) == expected_stack
                )
            else:
                record["passed"] = outcome["status"] == "error"
            if record["passed"]:
                passed += 1
            results.append(record)
        session.candidates[candidate.candidate_id] = replace(
            candidate,
            status="tested" if passed == len(tests) else "rejected",
            tests_passed=passed == len(tests),
            tests_total=len(tests),
            tests_passed_count=passed,
            test_results=tuple(results),
        )
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
                "status": "tested",
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
        session: JsonSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        candidate = self._candidate(
            session,
            str(arguments.get("candidate_id", "")),
            str(arguments.get("content_hash", "")),
        )
        if (
            bool(arguments.get("require_tests_passed", True))
            and not candidate.tests_passed
        ):
            raise ValueError("candidate not tested")
        session.words[candidate.name] = list(candidate.body_tokens)
        session.candidates[candidate.candidate_id] = replace(
            candidate, status="published"
        )
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result={
                "candidate_id": candidate.candidate_id,
                "word": {"name": candidate.name, "body": list(candidate.body_tokens)},
            },
            audit=[
                {
                    "kind": "candidate_published",
                    "status": "ok",
                    "details": {"candidate_id": candidate.candidate_id},
                }
            ],
        )

    def _execute(
        self,
        request: Mapping[str, Any],
        session: JsonSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        source = str(arguments.get("source", ""))
        budget = arguments.get("budget") or session.default_budget
        mode = str(arguments.get("mode", "normal"))
        target = copy.deepcopy(session) if mode == "test" else session
        outcome = self._execute_source(target, source, budget)
        if mode != "test":
            session.stack = list(target.stack)
            session.words = copy.deepcopy(target.words)
            session.active_versions = dict(target.active_versions)
            session.last_result = outcome
            if (
                session.transaction_snapshot is not None
                and outcome["status"] == "error"
            ):
                self._restore_transaction(session)
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status=outcome["status"],
            result=outcome if outcome["status"] == "ok" else None,
            error=outcome["error"],
            audit=[
                {
                    "kind": "execution_completed",
                    "status": outcome["status"],
                    "details": {"steps": outcome["steps"]},
                }
            ],
        )

    def _execute_source(
        self, session: JsonSession, source: str, budget: dict[str, int]
    ) -> dict[str, Any]:
        tokens = tokenize_source(source)
        step_counter = [0]
        try:
            _execute_tokens(
                tokens,
                stack=session.stack,
                words=session.words,
                budget=budget,
                step_counter=step_counter,
            )
            return {
                "status": "ok",
                "stack": _stack_snapshot(session.stack),
                "value": _stack_snapshot(session.stack)[-1] if session.stack else None,
                "trace": [],
                "steps": step_counter[0],
                "error": None,
            }
        except Exception as error:
            return {
                "status": "error",
                "stack": _stack_snapshot(session.stack),
                "value": None,
                "trace": [],
                "steps": step_counter[0],
                "error": make_error(
                    "json_tools.runtime_error",
                    str(error),
                    metadata={"type": type(error).__name__},
                ),
            }

    def _begin_transaction(
        self,
        request: Mapping[str, Any],
        session: JsonSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        session.transaction_snapshot = copy.deepcopy(
            {
                "stack": session.stack,
                "words": session.words,
                "active_versions": session.active_versions,
            }
        )
        session.transaction_active = True
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result={"transaction": {"status": "active"}},
            audit=[{"kind": "transaction_started", "status": "ok", "details": {}}],
        )

    def _commit_transaction(
        self,
        request: Mapping[str, Any],
        session: JsonSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        session.transaction_snapshot = None
        session.transaction_active = False
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result={"transaction": {"status": "committed"}},
            audit=[{"kind": "transaction_committed", "status": "ok", "details": {}}],
        )

    def _rollback_transaction(
        self,
        request: Mapping[str, Any],
        session: JsonSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        self._restore_transaction(session)
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result={"transaction": {"status": "rolled_back"}},
            audit=[{"kind": "transaction_rolled_back", "status": "ok", "details": {}}],
        )

    def _restore_transaction(self, session: JsonSession) -> None:
        if session.transaction_snapshot is None:
            return
        snapshot = session.transaction_snapshot
        session.stack = list(snapshot["stack"])
        session.words = copy.deepcopy(snapshot["words"])
        session.active_versions = dict(snapshot["active_versions"])
        session.transaction_snapshot = None
        session.transaction_active = False

    def _save_dictionary(
        self,
        request: Mapping[str, Any],
        session: JsonSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        repository = self._repository(session, arguments)
        result = repository.save_dictionary(session)
        session.active_versions = {
            item["name"]: item["version"] for item in result["active_versions"]
        }
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result=result,
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
        session: JsonSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        repository = self._repository(session, arguments)
        result = repository.load_dictionary(session)
        session.active_versions = {
            item["name"]: item["version"] for item in result["active_versions"]
        }
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result=result,
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
        session: JsonSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        repository = self._repository(session, arguments)
        word_name = str(arguments.get("word_name", ""))
        result = repository.list_versions(word_name)
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result=result,
            audit=[],
        )

    def _restore_version(
        self,
        request: Mapping[str, Any],
        session: JsonSession,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        repository = self._repository(session, arguments)
        word_name = str(arguments.get("word_name", ""))
        version = int(arguments.get("version", 0))
        result = repository.restore_version(session, word_name, version)
        session.active_versions = {
            item["name"]: item["version"] for item in result["active_versions"]
        }
        return make_response(
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            request_id=str(request["request_id"]),
            session_id=session.session_id,
            status="ok",
            result=result,
            audit=[
                {
                    "kind": "version_restored",
                    "status": "ok",
                    "details": {"word_name": word_name, "version": version},
                }
            ],
        )

    def _repository(
        self, session: JsonSession, arguments: Mapping[str, Any]
    ) -> JsonRepository:
        repository_id = str(arguments.get("repository_id", "main"))
        if repository_id not in session.repository_ids:
            raise ValueError("repository not authorized")
        repository = self._repositories.get(repository_id)
        if repository is None:
            raise ValueError("unknown repository")
        return repository
