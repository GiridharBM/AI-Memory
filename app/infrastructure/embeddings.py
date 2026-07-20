"""Embedding generation via Ollama."""

from __future__ import annotations

from dataclasses import dataclass

import ollama as _ollama

from app.core.config import OllamaSettings
from app.core.logging import get_logger

logger = get_logger(__name__)


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
        try:
            response = self._client.embed(model=self._model, input=text)
            data = response.model_dump() if hasattr(response, "model_dump") else dict(response)
            embeddings = data.get("embeddings", [[]])
            vector = embeddings[0] if embeddings else []
            return EmbeddingResult(
                model=self._model,
                embedding=vector,
                prompt_eval_count=data.get("prompt_eval_count"),
            )
        except Exception as exc:
            logger.warning("Embedding generation failed: %s", exc)
            raise

    def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        if not texts:
            return []
        try:
            response = self._client.embed(model=self._model, input=texts)
            data = response.model_dump() if hasattr(response, "model_dump") else dict(response)
            embeddings_list = data.get("embeddings", [])
            results: list[EmbeddingResult] = []
            for i, vector in enumerate(embeddings_list):
                results.append(EmbeddingResult(
                    model=self._model,
                    embedding=vector,
                ))
            return results
        except Exception as exc:
            logger.warning("Batch embedding generation failed: %s", exc)
            raise
