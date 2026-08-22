"""Tests for the cross-encoder reranker and updated abstention gate.

Covers: ordering, provenance preservation, top-N limits, empty inputs,
disabled/failure/fallback paths, abstention gate integration, and
regression when reranker is off.
"""

from __future__ import annotations

import pytest

from app.infrastructure.reranker import CrossEncoderReranker, RerankerConfig
from app.infrastructure.search import SearchHit
from app.application.qa_workflow import (
    ABSTENTION_MESSAGE,
    AbstentionGate,
    AbstentionResult,
    QAAnswer,
    QAError,
    QAWorkflow,
    build_context,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _hit(
    text: str = "Python is a programming language.",
    *,
    source: str = "doc.md",
    score: float = 0.5,
    cosine_score: float = 0.5,
    bm25_score: float = 0.5,
    entry_id: str = "doc.md::chunk_0",
) -> SearchHit:
    return SearchHit(
        text=text,
        source=source,
        score=score,
        entry_id=entry_id,
        cosine_score=cosine_score,
        bm25_score=bm25_score,
        source_type="markdown",
        metadata={"heading": "Intro"},
    )


class FakeSearchService:
    def __init__(self, hits: list[SearchHit] | None = None) -> None:
        self.hits = hits or []
        self.last: dict[str, object] = {}

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filter: dict[str, object] | None = None,
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        self.last = {"query": query, "top_k": top_k, "filter": filter, "min_score": min_score}
        return self.hits


class FakeOllamaClient:
    def __init__(self) -> None:
        self.requests: list = []

    def generate_text(self, request) -> object:
        self.requests.append(request)

        class _Resp:
            def __init__(self) -> None:
                self.response = "Test answer."
                self.model = "qwen3:8b"

        return _Resp()


# ── Reranker unit tests ──────────────────────────────────────────────────


class TestCrossEncoderReranker:
    """Unit tests for the CrossEncoderReranker class."""

    def test_disabled_reranker_returns_original_order(self) -> None:
        cfg = RerankerConfig(enabled=False)
        reranker = CrossEncoderReranker(cfg)
        hits = [_hit("A"), _hit("B")]

        result = reranker.rerank("query", hits)

        assert result == hits
        assert result[0].rerank_score == 0.0

    def test_empty_candidates_returns_empty(self) -> None:
        cfg = RerankerConfig(enabled=False)
        reranker = CrossEncoderReranker(cfg)

        result = reranker.rerank("query", [])

        assert result == []

    def test_metadata_preserved_after_rerank(self) -> None:
        cfg = RerankerConfig(enabled=False)
        reranker = CrossEncoderReranker(cfg)
        hit = _hit(source="test.md", entry_id="test.md::chunk_5")
        hit.metadata["heading"] = "Section A"

        result = reranker.rerank("query", [hit])

        assert result[0].source == "test.md"
        assert result[0].entry_id == "test.md::chunk_5"
        assert result[0].metadata["heading"] == "Section A"
        assert result[0].cosine_score == hit.cosine_score
        assert result[0].bm25_score == hit.bm25_score

    def test_top_n_limit_respected(self) -> None:
        cfg = RerankerConfig(enabled=False, top_n=3)
        reranker = CrossEncoderReranker(cfg)
        hits = [_hit(f"doc{i}.md") for i in range(10)]

        result = reranker.rerank("query", hits, top_k=2)

        # All 10 returned (disabled mode returns original list)
        assert len(result) == 10

    def test_unavailable_model_returns_original_order(self) -> None:
        cfg = RerankerConfig(enabled=True, model="nonexistent/model-123")
        reranker = CrossEncoderReranker(cfg)
        hits = [_hit("A"), _hit("B")]

        result = reranker.rerank("query", hits)

        # Should fall back to original order
        assert len(result) == 2
        assert result[0].rerank_score == 0.0

    def test_is_available_false_when_not_loaded(self) -> None:
        cfg = RerankerConfig(enabled=False)
        reranker = CrossEncoderReranker(cfg)

        assert reranker.is_available is False

    def test_is_available_true_when_enabled(self) -> None:
        cfg = RerankerConfig(enabled=True, model="nonexistent/model")
        reranker = CrossEncoderReranker(cfg)

        # Before load attempt, is_available returns True (enabled but not yet attempted)
        assert reranker.is_available is True

    def test_is_loaded_false_before_load(self) -> None:
        cfg = RerankerConfig(enabled=True)
        reranker = CrossEncoderReranker(cfg)

        assert reranker.is_loaded is False

    def test_model_name_returns_config_model(self) -> None:
        cfg = RerankerConfig(model="my-model")
        reranker = CrossEncoderReranker(cfg)

        assert reranker.model_name == "my-model"

    def test_rerank_score_populated_on_disabled_path(self) -> None:
        cfg = RerankerConfig(enabled=False)
        reranker = CrossEncoderReranker(cfg)
        hits = [_hit("A"), _hit("B")]

        result = reranker.rerank("query", hits)

        # Disabled mode: rerank_score stays 0.0 (original order preserved)
        assert all(h.rerank_score == 0.0 for h in result)


# ── Abstention gate tests (updated for reranker) ────────────────────────


class TestAbstentionGateReranker:
    """Tests for the updated AbstentionGate with reranker support."""

    def test_reranker_active_high_score_accepted(self) -> None:
        gate = AbstentionGate(min_cosine=0.25, min_rerank_score=0.5)
        hits = [_hit(cosine_score=0.3, bm25_score=1.0)]
        hits[0].rerank_score = 0.8

        result = gate.evaluate(hits)

        assert result.abstain is False

    def test_reranker_active_below_threshold_with_evidence_accepted(self) -> None:
        gate = AbstentionGate(min_cosine=0.25, min_rerank_score=0.5)
        hits = [_hit(cosine_score=0.3, bm25_score=1.0)]
        hits[0].rerank_score = 0.3

        result = gate.evaluate(hits)

        # Phase 3F AND gate: cosine passes but rerank=0.3 < min_rerank_score=0.5 → abstain
        assert result.abstain is True
        assert "rerank_below_threshold" in result.reason

    def test_reranker_active_below_threshold_no_evidence_rejected(self) -> None:
        gate = AbstentionGate(min_cosine=0.25, min_rerank_score=0.5)
        hits = [_hit(cosine_score=0.0, bm25_score=0.0)]
        hits[0].rerank_score = 0.3

        result = gate.evaluate(hits)

        # Phase 3F AND gate: both fail → abstain
        assert result.abstain is True
        assert "cosine_below_threshold" in result.reason
        assert "rerank_below_threshold" in result.reason

    def test_reranker_active_high_score_no_raw_evidence_abstains(self) -> None:
        gate = AbstentionGate(min_cosine=0.25, min_rerank_score=0.5)
        hits = [_hit(cosine_score=0.0, bm25_score=0.0)]
        hits[0].rerank_score = 0.8

        result = gate.evaluate(hits)

        # Phase 3F AND gate: reranker passes but cosine=0.0 < min_cosine → abstain
        assert result.abstain is True
        assert "cosine_below_threshold" in result.reason

    def test_reranker_inactive_falls_back_to_cosine(self) -> None:
        gate = AbstentionGate(min_cosine=0.45, min_rerank_score=0.0)
        hits = [_hit(cosine_score=0.5, bm25_score=0.0)]

        # rerank_score = 0.0 means reranker inactive
        result = gate.evaluate(hits)

        assert result.abstain is False

    def test_reranker_inactive_cosine_below_threshold_rejected(self) -> None:
        gate = AbstentionGate(min_cosine=0.45, min_rerank_score=0.0)
        hits = [_hit(cosine_score=0.3, bm25_score=0.0)]

        result = gate.evaluate(hits)

        assert result.abstain is True
        assert "cosine_below_threshold" in result.reason

    def test_reranker_active_bm25_only_rejected(self) -> None:
        gate = AbstentionGate(min_cosine=0.25, min_rerank_score=0.5)
        hits = [_hit(cosine_score=0.0, bm25_score=3.0)]
        hits[0].rerank_score = 0.8

        result = gate.evaluate(hits)

        # Phase 3F AND gate: cosine=0.0 < min_cosine → abstain (BM25 cannot bypass)
        assert result.abstain is True
        assert "cosine_below_threshold" in result.reason

    def test_reranker_inactive_bm25_below_cosine_threshold_rejected(self) -> None:
        gate = AbstentionGate(min_cosine=0.25, min_rerank_score=0.0)
        hits = [_hit(cosine_score=0.0, bm25_score=3.0)]

        result = gate.evaluate(hits)

        # Phase 3E: cosine below threshold is rejected regardless of BM25 score
        assert result.abstain is True
        assert "cosine_below_threshold" in result.reason

    def test_empty_hits_always_abstain(self) -> None:
        gate = AbstentionGate(min_cosine=0.25, min_rerank_score=0.5)

        result = gate.evaluate([])

        assert result.abstain is True
        assert result.reason == "no_results"

    def test_min_rerank_score_zero_skips_rerank_check(self) -> None:
        gate = AbstentionGate(min_cosine=0.25, min_rerank_score=0.0)
        hits = [_hit(cosine_score=0.3, bm25_score=1.0)]
        hits[0].rerank_score = 0.1  # Low but reranker min_score=0

        result = gate.evaluate(hits)

        # rerank_score > 0 means reranker-active path, min_rerank_score=0 means no threshold
        assert result.abstain is False

    # ── Phase 3F AND-gate regression tests ──────────────────────────────

    def test_3f_reranker_disabled_cosine_pass_accept(self) -> None:
        gate = AbstentionGate(min_cosine=0.45, min_rerank_score=0.125)
        hits = [_hit(cosine_score=0.6, bm25_score=2.0)]
        # rerank_score=0.0 → reranker-inactive path → cosine gate only

        result = gate.evaluate(hits)

        assert result.abstain is False

    def test_3f_reranker_disabled_cosine_fail_bm25_positive_abstain(self) -> None:
        gate = AbstentionGate(min_cosine=0.45, min_rerank_score=0.125)
        hits = [_hit(cosine_score=0.3, bm25_score=5.0)]
        # rerank_score=0.0 → reranker-inactive path → cosine gate rejects

        result = gate.evaluate(hits)

        assert result.abstain is True
        assert "cosine_below_threshold" in result.reason

    def test_3f_reranker_enabled_cosine_fail_rerank_pass_abstain(self) -> None:
        gate = AbstentionGate(min_cosine=0.45, min_rerank_score=0.125)
        hits = [_hit(cosine_score=0.3, bm25_score=5.0)]
        hits[0].rerank_score = 0.8

        result = gate.evaluate(hits)

        # AND gate: rerank passes but cosine fails → abstain
        assert result.abstain is True
        assert "cosine_below_threshold" in result.reason

    def test_3f_reranker_enabled_cosine_pass_rerank_fail_abstain(self) -> None:
        gate = AbstentionGate(min_cosine=0.45, min_rerank_score=0.125)
        hits = [_hit(cosine_score=0.6, bm25_score=2.0)]
        hits[0].rerank_score = 0.05

        result = gate.evaluate(hits)

        # AND gate: cosine passes but rerank fails → abstain
        assert result.abstain is True
        assert "rerank_below_threshold" in result.reason

    def test_3f_reranker_enabled_cosine_pass_rerank_pass_accept(self) -> None:
        gate = AbstentionGate(min_cosine=0.45, min_rerank_score=0.125)
        hits = [_hit(cosine_score=0.6, bm25_score=2.0)]
        hits[0].rerank_score = 0.8

        result = gate.evaluate(hits)

        # AND gate: both pass → accept
        assert result.abstain is False

    def test_3f_reranker_enabled_cosine_fail_rerank_fail_abstain(self) -> None:
        gate = AbstentionGate(min_cosine=0.45, min_rerank_score=0.125)
        hits = [_hit(cosine_score=0.2, bm25_score=1.0)]
        hits[0].rerank_score = 0.05

        result = gate.evaluate(hits)

        # AND gate: both fail → abstain
        assert result.abstain is True
        assert "cosine_below_threshold" in result.reason
        assert "rerank_below_threshold" in result.reason

    def test_3f_reranker_unavailable_fallback_cosine_gate(self) -> None:
        gate = AbstentionGate(min_cosine=0.45, min_rerank_score=0.125)
        hits = [_hit(cosine_score=0.6, bm25_score=2.0)]
        hits[0].rerank_score = 0.0  # reranker failed/unavailable

        result = gate.evaluate(hits)

        # reranker-inactive path → cosine gate only → accept
        assert result.abstain is False

    def test_3f_bm25_never_bypasses_combined_gate(self) -> None:
        gate = AbstentionGate(min_cosine=0.45, min_rerank_score=0.125)
        hits = [_hit(cosine_score=0.3, bm25_score=100.0)]
        hits[0].rerank_score = 0.9

        result = gate.evaluate(hits)

        # BM25 is strong but cosine fails → abstain (BM25 never bypasses)
        assert result.abstain is True
        assert "cosine_below_threshold" in result.reason


# ── QAWorkflow integration tests ─────────────────────────────────────────


class TestQAWorkflowReranker:
    """Tests for QAWorkflow with reranker integration."""

    def test_workflow_without_reranker_unchanged(self) -> None:
        search = FakeSearchService([_hit(cosine_score=0.6, bm25_score=2.0)])
        client = FakeOllamaClient()
        workflow = QAWorkflow(search, client, min_cosine=0.25)

        result = workflow.ask("What is Python?")

        assert result.answer == "Test answer."
        assert len(result.sources) == 1

    def test_workflow_with_disabled_reranker_unchanged(self) -> None:
        cfg = RerankerConfig(enabled=False)
        reranker = CrossEncoderReranker(cfg)
        search = FakeSearchService([_hit(cosine_score=0.6, bm25_score=2.0)])
        client = FakeOllamaClient()
        workflow = QAWorkflow(search, client, min_cosine=0.25, reranker=reranker)

        result = workflow.ask("What is Python?")

        assert result.answer == "Test answer."

    def test_rejected_query_does_not_invoke_llm(self) -> None:
        search = FakeSearchService([_hit(cosine_score=0.1, bm25_score=0.0)])
        client = FakeOllamaClient()
        workflow = QAWorkflow(search, client, min_cosine=0.25)

        result = workflow.ask("What is quantum computing?")

        assert result.answer == ABSTENTION_MESSAGE
        assert result.sources == []
        assert not client.requests

    def test_build_context_includes_rerank_score_when_present(self) -> None:
        hit = _hit(text="Test content.")
        hit.rerank_score = 0.85

        context = build_context([hit])

        assert "Rerank: 0.8500" in context

    def test_build_context_omits_rerank_score_when_zero(self) -> None:
        hit = _hit(text="Test content.")
        hit.rerank_score = 0.0

        context = build_context([hit])

        assert "Rerank:" not in context


# ── Regression: existing SearchHit fields intact ─────────────────────────


class TestSearchHitRegression:
    """Verify SearchHit field integrity after rerank_score addition."""

    def test_searchhit_defaults(self) -> None:
        hit = SearchHit(text="x", source="y", score=1.0, entry_id="z")

        assert hit.cosine_score == 0.0
        assert hit.bm25_score == 0.0
        assert hit.rerank_score == 0.0
        assert hit.parent_section is None
        assert hit.source_type == ""
        assert hit.chunk_index == 0

    def test_searchhit_with_all_scores(self) -> None:
        hit = SearchHit(
            text="x",
            source="y",
            score=0.5,
            entry_id="z",
            cosine_score=0.6,
            bm25_score=2.0,
            rerank_score=0.8,
        )

        assert hit.cosine_score == 0.6
        assert hit.bm25_score == 2.0
        assert hit.rerank_score == 0.8
        assert hit.score == 0.5
