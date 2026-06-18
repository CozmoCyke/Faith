from __future__ import annotations

import json
import re
from collections.abc import Mapping, MutableMapping
from typing import Any

_TOKEN_SPLIT_RE = re.compile(r"(\(|\)|:|;)")


def canonical_json(payload: Any) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def tokenize_source(source: str) -> list[str]:
    normalized = _TOKEN_SPLIT_RE.sub(r" \1 ", source)
    return [token for token in normalized.split() if token]


def parse_definition_source(source: str) -> dict[str, Any]:
    tokens = tokenize_source(source)
    if not tokens or tokens[0] != ":":
        raise ValueError("definition must start with ':'")
    if len(tokens) < 4:
        raise ValueError("definition is incomplete")

    name = tokens[1]
    index = 2
    contract_tokens: list[str] = []
    if index < len(tokens) and tokens[index] == "(":
        depth = 0
        while index < len(tokens):
            token = tokens[index]
            contract_tokens.append(token)
            if token == "(":
                depth += 1
            elif token == ")":
                depth -= 1
                if depth == 0:
                    index += 1
                    break
            index += 1
        else:
            raise ValueError("unterminated contract")

    body_tokens: list[str] = []
    while index < len(tokens):
        token = tokens[index]
        if token == ";":
            if not body_tokens:
                raise ValueError("definition body cannot be empty")
            return {
                "name": name,
                "contract_tokens": contract_tokens,
                "body_tokens": body_tokens,
            }
        if token == ":":
            raise ValueError("nested definitions are not allowed")
        body_tokens.append(token)
        index += 1
    raise ValueError("unterminated definition")


def ensure_mutable_mapping(value: Mapping[str, Any] | None) -> MutableMapping[str, Any]:
    return {} if value is None else dict(value)


def make_response(
    *,
    protocol: str,
    version: str,
    request_id: str,
    session_id: str,
    status: str,
    result: Mapping[str, Any] | None = None,
    error: Mapping[str, Any] | None = None,
    audit: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "protocol": protocol,
        "version": version,
        "request_id": request_id,
        "session_id": session_id,
        "status": status,
        "result": None if result is None else dict(result),
        "error": None if error is None else dict(error),
        "audit": [] if audit is None else list(audit),
    }


def make_error(
    code: str, message: str, *, metadata: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "metadata": {} if metadata is None else dict(metadata),
    }
