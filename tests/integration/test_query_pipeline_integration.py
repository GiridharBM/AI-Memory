"""P5-104 query pipeline integration tests — ingest → persist → query end to end.

Exercises the real production wiring: ``IngestionWorkflow`` persists a vector
store under ``manifest_root/vector_store.json``, then ``SearchService.create_default``
loads the same file and serves hybrid queries. Embeddings are deterministic
fakes, so no live Ollama is required.
"""

from __future__ import annotations

import hashlib
import math
import random

import pytest

from app.core.config import Settings
from app.domain.analysis import DocumentAnalysis, DocumentSummary, KeyConcept
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.search import SearchService
from app.pipelines.ingest_workflow import IngestionWorkflow

pytestmark = pytest.mark.integration


class FakeEmbeddingService:
    """Deterministic fake embeddings — no live Ollama required."""

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim

    def _text_to_vector(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        rng = random.Random(h[:8])
        vec = [rng.gauss(0, 1) for _ in range(self._dim)]
        norm = math.sqrt(sum(x * x for x in vec))
        return [x / norm for x in vec] if norm > 0 else vec

    def embed(self, text: str) -> list[float]:
        return self._text_to_vector(text)

    def embed_batch(self, texts: list[str]) -> list[object]:
        from app.infrastructure.embeddings import EmbeddingResult

        return [
            EmbeddingResult(model="fake-embed", embedding=self._text_to_vector(t))
            for t in texts
        ]


def _document(source: str, text: str) -> SourceDocument:
    return SourceDocument(
        source=source,
        source_path=None,
        source_type="markdown",
        filename=source,
        text=text,
        metadata=DocumentMetadata(title="Test"),
    )


def _analysis(note_title: str, concept: str) -> DocumentAnalysis:
    return DocumentAnalysis(
        suggested_note_title=note_title,
        summary=DocumentSummary(short="Short", detailed="Detailed"),
        key_concepts=[
            KeyConcept(name=concept, explanation="explanation", importance="high"),
        ],
    )


@pytest.fixture
def searchable_store(tmp_settings: Settings) -> tuple[Settings, FakeEmbeddingService]:
    workflow = IngestionWorkflow.create_default(tmp_settings)
    embed = FakeEmbeddingService()
    workflow._embedding_service = embed

    for doc, analysis in [
        (_document("one.md", "Introduction about Alpha."), _analysis("First", "Alpha")),
        (_document("two.md", "Follow-up about Beta."), _analysis("Second", "Beta")),
    ]:
        workflow._run_knowledge_engine(doc, analysis)

    return tmp_settings, embed


def test_ingested_documents_are_queryable(
    searchable_store: tuple[Settings, FakeEmbeddingService],
) -> None:
    settings, embed = searchable_store
    service = SearchService.create_default(settings, embed=embed.embed)

    hits = service.search("Beta", top_k=5)

    assert hits, "expected at least one hit for a known concept"
    assert hits[0].source == "two.md"


def test_ranking_is_deterministic(searchable_store: tuple[Settings, FakeEmbeddingService]) -> None:
    settings, embed = searchable_store
    service = SearchService.create_default(settings, embed=embed.embed)

    first = [(h.entry_id, h.score) for h in service.search("Alpha", top_k=5)]
    second = [(h.entry_id, h.score) for h in service.search("Alpha", top_k=5)]

    assert first == second
    assert first[0][0].startswith("one.md")


def test_filter_restricts_source(searchable_store: tuple[Settings, FakeEmbeddingService]) -> None:
    settings, embed = searchable_store
    service = SearchService.create_default(settings, embed=embed.embed)

    hits = service.search("knowledge", top_k=5, filter={"source_type": "markdown"})

    assert {h.source_type for h in hits} == {"markdown"}


def test_top_k_and_min_score(searchable_store: tuple[Settings, FakeEmbeddingService]) -> None:
    settings, embed = searchable_store
    service = SearchService.create_default(settings, embed=embed.embed)

    assert len(service.search("Alpha", top_k=1)) == 1
    # An impossibly high threshold yields no results.
    assert service.search("Alpha", min_score=1.0) == []


def test_blank_query_returns_nothing(
    searchable_store: tuple[Settings, FakeEmbeddingService],
) -> None:
    settings, embed = searchable_store
    service = SearchService.create_default(settings, embed=embed.embed)

    assert service.search("   ") == []
