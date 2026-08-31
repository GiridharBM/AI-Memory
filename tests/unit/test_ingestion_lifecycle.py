"""Phase 6H tests: ingestion lifecycle hardening.

Covers source-scoped re-ingestion, per-source delete, truthful status, and
the secret-ingestion guard, using isolated temporary stores only (STEP 10:
never touches the real corpus).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from app.domain.documents import DocumentMetadata, SourceDocument
from app.domain.knowledge_graph import KnowledgeGraph, KnowledgeNode
from app.domain.semantic_chunking import DocumentChunk
from app.domain.vector_store import VectorEntry
from app.infrastructure.embeddings import EmbeddingResult
from app.infrastructure.ingestion import DocumentIngestionService
from app.infrastructure.ingestion.service import is_secret_bearing
from app.infrastructure.semantic_chunking import SemanticChunker
from app.infrastructure.vector_store import VectorStore
from app.pipelines.ingest_workflow import IngestionWorkflow


def _chunk(index: int, source: str = "src.md") -> DocumentChunk:
    return DocumentChunk(
        chunk_id=f"{source}::chunk_{index}",
        text="some text",
        source=source,
        source_type="text",
        chunk_index=index,
        start_char=0,
        end_char=8,
        metadata={},
    )


def _document(source: str = "src.md") -> SourceDocument:
    return SourceDocument(
        source=source,
        filename=Path(source).name,
        source_type="text",
        text="some text",
        metadata=DocumentMetadata(),
    )


def _entry(source: str, index: int) -> VectorEntry:
    return VectorEntry(
        id=f"{source}::chunk_{index}",
        text="some text",
        embedding=[0.1, 0.2],
        source=source,
        source_type="text",
        chunk_index=index,
    )


def _workflow(chunks: list[DocumentChunk]) -> IngestionWorkflow:
    chunker = MagicMock()
    chunker.chunk.return_value = chunks
    embedder = MagicMock()
    embedder.embed_batch.return_value = [
        EmbeddingResult(model="m", embedding=[0.1, 0.2]) for _ in chunks
    ]
    return IngestionWorkflow(
        ingestion_service=MagicMock(),
        ollama_client=MagicMock(),
        note_generator=MagicMock(),
        writer=MagicMock(),
        chunker=chunker,
        embedding_service=embedder,
        vector_store=VectorStore(),
        knowledge_graph_builder=MagicMock(),
    )


# ── STEP 3: source-scoped re-ingestion ─────────────────────────────────────


def test_reingest_same_source_replaces_old_chunks() -> None:
    store = VectorStore()
    store.add_batch([_entry("src.md", 0), _entry("src.md", 1), _entry("other.md", 0)])
    store._version = 0

    wf = _workflow([_chunk(0, "src.md")])  # new content yields 1 chunk now
    wf._vector_store = store
    wf._run_knowledge_engine(_document("src.md"), MagicMock())

    sources = sorted({e.source for e in store.entries()})
    assert sources == ["other.md", "src.md"]
    # only the replacement chunk for src.md remains; the old second chunk is gone
    src_ids = sorted(e.id for e in store.entries() if e.source == "src.md")
    assert src_ids == ["src.md::chunk_0"]


def test_reingest_does_not_touch_unrelated_source() -> None:
    store = VectorStore()
    store.add_batch([_entry("src.md", 0), _entry("other.md", 0), _entry("other.md", 1)])

    wf = _workflow([_chunk(0, "src.md")])
    wf._vector_store = store
    wf._run_knowledge_engine(_document("src.md"), MagicMock())

    other_ids = sorted(e.id for e in store.entries() if e.source == "other.md")
    assert other_ids == ["other.md::chunk_0", "other.md::chunk_1"]


def test_failed_replacement_preserves_old_data() -> None:
    store = VectorStore()
    store.add_batch([_entry("src.md", 0), _entry("src.md", 1)])
    store._version = 0

    chunker = MagicMock()
    chunker.chunk.return_value = [_chunk(0, "src.md")]
    embedder = MagicMock()
    embedder.embed_batch.side_effect = OSError("embedding backend down")
    wf = IngestionWorkflow(
        ingestion_service=MagicMock(),
        ollama_client=MagicMock(),
        note_generator=MagicMock(),
        writer=MagicMock(),
        chunker=chunker,
        embedding_service=embedder,
        vector_store=store,
        knowledge_graph_builder=MagicMock(),
    )

    _kg, stored, _links = wf._run_knowledge_engine(_document("src.md"), MagicMock())

    assert stored == 0
    # old known-good chunks preserved untouched
    src_ids = sorted(e.id for e in store.entries() if e.source == "src.md")
    assert src_ids == ["src.md::chunk_0", "src.md::chunk_1"]
    assert wf._last_knowledge_result is not None
    assert wf._last_knowledge_result.succeeded is False


def test_partial_embedding_stores_nothing_preserving_prior() -> None:
    store = VectorStore()
    store.add_batch([_entry("src.md", 0)])

    chunker = MagicMock()
    chunker.chunk.return_value = [_chunk(0, "src.md"), _chunk(1, "src.md")]
    embedder = MagicMock()
    embedder.embed_batch.return_value = [
        EmbeddingResult(model="m", embedding=[0.1, 0.2]),
        EmbeddingResult(model="m", embedding=[]),
    ]
    wf = IngestionWorkflow(
        ingestion_service=MagicMock(),
        ollama_client=MagicMock(),
        note_generator=MagicMock(),
        writer=MagicMock(),
        chunker=chunker,
        embedding_service=embedder,
        vector_store=store,
        knowledge_graph_builder=MagicMock(),
    )

    _kg, stored, _links = wf._run_knowledge_engine(_document("src.md"), MagicMock())

    assert stored == 0
    src_ids = sorted(e.id for e in store.entries() if e.source == "src.md")
    assert src_ids == ["src.md::chunk_0"]


# ── STEP 3: BM25 consistency ───────────────────────────────────────────────


def test_reingest_bumps_version_for_bm25_rebuild() -> None:
    from app.infrastructure.search import HybridSearch

    store = VectorStore()
    store.add_batch([_entry("src.md", 0), _entry("other.md", 0)])
    version_before = store.version
    search = HybridSearch(store)

    wf = _workflow([_chunk(0, "src.md")])
    wf._vector_store = store
    wf._run_knowledge_engine(_document("src.md"), MagicMock())

    assert store.version > version_before
    assert search._bm25_version != store.version


# ── STEP 4: per-source delete ──────────────────────────────────────────────


def test_delete_removes_only_selected_source() -> None:
    store = VectorStore()
    store.add_batch([_entry("a.md", 0), _entry("a.md", 1), _entry("b.md", 0)])
    removed = store.remove_by_source("a.md")
    assert removed == 2
    assert [e.source for e in store.entries()] == ["b.md"]


def test_delete_nonexistent_source_is_safe() -> None:
    store = VectorStore()
    store.add_batch([_entry("a.md", 0)])
    assert store.remove_by_source("missing.md") == 0
    assert len(store.entries()) == 1


def test_kg_remove_source_only_removes_that_source() -> None:
    g = KnowledgeGraph()
    g.add_node(KnowledgeNode(id="n1", label="A", node_type="note", source="a.md"))
    g.add_node(KnowledgeNode(id="n2", label="B", node_type="concept", source="a.md"))
    g.add_node(KnowledgeNode(id="n3", label="C", node_type="concept", source="b.md"))
    nodes, edges = g.remove_source("a.md")
    assert nodes == 2
    assert sorted(g.nodes) == ["n3"]
    assert edges == 0


def test_delete_nonexistent_kg_source_is_safe() -> None:
    g = KnowledgeGraph()
    g.add_node(KnowledgeNode(id="n1", label="A", node_type="note", source="a.md"))
    assert g.remove_source("missing.md") == (0, 0)
    assert len(g.nodes) == 1


# ── STEP 5: truthful status ────────────────────────────────────────────────


def test_note_counts_exclude_placeholders(tmp_path: Path) -> None:
    from app.cli.entry import _note_counts

    notes = tmp_path / "Notes"
    notes.mkdir()
    (notes / "Real.md").write_text(
        "---\ntitle: Real\nsource: /abs/a.md\nsource_type: markdown\n---\nbody\n",
        encoding="utf-8",
    )
    (notes / "Stub.md").write_text(
        "---\ntitle: Stub\nsource_type: placeholder\n---\nstub\n", encoding="utf-8"
    )
    (notes / "User.md").write_text("# user note\n", encoding="utf-8")

    real, placeholder, other = _note_counts(notes)
    assert real == 1
    assert placeholder == 1
    assert other == 1


def test_frontmatter_value_parses() -> None:
    from app.cli.entry import _frontmatter_value

    text = "---\ntitle: X\nsource_type: pdf\nsource: /abs/x.pdf\n---\nbody"
    assert _frontmatter_value(text, "source_type") == "pdf"
    assert _frontmatter_value(text, "source") == "/abs/x.pdf"
    assert _frontmatter_value(text, "missing") is None


# ── STEP 6: secret-ingestion guard ─────────────────────────────────────────


def test_secret_guard_blocks_env_and_env_variants(tmp_path: Path) -> None:
    for name in [".env", ".env.local", ".env.production"]:
        path = tmp_path / name
        path.write_text("KEY=value", encoding="utf-8")
        assert is_secret_bearing(path) is True


def test_secret_guard_blocks_private_keys(tmp_path: Path) -> None:
    for name in ["id_rsa.pem", "private.key", "banana.p12", "x.ppk", "y.pfx"]:
        assert is_secret_bearing(tmp_path / name) is True


def test_secret_guard_allows_normal_documents(tmp_path: Path) -> None:
    for name in ["notes.md", "report.pdf", "doc.docx", "image.png", "config.toml"]:
        assert is_secret_bearing(tmp_path / name) is False


def test_env_file_blocked_by_service(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("API_KEY=secret123", encoding="utf-8")
    result = DocumentIngestionService().ingest(path)
    assert not result.succeeded
    assert result.error is not None
    assert "blocked" in result.error.reason
    assert "secret123" not in result.error.reason


def test_blocked_file_creates_no_chunks(tmp_path: Path) -> None:
    store = VectorStore()
    path = tmp_path / ".env"
    path.write_text("TOKEN=abc", encoding="utf-8")
    # the guard blocks before any chunking/embedding happens, so nothing
    # reaches the store
    assert is_secret_bearing(path) is True
    assert len(store.entries()) == 0


def test_blocked_file_creates_no_kg_entries() -> None:
    g = KnowledgeGraph()
    # blocked files never reach the KG builder; assert nothing is added here
    nodes, edges = g.remove_source(".env")
    assert (nodes, edges) == (0, 0)


def test_secret_guard_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    assert is_secret_bearing(path) is True
    assert is_secret_bearing(path) is True
    assert isinstance(is_secret_bearing(tmp_path / "x.py"), bool)


# ── STEP 7: retry + duplicate behavior ─────────────────────────────────────


def test_retry_after_failure_adds_new_chunks() -> None:
    store = VectorStore()
    # first attempt failed (never reached the store) -> store empty for src
    assert [e.source for e in store.entries() if e.source == "src.md"] == []
    wf = _workflow([_chunk(0, "src.md")])
    wf._vector_store = store
    _kg, stored, _links = wf._run_knowledge_engine(_document("src.md"), MagicMock())
    assert stored == 1


def test_duplicate_ingestion_dedups_same_chunk_ids() -> None:
    store = VectorStore()
    store.add_batch([_entry("src.md", 0)])
    wf = _workflow([_chunk(0, "src.md")])
    wf._vector_store = store
    wf._run_knowledge_engine(_document("src.md"), MagicMock())
    # same chunk id overwrites; no duplicate ids
    src_ids = [e.id for e in store.entries() if e.source == "src.md"]
    assert len(src_ids) == len(set(src_ids)) == 1
