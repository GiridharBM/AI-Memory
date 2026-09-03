"""Tests for Phase 6A knowledge-engine outcome surfacing."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.domain.documents import DocumentMetadata, SourceDocument
from app.domain.semantic_chunking import DocumentChunk
from app.infrastructure.embeddings import EmbeddingResult
from app.infrastructure.vector_store import VectorStore
from app.pipelines.ingest_workflow import IngestionWorkflow


def _chunk(index: int) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=f"c{index}",
        text="some text",
        source="t.md",
        source_type="text",
        chunk_index=index,
        start_char=0,
        end_char=8,
    )


def _document() -> SourceDocument:
    return SourceDocument(
        source="t.md",
        filename="t.md",
        source_type="text",
        text="some text",
        metadata=DocumentMetadata(),
    )


def _workflow(*, chunks: list[DocumentChunk], embedding_error: bool = False) -> IngestionWorkflow:
    chunker = MagicMock()
    chunker.chunk.return_value = chunks

    embedder = MagicMock()
    if embedding_error:
        embedder.embed_batch.side_effect = OSError("embedding backend down")

    store = VectorStore()
    return IngestionWorkflow(
        ingestion_service=MagicMock(),
        ollama_client=MagicMock(),
        note_generator=MagicMock(),
        writer=MagicMock(),
        chunker=chunker,
        embedding_service=embedder,
        vector_store=store,
        knowledge_graph_builder=MagicMock(),
    )


def test_engine_outcome_all_chunks_stored() -> None:
    wf = _workflow(
        chunks=[_chunk(0), _chunk(1)],
        embedding_error=False,
    )
    wf._embedding_service.embed_batch.return_value = [
        EmbeddingResult(model="m", embedding=[0.1, 0.2]),
        EmbeddingResult(model="m", embedding=[0.3, 0.4]),
    ]

    _kg, stored, _links = wf._run_knowledge_engine(_document(), MagicMock())
    outcome = wf._last_knowledge_result

    assert stored == 2
    assert outcome is not None
    assert outcome.chunks_created == 2
    assert outcome.chunks_stored == 2
    assert outcome.embedding_succeeded is True
    assert outcome.indexing_succeeded is True
    assert outcome.succeeded is True
    assert outcome.error is None


def test_engine_outcome_partial_embedding_surfaces_failure() -> None:
    wf = _workflow(chunks=[_chunk(0), _chunk(1)])
    wf._embedding_service.embed_batch.return_value = [
        EmbeddingResult(model="m", embedding=[0.1, 0.2]),
        EmbeddingResult(model="m", embedding=[]),  # failed embedding for the second chunk
    ]

    _kg, stored, _links = wf._run_knowledge_engine(_document(), MagicMock())
    outcome = wf._last_knowledge_result

    # Phase 6H atomicity: a partial-embedding re-ingest must not leave the
    # store half-updated.  Nothing is written (stored == 0), so a prior
    # known-good copy of the source would be preserved and the failure is
    # surfaced for retry.
    assert stored == 0
    assert outcome is not None
    assert outcome.chunks_created == 2
    assert outcome.chunks_stored == 0
    assert outcome.embedding_succeeded is False
    assert outcome.indexing_succeeded is False
    assert outcome.succeeded is False
    assert "embedding/indexing incomplete" in outcome.error


def test_engine_outcome_embedding_exception_surfaces_failure() -> None:
    wf = _workflow(chunks=[_chunk(0)], embedding_error=True)

    _kg, stored, _links = wf._run_knowledge_engine(_document(), MagicMock())
    outcome = wf._last_knowledge_result

    assert stored == 0
    assert outcome is not None
    assert outcome.embedding_succeeded is False
    assert outcome.indexing_succeeded is False
    assert outcome.succeeded is False
    assert outcome.error == "embedding backend down"


def test_engine_outcome_vacuously_successful_when_no_chunks() -> None:
    wf = _workflow(chunks=[])

    _kg, stored, _links = wf._run_knowledge_engine(_document(), MagicMock())
    outcome = wf._last_knowledge_result

    assert stored == 0
    assert outcome is not None
    assert outcome.succeeded is True  # nothing to embed/store is a legitimate success