"""Reusable Ollama integration for the Personal AI Memory System."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from json import JSONDecodeError
from typing import Any, Literal, TypeVar

import ollama
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import OllamaSettings
from app.core.logging import get_logger

logger = get_logger(__name__)

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


class OllamaClientError(RuntimeError):
    """Base exception for Ollama client failures."""


class OllamaConnectionError(OllamaClientError):
    """Raised when the client cannot reach the local Ollama server."""


class OllamaTimeoutError(OllamaClientError):
    """Raised when an Ollama request exceeds the configured timeout."""


class OllamaResponseError(OllamaClientError):
    """Raised when Ollama returns an invalid or unsuccessful response."""


@dataclass(slots=True)
class OllamaRequest:
    """Generic model request sent to Ollama."""

    prompt: str
    system_prompt: str | None = None
    model: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


class OllamaTextResponse(BaseModel):
    """Structured plain-text response from Ollama."""

    model_config = ConfigDict(extra="forbid")

    model: str
    response: str
    raw: dict[str, Any] = Field(default_factory=dict)
    prompt_eval_count: int | None = None
    eval_count: int | None = None
    total_duration: int | None = None
    load_duration: int | None = None


class OllamaJsonResponse(BaseModel):
    """Structured JSON response from Ollama."""

    model_config = ConfigDict(extra="forbid")

    model: str
    payload: dict[str, Any] | list[Any]
    raw_text: str
    raw: dict[str, Any] = Field(default_factory=dict)
    prompt_eval_count: int | None = None
    eval_count: int | None = None
    total_duration: int | None = None
    load_duration: int | None = None


class OllamaClient:
    """Single integration boundary for all Ollama communication."""

    def __init__(self, settings: OllamaSettings) -> None:
        self._settings = settings
        self._client = ollama.Client(
            host=str(settings.host),
            timeout=settings.timeout_seconds,
        )

    @property
    def model(self) -> str:
        """Return the default model configured for the client."""

        return self._settings.model

    @property
    def endpoint(self) -> str:
        """Return the configured Ollama endpoint."""

        return str(self._settings.host)

    def is_available(self) -> bool:
        """Check whether the local Ollama server is reachable."""

        try:
            self._client.ps()
        except Exception as exc:
            logger.debug("Ollama availability check failed: %s", exc)
            return False
        return True

    def generate_text(self, request: OllamaRequest) -> OllamaTextResponse:
        """Generate a plain-text response using the configured Ollama model."""

        response = self._execute_generate(request=request, output_format=None)
        response_text = self._extract_response_text(response)

        return OllamaTextResponse(
            model=response.get("model", request.model or self._settings.model),
            response=response_text,
            raw=dict(response),
            prompt_eval_count=response.get("prompt_eval_count"),
            eval_count=response.get("eval_count"),
            total_duration=response.get("total_duration"),
            load_duration=response.get("load_duration"),
        )

    def generate_json(
        self,
        request: OllamaRequest,
        *,
        response_model: type[ResponseModelT] | None = None,
    ) -> OllamaJsonResponse | ResponseModelT:
        """Generate and parse a structured JSON response from Ollama."""

        output_format: Literal["json"] | dict[str, Any] = "json"
        if response_model is not None:
            output_format = response_model.model_json_schema()

        response = self._execute_generate(request=request, output_format=output_format)
        raw_text = self._extract_response_text(response)

        try:
            payload = json.loads(raw_text)
        except JSONDecodeError as exc:
            raise OllamaResponseError("Ollama returned invalid JSON output.") from exc

        structured_response = OllamaJsonResponse(
            model=response.get("model", request.model or self._settings.model),
            payload=payload,
            raw_text=raw_text,
            raw=dict(response),
            prompt_eval_count=response.get("prompt_eval_count"),
            eval_count=response.get("eval_count"),
            total_duration=response.get("total_duration"),
            load_duration=response.get("load_duration"),
        )

        if response_model is None:
            return structured_response

        try:
            return response_model.model_validate(structured_response.payload)
        except ValidationError as exc:
            raise OllamaResponseError(
                f"Ollama JSON output did not match the expected schema '{response_model.__name__}'."
            ) from exc

    def _execute_generate(
        self,
        *,
        request: OllamaRequest,
        output_format: Literal["json"] | dict[str, Any] | None,
    ) -> dict[str, Any]:
        model_name = request.model or self._settings.model
        max_attempts = self._settings.request_retries + 1

        for attempt in range(1, max_attempts + 1):
            try:
                logger.debug(
                    "Sending Ollama request.",
                    extra={
                        "model_name": model_name,
                        "endpoint": self.endpoint,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "json_output": output_format is not None,
                    },
                )

                generate_kwargs: dict[str, Any] = {
                    "model": model_name,
                    "prompt": request.prompt,
                    "stream": False,
                }
                if request.system_prompt is not None:
                    generate_kwargs["system"] = request.system_prompt
                if request.options:
                    generate_kwargs["options"] = request.options
                if output_format is not None:
                    generate_kwargs["format"] = output_format

                response = self._client.generate(**generate_kwargs)

                if not isinstance(response, dict):
                    response = dict(response)

                if not response.get("response"):
                    raise OllamaResponseError("Ollama returned an empty response body.")

                return response
            except ollama.ResponseError as exc:
                if exc.status_code == 404:
                    raise OllamaResponseError(
                        f"Ollama model '{model_name}' was not found at {self.endpoint}."
                    ) from exc
                if exc.status_code >= 500 and attempt < max_attempts:
                    self._sleep_before_retry(attempt)
                    continue
                raise OllamaResponseError(
                    f"Ollama request failed with status code {exc.status_code}."
                ) from exc
            except TimeoutError as exc:
                if attempt < max_attempts:
                    self._sleep_before_retry(attempt)
                    continue
                raise OllamaTimeoutError(
                    f"Ollama request timed out after {self._settings.timeout_seconds} seconds."
                ) from exc
            except OllamaClientError:
                raise
            except Exception as exc:
                if self._should_retry(exc) and attempt < max_attempts:
                    self._sleep_before_retry(attempt)
                    continue
                raise OllamaConnectionError(
                    f"Failed to communicate with Ollama at {self.endpoint}."
                ) from exc

        raise OllamaClientError("Ollama request exhausted all retry attempts.")

    def _extract_response_text(self, response: dict[str, Any]) -> str:
        response_text = response.get("response")
        if not isinstance(response_text, str):
            raise OllamaResponseError("Ollama returned a non-text response payload.")
        return response_text.strip()

    def _sleep_before_retry(self, attempt: int) -> None:
        delay = self._settings.retry_backoff_seconds * attempt
        if delay <= 0:
            return
        time.sleep(delay)

    @staticmethod
    def _should_retry(exc: Exception) -> bool:
        retryable_exception_names = {
            "ConnectError",
            "ConnectionError",
            "ConnectTimeout",
            "ReadTimeout",
            "RemoteProtocolError",
            "TimeoutException",
            "TransportError",
            "WriteTimeout",
        }
        return exc.__class__.__name__ in retryable_exception_names
