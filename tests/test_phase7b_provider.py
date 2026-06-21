# ruff: noqa: E402, I001
"""Phase 7B provider adapter tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.phase7b.provider import (  # noqa: E402
    OpenAIProviderConfiguration,
    build_response_request,
    classify_provider_error,
    create_openai_client,
    resolve_exact_model,
    serialize_tools,
    validate_configuration,
)


class _FakeResponses:
    def __init__(self) -> None:
        self.calls = 0

    def create(self, **_: object) -> dict[str, object]:
        self.calls += 1
        return {"status": "ok"}


class _FakeOpenAI:
    def __init__(self, **_: object) -> None:
        self.responses = _FakeResponses()


def _install_fake_openai(
    monkeypatch: pytest.MonkeyPatch, *, version: str = "9.9.9"
) -> None:
    fake_module = SimpleNamespace(__version__=version, OpenAI=_FakeOpenAI)
    monkeypatch.setitem(sys.modules, "openai", fake_module)


def test_validate_configuration_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_openai(monkeypatch)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        validate_configuration(OpenAIProviderConfiguration(), env={})


def test_validate_configuration_resolves_snapshot_and_redacts_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_openai(monkeypatch)
    env = {
        "OPENAI_API_KEY": "sk-test-super-secret-token",
        "OPENAI_ORG_ID": "org_123",
        "OPENAI_PROJECT_ID": "proj_456",
    }

    validation = validate_configuration(
        OpenAIProviderConfiguration(),
        env=env,
        tools=[{"type": "function", "name": "echo"}],
    )

    assert validation.sdk_version == "9.9.9"
    assert validation.api_key_present is True
    assert validation.organization_present is True
    assert validation.project_present is True
    assert validation.resolved_model == "gpt-5.5-2026-04-23"
    assert validation.redacted_configuration["max_output_tokens"] == 4096
    assert validation.redacted_configuration["model_snapshot"] == "gpt-5.5-2026-04-23"
    assert validation.serialized_tools == ({"name": "echo", "type": "function"},)


def test_create_client_requires_sdk_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_openai(monkeypatch)

    client = create_openai_client(
        OpenAIProviderConfiguration(),
        env={"OPENAI_API_KEY": "sk-test-client-key"},
    )

    assert isinstance(client, _FakeOpenAI)
    assert client.responses.calls == 0


def test_build_response_request_uses_exact_snapshot_and_tool_serialization() -> None:
    request = build_response_request(
        OpenAIProviderConfiguration(),
        user_prompt="hello",
        system_prompt="system",
        tools=[{"type": "function", "name": "echo"}],
    )

    assert request.model == "gpt-5.5-2026-04-23"
    assert request.input == "hello"
    assert request.instructions == "system"
    assert request.tools == ({"name": "echo", "type": "function"},)
    assert request.max_output_tokens == 4096
    assert request.timeout == 120
    assert request.temperature is None
    assert "temperature" not in request.to_dict()


def test_resolve_exact_model_rejects_alias() -> None:
    with pytest.raises(ValueError, match="fallback"):
        resolve_exact_model("gpt-5.5")


def test_classify_provider_error_distinguishes_insufficient_quota() -> None:
    class QuotaError(RuntimeError):
        status_code = 429

    error = QuotaError(
        "RateLimitError: Error code: 429 - {'error': {'message': "
        "'You exceeded your current quota, please check your plan and billing "
        "details.', 'type': 'insufficient_quota', 'param': None, "
        "'code': 'insufficient_quota'}}"
    )

    assert classify_provider_error(error) == "provider_insufficient_quota"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (SimpleNamespace(status_code=429), "rate_limit"),
        (SimpleNamespace(response=SimpleNamespace(status_code=503)), "provider_5xx"),
        (TimeoutError("timed out"), "timeout_transport"),
    ],
)
def test_classify_provider_error_maps_retry_conditions(
    error: BaseException, expected: str
) -> None:
    assert classify_provider_error(error) == expected


def test_serialize_tools_requires_mappings() -> None:
    with pytest.raises(TypeError, match="tools must be mappings"):
        serialize_tools([1])  # type: ignore[list-item]
