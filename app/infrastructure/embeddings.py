"""Embedding generation via Ollama."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import ollama as _ollama

from app.core.config import OllamaSettings
from app.core.logging import get_logger

logger = get_logger(__name__)

_RETRIES = 2
_RETRY_BACKOFF_SECONDS = 1.0


@dataclass(slots=True)
class EmbeddingResult:
    """Result of embedding generation."""

    model: str
    embedding: list[float]
    prompt_eval_count: int | None = None


class EmbeddingService:
    """Generate embeddings via Ollama's embedding endpoint."""

    def __init__(
        self,
        settings: OllamaSettings,
        *,
        model: str = "nomic-embed-text",
    ) -> None:
        self._client = _ollama.Client(
            host=str(settings.host),
            timeout=settings.timeout_seconds,
        )
        self._model = model

    def embed(self, text: str) -> EmbeddingResult:
        if not text.strip():
            raise ValueError("Cannot embed empty text.")
        return self._with_retry(lambda: self._embed(text), action="Embedding")

    def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        if not texts:
            return []
        return self._with_retry(lambda: self._embed_batch(texts), action="Batch embedding")

    def _with_retry(self, operation: Callable[[], Any], *, action: str) -> Any:
        for attempt in range(1, _RETRIES + 2):
            try:
                return operation()
            except Exception as exc:
                logger.warning("%s generation failed: %s", action, exc)
                if attempt > _RETRIES:
                    raise
                time.sleep(_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))

    def _embed(self, text: str) -> EmbeddingResult:
        response = self._client.embed(model=self._model, input=text)
        data = response.model_dump() if hasattr(response, "model_dump") else dict(response)
        embeddings = data.get("embeddings", [[]])
        vector = embeddings[0] if embeddings else []
        return EmbeddingResult(
            model=self._model,
            embedding=vector,
            prompt_eval_count=data.get("prompt_eval_count"),
        )

    def _embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        response = self._client.embed(model=self._model, input=texts)
        data = response.model_dump() if hasattr(response, "model_dump") else dict(response)
        embeddings_list = data.get("embeddings", [])
        results: list[EmbeddingResult] = []
        for vector in embeddings_list:
            results.append(EmbeddingResult(
                model=self._model,
                embedding=vector,
            ))
        return results
