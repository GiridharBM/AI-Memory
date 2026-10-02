"""Tests for the V2 flashcard/quiz set response models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.generation_sets import FlashcardSet, QuizSet


def _card(front: str = "front", back: str = "back") -> dict[str, str]:
    return {"front": front, "back": back}


def _mcq(question: str = "q?", options: list[str] | None = None) -> dict[str, object]:
    options = options if options is not None else ["a", "b", "c", "d"]
    return {
        "question": question,
        "options": options,
        "correct_answer": options[0],
        "explanation": "because",
    }


def test_valid_flashcard_set() -> None:
    card_set = FlashcardSet(cards=[_card(), _card("f2", "b2")])

    assert len(card_set.cards) == 2
    assert card_set.cards[0].front == "front"


def test_empty_flashcard_set_rejected() -> None:
    with pytest.raises(ValidationError):
        FlashcardSet(cards=[])


def test_valid_quiz_set() -> None:
    quiz_set = QuizSet(questions=[_mcq(), _mcq("q2?")])

    assert len(quiz_set.questions) == 2
    assert quiz_set.questions[0].correct_answer == "a"


def test_malformed_quiz_item_rejected() -> None:
    with pytest.raises(ValidationError):
        QuizSet(questions=[{"question": "q?"}])


def test_quiz_options_bounds_enforced() -> None:
    with pytest.raises(ValidationError):
        QuizSet(questions=[_mcq(options=["only-one"])])
    with pytest.raises(ValidationError):
        QuizSet(questions=[_mcq(options=[f"o{i}" for i in range(7)])])
    valid = QuizSet(questions=[_mcq(options=["a", "b"])])
    assert len(valid.questions[0].options) == 2


def test_invalid_nested_structures_rejected() -> None:
    with pytest.raises(ValidationError):
        FlashcardSet(cards=[{"front": "f"}])
    with pytest.raises(ValidationError):
        QuizSet(questions="not-a-list")


def test_json_round_trip() -> None:
    card_set = FlashcardSet(cards=[_card()])
    quiz_set = QuizSet(questions=[_mcq()])

    assert FlashcardSet.model_validate_json(card_set.model_dump_json()) == card_set
    assert QuizSet.model_validate_json(quiz_set.model_dump_json()) == quiz_set
