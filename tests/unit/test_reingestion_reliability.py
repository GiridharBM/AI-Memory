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

from app.domain.documents import DocumentMetadata, SourceDocument
from app.domain.knowledge_graph import KnowledgeGraph, KnowledgeNode
from app.domain.semantic_chunking import DocumentChunk
from app.domain.vector_store import VectorEntry
from app.infrastructure.embeddings import EmbeddingResult
from app.infrastructure.semantic_chunking import SemanticChunker
from app.infrastructure.state.manifest import ManifestManager
from app.infrastructure.vector_store import VectorStore
from app.pipelines.ingest_workflow import IngestionWorkflow


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
    wf2 = _workflow(
        chunks=[_chunk("a.md", 10), _chunk("a.md", 11)],
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