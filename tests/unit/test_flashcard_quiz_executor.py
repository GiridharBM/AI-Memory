"""End-to-end V2-C executor runs for flashcards and quizzes."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.application.flashcard_handler import FlashcardTaskHandler
from app.application.generation_errors import HandlerError
from app.application.generation_executor import GenerationExecutor
from app.application.quiz_handler import QuizTaskHandler
from app.application.task_handler import register_handlers
from app.domain.artifacts import ArtifactKind
from app.domain.generation import GenerationRequest, GenerationTaskType
from app.domain.jobs import GenerationJobStatus
from app.domain.scopes import MemoryScope
from app.infrastructure.artifacts import ArtifactStore, ProvenanceStore
from app.infrastructure.jobs import GenerationJobStore
from app.infrastructure.search import SearchHit


class StubSearchService:
    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filter: dict[str, object] | None = None,  # noqa: A002 - mirrors service signature
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        return [
            SearchHit(text="body a", source="a.md", score=0.9, entry_id="a.md::0"),
            SearchHit(text="body b", source="b.md", score=0.8, entry_id="b.md::0"),
        ]


def _cards(count: int) -> dict[str, object]:
    return {
        "cards": [{"front": f"card {i}?", "back": f"answer {i}"} for i in range(count)]
    }


def _mcqs(count: int) -> dict[str, object]:
    return {
        "questions": [
            {
                "question": f"question {i}?",
                "options": ["a", "b", "c", "d"],
                "correct_answer": "a",
                "explanation": f"because {i}",
            }
            for i in range(count)
        ]
    }


class ScriptedGenerate:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)

    def __call__(self, system_prompt: str, user_prompt: str, model: type) -> object:
        if not self._responses:
            raise AssertionError("Fake LLM called more times than scripted.")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return model.model_validate(response)


def _executor(
    tmp_path: Path, cards: object = None, mcqs: object = None
) -> GenerationExecutor:
    card_responses = cards if isinstance(cards, list) else [_cards(2) if cards is None else cards]
    mcq_responses = mcqs if isinstance(mcqs, list) else [_mcqs(2) if mcqs is None else mcqs]
    return GenerationExecutor(
        job_store=GenerationJobStore(tmp_path / "jobs.json"),
        artifact_store=ArtifactStore(tmp_path / "artifacts.json"),
        provenance_store=ProvenanceStore(tmp_path / "provenance.json"),
        handlers=register_handlers(
            FlashcardTaskHandler(ScriptedGenerate(card_responses)),
            QuizTaskHandler(ScriptedGenerate(mcq_responses)),
        ),
        search_service=StubSearchService(),
    )


def _request(task: str, config: dict[str, object]) -> GenerationRequest:
    return GenerationRequest(
        task_type=task,  # type: ignore[arg-type]
        memory_scope=MemoryScope.all(),
        config=config,  # type: ignore[arg-type]
    )


def test_flashcards_end_to_end(tmp_path: Path) -> None:
    executor = _executor(tmp_path)

    outcome = executor.run(_request("flashcards", {"count": 2}))

    assert outcome.job.status is GenerationJobStatus.DONE
    assert outcome.job.progress == 100
    assert outcome.artifact_id is not None
    artifact = ArtifactStore(tmp_path / "artifacts.json").get(outcome.artifact_id)
    assert artifact is not None
    assert artifact.kind is ArtifactKind.FLASHCARDS
    assert artifact.job_id == outcome.job.job_id
    assert artifact.request.task_type is GenerationTaskType.FLASHCARDS
    records = ProvenanceStore(tmp_path / "provenance.json").for_artifact(
        outcome.artifact_id
    )
    assert len(records) == 2 * 2
    reloaded = GenerationJobStore(tmp_path / "jobs.json").get(outcome.job.job_id)
    assert reloaded is not None and reloaded.status is GenerationJobStatus.DONE


def test_quiz_end_to_end(tmp_path: Path) -> None:
    executor = _executor(tmp_path)

    outcome = executor.run(_request("quiz", {"count": 2}))

    assert outcome.job.status is GenerationJobStatus.DONE
    assert outcome.artifact_id is not None
    artifact = ArtifactStore(tmp_path / "artifacts.json").get(outcome.artifact_id)
    assert artifact is not None
    assert artifact.kind is ArtifactKind.QUIZ
    assert artifact.job_id == outcome.job.job_id
    records = ProvenanceStore(tmp_path / "provenance.json").for_artifact(
        outcome.artifact_id
    )
    assert len(records) == 2 * 2


def test_failed_generation_marks_job_failed(tmp_path: Path) -> None:
    executor = _executor(tmp_path, cards=[ValueError("bad"), ValueError("bad")])

    with pytest.raises(HandlerError):
        executor.run(_request("flashcards", {"count": 2}))

    jobs = GenerationJobStore(tmp_path / "jobs.json").list_jobs()
    assert len(jobs) == 1
    assert jobs[0].status is GenerationJobStatus.FAILED
    assert ArtifactStore(tmp_path / "artifacts.json").list_artifacts() == []


def test_cancellation_before_generation(tmp_path: Path) -> None:
    executor = GenerationExecutor(
        job_store=GenerationJobStore(tmp_path / "jobs.json"),
        artifact_store=ArtifactStore(tmp_path / "artifacts.json"),
        provenance_store=ProvenanceStore(tmp_path / "provenance.json"),
        handlers=register_handlers(
            FlashcardTaskHandler(ScriptedGenerate([_cards(2)])),
            QuizTaskHandler(ScriptedGenerate([_mcqs(2)])),
        ),
        search_service=StubSearchService(),
        is_cancelled=lambda: True,
    )

    outcome = executor.run(_request("flashcards", {"count": 2}))

    assert outcome.job.status is GenerationJobStatus.CANCELLED
    assert outcome.artifact_id is None
    assert ArtifactStore(tmp_path / "artifacts.json").list_artifacts() == []
