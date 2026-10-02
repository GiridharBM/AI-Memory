"""Tests for the V2 flashcard and quiz task handlers (fake LLM)."""

from __future__ import annotations

from typing import Any

import pytest

from app.application.flashcard_handler import FlashcardTaskHandler
from app.application.generation_errors import HandlerError
from app.application.quiz_handler import QuizTaskHandler
from app.domain.artifacts import ArtifactKind, ProvenanceRole
from app.domain.generation import GenerationRequest, GenerationTaskType
from app.domain.generation_context import GenerationContext, RetrievedChunk
from app.domain.scopes import MemoryScope, resolve_memory_scope


def _hit(source: str = "a.md") -> RetrievedChunk:
    return RetrievedChunk(source=source, text="body", entry_id=f"{source}::0")


def _context(config: dict[str, object], task: str = "flashcards") -> GenerationContext:
    request = GenerationRequest(
        task_type=task,  # type: ignore[arg-type]
        memory_scope=MemoryScope.documents(["a.md", "b.md"]),
        config=config,  # type: ignore[arg-type]
    )
    return GenerationContext(
        request=request,
        scope=resolve_memory_scope(request.memory_scope),
        hits=(_hit("a.md"), _hit("b.md")),
    )


def _cards(count: int, prefix: str = "card") -> dict[str, object]:
    return {
        "cards": [{"front": f"{prefix} {i}?", "back": f"answer {i}"} for i in range(count)]
    }


def _mcqs(count: int, options: int = 4) -> dict[str, object]:
    choices = [f"option {chr(97 + i)}" for i in range(options)]
    return {
        "questions": [
            {
                "question": f"question {i}?",
                "options": list(choices),
                "correct_answer": choices[0],
                "explanation": f"because {i}",
            }
            for i in range(count)
        ]
    }


class ScriptedGenerate:
    """Fake structured LLM: each call consumes the next scripted response."""

    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system_prompt: str, user_prompt: str, model: type) -> Any:
        self.calls.append((system_prompt, user_prompt))
        if not self._responses:
            raise AssertionError("Fake LLM called more times than scripted.")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return model.model_validate(response)


# ── Flashcards ────────────────────────────────────────────────────────


def test_flashcard_task_type_and_kind() -> None:
    handler = FlashcardTaskHandler(ScriptedGenerate([_cards(2)]))

    assert handler.task_type is GenerationTaskType.FLASHCARDS
    result = handler.handle(_context({"count": 2}))

    assert result.kind is ArtifactKind.FLASHCARDS


def test_flashcard_requested_count_and_rendering() -> None:
    handler = FlashcardTaskHandler(ScriptedGenerate([_cards(3)]))

    result = handler.handle(_context({"count": 3}))

    assert "**Front:** card 0?" in (result.content or "")
    assert "**Back:** answer 0" in (result.content or "")
    assert result.content is not None and "## Card 3" in result.content
    assert result.metadata == {"cards": "3"}


def test_flashcard_provenance_candidates() -> None:
    handler = FlashcardTaskHandler(ScriptedGenerate([_cards(2)]))

    result = handler.handle(_context({"count": 2}))

    # Every card references every retrieved hit (set-level attribution).
    assert len(result.provenance) == 2 * 2
    assert {record.source_id for record in result.provenance} == {"a.md", "b.md"}
    assert all(record.role is ProvenanceRole.EVIDENCE_CHUNK for record in result.provenance)


def test_flashcard_deterministic_output() -> None:
    first = FlashcardTaskHandler(ScriptedGenerate([_cards(2)])).handle(
        _context({"count": 2})
    )
    second = FlashcardTaskHandler(ScriptedGenerate([_cards(2)])).handle(
        _context({"count": 2})
    )

    assert first == second


def test_flashcard_duplicate_fronts_rejected() -> None:
    payload = {"cards": [{"front": "same?", "back": "one"}, {"front": "Same? ", "back": "two"}]}
    handler = FlashcardTaskHandler(ScriptedGenerate([payload, payload]))

    with pytest.raises(HandlerError):
        handler.handle(_context({"count": 2}))


def test_flashcard_malformed_json_retries_then_succeeds() -> None:
    malformed = {"cards": [{"front": "no-back"}]}
    handler = FlashcardTaskHandler(ScriptedGenerate([malformed, _cards(1)]))

    result = handler.handle(_context({"count": 1}))

    assert result.metadata == {"cards": "1"}


def test_flashcard_second_failure_raises() -> None:
    malformed = {"cards": [{"front": "no-back"}]}
    handler = FlashcardTaskHandler(ScriptedGenerate([malformed, malformed]))

    with pytest.raises(HandlerError):
        handler.handle(_context({"count": 1}))


def test_flashcard_transport_failure_fails_immediately() -> None:
    handler = FlashcardTaskHandler(ScriptedGenerate([RuntimeError("down")]))

    with pytest.raises(HandlerError):
        handler.handle(_context({"count": 1}))


def test_flashcard_empty_item_rejected() -> None:
    payload = {"cards": [{"front": "  ", "back": "answer"}]}
    handler = FlashcardTaskHandler(ScriptedGenerate([payload, payload]))

    with pytest.raises(HandlerError):
        handler.handle(_context({"count": 1}))


def test_flashcard_count_bounds_rejected() -> None:
    handler = FlashcardTaskHandler(ScriptedGenerate([_cards(1)]))

    with pytest.raises(HandlerError):
        handler.handle(_context({"count": 0}))
    with pytest.raises(HandlerError):
        handler.handle(_context({"count": 16}))


def test_flashcard_ignores_stray_explanation_key() -> None:
    # The Flashcard model is front/back only: no explanation option exists.
    # A supplied key must not change behavior or fail validation.
    handler = FlashcardTaskHandler(ScriptedGenerate([_cards(1)]))

    result = handler.handle(_context({"count": 1, "explanation": True}))

    assert result.metadata == {"cards": "1"}


# ── Quiz ──────────────────────────────────────────────────────────────


def test_quiz_task_type_and_kind() -> None:
    handler = QuizTaskHandler(ScriptedGenerate([_mcqs(2)]))

    assert handler.task_type is GenerationTaskType.QUIZ
    result = handler.handle(_context({"count": 2}, task="quiz"))

    assert result.kind is ArtifactKind.QUIZ
    assert result.metadata == {"questions": "2", "question_type": "mcq"}


@pytest.mark.parametrize("options", [2, 3, 4, 5, 6])
def test_quiz_option_counts_accepted(options: int) -> None:
    handler = QuizTaskHandler(ScriptedGenerate([_mcqs(1, options)]))

    result = handler.handle(_context({"count": 1}, task="quiz"))

    assert "A. " in (result.content or "")


def test_quiz_option_bounds_rejected() -> None:
    handler = QuizTaskHandler(ScriptedGenerate([_mcqs(1)]))

    with pytest.raises(HandlerError):
        handler.handle(_context({"count": 1, "options_per_question": 1}, task="quiz"))
    with pytest.raises(HandlerError):
        handler.handle(_context({"count": 1, "options_per_question": 7}, task="quiz"))


def test_quiz_duplicate_options_rejected() -> None:
    payload = {
        "questions": [
            {
                "question": "q?",
                "options": ["same", "same"],
                "correct_answer": "same",
                "explanation": "",
            }
        ]
    }
    handler = QuizTaskHandler(ScriptedGenerate([payload, payload]))

    with pytest.raises(HandlerError):
        handler.handle(_context({"count": 1}, task="quiz"))


def test_quiz_correct_answer_must_match_option() -> None:
    payload = {
        "questions": [
            {
                "question": "q?",
                "options": ["a", "b"],
                "correct_answer": "c",
                "explanation": "",
            }
        ]
    }
    handler = QuizTaskHandler(ScriptedGenerate([payload, payload]))

    with pytest.raises(HandlerError):
        handler.handle(_context({"count": 1}, task="quiz"))


def test_quiz_duplicate_questions_rejected() -> None:
    payload = {
        "questions": [
            {"question": "Same? ", "options": ["a", "b"], "correct_answer": "a", "explanation": ""},
            {"question": "same?", "options": ["c", "d"], "correct_answer": "c", "explanation": ""},
        ]
    }
    handler = QuizTaskHandler(ScriptedGenerate([payload, payload]))

    with pytest.raises(HandlerError):
        handler.handle(_context({"count": 2}, task="quiz"))


def test_quiz_non_mcq_rejected() -> None:
    handler = QuizTaskHandler(ScriptedGenerate([_mcqs(1)]))

    with pytest.raises(HandlerError):
        handler.handle(_context({"count": 1, "question_type": "true_false"}, task="quiz"))


def test_quiz_explanation_respected() -> None:
    with_explanation = QuizTaskHandler(ScriptedGenerate([_mcqs(1)])).handle(
        _context({"count": 1, "explanation": True}, task="quiz")
    )
    without_explanation = QuizTaskHandler(ScriptedGenerate([_mcqs(1)])).handle(
        _context({"count": 1, "explanation": False}, task="quiz")
    )

    assert "because 0" in (with_explanation.content or "")
    assert "Explanation" not in (without_explanation.content or "")


def test_quiz_provenance_and_rendering() -> None:
    handler = QuizTaskHandler(ScriptedGenerate([_mcqs(2)]))

    result = handler.handle(_context({"count": 2}, task="quiz"))

    assert len(result.provenance) == 2 * 2
    assert "**Answer:** option a" in (result.content or "")
    assert "## Question 2" in (result.content or "")


def test_quiz_malformed_then_retry_then_failure() -> None:
    malformed = {"questions": [{"question": "incomplete"}]}
    handler = QuizTaskHandler(ScriptedGenerate([malformed, _mcqs(1)]))

    assert handler.handle(_context({"count": 1}, task="quiz")).metadata["questions"] == "1"

    failing = QuizTaskHandler(ScriptedGenerate([malformed, malformed]))
    with pytest.raises(HandlerError):
        failing.handle(_context({"count": 1}, task="quiz"))
