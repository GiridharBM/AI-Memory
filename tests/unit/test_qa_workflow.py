"""Tests for the RAG question-answering workflow."""

from __future__ import annotations

import threading
import time

import pytest

from app.application.qa_workflow import (
    ABSTENTION_MESSAGE,
    MAX_CONTEXT_CHARS,
    MAX_CONTEXT_CHUNKS,
    OUTCOME_ABSTAINED,
    OUTCOME_ANSWERED,
    AbstentionGate,
    QAAnswer,
    QAEmptyAnswerError,
    QAError,
    QATimeoutError,
    QAWorkflow,
    build_context,
    extract_citations,
    has_insufficiency_language,
    resolve_citations,
)
from app.infrastructure.llm import (
    OllamaClientError,
    OllamaRequest,
    OllamaTextResponse,
    OllamaTimeoutError,
)
from app.infrastructure.search import SearchHit


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
    def __init__(
        self,
        response: OllamaTextResponse | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.requests: list[OllamaRequest] = []

    def generate_text(self, request: OllamaRequest) -> OllamaTextResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


class BlockingOllamaClient:
    """Client whose ``generate_text`` blocks until the test releases it."""

    def __init__(self, blocker: threading.Event) -> None:
        self._blocker = blocker

    def generate_text(self, request: OllamaRequest) -> OllamaTextResponse:
        self._blocker.wait(timeout=30)
        return _response("a late answer")


class SlowOllamaClient(FakeOllamaClient):
    """Client that completes a real response after a fixed delay."""

    def __init__(self, delay: float, response: OllamaTextResponse) -> None:
        super().__init__(response)
        self._delay = delay

    def generate_text(self, request: OllamaRequest) -> OllamaTextResponse:
        time.sleep(self._delay)
        return super().generate_text(request)


def _hit(
    text: str = "Python is a programming language.",
    *,
    source: str = "doc.md",
    score: float = 0.5,
    cosine_score: float = 0.5,
    bm25_score: float = 0.5,
    metadata: dict[str, str] | None = None,
) -> SearchHit:
    return SearchHit(
        text=text,
        source=source,
        score=score,
        entry_id="doc.md::chunk_0",
        cosine_score=cosine_score,
        bm25_score=bm25_score,
        source_type="markdown",
        metadata=metadata if metadata is not None else {"heading": "Intro"},
    )


def _response(text: str = "Python is a language.") -> OllamaTextResponse:
    return OllamaTextResponse(model="qwen3:8b", response=text, raw={})


def _workflow(search: FakeSearchService, client: FakeOllamaClient) -> QAWorkflow:
    return QAWorkflow(search, client)


def test_ask_returns_answer_and_sources() -> None:
    hits = [_hit()]
    search = FakeSearchService(hits)
    client = FakeOllamaClient(_response("Python is a language."))
    workflow = _workflow(search, client)

    result = workflow.ask("What is Python?")

    assert isinstance(result, QAAnswer)
    assert result.answer == "Python is a language."
    assert result.sources == hits
    assert result.model == "qwen3:8b"


def test_ask_places_question_in_prompt() -> None:
    search = FakeSearchService([_hit()])
    client = FakeOllamaClient(_response())
    workflow = _workflow(search, client)

    workflow.ask("What is Python?")

    prompt = client.requests[0].prompt
    assert "What is Python?" in prompt
    assert client.requests[0].system_prompt is not None


def test_ask_places_retrieved_context_in_prompt() -> None:
    search = FakeSearchService([_hit(text="Guido wrote CPython in 1991.")])
    client = FakeOllamaClient(_response())
    workflow = _workflow(search, client)

    workflow.ask("Who wrote Python?")

    prompt = client.requests[0].prompt
    assert "Guido wrote CPython in 1991." in prompt
    assert "doc.md" in prompt
    assert "[SOURCE 1]" in prompt


def test_ask_forwards_top_k() -> None:
    search = FakeSearchService([_hit()])
    client = FakeOllamaClient(_response())
    workflow = _workflow(search, client)

    workflow.ask("What is Python?", top_k=3)

    assert search.last["top_k"] == 3


def test_ask_forwards_min_score() -> None:
    search = FakeSearchService([_hit()])
    client = FakeOllamaClient(_response())
    workflow = _workflow(search, client)

    workflow.ask("What is Python?", min_score=0.1)

    assert search.last["min_score"] == 0.1


def test_ask_forwards_filter() -> None:
    search = FakeSearchService([_hit()])
    client = FakeOllamaClient(_response())
    workflow = _workflow(search, client)

    workflow.ask("What is Python?", filter={"heading": "Intro"})

    assert search.last["filter"] == {"heading": "Intro"}


@pytest.mark.parametrize("question", ["", "   ", None])
def test_ask_rejects_invalid_question(question: str | None) -> None:
    search = FakeSearchService([_hit()])
    client = FakeOllamaClient(_response())
    workflow = _workflow(search, client)

    with pytest.raises(QAError, match="must not be empty"):
        workflow.ask(question)  # type: ignore[arg-type]


def test_ask_handles_empty_retrieval_safely() -> None:
    search = FakeSearchService([])
    client = FakeOllamaClient(_response("No relevant context was retrieved."))
    workflow = _workflow(search, client)

    result = workflow.ask("What is Python?")

    assert result.answer == ABSTENTION_MESSAGE
    assert result.sources == []
    assert not client.requests  # LLM not invoked when gate abstains on empty hits


def test_ask_wraps_ollama_failure() -> None:
    search = FakeSearchService([_hit()])
    client = FakeOllamaClient(error=OllamaClientError("connection refused"))
    workflow = _workflow(search, client)

    with pytest.raises(QAError, match="Ollama server is unavailable"):
        workflow.ask("What is Python?")


def test_build_context_is_bounded() -> None:
    huge_text = "x" * 5_000
    hits = [_hit(text=huge_text, source=f"doc{i}.md") for i in range(100)]

    context = build_context(hits)

    assert len(context) < 100 * len(huge_text)
    assert context.count("[SOURCE") <= MAX_CONTEXT_CHUNKS
    assert len(context) <= MAX_CONTEXT_CHARS + 1_000


def test_build_context_preserves_ranking() -> None:
    hits = [_hit(source="first.md"), _hit(source="second.md")]

    context = build_context(hits)

    assert context.index("first.md") < context.index("second.md")


# ── Abstention gate tests ──────────────────────────────────────────────


class TestAbstentionGate:
    """Unit tests for the retrieval-confidence abstention gate."""

    def test_strong_relevant_retrieval_accepted(self) -> None:
        gate = AbstentionGate(min_cosine=0.25)
        hits = [_hit(cosine_score=0.6, bm25_score=2.0)]

        result = gate.evaluate(hits)

        assert result.abstain is False
        assert result.reason is None

    def test_weak_retrieval_rejected(self) -> None:
        gate = AbstentionGate(min_cosine=0.25)
        hits = [_hit(cosine_score=0.1, bm25_score=0.0)]

        result = gate.evaluate(hits)

        assert result.abstain is True
        assert "cosine_below_threshold" in result.reason

    def test_negative_query_no_results_rejected(self) -> None:
        gate = AbstentionGate(min_cosine=0.25)

        result = gate.evaluate([])

        assert result.abstain is True
        assert result.reason == "no_results"

    def test_borderline_score_deterministic(self) -> None:
        gate = AbstentionGate(min_cosine=0.25)
        hits_exact = [_hit(cosine_score=0.25, bm25_score=0.0)]
        hits_below = [_hit(cosine_score=0.2499, bm25_score=0.0)]

        assert gate.evaluate(hits_exact).abstain is False
        assert gate.evaluate(hits_below).abstain is True

    def test_accepted_query_context_built_normally(self) -> None:
        hits = [_hit(cosine_score=0.6, bm25_score=2.0, text="Guido wrote CPython.")]
        search = FakeSearchService(hits)
        client = FakeOllamaClient(_response("Python is a language."))
        workflow = QAWorkflow(search, client, min_cosine=0.25)

        result = workflow.ask("What is Python?")

        assert result.answer == "Python is a language."
        assert result.sources == hits
        assert client.requests  # LLM was invoked

    def test_rejected_query_llm_not_invoked(self) -> None:
        hits = [_hit(cosine_score=0.1, bm25_score=0.0)]
        search = FakeSearchService(hits)
        client = FakeOllamaClient(_response("This should not be called."))
        workflow = QAWorkflow(search, client, min_cosine=0.25)

        result = workflow.ask("What is quantum computing?")

        assert result.answer == ABSTENTION_MESSAGE
        assert result.sources == []
        assert result.model == ""
        assert not client.requests  # LLM was NOT invoked

    def test_existing_behavior_unchanged_when_gate_accepts(self) -> None:
        hits = [_hit(cosine_score=0.6, bm25_score=2.0)]
        search = FakeSearchService(hits)
        client = FakeOllamaClient(_response("Python is a language."))
        workflow = QAWorkflow(search, client, min_cosine=0.25)

        result = workflow.ask("What is Python?", top_k=3, filter={"heading": "Intro"})

        assert search.last["top_k"] == 3
        assert search.last["filter"] == {"heading": "Intro"}
        assert result.answer == "Python is a language."
        assert "[SOURCE 1]" in client.requests[0].prompt

    def test_bm25_below_cosine_threshold_rejected(self) -> None:
        gate = AbstentionGate(min_cosine=0.25)
        hits = [_hit(cosine_score=0.0, bm25_score=3.0)]

        result = gate.evaluate(hits)

        assert result.abstain is True
        assert "cosine_below_threshold" in result.reason

    def test_no_evidence_both_scores_zero_rejected(self) -> None:
        gate = AbstentionGate(min_cosine=0.25)
        hits = [_hit(cosine_score=0.0, bm25_score=0.0)]

        result = gate.evaluate(hits)

        assert result.abstain is True
        assert result.reason == "no_evidence"

    def test_bm25_only_with_zero_cosine_above_threshold_accepted(self) -> None:
        gate = AbstentionGate(min_cosine=0.0)
        hits = [_hit(cosine_score=0.0, bm25_score=3.0)]

        result = gate.evaluate(hits)

        assert result.abstain is False

    # ── BM25 override regression tests (Phase 3E) ───────────────────

    def test_bm25_override_rejected_cosine_below_threshold(self) -> None:
        gate = AbstentionGate(min_cosine=0.45)
        hits = [_hit(cosine_score=0.30, bm25_score=5.0)]

        result = gate.evaluate(hits)

        assert result.abstain is True
        assert "cosine_below_threshold" in result.reason

    def test_bm25_override_rejected_even_with_strong_bm25(self) -> None:
        gate = AbstentionGate(min_cosine=0.45)
        hits = [_hit(cosine_score=0.40, bm25_score=10.0)]

        result = gate.evaluate(hits)

        assert result.abstain is True

    def test_cosine_above_threshold_accepted_with_zero_bm25(self) -> None:
        gate = AbstentionGate(min_cosine=0.45)
        hits = [_hit(cosine_score=0.60, bm25_score=0.0)]

        result = gate.evaluate(hits)

        assert result.abstain is False

    def test_cosine_above_threshold_accepted_with_bm25(self) -> None:
        gate = AbstentionGate(min_cosine=0.45)
        hits = [_hit(cosine_score=0.60, bm25_score=3.0)]

        result = gate.evaluate(hits)

        assert result.abstain is False

    def test_no_results_always_abstains(self) -> None:
        gate = AbstentionGate(min_cosine=0.45)
        result = gate.evaluate([])
        assert result.abstain is True
        assert result.reason == "no_results"

    def test_both_zero_scores_abstains(self) -> None:
        gate = AbstentionGate(min_cosine=0.45)
        hits = [_hit(cosine_score=0.0, bm25_score=0.0)]
        result = gate.evaluate(hits)
        assert result.abstain is True
        assert result.reason == "no_evidence"


# ── Citation validation (Phase 6B) ────────────────────────────────────


class TestCitationValidation:
    """Unit tests for parsing and validating [SOURCE N] references."""

    def test_extract_citations_returns_numbers_in_order(self) -> None:
        assert extract_citations("a [SOURCE 2] b [SOURCE 1] c") == [2, 1]

    def test_extract_citations_is_case_insensitive(self) -> None:
        assert extract_citations("[source 3] [Source 4]") == [3, 4]

    def test_extract_citations_ignores_malformed_tokens(self) -> None:
        text = "no brackets SOURCE 1, [SOURCES 2], [SOURCE x], [SOURCE1], (source 3)"
        assert extract_citations(text) == []

    def test_extract_citations_preserves_duplicates(self) -> None:
        assert extract_citations("[SOURCE 1] [SOURCE 1]") == [1, 1]

    def test_valid_single_citation_resolves(self) -> None:
        hits = [_hit(source="a.md"), _hit(source="b.md")]

        citations, invalid, duplicates = resolve_citations("uses [SOURCE 2]", hits)

        assert [c.number for c in citations] == [2]
        assert citations[0].hit.source == "b.md"
        assert invalid == []
        assert duplicates == 0

    def test_multiple_valid_citations_preserve_order(self) -> None:
        hits = [_hit(source=f"d{i}.md") for i in range(4)]

        citations, invalid, duplicates = resolve_citations("[SOURCE 4] and [SOURCE 1]", hits)

        assert [c.number for c in citations] == [4, 1]
        assert invalid == []
        assert duplicates == 0

    def test_out_of_range_citation_rejected_not_remapped(self) -> None:
        hits = [_hit()]  # only one retrieved source

        citations, invalid, duplicates = resolve_citations("cites [SOURCE 9]", hits)

        assert citations == []
        assert invalid == [9]
        assert duplicates == 0

    def test_source_zero_is_invalid(self) -> None:
        hits = [_hit()]

        _, invalid, _ = resolve_citations("[SOURCE 0]", hits)

        assert invalid == [0]

    def test_duplicate_valid_citations_deduplicated_and_counted(self) -> None:
        hits = [_hit(source="d.md"), _hit(source="e.md")]

        citations, invalid, duplicates = resolve_citations(
            "[SOURCE 2] [SOURCE 2] [SOURCE 1]", hits
        )

        assert [c.number for c in citations] == [2, 1]
        assert invalid == []
        assert duplicates == 1

    def test_hit_lookup_is_offsets_aligned_to_retrieved_source_numbering(self) -> None:
        hits = [_hit(source="first.md"), _hit(source="second.md")]

        _, _, _ = resolve_citations("[SOURCE 1] [SOURCE 2]", hits)
        assert hits[0].source == "first.md"


# ── Answer output contract (Phase 6B) ─────────────────────────────────


class TestQaAnswerContract:
    """Workflow-level behavior of the ANSWERED / ABSTAINED contract."""

    def test_answered_outcome_carries_resolved_citations(self) -> None:
        hits = [_hit(source="a.md"), _hit(source="b.md")]
        search = FakeSearchService(hits)
        client = FakeOllamaClient(_response("Python is a language. [SOURCE 2] [SOURCE 1]"))
        workflow = _workflow(search, client)

        result = workflow.ask("What is Python?")

        assert result.outcome == OUTCOME_ANSWERED
        assert [c.number for c in result.citations] == [2, 1]
        assert [c.hit.source for c in result.citations] == ["b.md", "a.md"]
        assert result.sources == hits
        assert result.invalid_citations == []
        assert result.duplicate_citations == 0

    def test_answer_text_is_verbatim_and_valid_citations_preserved(self) -> None:
        body = "CPython was first released in 1991 [SOURCE 1]."
        search = FakeSearchService([_hit()])
        client = FakeOllamaClient(_response(body))
        workflow = _workflow(search, client)

        result = workflow.ask("When was CPython released?")

        assert result.answer == body
        assert _noccs(result.answer, "[SOURCE 1]") == 1
        assert [c.number for c in result.citations] == [1]

    def test_out_of_range_citation_surfaces_in_invalid_citations(self) -> None:
        body = "The answer is X. [SOURCE 9]"
        search = FakeSearchService([_hit()])
        client = FakeOllamaClient(_response(body))
        workflow = _workflow(search, client)

        result = workflow.ask("What is Python?")

        assert result.answer == body  # text untouched, no silent remap
        assert result.citations == []
        assert result.invalid_citations == [9]

    def test_duplicate_citations_deduplicated_at_workflow(self) -> None:
        search = FakeSearchService([_hit()])
        client = FakeOllamaClient(_response("A [SOURCE 1] is B [SOURCE 1]."))
        workflow = _workflow(search, client)

        result = workflow.ask("What?")

        assert [c.number for c in result.citations] == [1]
        assert result.duplicate_citations == 1

    def test_answer_without_citations_keeps_full_sources_for_display(self) -> None:
        hits = [_hit(source="a.md"), _hit(source="b.md")]
        search = FakeSearchService(hits)
        client = FakeOllamaClient(_response("No [SOURCE markers at all.]"))
        workflow = _workflow(search, client)

        result = workflow.ask("What?")

        assert result.citations == []
        assert result.invalid_citations == []
        assert result.sources == hits

    def test_abstention_outcome_preserves_reason_and_skips_llm(self) -> None:
        hits = [_hit(cosine_score=0.10, bm25_score=0.0)]
        search = FakeSearchService(hits)
        client = FakeOllamaClient(_response("This should not be called."))
        workflow = QAWorkflow(search, client, min_cosine=0.25)

        result = workflow.ask("Can I buy a home in Denmark?")

        assert result.outcome == OUTCOME_ABSTAINED
        assert result.answer == ABSTENTION_MESSAGE
        assert result.sources == []
        assert result.abstention_reason is not None
        assert not client.requests  # LLM never invoked after an abstention

    def test_source_metadata_reachable_via_citation_hit(self) -> None:
        search = FakeSearchService([_hit(text="Guido wrote it.", metadata={"heading": "History"})])
        client = FakeOllamaClient(_response("Author is Guido. [SOURCE 1]"))
        workflow = _workflow(search, client)

        result = workflow.ask("Who wrote Python?")

        citation = result.citations[0]
        assert citation.hit.source_type == "markdown"
        assert citation.hit.metadata["heading"] == "History"
        assert citation.hit.entry_id.endswith("chunk_0")


# ── Empty-answer handling + exception wrapping (Phase 6C) ─────────────


class TestEmptyAnswerHandling:
    """An empty or whitespace-only model response is FAILED, never ANSWERED."""

    @pytest.mark.parametrize("blank", ["", "   ", "\n\t ", " \r\n "])
    def test_empty_or_whitespace_response_is_failure(self, blank: str) -> None:
        search = FakeSearchService([_hit()])
        client = FakeOllamaClient(_response(blank))
        workflow = _workflow(search, client)

        with pytest.raises(QAEmptyAnswerError, match="empty response"):
            workflow.ask("What is Python?")

    def test_empty_answer_error_is_qa_error_subclass(self) -> None:
        assert issubclass(QAEmptyAnswerError, QAError)

    def test_empty_answer_is_distinguishable_from_abstention(self) -> None:
        search = FakeSearchService([_hit()])
        client = FakeOllamaClient(_response(""))
        workflow = _workflow(search, client)

        with pytest.raises(QAEmptyAnswerError) as excinfo:
            workflow.ask("What is Python?")

        # A failure was raised; it is NOT an ABSTAINED QAAnswer.
        assert isinstance(excinfo.value, QAError)
        assert not isinstance(excinfo.value, QATimeoutError)

    def test_normal_answer_remains_answered_with_measurements(self) -> None:
        search = FakeSearchService([_hit()])
        client = FakeOllamaClient(_response("Python is a language."))
        workflow = _workflow(search, client)

        result = workflow.ask("What is Python?")

        assert result.outcome == OUTCOME_ANSWERED
        assert result.latency_seconds is not None and result.latency_seconds >= 0.0
        assert result.telemetry is not None
        assert result.telemetry.answer_length == len("Python is a language.")
        assert result.telemetry.source_count == 1
        assert result.telemetry.latency_seconds == result.latency_seconds


class TestModelExceptionWrapping:
    """Unexpected provider exceptions are wrapped in the QA hierarchy."""

    def test_unexpected_model_exception_wrapped_as_qa_error(self) -> None:
        search = FakeSearchService([_hit()])
        client = FakeOllamaClient(error=RuntimeError("boom"))
        workflow = _workflow(search, client)

        with pytest.raises(QAError, match="unexpected error"):
            workflow.ask("What is Python?")

    def test_timeout_error_preserved_as_qatimeout(self) -> None:
        search = FakeSearchService([_hit()])
        client = FakeOllamaClient(error=OllamaTimeoutError("timed out"))
        workflow = _workflow(search, client)

        with pytest.raises(QATimeoutError):
            workflow.ask("What is Python?")

    def test_unavailable_error_preserved_as_qa_error(self) -> None:
        search = FakeSearchService([_hit()])
        client = FakeOllamaClient(error=OllamaClientError("connection refused"))
        workflow = _workflow(search, client)

        with pytest.raises(QAError, match="Ollama server is unavailable"):
            workflow.ask("What is Python?")

    def test_insufficiency_heuristic_is_measurement_only(self) -> None:
        # An answer that reads like a soft abstention stays ANSWERED; the
        # heuristic only labels telemetry, it never changes the outcome.
        search = FakeSearchService([_hit()])
        client = FakeOllamaClient(
            _response("I don't have enough information in the provided sources to answer.")
        )
        workflow = _workflow(search, client)

        result = workflow.ask("What is Python?")

        assert result.outcome == OUTCOME_ANSWERED
        assert result.telemetry is not None
        assert result.telemetry.answer_has_insufficiency_language is True

    def test_insufficiency_heuristic_flags_obvious_soft_abstention(self) -> None:
        assert has_insufficiency_language("I don't have enough information to answer.")
        assert has_insufficiency_language("The context does not contain the answer.")
        assert has_insufficiency_language("Insufficient evidence was retrieved.")
        assert not has_insufficiency_language("Python was created by Guido van Rossum.")


class TestWallClockTimeout:
    """Phase 6F-A: ``generation_timeout_seconds`` is a true wall-clock bound."""

    def test_completes_within_deadline_returns_answered(self) -> None:
        search = FakeSearchService([_hit()])
        client = FakeOllamaClient(_response("Python is a language."))
        workflow = QAWorkflow(search, client, generation_timeout_seconds=5.0)

        result = workflow.ask("What is Python?")

        assert result.outcome == OUTCOME_ANSWERED
        assert result.answer == "Python is a language."
        assert len(client.requests) == 1

    def test_slower_than_fast_recognizes_loss_is_still_answered_inside_budget(self) -> None:
        search = FakeSearchService([_hit()])
        client = SlowOllamaClient(delay=0.2, response=_response("a slow answer"))
        workflow = QAWorkflow(search, client, generation_timeout_seconds=5.0)

        result = workflow.ask("What is Python?")

        assert result.outcome == OUTCOME_ANSWERED
        assert result.answer == "a slow answer"
        assert result.latency_seconds is not None and result.latency_seconds >= 0.2

    def test_exceeding_deadline_raises_qatimeout(self) -> None:
        blocker = threading.Event()
        search = FakeSearchService([_hit()])
        client = BlockingOllamaClient(blocker)
        workflow = QAWorkflow(search, client, generation_timeout_seconds=0.1)

        with pytest.raises(QATimeoutError, match="request timed out"):
            workflow.ask("What is Python?")

        blocker.set()

    def test_qatimeout_is_qa_error_subclass(self) -> None:
        assert issubclass(QATimeoutError, QAError)
        assert QATimeoutError is not QAEmptyAnswerError

    def test_deadline_expiry_short_circuits_before_any_answer(self) -> None:
        blocker = threading.Event()
        search = FakeSearchService([_hit()])
        client = BlockingOllamaClient(blocker)
        workflow = QAWorkflow(search, client, generation_timeout_seconds=0.1)

        with pytest.raises(QATimeoutError):
            workflow.ask("What is Python?")
        blocker.set()

    def test_unavailable_error_stays_qa_error_with_deadline(self) -> None:
        search = FakeSearchService([_hit()])
        client = FakeOllamaClient(error=OllamaClientError("server down"))
        workflow = QAWorkflow(search, client, generation_timeout_seconds=5.0)

        with pytest.raises(QAError, match="Ollama server is unavailable"):
            workflow.ask("What is Python?")

    def test_ordinary_exception_stays_qa_error_with_deadline(self) -> None:
        search = FakeSearchService([_hit()])
        client = FakeOllamaClient(error=RuntimeError("boom"))
        workflow = QAWorkflow(search, client, generation_timeout_seconds=5.0)

        with pytest.raises(QAError, match="unexpected error"):
            workflow.ask("What is Python?")

    def test_empty_answer_stays_empty_error_with_deadline(self) -> None:
        search = FakeSearchService([_hit()])
        client = FakeOllamaClient(_response(" \n\t "))
        workflow = QAWorkflow(search, client, generation_timeout_seconds=5.0)

        with pytest.raises(QAEmptyAnswerError, match="empty response"):
            workflow.ask("What is Python?")

    def test_citation_behavior_unchanged_with_deadline(self) -> None:
        search = FakeSearchService([_hit(), _hit(source="other.md")])
        client = FakeOllamaClient(_response("Based on [SOURCE 1] and [SOURCE 9]."))
        workflow = QAWorkflow(search, client, generation_timeout_seconds=5.0)

        result = workflow.ask("What is Python?")

        assert [c.number for c in result.citations] == [1]
        assert result.invalid_citations == [9]


def _noccs(text: str, needle: str) -> int:
    return text.count(needle)
