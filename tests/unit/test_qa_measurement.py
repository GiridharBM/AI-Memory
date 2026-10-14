"""Tests for the observational QA measurement harness (Phase 6C).

The harness is measurement-only: it must record empirical facts about model
responses without changing the ANSWERED / ABSTAINED / FAILED outcome, without
adding an LLM judge, and without extra model calls.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.application.qa_measurement_harness import (
    FAILURE_EMPTY_ANSWER,
    FAILURE_GENERATION,
    FAILURE_TIMEOUT,
    FAILURE_UNEXPECTED,
    _classify,
    main,
    record_row,
)
from app.application.qa_workflow import (
    ABSTENTION_MESSAGE,
    OUTCOME_ABSTAINED,
    OUTCOME_ANSWERED,
    QAAnswer,
    QAEmptyAnswerError,
    QAError,
    QATimeoutError,
    SourceCitation,
)
from app.infrastructure.search import SearchHit


def _hit() -> SearchHit:
    return SearchHit(
        text="Python is a programming language.",
        source="doc.md",
        score=0.5,
        entry_id="doc.md::chunk_0",
        cosine_score=0.5,
        bm25_score=0.5,
        source_type="markdown",
        metadata={},
    )


def _answered(
    answer: str = "Python is a language. [SOURCE 1]",
    *,
    citations: list[SourceCitation] | None = None,
    invalid: list[int] | None = None,
    duplicates: int = 0,
) -> QAAnswer:
    return QAAnswer(
        answer=answer,
        sources=[_hit()],
        model="qwen3:8b",
        outcome=OUTCOME_ANSWERED,
        citations=citations or [],
        invalid_citations=invalid or [],
        duplicate_citations=duplicates,
    )


def test_record_row_captures_answered_statistics() -> None:
    row = record_row("What is Python?", result=_answered())

    assert row["query"] == "What is Python?"
    assert row["outcome"] == OUTCOME_ANSWERED
    assert row["failure_category"] == "none"
    assert row["answer_length"] == len("Python is a language. [SOURCE 1]")
    assert row["retrieved_source_count"] == 1
    assert row["citation_count"] == 1  # total [SOURCE N] tokens in the answer
    assert row["latency_ms"] >= 0.0


def test_record_row_latency_and_citation_statistics() -> None:
    row = record_row(
        "What?",
        result=_answered(
            "a [SOURCE 1] is b [SOURCE 1] [SOURCE 2]",
            citations=[SourceCitation(number=1, hit=_hit())],
            invalid=[9],
            duplicates=1,
        ),
        latency_s=2.5,
    )

    assert row["latency_ms"] == 2500.0
    assert row["citation_count"] == 3  # three [SOURCE N] tokens
    assert row["valid_citation_count"] == 1
    assert row["invalid_citation_count"] == 1
    assert row["duplicate_citation_count"] == 1


def test_record_row_captures_abstention_without_changing_outcome() -> None:
    result = QAAnswer(
        answer=ABSTENTION_MESSAGE,
        sources=[],
        model="",
        outcome=OUTCOME_ABSTAINED,
        abstention_reason="no_results",
    )
    row = record_row("What?", result=result)

    assert row["outcome"] == OUTCOME_ABSTAINED
    assert row["failure_category"] == "none"
    assert row["retrieved_source_count"] == 0
    assert row["has_insufficiency_language"] is True


def test_insufficiency_detection_does_not_change_outcome() -> None:
    # The answer is obvious insufficiency prose, but the recorded outcome stays
    # ANSWERED: the heuristic is observational telemetry, never a gate.
    result = _answered("I don't have enough information in the sources to answer.")
    row = record_row("What?", result=result)

    assert row["outcome"] == OUTCOME_ANSWERED
    assert row["has_insufficiency_language"] is True


def test_record_row_without_result_records_failure_category() -> None:
    row = record_row("What?", failure=FAILURE_TIMEOUT, latency_s=9.5)

    assert row["outcome"] == "failed"
    assert row["failure_category"] == FAILURE_TIMEOUT
    assert row["latency_ms"] == 9500.0
    assert row["answer_length"] is None


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (QATimeoutError("t"), FAILURE_TIMEOUT),
        (QAEmptyAnswerError("e"), FAILURE_EMPTY_ANSWER),
        (QAError("g"), FAILURE_GENERATION),
        (RuntimeError("u"), FAILURE_UNEXPECTED),
    ],
)
def test_classify_maps_exceptions_to_failure_categories(
    exc: BaseException, expected: str
) -> None:
    assert _classify(exc) == expected


class _FakeWorkflowForHarness:
    def __init__(self) -> None:
        self.asked: list[str] = []

    @classmethod
    def create_default(cls, settings: object) -> _FakeWorkflowForHarness:
        return cls()

    def ask(
        self,
        query: str,
        *,
        top_k: int = 5,
        min_score: float = 0.0,
        filter: dict[str, object] | None = None,
    ) -> QAAnswer:
        self.asked.append(query)
        return _answered(f"answer about {query} [SOURCE 1]")


def test_harness_main_runs_and_writes_jsonl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps({"metadata": {"version": "3.0"}, "queries": [
            {"id": "q1", "query": "first?", "category": "factoid"},
            {"id": "q2", "query": "second?", "category": "factoid"},
        ]}),
        encoding="utf-8",
    )
    out = tmp_path / "out" / "qa.jsonl"
    fake = _FakeWorkflowForHarness()
    # expose the class-level factory exactly like QAWorkflow.create_default
    fake_cls = type("WF", (), {"create_default": classmethod(lambda cls, s: fake)})
    monkeypatch.setattr("app.application.qa_measurement_harness.QAWorkflow", fake_cls)
    monkeypatch.setattr("app.application.qa_measurement_harness.load_settings", lambda: object())

    exit_code = main(["--dataset", str(dataset), "--out", str(out)])

    assert exit_code == 0
    assert fake.asked == ["first?", "second?"]
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    row = json.loads(lines[0])
    assert row["query"] == "first?"
    assert row["outcome"] == OUTCOME_ANSWERED
    assert row["failure_category"] == "none"
    assert row["citation_count"] == 1


def test_harness_main_records_failure_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps({"queries": [{"id": "q1", "query": "boom?"}]}),
        encoding="utf-8",
    )
    out = tmp_path / "qa.jsonl"

    class FailingWorkflow:
        @classmethod
        def create_default(cls, settings: object) -> FailingWorkflow:
            return cls()

        def ask(self, query: str, **kwargs: object) -> object:
            raise QATimeoutError("timed out")

    monkeypatch.setattr("app.application.qa_measurement_harness.QAWorkflow", FailingWorkflow)
    monkeypatch.setattr("app.application.qa_measurement_harness.load_settings", lambda: object())

    exit_code = main(["--dataset", str(dataset), "--out", str(out)])

    assert exit_code == 0
    row = json.loads(out.read_text(encoding="utf-8").strip().splitlines()[0])
    assert row["outcome"] == "failed"
    assert row["failure_category"] == FAILURE_TIMEOUT