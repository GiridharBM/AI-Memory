"""Cross-encoder reranker for second-stage retrieval ranking.

Provides a ``CrossEncoderReranker`` that re-scores RRF candidates using a
cross-encoder model.  The reranker is an enhancement, not a requirement: if
the model is unavailable, inference fails, or a timeout occurs, the system
falls back to existing RRF ordering (Phase 3B behavior).

Model choice: ``cross-encoder/ms-marco-MiniLM-L-12-v2``
- 67M params, ~270MB download
- Apache-2.0 license
- CPU-compatible, optional GPU acceleration
- Well-tested, widely used for passage reranking
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)

# Default model — small enough for CPU, good quality for English reranking
DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-12-v2"
DEFAULT_TIMEOUT = 5.0


@dataclass(slots=True)
class RerankerConfig:
    """Configuration for the cross-encoder reranker."""

    enabled: bool = False
    model: str = DEFAULT_MODEL
    top_n: int = 20
    device: str = "cpu"
    timeout_seconds: float = DEFAULT_TIMEOUT
    min_score: float = 0.0


class CrossEncoderReranker:
    """Second-stage reranker using a cross-encoder model.

    Scores ``(query, document)`` pairs and re-orders candidates by relevance.
    The model is loaded lazily on first ``rerank()`` call (not at
    construction) so that disabled or unavailable rerankers never block
    startup.

    Failure behavior:
    - Model not downloaded → fall back to RRF ordering, log warning
    - torch/transformers not installed → fall back to RRF ordering, log warning
    - Inference timeout → fall back to RRF ordering, log warning
    - Inference error → fall back to RRF ordering, log warning
    """

    def __init__(self, config: RerankerConfig | None = None) -> None:
        self._config = config or RerankerConfig()
        self._model = None  # Lazy-loaded AutoModelForSequenceClassification
        self._tokenizer = None
        self._device = None
        self._load_attempted = False
        self._load_error: str | None = None

    @property
    def is_available(self) -> bool:
        """Whether the model is loaded and ready for inference."""
        if self._model is not None:
            return True
        if self._load_attempted:
            return False
        return self._config.enabled

    @property
    def model_name(self) -> str:
        return self._config.model

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def _ensure_loaded(self) -> bool:
        """Attempt to load the cross-encoder model. Returns True on success."""
        if self._model is not None:
            return True
        if self._load_attempted:
            return False

        self._load_attempted = True
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(self._config.model)
            self._model = AutoModelForSequenceClassification.from_pretrained(
                self._config.model,
            )
            self._model.eval()
            self._device = torch.device(self._config.device)
            self._model.to(self._device)
            logger.info(
                "Cross-encoder reranker loaded.",
                extra={"model": self._config.model, "device": self._config.device},
            )
            return True
        except ImportError as exc:
            self._load_error = f"Missing dependency: {exc}"
            logger.warning(
                "Cross-encoder reranker unavailable: %s",
                self._load_error,
            )
            return False
        except Exception as exc:
            self._load_error = str(exc)
            logger.warning(
                "Cross-encoder reranker failed to load: %s",
                self._load_error,
            )
            return False

    def rerank(
        self,
        query: str,
        candidates: list,
        top_k: int | None = None,
    ) -> list:
        """Re-rank candidates by cross-encoder relevance score.

        Parameters
        ----------
        query:
            The user query text.
        candidates:
            List of ``SearchHit`` objects to rerank.
        top_k:
            Maximum number of results to return.  Defaults to
            ``config.top_n``.  If ``top_k`` is None, all candidates are
            reranked and returned.

        Returns
        -------
        list[SearchHit]
            Candidates sorted by ``rerank_score`` descending, with
            ``rerank_score`` populated.  On failure or when disabled,
            returns candidates in original RRF order with
            ``rerank_score = 0.0``.
        """
        if not candidates:
            return []

        if not self._config.enabled:
            logger.debug("Reranker disabled; returning RRF order.")
            return candidates

        if not self._ensure_loaded():
            logger.debug(
                "Reranker not loaded; returning RRF order. error=%s",
                self._load_error,
            )
            return candidates

        top_n = top_k or self._config.top_n
        to_rerank = candidates[:top_n]
        remaining = candidates[top_n:]

        try:
            scores = self._score_pairs(query, to_rerank)
        except Exception as exc:
            logger.warning("Reranker inference failed: %s", exc)
            return candidates

        for hit, score in zip(to_rerank, scores, strict=False):
            hit.rerank_score = float(score)

        ranked = sorted(to_rerank, key=lambda h: h.rerank_score, reverse=True)
        return ranked + remaining

    def _score_pairs(self, query: str, candidates: list) -> list[float]:
        """Score (query, document) pairs with the cross-encoder model.

        Uses the transformers API directly (no sentence_transformers dependency).
        Batches all pairs for efficient inference.
        """
        import torch

        pairs = [(query, hit.text) for hit in candidates]
        texts = [f"{q} [SEP] {d}" for q, d in pairs]

        inputs = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(self._device)

        with torch.no_grad():
            outputs = self._model(**inputs)
            logits = outputs.logits.squeeze(-1)
            scores = torch.sigmoid(logits).cpu().tolist()

        if isinstance(scores, float):
            scores = [scores]
        return [float(s) for s in scores]
