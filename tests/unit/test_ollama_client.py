"""Tests for the Ollama client with mocked transport."""

from __future__ import annotations

from typing import Any, cast

import httpx
import pytest
from pydantic import BaseModel

import app.infrastructure.llm.ollama_client as ollama_client_module
from app.core.config import OllamaSettings
from app.infrastructure.llm import OllamaClient, OllamaRequest, OllamaResponseError


class SimpleResponse(BaseModel):
    value: str


class FakeTransport:
    def __init__(self, responses: list[dict[str, str] | Exception]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def generate(self, **kwargs: object) -> dict[str, str]:
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def ps(self) -> dict[str, list[object]]:
        return {"models": []}

    def list(self) -> dict[str, list[dict[str, str]]]:
        return {"models": [{"name": "qwen3:8b"}]}


def test_ollama_client_generates_text() -> None:
    client = OllamaClient(_settings())
    client._client = cast(Any, FakeTransport([{"model": "qwen3:8b", "response": "hello"}]))

    response = client.generate_text(OllamaRequest(prompt="Say hello"))

    assert response.response == "hello"
    assert response.model == "qwen3:8b"


def test_ollama_client_finds_configured_model() -> None:
    client = OllamaClient(_settings())
    client._client = cast(Any, FakeTransport([]))

    assert client.model_exists()


def test_ollama_client_validates_json_response_model() -> None:
    client = OllamaClient(_settings())
    client._client = cast(
        Any,
        FakeTransport([{"model": "qwen3:8b", "response": '{"value": "ok"}'}]),
    )

    response = client.generate_json(OllamaRequest(prompt="JSON"), response_model=SimpleResponse)

    assert response == SimpleResponse(value="ok")


def test_ollama_client_rejects_invalid_json() -> None:
    client = OllamaClient(_settings())
    client._client = cast(Any, FakeTransport([{"model": "qwen3:8b", "response": "not json"}]))

    with pytest.raises(OllamaResponseError):
        client.generate_json(OllamaRequest(prompt="JSON"))


def test_ollama_client_retries_retryable_transport_errors() -> None:
    transport = FakeTransport(
        [httpx.ConnectError("temporary"), {"model": "qwen3:8b", "response": "ok"}]
    )
    client = OllamaClient(_settings(request_retries=1, retry_backoff_seconds=0))
    client._client = cast(Any, transport)

    response = client.generate_text(OllamaRequest(prompt="hello"))

    assert response.response == "ok"
    assert transport.calls == 2


def test_ollama_client_uses_exponential_retry_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep_delays: list[float] = []
    monkeypatch.setattr(ollama_client_module.time, "sleep", sleep_delays.append)
    transport = FakeTransport(
        [
            httpx.ConnectError("temporary"),
            httpx.ConnectError("temporary"),
            httpx.ConnectError("temporary"),
            {"model": "qwen3:8b", "response": "ok"},
        ]
    )
    client = OllamaClient(_settings(request_retries=3, retry_backoff_seconds=1))
    client._client = cast(Any, transport)

    response = client.generate_text(OllamaRequest(prompt="hello"))

    assert response.response == "ok"
    assert sleep_delays == [1, 2, 4]


def _settings(*, request_retries: int = 0, retry_backoff_seconds: float = 0) -> OllamaSettings:
    return OllamaSettings(
        model="qwen3:8b",
        request_retries=request_retries,
        retry_backoff_seconds=retry_backoff_seconds,
    )
