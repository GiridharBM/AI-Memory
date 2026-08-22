"""Hypothetical Document Embedding (HyDE) for improved retrieval.

Transforms a query into a hypothetical answer paragraph before embedding.
The hypothetical answer is in "answer space" rather than "question space",
which produces much stronger cosine similarity to genuinely relevant chunks.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

_HYDE_SYSTEM_PROMPT = (
    "Write a short factual paragraph (2-4 sentences) that answers the given "
    "question. Write as if the information exists in a knowledge base. "
    "Do not say 'I don't know' or 'I cannot find'. Be specific and concrete."
)


class HyDETransform:
    """Generate a hypothetical answer for query transformation.

    When enabled, the original query is sent to the LLM to produce a
    hypothetical answer paragraph.  This paragraph is then embedded and
    used for vector retrieval, while the *original* query text is used
    for BM25 lexical retrieval.

    If the LLM call fails, times out, or returns an empty response,
    the transform returns ``None`` and the caller falls back to the
    original query embedding.
    """

    def __init__(
        self,
        generate: Callable[[str, str], str | None],
        *,
        max_length: int = 500,
    ) -> None:
        """
        Parameters
        ----------
        generate:
            Callable ``(system_prompt, user_prompt) -> response_text``.
            Wraps the Ollama ``generate_text`` call.  Returns ``None`` on
            any failure so the caller can fall back gracefully.
        max_length:
            Truncate the hypothetical answer to this many characters.
        """
        self._generate = generate
        self._max_length = max_length

    def transform(self, query: str) -> str | None:
        """Return a hypothetical answer paragraph, or ``None`` on failure."""
        try:
            response = self._generate(_HYDE_SYSTEM_PROMPT, query)
            if not response or not response.strip():
                logger.warning("HyDE: empty response for query=%r", query[:80])
                return None
            text = response.strip()[: self._max_length]
            return text
        except Exception:
            logger.warning("HyDE: generation failed for query=%r", query[:80], exc_info=True)
            return None
