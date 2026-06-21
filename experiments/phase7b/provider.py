from __future__ import annotations

import importlib
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from .infra import MODEL_ALIAS, MODEL_SNAPSHOT, PILOT_BUDGETS, redact_secrets

_TIMEOUT_CLASS_NAMES = (
    "timeout",
    "timeoutexception",
    "apitimeouterror",
    "readtimeout",
    "writetimeout",
    "connecttimeout",
)
_RATE_LIMIT_CLASS_NAMES = (
    "ratelimit",
    "rate_limit",
)
_QUOTA_CLASS_NAMES = (
    "insufficient_quota",
    "quota",
    "credit",
)
_SERVER_ERROR_CLASS_NAMES = (
    "servererror",
    "internalservererror",
    "badgatewayerror",
    "serviceunavailableerror",
)


@dataclass(frozen=True, slots=True)
class OpenAIProviderConfiguration:
    model_alias: str = MODEL_ALIAS
    model_snapshot: str = MODEL_SNAPSHOT
    temperature: float | None = None
    max_output_tokens: int = PILOT_BUDGETS.max_output_tokens
    timeout_seconds: int = PILOT_BUDGETS.timeout_per_call_seconds
    max_retries: int = PILOT_BUDGETS.max_provider_retries_per_call

    def to_dict(self) -> dict[str, Any]:
        configuration: dict[str, Any] = {
            "model_alias": self.model_alias,
            "model_snapshot": self.model_snapshot,
            "max_output_tokens": self.max_output_tokens,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
        }
        return configuration


@dataclass(frozen=True, slots=True)
class OpenAIProviderValidation:
    sdk_version: str
    api_key_present: bool
    organization_present: bool
    project_present: bool
    resolved_model: str
    redacted_configuration: Mapping[str, Any]
    serialized_tools: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class OpenAIResponseRequest:
    model: str
    input: str
    instructions: str
    tools: tuple[dict[str, Any], ...]
    max_output_tokens: int
    temperature: float | None
    parallel_tool_calls: bool
    timeout: int

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": self.input,
            "instructions": self.instructions,
            "tools": list(self.tools),
            "max_output_tokens": self.max_output_tokens,
            "parallel_tool_calls": self.parallel_tool_calls,
            "timeout": self.timeout,
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        return payload


def import_openai_sdk() -> Any:
    try:
        return importlib.import_module("openai")
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised in env checks
        raise RuntimeError("openai SDK is not installed") from exc


def _env_flag(name: str, env: Mapping[str, str]) -> bool:
    return bool(str(env.get(name, "")).strip())


def resolve_exact_model(requested_model: str, *, snapshot: str = MODEL_SNAPSHOT) -> str:
    requested = str(requested_model).strip()
    if not requested:
        raise ValueError("model name cannot be empty")
    if requested != snapshot:
        raise ValueError(
            "model alias fallback is not allowed: expected "
            f"{snapshot!r}, got {requested!r}"
        )
    return requested


def serialize_tools(tools: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    serialized: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, Mapping):
            raise TypeError("tools must be mappings")
        serialized.append(
            {
                key: json_value
                for key, json_value in sorted(
                    _json_safe_mapping(dict(tool)).items(), key=lambda item: item[0]
                )
            }
        )
    return tuple(serialized)


def _json_safe_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    import json

    safe_payload = json.loads(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    return cast(dict[str, Any], safe_payload)


def _response_temperature(model_snapshot: str) -> float | None:
    if model_snapshot == MODEL_SNAPSHOT:
        return None
    return 0.0


def validate_configuration(
    configuration: OpenAIProviderConfiguration,
    *,
    env: Mapping[str, str] | None = None,
    tools: Sequence[Mapping[str, Any]] = (),
) -> OpenAIProviderValidation:
    sdk = import_openai_sdk()
    environment = os.environ if env is None else env
    if configuration.model_alias != MODEL_ALIAS:
        raise ValueError(
            "model alias mismatch: expected "
            f"{MODEL_ALIAS!r}, got {configuration.model_alias!r}"
        )
    if configuration.model_snapshot != MODEL_SNAPSHOT:
        raise ValueError(
            "model snapshot mismatch: expected "
            f"{MODEL_SNAPSHOT!r}, got {configuration.model_snapshot!r}"
        )
    api_key_present = _env_flag("OPENAI_API_KEY", environment)
    organization_present = _env_flag("OPENAI_ORG_ID", environment)
    project_present = _env_flag("OPENAI_PROJECT_ID", environment)
    if not api_key_present:
        raise RuntimeError("OPENAI_API_KEY is required for the real provider")

    resolved_model = resolve_exact_model(configuration.model_snapshot)
    serialized_tools = serialize_tools(tools)
    redacted_configuration = redact_secrets(configuration.to_dict())
    sdk_version = str(getattr(sdk, "__version__", "unknown"))
    return OpenAIProviderValidation(
        sdk_version=sdk_version,
        api_key_present=api_key_present,
        organization_present=organization_present,
        project_present=project_present,
        resolved_model=resolved_model,
        redacted_configuration=redacted_configuration,
        serialized_tools=serialized_tools,
    )


def create_openai_client(
    configuration: OpenAIProviderConfiguration,
    *,
    env: Mapping[str, str] | None = None,
) -> Any:
    sdk = import_openai_sdk()
    environment = os.environ if env is None else env
    api_key = str(environment.get("OPENAI_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for the real provider")

    kwargs: dict[str, Any] = {"api_key": api_key}
    organization = str(environment.get("OPENAI_ORG_ID", "")).strip()
    project = str(environment.get("OPENAI_PROJECT_ID", "")).strip()
    if organization:
        kwargs["organization"] = organization
    if project:
        kwargs["project"] = project

    client_cls = getattr(sdk, "OpenAI", None)
    if client_cls is None:
        raise RuntimeError("openai SDK does not expose OpenAI")
    return client_cls(**kwargs)


def build_response_request(
    configuration: OpenAIProviderConfiguration,
    *,
    user_prompt: str,
    system_prompt: str,
    tools: Sequence[Mapping[str, Any]] = (),
) -> OpenAIResponseRequest:
    resolved_model = resolve_exact_model(configuration.model_snapshot)
    return OpenAIResponseRequest(
        model=resolved_model,
        input=str(user_prompt),
        instructions=str(system_prompt),
        tools=serialize_tools(tools),
        max_output_tokens=configuration.max_output_tokens,
        temperature=_response_temperature(resolved_model),
        parallel_tool_calls=False,
        timeout=configuration.timeout_seconds,
    )


def invoke_response(
    client: Any,
    request: OpenAIResponseRequest,
) -> Any:
    return client.responses.create(**request.to_dict())


def classify_provider_error(error: BaseException) -> str:
    status_code = _error_status_code(error)
    if status_code == 429:
        if _is_insufficient_quota_error(error):
            return "provider_insufficient_quota"
        return "rate_limit"
    if status_code is not None and 500 <= status_code <= 599:
        return "provider_5xx"

    lowered_name = type(error).__name__.lower()
    lowered_message = str(error).lower()
    if any(fragment in lowered_name for fragment in _RATE_LIMIT_CLASS_NAMES):
        return "rate_limit"
    if any(fragment in lowered_name for fragment in _TIMEOUT_CLASS_NAMES):
        return "timeout_transport"
    if "timeout" in lowered_message:
        return "timeout_transport"
    if any(fragment in lowered_name for fragment in _SERVER_ERROR_CLASS_NAMES):
        return "provider_5xx"
    if "429" in lowered_message:
        if _is_insufficient_quota_error(error):
            return "provider_insufficient_quota"
        return "rate_limit"
    if re.search(r"\b5\d{2}\b", lowered_message):
        return "provider_5xx"
    return "provider_error"


def _is_insufficient_quota_error(error: BaseException) -> bool:
    lowered_name = type(error).__name__.lower()
    lowered_message = str(error).lower()
    if "insufficient_quota" in lowered_name or "insufficient_quota" in lowered_message:
        return True
    if any(fragment in lowered_name for fragment in _QUOTA_CLASS_NAMES):
        return True
    if "current quota" in lowered_message:
        return True
    if "consumed all your credits" in lowered_message:
        return True
    if "maximum monthly spend" in lowered_message:
        return True
    if "monthly budget is set too low" in lowered_message:
        return True
    return False


def _error_status_code(error: BaseException) -> int | None:
    for attr_name in ("status_code",):
        value = getattr(error, attr_name, None)
        if isinstance(value, int):
            return value
    response = getattr(error, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    return None
