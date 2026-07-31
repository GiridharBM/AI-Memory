"""Integration tests for knowledge engine persistence wiring (P1-03)."""

from __future__ import annotations

import hashlib
import math
import random
from typing import Any

from app.core.config import Settings
from app.domain.analysis import DocumentAnalysis, DocumentSummary, KeyConcept
from app.domain.documents import DocumentMetadata, SourceDocument
from app.pipelines.ingest_workflow import IngestionWorkflow


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

    def embed(self, text: str) -> Any:
        from app.infrastructure.embeddings import EmbeddingResult

        return EmbeddingResult(model="fake-embed", embedding=self._text_to_vector(text))

    def embed_batch(self, texts: list[str]) -> list[Any]:
        return [self.embed(t) for t in texts]


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


def test_create_default_wires_knowledge_engine(tmp_settings: Settings) -> None:
    workflow = IngestionWorkflow.create_default(tmp_settings)

    manifest_root = tmp_settings.paths.manifest_root
    assert workflow._chunker is not None
    assert workflow._embedding_service is not None
    assert workflow._kg_builder is not None
    assert workflow._vector_store is not None
    assert workflow._graph_path == manifest_root / "knowledge_graph.json"
    assert workflow._vector_store._persistence_path == manifest_root / "vector_store.json"


def test_knowledge_engine_persists_and_merges(tmp_settings: Settings) -> None:
    workflow = IngestionWorkflow.create_default(tmp_settings)
    workflow._embedding_service = FakeEmbeddingService()

    graph1, stored1, _ = workflow._run_knowledge_engine(
        _document("one.md", "Introduction about Alpha."),
        _analysis("First", "Alpha"),
    )
    manifest_root = tmp_settings.paths.manifest_root
    vector_path = manifest_root / "vector_store.json"
    graph_path = manifest_root / "knowledge_graph.json"

    assert stored1 > 0
    assert graph1 is not None
    assert vector_path.exists()
    assert graph_path.exists()

    graph2, stored2, _ = workflow._run_knowledge_engine(
        _document("two.md", "Follow-up about Beta."),
        _analysis("Second", "Beta"),
    )

    assert stored2 > 0
    assert graph2 is not None
    labels = {node.label for node in graph2.nodes.values()}
    assert {"First", "Alpha", "Second", "Beta"} <= labels

    persisted = __import__(
        "app.domain.knowledge_graph",
        fromlist=["KnowledgeGraph"],
    ).KnowledgeGraph.load(graph_path)
    assert {node.label for node in persisted.nodes.values()} == labels
