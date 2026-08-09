"""P5-104 query pipeline tests — canonical entry, wiring, complete query path.
P5-105 additions — large/sparse/empty corpora, cache invalidation, and the
precomputed-norm fast path (all deterministic and correctness-preserving).

``SearchService`` (MEDD §7.6) is the canonical query entry point; P5-104 adds
``SearchService.create_default`` so a query flows through production wiring
(settings → persisted store → embed → hybrid retrieval → RRF ranking →
filter → top-k) without duplicating pipeline logic.
"""

from __future__ import annotations

import math
import random

import pytest

from app.core.config import Settings
from app.domain.vector_store import VectorEntry
from app.infrastructure import search as search_module
from app.infrastructure.search import HybridSearch, SearchService
from app.infrastructure.vector_store import VectorStore, _cosine_similarity


def _seed(settings: Settings) -> None:
    store = VectorStore(
        persistence_path=settings.paths.manifest_root / "vector_store.json",
    )
    store.add_batch([
        VectorEntry(
            id="doc.py::chunk_0", text="python is great",
            embedding=[1.0, 0.0, 0.0], source="doc.py", source_type="pdf",
            chunk_index=0, start_char=0, end_char=16, metadata={"heading": "Intro"},
        ),
        VectorEntry(
            id="doc.py::chunk_1", text="rust is fast",
            embedding=[0.0, 1.0, 0.0], source="doc.py", source_type="pdf",
            chunk_index=1, start_char=16, end_char=30, metadata={"heading": "Outro"},
        ),
        VectorEntry(
            id="other.md::chunk_0", text="java is okay",
            embedding=[0.9, 0.1, 0.0], source="other.md", source_type="markdown",
            chunk_index=0, start_char=0, end_char=13,
        ),
    ])
    store.save()


class TestCreateDefaultWiring:
    def test_loads_persisted_store(self, tmp_settings: Settings) -> None:
        _seed(tmp_settings)
        service = SearchService.create_default(tmp_settings, embed=lambda q: [1.0, 0.0, 0.0])
        hits = service.search("python", top_k=5)
        assert hits[0].entry_id == "doc.py::chunk_0"
        assert hits[0].source == "doc.py"
        assert hits[0].source_type == "pdf"
        assert hits[0].metadata == {"heading": "Intro"}

    def test_missing_store_returns_empty(self, tmp_settings: Settings) -> None:
        service = SearchService.create_default(tmp_settings, embed=lambda q: [1.0, 0.0])
        assert service.search("python") == []


class TestCompleteQueryPath:
    def test_normal_query(self, tmp_settings: Settings) -> None:
        _seed(tmp_settings)
        svc = SearchService.create_default(tmp_settings, embed=lambda q: [1.0, 0.0, 0.0])
        hits = svc.search("python")
        assert len(hits) >= 1
        assert hits[0].entry_id == "doc.py::chunk_0"

    def test_empty_and_whitespace_query(self, tmp_settings: Settings) -> None:
        _seed(tmp_settings)
        calls: list[str] = []

        def _embed(q: str) -> list[float]:
            calls.append(q)
            return [1.0, 0.0]

        svc = SearchService.create_default(tmp_settings, embed=_embed)
        assert svc.search("") == []
        assert svc.search("   ") == []
        assert calls == []

    def test_multiple_results(self, tmp_settings: Settings) -> None:
        _seed(tmp_settings)
        svc = SearchService.create_default(tmp_settings, embed=lambda q: [1.0, 0.0, 0.0])
        hits = svc.search("python", top_k=5)
        assert len(hits) == 3
        assert [h.entry_id for h in hits] == [
            "doc.py::chunk_0", "other.md::chunk_0", "doc.py::chunk_1",
        ]

    def test_no_result_query(self, tmp_settings: Settings) -> None:
        _seed(tmp_settings)
        svc = SearchService.create_default(tmp_settings, embed=lambda q: None)
        assert svc.search("zzz") == []

    def test_filtered_query(self, tmp_settings: Settings) -> None:
        _seed(tmp_settings)
        svc = SearchService.create_default(tmp_settings, embed=lambda q: [1.0, 0.0, 0.0])
        hits = svc.search("python", top_k=5, filter={"source_type": "markdown"})
        assert [h.entry_id for h in hits] == ["other.md::chunk_0"]

    def test_top_k_query(self, tmp_settings: Settings) -> None:
        _seed(tmp_settings)
        svc = SearchService.create_default(tmp_settings, embed=lambda q: [1.0, 0.0, 0.0])
        assert len(svc.search("python", top_k=1)) == 1

    def test_min_score_query(self, tmp_settings: Settings) -> None:
        _seed(tmp_settings)
        svc = SearchService.create_default(tmp_settings, embed=lambda q: [1.0, 0.0, 0.0])
        # Only doc.py::chunk_0 clears a high RRF threshold (both legs).
        assert [h.entry_id for h in svc.search("python", min_score=0.03)] == [
            "doc.py::chunk_0",
        ]

    def test_repeated_identical_query_deterministic(self, tmp_settings: Settings) -> None:
        _seed(tmp_settings)
        svc = SearchService.create_default(tmp_settings, embed=lambda q: [1.0, 0.0, 0.0])
        first = [h.entry_id for h in svc.search("python", top_k=5)]
        second = [h.entry_id for h in svc.search("python", top_k=5)]
        assert first == second == [
            "doc.py::chunk_0", "other.md::chunk_0", "doc.py::chunk_1",
        ]


class TestEmbeddingAvoidanceAndFallback:
    def test_embed_called_once_per_query(self, tmp_settings: Settings) -> None:
        _seed(tmp_settings)
        calls: list[str] = []

        def _embed(q: str) -> list[float]:
            calls.append(q)
            return [1.0, 0.0, 0.0]

        svc = SearchService.create_default(tmp_settings, embed=_embed)
        svc.search("python")
        assert len(calls) == 1

    def test_embedder_failure_falls_back_to_lexical(self, tmp_settings: Settings) -> None:
        _seed(tmp_settings)

        def _fail(_q: str) -> list[float]:
            raise RuntimeError("ollama down")

        svc = SearchService.create_default(tmp_settings, embed=_fail)
        # "python" matches only doc.py::chunk_0 lexically; no crash.
        assert [h.entry_id for h in svc.search("python", top_k=5)] == ["doc.py::chunk_0"]


def _make_entries(
    n: int,
    *,
    dim: int = 8,
    seed: int = 7,
    vocab: tuple[str, ...] = (
        "alpha beta gamma delta epsilon zeta eta theta knowledge retrieval engine "
        "search query vector semantic sparse dense rank score fusion fast cache"
    ).split(),
) -> list[VectorEntry]:
    rng = random.Random(seed)
    entries: list[VectorEntry] = []
    for i in range(n):
        words = " ".join(rng.choice(vocab) for _ in range(rng.randint(6, 18)))
        vec = [rng.gauss(0, 1) for _ in range(dim)]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        entries.append(
            VectorEntry(
                id=f"doc{i // 5}.md::chunk{i % 5}",
                text=words,
                embedding=[x / norm for x in vec],
                source=f"doc{i // 5}.md",
                source_type="markdown",
                chunk_index=i % 5,
                metadata={"heading": f"h{i % 4}"},
            )
        )
    return entries


class TestLargeCorpus:
    def test_retrieval_over_5000_entries(self) -> None:
        store = VectorStore()
        store.add_batch(_make_entries(5000))
        svc = SearchService(store, embed=lambda q: [0.25] * 8)

        hits = svc.search("knowledge retrieval", top_k=10)

        assert len(hits) == 10
        assert len({h.entry_id for h in hits}) == 10
        assert all(h.score > 0.0 for h in hits)

    def test_large_corpus_is_deterministic(self) -> None:
        store = VectorStore()
        store.add_batch(_make_entries(5000))
        svc = SearchService(store, embed=lambda q: [0.25] * 8)

        first = [(h.entry_id, h.score) for h in svc.search("rank fusion", top_k=10)]
        second = [(h.entry_id, h.score) for h in svc.search("rank fusion", top_k=10)]
        assert first == second

    def test_large_corpus_top_k_and_filter(self) -> None:
        store = VectorStore()
        store.add_batch(_make_entries(5000))
        svc = SearchService(store, embed=lambda q: [0.25] * 8)

        assert len(svc.search("engine", top_k=3)) == 3
        hits = svc.search("engine", top_k=10, filter={"source_type": "markdown"})
        assert {h.source_type for h in hits} == {"markdown"}

    def test_large_corpus_no_match_returns_empty(self) -> None:
        store = VectorStore()
        store.add_batch(_make_entries(5000))
        # Lexical-only path: a term absent from the whole corpus matches nothing.
        svc = SearchService(store, embed=lambda q: None)

        assert svc.search("zzz-no-such-term") == []


class TestSparseDataset:
    def test_zero_norm_entries_included_at_min_score_zero(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="zero", text="dead text", embedding=[0.0, 0.0]))
        store.add(VectorEntry(id="dim", text="wrong dim", embedding=[1.0]))
        store.add(VectorEntry(id="live", text="match", embedding=[1.0, 0.0]))

        results = store.search([1.0, 0.0], top_k=5, min_score=0.0)

        # Zero-vector and dim-mismatch entries score 0.0 and are included at
        # min_score=0.0 (matches pre-optimization _cosine_similarity semantics);
        # among equal 0.0 scores the id tie-break is ascending.
        assert [r.entry.id for r in results] == ["live", "dim", "zero"]

    def test_zero_norm_entries_excluded_by_min_score(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="zero", text="dead", embedding=[0.0, 0.0]))
        store.add(VectorEntry(id="live", text="match", embedding=[1.0, 0.0]))

        results = store.search([1.0, 0.0], top_k=5, min_score=0.5)

        assert [r.entry.id for r in results] == ["live"]

    def test_sparse_queries_never_crash(self) -> None:
        store = VectorStore()
        store.add_batch(
            [
                VectorEntry(id="a", text="alpha", embedding=[1.0, 0.0, 0.0]),
                VectorEntry(id="b", text="beta", embedding=[0.0, 0.0, 0.0]),
            ]
        )
        svc = SearchService(store, embed=lambda q: None)
        assert isinstance(svc.search("alpha", top_k=5), list)


class TestPrecomputedNorms:
    def test_scores_match_cosine_similarity_bit_for_bit(self) -> None:
        store = VectorStore()
        entries = _make_entries(200)
        store.add_batch(entries)

        query = [0.3, -0.1, 0.7, 0.2, 0.5, -0.4, 0.1, 0.9]
        results = store.search(query, top_k=200, min_score=-1.0)

        for result in results:
            expected = _cosine_similarity(query, result.entry.embedding)
            assert result.score == expected

    def test_scores_identical_across_repeated_queries(self) -> None:
        store = VectorStore()
        store.add_batch(_make_entries(300))

        query = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        first = [(r.entry.id, r.score) for r in store.search(query, top_k=50)]
        second = [(r.entry.id, r.score) for r in store.search(query, top_k=50)]
        assert first == second

    def test_search_results_unchanged_by_optimization(self) -> None:
        """Optimized path must return the same result ids as the function."""
        store = VectorStore()
        store.add_batch(_make_entries(150))

        query = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        results = store.search(query, top_k=10)
        scores = {r.entry.id: r.score for r in results}
        for entry in store.entries():
            if entry.id in scores:
                assert scores[entry.id] == _cosine_similarity(query, entry.embedding)

    def test_empty_embedding_handled(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e", text="x", embedding=[]))
        # Empty query vector scores 0.0 against an empty entry and, at
        # min_score=0.0, is included — same as pre-optimization behavior.
        results = store.search([], top_k=5, min_score=0.0)
        assert [(r.entry.id, r.score) for r in results] == [("e", 0.0)]
        assert store.search([], top_k=5, min_score=0.1) == []


class TestStoreVersion:
    def test_version_bumps_on_mutations(self) -> None:
        store = VectorStore()
        assert store.version == 0
        store.add(VectorEntry(id="a", text="a", embedding=[1.0]))
        assert store.version == 1
        store.add_batch(
            [
                VectorEntry(id="b", text="b", embedding=[1.0]),
                VectorEntry(id="c", text="c", embedding=[1.0]),
            ]
        )
        assert store.version == 2
        assert store.remove("a") is True
        assert store.version == 3
        assert store.remove("missing") is False
        assert store.version == 3
        store.add(VectorEntry(id="a", text="a", embedding=[1.0]))
        assert store.version == 4

    def test_version_bumps_on_load(self, tmp_settings: Settings) -> None:
        store = VectorStore(persistence_path=tmp_settings.paths.manifest_root / "v.json")
        store.add_batch([VectorEntry(id="x", text="x", embedding=[1.0])])
        store.save()
        reloaded = VectorStore(persistence_path=tmp_settings.paths.manifest_root / "v.json")
        assert reloaded.version == 1
        assert len(reloaded.entries()) == 1


class TestBm25CacheInvalidation:
    def test_add_after_query_is_reflected(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="a", text="python basics", embedding=[1.0, 0.0]))
        svc = SearchService(store, embed=lambda q: [1.0, 0.0])

        assert svc.search("python", top_k=5)[0].entry_id == "a"
        store.add(VectorEntry(id="b", text="python advanced", embedding=[0.9, 0.1]))
        # Lexical leg must reflect the new entry (index invalidated by version).
        hits = svc.search("python advanced", top_k=5)
        assert "b" in {h.entry_id for h in hits}

    def test_remove_after_query_is_reflected(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="a", text="python basics", embedding=[1.0, 0.0]))
        store.add(VectorEntry(id="b", text="python advanced", embedding=[0.9, 0.1]))
        svc = SearchService(store, embed=lambda q: [1.0, 0.0])

        assert len(svc.search("python", top_k=5)) == 2
        store.remove("b")
        hits = svc.search("python", top_k=5)
        assert {h.entry_id for h in hits} == {"a"}

    def test_repeated_query_reuses_index(self) -> None:
        store = VectorStore()
        store.add_batch(_make_entries(500))
        svc = SearchService(store, embed=lambda q: [0.5] * 8)

        first = [(h.entry_id, h.score) for h in svc.search("retrieval", top_k=5)]
        # No mutation between queries: cache must be stable and identical.
        second = [(h.entry_id, h.score) for h in svc.search("retrieval", top_k=5)]
        assert first == second
        assert store.version == svc._hybrid._bm25_version


class TestFallbackBehavior:
    def test_bm25_build_failure_falls_back_to_dense(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A broken/disabled lexical leg degrades to dense-only (roadmap 4.1)."""
        store = VectorStore()
        store.add(VectorEntry(id="a", text="python basics", embedding=[1.0, 0.0]))

        def _boom(_corpus: list[str], **_: object) -> object:
            raise RuntimeError("bm25 broken")

        monkeypatch.setattr(search_module, "BM25Index", _boom)

        hs = HybridSearch(store)
        hits = hs.search("python basics", [1.0, 0.0], top_k=5)

        assert [h.entry_id for h in hits] == ["a"]
        # Dense leg is intact; the failure was contained to the lexical leg.
        assert len(store.search([1.0, 0.0], top_k=5)) == 1
        # A later successful build recovers the full path (no poisoned cache).
        monkeypatch.undo()
        hits = HybridSearch(store).search("python basics", [1.0, 0.0], top_k=5)
        assert [h.entry_id for h in hits] == ["a"]

    def test_blank_query_with_cached_index_returns_dense_only(self) -> None:
        store = VectorStore()
        store.add_batch(_make_entries(100))
        hs = HybridSearch(store)
        # Warm the lexical cache, then a blank query must not search it.
        hs.search("engine", [0.5] * 8, top_k=5)
        hits = hs.search("", [0.5] * 8, top_k=5)
        assert len(hits) == 5
