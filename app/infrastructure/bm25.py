"""Deterministic Okapi BM25 sparse retrieval (roadmap 4.1).

Pure-Python implementation with no external dependency (MEDD §7.6 permits
"rank_bm25 or custom BM25 implementation"); kept dependency-free to match the
project's offline, local-first convention.
"""

from __future__ import annotations

import math
import re

_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    """Deterministic lowercase alphanumeric + underscore tokenization."""
    return _TOKEN_PATTERN.findall(text.lower())


class BM25Index:
    """Okapi BM25 over a fixed corpus snapshot.

    Builds term-frequency and document-frequency statistics once per corpus.
    ``search`` returns ``(doc_index, score)`` pairs ranked by ``(-score,
    doc_index)`` so ties are stable regardless of corpus insertion order.
    """

    def __init__(
        self,
        corpus: list[str],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self._docs = list(corpus)
        self._k1 = k1
        self._b = b
        self._doc_terms: list[dict[str, int]] = []
        self._lengths: list[int] = []
        self._postings: dict[str, list[int]] = {}
        for doc_index, doc in enumerate(self._docs):
            counts: dict[str, int] = {}
            for term in tokenize(doc):
                counts[term] = counts.get(term, 0) + 1
            for term in counts:
                self._postings.setdefault(term, []).append(doc_index)
            self._doc_terms.append(counts)
            self._lengths.append(sum(counts.values()))
        self._avgdl = sum(self._lengths) / len(self._lengths) if self._lengths else 0.0

    def search(self, query: str, *, top_k: int = 5) -> list[tuple[int, float]]:
        """Return up to ``top_k`` ``(doc_index, score)`` pairs, best first."""
        if not self._docs or top_k <= 0:
            return []
        terms = tokenize(query)
        if not terms:
            return []

        n = len(self._docs)
        scores: dict[int, float] = {}
        for term in set(terms):
            postings = self._postings.get(term)
            if not postings:
                continue
            df = len(postings)
            idf = math.log((n - df + 0.5) / (df + 0.5) + 1.0)
            for doc_index in postings:
                tf = self._doc_terms[doc_index][term]
                length_norm = 1 - self._b + self._b * self._lengths[doc_index] / self._avgdl
                denom = tf + self._k1 * length_norm
                scores[doc_index] = (
                    scores.get(doc_index, 0.0)
                    + idf * tf * (self._k1 + 1) / denom
                )

        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return ranked[:top_k]
