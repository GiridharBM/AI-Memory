"""Phase V1.1-A3 tests: re-ingestion reliability hardening.

Verifies the primary invariant — a failed re-ingestion MUST NOT destroy or
replace previously known-good data, and a successful one replaces it cleanly —
at the PERSISTENCE boundary (the disk state after reload), which the Phase 6H
in-memory lifecycle tests do not exercise. Uses isolated temporary stores only
(STEP 10: never touches the real corpus).

Coverage map (A3 STEP 4 edge cases):
- first success, modified re-ingest, shrink (stale-chunk removal), grow (no
  duplicates): persistence-level replacement.
- embedding exception, partial embedding, index/save failure: prior known-good
  data preserved on disk after reload.
- retry: failure then success replaces cleanly with no stale chunks.
- crash semantics: an in-memory remove+add without save() leaves disk old data
  intact after reload.
- KG: successful re-ingest replaces only that source's nodes on disk; a graph
  build failure leaves the prior persisted graph intact (graph_succeeded lost).
- identical-SHA different-path: hash dedup at the ledger gate; store identity
  stays path-scoped.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from app.domain.documents import DocumentMetadata, SourceDocument
from app.domain.knowledge_graph import KnowledgeGraph, KnowledgeNode
from app.domain.semantic_chunking import DocumentChunk
from app.domain.vector_store import VectorEntry
from app.infrastructure.embeddings import EmbeddingResult
from app.infrastructure.semantic_chunking import SemanticChunker
from app.infrastructure.state.manifest import ManifestManager
from app.infrastructure.vector_store import VectorStore
from app.pipelines.ingest_workflow import IngestionWorkflow, IngestionWorkflowError


class _Embedder:
    """Minimal embedding service with controllable partial/full failure."""

    def __init__(self, dim: int = 4) -> None:
        self._dim = dim
        self.fail_next = False
        self.fail_indices: set[int] = set()

    def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        if self.fail_next:
            self.fail_next = False
            raise OSError("embedding backend down")
        return [
            EmbeddingResult(
                model="m",
                embedding=[] if i in self.fail_indices else [0.1] * self._dim,
            )
            for i in range(len(texts))
        ]


class _KGBuilder:
    """Fake graph builder: one node per source, replaceable by id."""

    def __init__(self) -> None:
        self.fail_build = False

    def build_from_analysis(self, analysis: object, source: str) -> SimpleNamespace:
        if self.fail_build:
            raise RuntimeError("graph analysis failed")
        g = KnowledgeGraph()
        g.add_node(
            KnowledgeNode(
                id=f"{source}::n1", label="N1", node_type="concept", source=source
            )
        )
        return SimpleNamespace(graph=g)

    def merge_graphs(
        self, existing: KnowledgeGraph, graph: KnowledgeGraph
    ) -> KnowledgeGraph:
        merged = KnowledgeGraph()
        merged.nodes.update(existing.nodes)
        merged.nodes.update(graph.nodes)
        merged.edges = list(existing.edges) + list(graph.edges)
        return merged


def _chunk(source: str, index: int) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=f"{source}::chunk_{index}",
        text=f"{source} chunk {index}",
        source=source,
        source_type="text",
        chunk_index=index,
        start_char=0,
        end_char=8,
        metadata={},
    )


def _document(source: str) -> SourceDocument:
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
        text="t",
        embedding=[0.1, 0.2],
        source=source,
        source_type="text",
        chunk_index=index,
    )


def _workflow(
    *,
    chunks: list[DocumentChunk],
    vector_store: VectorStore,
    graph_path: Path | None,
    embedder: _Embedder,
    kg_builder: _KGBuilder,
) -> IngestionWorkflow:
    chunker = MagicMock(spec=SemanticChunker)
    chunker.chunk.return_value = chunks
    return IngestionWorkflow(
        ingestion_service=MagicMock(),
        ollama_client=MagicMock(),
        note_generator=MagicMock(),
        writer=MagicMock(),
        chunker=chunker,
        embedding_service=cast(Any, embedder),
        vector_store=vector_store,
        knowledge_graph_builder=cast(Any, kg_builder),
        graph_persistence_path=graph_path,
    )


def _run(wf: IngestionWorkflow, source: str) -> tuple[KnowledgeGraph | None, int, int]:
    return wf._run_knowledge_engine(_document(source), MagicMock())


def _reload_vector(persistence_path: Path) -> VectorStore:
    return VectorStore(persistence_path=persistence_path)


def _source_ids(entries: list[VectorEntry]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for e in entries:
        out.setdefault(e.source, []).append(e.id)
    return {k: sorted(v) for k, v in out.items()}


def _node_ids(graph: KnowledgeGraph) -> list[str]:
    return sorted(n.id for n in graph.nodes.values())


# ── STEP 4: persistence-level replacement ─────────────────────────────────


def test_first_ingest_stores_and_saves(tmp_path: Path) -> None:
    vpath = tmp_path / "vstore.json"
    store = VectorStore(persistence_path=vpath)
    wf = _workflow(
        chunks=[_chunk("a.md", 0), _chunk("a.md", 1)],
        vector_store=store,
        graph_path=None,
        embedder=_Embedder(),
        kg_builder=_KGBuilder(),
    )
    _kg, stored, _links = _run(wf, "a.md")

    assert wf._last_knowledge_result is not None
    assert wf._last_knowledge_result.succeeded is True
    assert wf._last_knowledge_result.graph_succeeded is True
    assert stored == 2
    assert _source_ids(_reload_vector(vpath).entries()) == {
        "a.md": ["a.md::chunk_0", "a.md::chunk_1"]
    }


def test_reingest_modified_source_replaces_cleanly_on_disk(tmp_path: Path) -> None:
    vpath = tmp_path / "vstore.json"
    embedder = _Embedder()

    store = VectorStore(persistence_path=vpath)
    wf = _workflow(
        chunks=[_chunk("a.md", 0), _chunk("a.md", 1), _chunk("a.md", 2)],
        vector_store=store,
        graph_path=None,
        embedder=embedder,
        kg_builder=_KGBuilder(),
    )
    _run(wf, "a.md")  # v1: three chunks persisted

    store2 = VectorStore(persistence_path=vpath)
    wf2 = _workflow(
        chunks=[_chunk("a.md", 10), _chunk("a.md", 11)],  # v2 content
        vector_store=store2,
        graph_path=None,
        embedder=embedder,
        kg_builder=_KGBuilder(),
    )
    _run(wf2, "a.md")

    assert _source_ids(_reload_vector(vpath).entries()) == {
        "a.md": ["a.md::chunk_10", "a.md::chunk_11"]
    }


def test_reingest_shrink_removes_stale_chunks_on_disk(tmp_path: Path) -> None:
    vpath = tmp_path / "vstore.json"
    embedder = _Embedder()

    store = VectorStore(persistence_path=vpath)
    wf = _workflow(
        chunks=[_chunk("a.md", 0), _chunk("a.md", 1), _chunk("a.md", 2)],
        vector_store=store,
        graph_path=None,
        embedder=embedder,
        kg_builder=_KGBuilder(),
    )
    _run(wf, "a.md")

    store2 = VectorStore(persistence_path=vpath)
    wf2 = _workflow(
        chunks=[_chunk("a.md", 0)],  # shrunk
        vector_store=store2,
        graph_path=None,
        embedder=embedder,
        kg_builder=_KGBuilder(),
    )
    _run(wf2, "a.md")

    assert _source_ids(_reload_vector(vpath).entries()) == {"a.md": ["a.md::chunk_0"]}


def test_reingest_grow_has_no_duplicates_on_disk(tmp_path: Path) -> None:
    vpath = tmp_path / "vstore.json"
    embedder = _Embedder()

    store = VectorStore(persistence_path=vpath)
    wf = _workflow(
        chunks=[_chunk("a.md", 0)],
        vector_store=store,
        graph_path=None,
        embedder=embedder,
        kg_builder=_KGBuilder(),
    )
    _run(wf, "a.md")

    store2 = VectorStore(persistence_path=vpath)
    wf2 = _workflow(
        chunks=[_chunk("a.md", 1), _chunk("a.md", 2), _chunk("a.md", 3)],
        vector_store=store2,
        graph_path=None,
        embedder=embedder,
        kg_builder=_KGBuilder(),
    )
    _run(wf2, "a.md")

    ids = _source_ids(_reload_vector(vpath).entries())["a.md"]
    assert ids == ["a.md::chunk_1", "a.md::chunk_2", "a.md::chunk_3"]
    assert len(ids) == len(set(ids))


# ── STEP 4: failed re-ingest preserves prior data on disk ─────────────────


def test_embedding_exception_preserves_prior_data_on_disk(tmp_path: Path) -> None:
    vpath = tmp_path / "vstore.json"
    embedder = _Embedder()

    store = VectorStore(persistence_path=vpath)
    wf = _workflow(
        chunks=[_chunk("a.md", 0), _chunk("a.md", 1)],
        vector_store=store,
        graph_path=None,
        embedder=embedder,
        kg_builder=_KGBuilder(),
    )
    _run(wf, "a.md")

    embedder.fail_next = True  # retry attempt fails at embedding
    store2 = VectorStore(persistence_path=vpath)
    wf2 = _workflow(
        chunks=[_chunk("a.md", 0), _chunk("a.md", 1)],
        vector_store=store2,
        graph_path=None,
        embedder=embedder,
        kg_builder=_KGBuilder(),
    )
    _kg, stored, _links = _run(wf2, "a.md")

    assert stored == 0
    assert wf2._last_knowledge_result is not None
    assert wf2._last_knowledge_result.succeeded is False
    assert _source_ids(_reload_vector(vpath).entries()) == {
        "a.md": ["a.md::chunk_0", "a.md::chunk_1"]
    }


def test_partial_embedding_preserves_prior_data_on_disk(tmp_path: Path) -> None:
    vpath = tmp_path / "vstore.json"
    embedder = _Embedder()

    store = VectorStore(persistence_path=vpath)
    wf = _workflow(
        chunks=[_chunk("a.md", 0), _chunk("a.md", 1)],
        vector_store=store,
        graph_path=None,
        embedder=embedder,
        kg_builder=_KGBuilder(),
    )
    _run(wf, "a.md")

    embedder.fail_indices = {1}  # one chunk emits no embedding
    store2 = VectorStore(persistence_path=vpath)
    store2.save = MagicMock(wraps=store2.save)  # type: ignore[method-assign]
    wf2 = _workflow(
        chunks=[_chunk("a.md", 10), _chunk("a.md", 11)],
        vector_store=store2,
        graph_path=None,
        embedder=embedder,
        kg_builder=_KGBuilder(),
    )
    _kg, stored, _links = _run(wf2, "a.md")

    assert stored == 0
    assert store2.save.call_count == 0  # a partial embed must never reach disk
    assert wf2._last_knowledge_result is not None
    assert wf2._last_knowledge_result.succeeded is False
    assert _source_ids(_reload_vector(vpath).entries()) == {
        "a.md": ["a.md::chunk_0", "a.md::chunk_1"]
    }


def test_indexing_save_failure_preserves_prior_data_on_disk(
    tmp_path: Path, monkeypatch: object
) -> None:
    vpath = tmp_path / "vstore.json"
    embedder = _Embedder()

    store = VectorStore(persistence_path=vpath)
    wf = _workflow(
        chunks=[_chunk("a.md", 0), _chunk("a.md", 1)],
        vector_store=store,
        graph_path=None,
        embedder=embedder,
        kg_builder=_KGBuilder(),
    )
    _run(wf, "a.md")

    store2 = VectorStore(persistence_path=vpath)

    def _boom() -> None:
        raise OSError("disk full")

    monkeypatch.setattr(store2, "save", _boom)  # type: ignore[attr-defined]
    wf2 = _workflow(
        chunks=[_chunk("a.md", 10), _chunk("a.md", 11)],
        vector_store=store2,
        graph_path=None,
        embedder=embedder,
        kg_builder=_KGBuilder(),
    )
    _run(wf2, "a.md")

    assert wf2._last_knowledge_result is not None
    assert wf2._last_knowledge_result.succeeded is False
    assert _source_ids(_reload_vector(vpath).entries()) == {
        "a.md": ["a.md::chunk_0", "a.md::chunk_1"]
    }


def test_retry_after_failure_replaces_cleanly_on_disk(tmp_path: Path) -> None:
    vpath = tmp_path / "vstore.json"
    embedder = _Embedder()

    store = VectorStore(persistence_path=vpath)
    wf = _workflow(
        chunks=[_chunk("a.md", 0), _chunk("a.md", 1)],
        vector_store=store,
        graph_path=None,
        embedder=embedder,
        kg_builder=_KGBuilder(),
    )
    _run(wf, "a.md")

    embedder.fail_next = True
    store2 = VectorStore(persistence_path=vpath)
    wf2 = _workflow(
        chunks=[_chunk("a.md", 0), _chunk("a.md", 1)],
        vector_store=store2,
        graph_path=None,
        embedder=embedder,
        kg_builder=_KGBuilder(),
    )
    _kg, stored, _links = _run(wf2, "a.md")
    assert stored == 0

    store3 = VectorStore(persistence_path=vpath)
    wf3 = _workflow(
        chunks=[_chunk("a.md", 20), _chunk("a.md", 21)],
        vector_store=store3,
        graph_path=None,
        embedder=embedder,
        kg_builder=_KGBuilder(),
    )
    _kg, stored, _links = _run(wf3, "a.md")

    assert stored == 2
    assert wf3._last_knowledge_result is not None
    assert wf3._last_knowledge_result.succeeded is True
    ids = _source_ids(_reload_vector(vpath).entries())["a.md"]
    assert ids == ["a.md::chunk_20", "a.md::chunk_21"]
    assert len(ids) == len(set(ids))


# ── STEP 4/6: crash semantics — in-memory mutation does not persist ────────


def test_in_memory_mutation_not_persisted_without_save(tmp_path: Path) -> None:
    vpath = tmp_path / "vstore.json"
    store = VectorStore(persistence_path=vpath)
    store.add_batch([_entry("a.md", 0)])
    store.save()

    store2 = VectorStore(persistence_path=vpath)
    store2.remove_by_source("a.md")
    store2.add_batch([_entry("a.md", 1)])
    # no store2.save() — simulates a crash between remove+add and persistence

    assert _source_ids(_reload_vector(vpath).entries()) == {
        "a.md": ["a.md::chunk_0"]
    }


# ── STEP 4: knowledge graph replacement semantics ─────────────────────────


def test_kg_success_replaces_source_nodes_and_keeps_others(tmp_path: Path) -> None:
    gpath = tmp_path / "graph.json"
    embedder = _Embedder()
    kg_builder = _KGBuilder()

    g = KnowledgeGraph()
    g.add_node(
        KnowledgeNode(
            id="other.md::x", label="X", node_type="concept", source="other.md"
        )
    )
    g.save(gpath)

    store = VectorStore(persistence_path=tmp_path / "vstore.json")
    store.add_batch([_entry("other.md", 0)])

    wf = _workflow(
        chunks=[_chunk("a.md", 0)],
        vector_store=store,
        graph_path=gpath,
        embedder=embedder,
        kg_builder=kg_builder,
    )
    _run(wf, "a.md")

    wf2 = _workflow(
        chunks=[_chunk("a.md", 1)],
        vector_store=store,
        graph_path=gpath,
        embedder=embedder,
        kg_builder=kg_builder,
    )
    _run(wf2, "a.md")

    reloaded = KnowledgeGraph.load(gpath)
    # a.md replaced by its latest node; unrelated source untouched
    assert sorted(n.id for n in reloaded.nodes.values()) == ["a.md::n1", "other.md::x"]
    assert sorted(n.source for n in reloaded.nodes.values()) == ["a.md", "other.md"]


def test_kg_failure_preserves_prior_graph_on_disk(tmp_path: Path) -> None:
    gpath = tmp_path / "graph.json"
    embedder = _Embedder()
    kg_builder = _KGBuilder()

    store = VectorStore()
    wf = _workflow(
        chunks=[_chunk("a.md", 0)],
        vector_store=store,
        graph_path=gpath,
        embedder=embedder,
        kg_builder=kg_builder,
    )
    _run(wf, "a.md")
    assert _node_ids(KnowledgeGraph.load(gpath)) == ["a.md::n1"]

    kg_builder.fail_build = True
    store2 = VectorStore()
    wf2 = _workflow(
        chunks=[_chunk("a.md", 1)],
        vector_store=store2,
        graph_path=gpath,
        embedder=embedder,
        kg_builder=kg_builder,
    )
    _run(wf2, "a.md")

    assert wf2._last_knowledge_result is not None
    assert wf2._last_knowledge_result.graph_succeeded is False
    assert _node_ids(KnowledgeGraph.load(gpath)) == ["a.md::n1"]


def test_failed_vector_ingest_leaves_graph_untouched_on_disk(tmp_path: Path) -> None:
    gpath = tmp_path / "graph.json"
    embedder = _Embedder()
    kg_builder = _KGBuilder()

    store = VectorStore()
    wf = _workflow(
        chunks=[_chunk("a.md", 0)],
        vector_store=store,
        graph_path=gpath,
        embedder=embedder,
        kg_builder=kg_builder,
    )
    _run(wf, "a.md")
    assert _node_ids(KnowledgeGraph.load(gpath)) == ["a.md::n1"]

    embedder.fail_next = True  # vector step fails -> outcome.succeeded False
    store2 = VectorStore()
    wf2 = _workflow(
        chunks=[_chunk("a.md", 0)],
        vector_store=store2,
        graph_path=gpath,
        embedder=embedder,
        kg_builder=kg_builder,
    )
    _run(wf2, "a.md")

    assert wf2._last_knowledge_result is not None
    assert wf2._last_knowledge_result.succeeded is False
    assert _node_ids(KnowledgeGraph.load(gpath)) == ["a.md::n1"]


# ── STEP 5: identical-SHA different-path dedup stays safe ─────────────────


def test_identical_hash_different_path_dedups_safely(tmp_path: Path) -> None:
    from app.infrastructure.state.hashing import compute_file_hash

    manifest = ManifestManager(tmp_path / "manifest.json", project_root=tmp_path)
    p1 = tmp_path / "one.md"
    p2 = tmp_path / "two.md"
    p1.write_text("identical content", encoding="utf-8")
    p2.write_text("identical content", encoding="utf-8")

    digest = compute_file_hash(p1)
    assert compute_file_hash(p2) == digest  # identical SHA

    manifest.add_processed_file(
        path=p1, sha256=digest, extension="md", status="processed",
    )
    assert manifest.contains_successful_hash(digest) is True
    # re-drop of the identical-content sibling dedups at the ledger gate
    assert manifest.contains_successful_hash(compute_file_hash(p2)) is True
    # store identity stays path-scoped: replacement targets the ingested path
    assert manifest.contains_path(p2) is False
    assert manifest.contains_path(p1) is True


# ── V1.1.1 D5: fail closed on an unreadable vector store ───────────────────
#
# A store that failed to load looks EMPTY, so continuing would save only the
# new entries and silently destroy every other source's vectors.  The guard
# lives in IngestionWorkflow.run(), so it covers the shared CLI / queue / GUI
# path and must fire before ANY durable write.


def _run_workflow(
    *,
    chunks: list[DocumentChunk],
    vector_store: Any,
    graph_path: Path | None,
    embedder: _Embedder | None = None,
    kg_builder: _KGBuilder | None = None,
) -> IngestionWorkflow:
    """Workflow wired for the public run() entry point the CLI/queue/GUI use."""
    ingestion_service = MagicMock()
    ingestion_service.ingest.return_value = SimpleNamespace(
        succeeded=True, document=_document("a.md"), error=None
    )
    chunker = MagicMock(spec=SemanticChunker)
    chunker.chunk.return_value = chunks
    return IngestionWorkflow(
        ingestion_service=ingestion_service,
        processor=MagicMock(),
        ollama_client=MagicMock(),
        note_generator=MagicMock(),
        writer=MagicMock(),
        chunker=chunker,
        embedding_service=cast(Any, embedder or _Embedder()),
        vector_store=vector_store,
        knowledge_graph_builder=cast(Any, kg_builder or _KGBuilder()),
        graph_persistence_path=graph_path,
    )


def test_corrupt_store_fails_closed_before_any_durable_write(tmp_path: Path) -> None:
    vpath = tmp_path / "vstore.json"
    gpath = tmp_path / "graph.json"
    corrupt = b'{"entries": [ this is not json'
    vpath.write_bytes(corrupt)

    store = VectorStore(persistence_path=vpath)
    assert store.load_error is not None  # the store looks empty but is unreadable

    wf = _run_workflow(
        chunks=[_chunk("a.md", 0), _chunk("a.md", 1)],
        vector_store=store,
        graph_path=gpath,
    )

    with pytest.raises(IngestionWorkflowError) as excinfo:
        wf.run("a.md")

    assert excinfo.value.category == "unreadable_state"
    assert "index could not be read" in str(excinfo.value)
    # the corrupt file is byte-identical and no atomic-write temp file is left
    assert vpath.read_bytes() == corrupt
    assert list(tmp_path.glob("*.tmp")) == []
    # no durable write of any kind happened
    wf._writer.save.assert_not_called()
    wf._writer.create_placeholder.assert_not_called()
    assert not gpath.exists()
    # the guard precedes even reading the source
    wf._ingestion_service.ingest.assert_not_called()


def test_corrupt_store_leaves_prior_graph_and_bytes_untouched(tmp_path: Path) -> None:
    vpath = tmp_path / "vstore.json"
    gpath = tmp_path / "graph.json"

    healthy = _run_workflow(
        chunks=[_chunk("a.md", 0)],
        vector_store=VectorStore(persistence_path=vpath),
        graph_path=gpath,
    )
    healthy.run("a.md")
    assert _node_ids(KnowledgeGraph.load(gpath)) == ["a.md::n1"]
    graph_before = gpath.read_bytes()

    corrupt = b"totally corrupt"
    vpath.write_bytes(corrupt)
    store = VectorStore(persistence_path=vpath)
    assert store.load_error is not None

    wf = _run_workflow(
        chunks=[_chunk("a.md", 5)],
        vector_store=store,
        graph_path=gpath,
    )
    with pytest.raises(IngestionWorkflowError) as excinfo:
        wf.run("a.md")

    assert excinfo.value.category == "unreadable_state"
    assert vpath.read_bytes() == corrupt
    assert list(tmp_path.glob("*.tmp")) == []
    assert gpath.read_bytes() == graph_before
    wf._writer.save.assert_not_called()


def test_healthy_store_still_ingests_normally_via_run(tmp_path: Path) -> None:
    vpath = tmp_path / "vstore.json"
    store = VectorStore(persistence_path=vpath)
    store.add_batch([_entry("other.md", 0)])
    store._version = 0

    wf = _run_workflow(chunks=[_chunk("a.md", 0)], vector_store=store, graph_path=None)
    result = wf.run("a.md")

    assert wf._writer.save.call_count == 1
    assert result.chunks_stored == 1
    assert wf._last_knowledge_result is not None
    assert wf._last_knowledge_result.succeeded is True
    # the pre-existing source survives alongside the new one
    assert _source_ids(_reload_vector(vpath).entries()) == {
        "a.md": ["a.md::chunk_0"],
        "other.md": ["other.md::chunk_0"],
    }


def test_missing_store_first_ingest_still_succeeds(tmp_path: Path) -> None:
    vpath = tmp_path / "vstore.json"
    assert not vpath.exists()

    store = VectorStore(persistence_path=vpath)
    assert store.load_error is None  # absent store is a valid first-run state

    wf = _run_workflow(chunks=[_chunk("a.md", 0)], vector_store=store, graph_path=None)
    wf.run("a.md")

    assert wf._writer.save.call_count == 1
    assert _source_ids(_reload_vector(vpath).entries()) == {"a.md": ["a.md::chunk_0"]}


def test_stub_store_without_load_error_is_not_blocked() -> None:
    """A MagicMock store (as used by knowledge-engine tests) is not a real
    VectorStore, so its truthy mock load_error must not trip the guard."""
    wf = _run_workflow(
        chunks=[_chunk("a.md", 0)],
        vector_store=MagicMock(),
        graph_path=None,
    )
    result = wf.run("a.md")
    assert wf._writer.save.call_count == 1
    assert result.chunks_stored == 1