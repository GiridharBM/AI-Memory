"""P5-103 scoring verification — RRF formula, determinism, limits, extremes.

The frozen spec (MEDD §7.6, roadmap §4.2) fixes the retrieval scoring as
Reciprocal Rank Fusion with k=60: each ranked leg contributes ``1/(k + rank)``
per candidate; fused ties resolve by entry id. Scores are never normalized
(RRF works on ranks), and no metadata/quality boosters apply (the spec names
none). These tests lock that behavior against the P5-101/P5-102 layers.
"""

from __future__ import annotations

import pytest

from app.domain.vector_store import VectorEntry
from app.infrastructure.search import HybridSearch, SearchService, _rrf_fuse
from app.infrastructure.vector_store import VectorStore, _cosine_similarity

# RRF k=60 anchor values used by exact-score assertions.
R1 = 1.0 / 61.0
R2 = 1.0 / 62.0
R1_BOTH = 2.0 / 61.0
R2_BOTH = 2.0 / 62.0


def _store_with(*entries: VectorEntry) -> VectorStore:
    store = VectorStore()
    store.add_batch(list(entries))
    return store


class TestRrfFormula:
    def test_single_rank_value(self) -> None:
        assert _rrf_fuse(["a"]) == [("a", pytest.approx(R1))]

    def test_multi_rank_descending(self) -> None:
        fused = _rrf_fuse(["a", "b", "c"])
        assert fused[0][1] == pytest.approx(R1)
        assert fused[1][1] == pytest.approx(R2)
        assert fused[2][1] < fused[1][1]

    def test_dual_list_accumulates(self) -> None:
        fused = _rrf_fuse(["a", "b"], ["a", "c"])
        assert fused == [
            ("a", pytest.approx(R1_BOTH)),
            ("b", pytest.approx(R2)),
            ("c", pytest.approx(R2)),
        ]

    def test_custom_k(self) -> None:
        assert _rrf_fuse(["a"], k=10) == [("a", pytest.approx(1.0 / 11.0))]

    def test_ties_resolve_by_id(self) -> None:
        fused = _rrf_fuse(["b", "a"], ["a", "b"])
        # a and b both score 1/61 + 1/62 (one rank-1, one rank-2 leg each);
        # the equal fused scores resolve by entry id.
        assert fused == [
            ("a", pytest.approx(R1 + R2)),
            ("b", pytest.approx(R1 + R2)),
        ]

    def test_no_lists_returns_empty(self) -> None:
        assert _rrf_fuse() == []
        assert _rrf_fuse([], []) == []

    def test_duplicate_id_in_single_list_accumulates(self) -> None:
        fused = _rrf_fuse(["a", "a"])
        assert fused == [("a", pytest.approx(R1 + R2))]


class TestCosineExtremes:
    def test_identical_vectors_score_one(self) -> None:
        assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self) -> None:
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_score_negative_one(self) -> None:
        assert _cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_zero_vector_scores_zero(self) -> None:
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)

    def test_dimension_mismatch_scores_zero(self) -> None:
        assert _cosine_similarity([1.0], [1.0, 0.0]) == pytest.approx(0.0)

    def test_negative_scores_excluded_by_default(self) -> None:
        store = _store_with(
            VectorEntry(id="e1", text="near", embedding=[1.0, 0.0]),
            VectorEntry(id="e2", text="away", embedding=[-1.0, 0.0]),
        )
        results = store.search([1.0, 0.0], top_k=5)
        assert [r.entry.id for r in results] == ["e1"]

    def test_negative_min_score_admits_negative_cosine(self) -> None:
        store = _store_with(
            VectorEntry(id="e1", text="near", embedding=[1.0, 0.0]),
            VectorEntry(id="e2", text="away", embedding=[-1.0, 0.0]),
        )
        results = store.search([1.0, 0.0], top_k=5, min_score=-1.0)
        assert [r.entry.id for r in results] == ["e1", "e2"]


class TestCombinedScoreOrdering:
    def test_both_legs_outranks_single_leg(self) -> None:
        store = _store_with(
            VectorEntry(id="e1", text="python async", embedding=[1.0, 0.0]),
            VectorEntry(id="e2", text="async internals", embedding=[0.0, 1.0]),
        )
        hits = HybridSearch(store).search("python async", [1.0, 0.0], top_k=5)
        # e1: dense rank 1 + lexical rank 1 = 2/61; e2: both legs rank 2 = 2/62.
        assert [h.entry_id for h in hits] == ["e1", "e2"]
        assert hits[0].score == pytest.approx(R1_BOTH)
        assert hits[1].score == pytest.approx(R2_BOTH)

    def test_lexical_leg_breaks_dense_tie(self) -> None:
        store = _store_with(
            VectorEntry(id="e1", text="python", embedding=[1.0, 0.0]),
            VectorEntry(id="e2", text="java", embedding=[1.0, 0.0]),
        )
        hits = HybridSearch(store).search("python", [1.0, 0.0], top_k=5)
        # Dense leg ties (both cosine 1.0, id order e1/e2); the lexical leg
        # boosts e1 (exact "python" match) above e2 (no match).
        assert [h.entry_id for h in hits] == ["e1", "e2"]
        assert hits[0].score == pytest.approx(R1_BOTH)
        assert hits[1].score == pytest.approx(R2)

    def test_min_score_separates_fused_scores(self) -> None:
        store = _store_with(
            VectorEntry(id="e1", text="python async", embedding=[1.0, 0.0]),
            VectorEntry(id="e2", text="async internals", embedding=[0.0, 1.0]),
        )
        hs = HybridSearch(store)
        cutoff = (R1_BOTH + R2_BOTH) / 2.0
        hits = hs.search("python async", [1.0, 0.0], min_score=cutoff)
        assert [h.entry_id for h in hits] == ["e1"]


class TestTopKBoundaries:
    def test_zero_and_negative_top_k(self) -> None:
        store = _store_with(VectorEntry(id="e1", text="python", embedding=[1.0, 0.0]))
        assert store.search([1.0, 0.0], top_k=0) == []
        assert HybridSearch(store).search("python", [1.0, 0.0], top_k=0) == []
        assert SearchService(store, embed=lambda q: [1.0, 0.0]).search("python", top_k=-1) == []

    def test_top_k_one(self) -> None:
        store = _store_with(
            VectorEntry(id="e1", text="python async", embedding=[1.0, 0.0]),
            VectorEntry(id="e2", text="async internals", embedding=[0.0, 1.0]),
        )
        hits = HybridSearch(store).search("python async", [1.0, 0.0], top_k=1)
        assert [h.entry_id for h in hits] == ["e1"]

    def test_top_k_exceeds_corpus(self) -> None:
        store = _store_with(VectorEntry(id="e1", text="python", embedding=[1.0, 0.0]))
        assert len(store.search([1.0, 0.0], top_k=50)) == 1


class TestDuplicateCandidates:
    def test_cross_leg_overlap_single_fused_hit(self) -> None:
        store = _store_with(VectorEntry(id="e1", text="python", embedding=[1.0, 0.0]))
        hits = HybridSearch(store).search("python", [1.0, 0.0], top_k=5)
        assert [h.entry_id for h in hits] == ["e1"]
        assert hits[0].score == pytest.approx(R1_BOTH)

    def test_store_dedups_duplicate_ids(self) -> None:
        store = VectorStore()
        store.add_batch([
            VectorEntry(id="e1", text="first", embedding=[1.0, 0.0]),
            VectorEntry(id="e1", text="second", embedding=[1.0, 0.0]),
        ])
        assert len(store.search([1.0, 0.0], top_k=5)) == 1


class TestEmptyResults:
    def test_empty_store_all_layers(self) -> None:
        store = VectorStore()
        assert store.search([1.0, 0.0]) == []
        assert HybridSearch(store).search("python", [1.0, 0.0]) == []
        assert SearchService(store, embed=lambda q: [1.0, 0.0]).search("python") == []

    def test_blank_query(self) -> None:
        store = _store_with(VectorEntry(id="e1", text="python", embedding=[1.0, 0.0]))
        # HybridSearch skips the lexical leg on blank text but keeps dense.
        assert [h.entry_id for h in HybridSearch(store).search("", [1.0, 0.0])] == ["e1"]
        # SearchService short-circuits entirely on blank queries.
        assert SearchService(store, embed=lambda q: [1.0, 0.0]).search("   ") == []

    def test_no_matches_anywhere(self) -> None:
        store = _store_with(VectorEntry(id="e1", text="python", embedding=[1.0, 0.0]))
        assert HybridSearch(store).search("zzz", None) == []
        assert SearchService(store, embed=lambda q: None).search("zzz") == []


class TestDeterministicRuns:
    def test_store_repeated_runs_shuffled_insertion(self) -> None:
        store = VectorStore()
        for eid in ("e3", "e1", "e2"):
            store.add(VectorEntry(id=eid, text=eid, embedding=[1.0, 0.0]))
        first = store.search([1.0, 0.0], top_k=5)
        second = store.search([1.0, 0.0], top_k=5)
        assert [r.entry.id for r in first] == ["e1", "e2", "e3"]
        assert [r.entry.id for r in second] == ["e1", "e2", "e3"]

    def test_hybrid_repeated_runs(self) -> None:
        store = VectorStore()
        for eid in ("e3", "e1", "e2"):
            store.add(VectorEntry(id=eid, text=eid, embedding=[1.0, 0.0]))
        hs = HybridSearch(store)
        first = [h.entry_id for h in hs.search("query", [1.0, 0.0], top_k=5)]
        second = [h.entry_id for h in hs.search("query", [1.0, 0.0], top_k=5)]
        assert first == second == ["e1", "e2", "e3"]

    def test_fuse_repeated_runs(self) -> None:
        first = _rrf_fuse(["a", "b", "c"], ["c", "b", "a"])
        second = _rrf_fuse(["a", "b", "c"], ["c", "b", "a"])
        assert first == second
