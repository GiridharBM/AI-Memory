"""Structured LLM response models for V2 flashcard and quiz generation.

The item shapes are reused verbatim from ``app.domain.analysis`` (the same
models ingestion already validates); these wrappers exist solely as
top-level structured-output contracts for generation calls. Provenance is
not embedded here — it lives in ``ProvenanceStore``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.analysis import Flashcard, MultipleChoiceQuestion


class FlashcardSet(BaseModel):
    """A validated set of flashcards from one generation call."""

    model_config = ConfigDict(extra="forbid")

    cards: list[Flashcard] = Field(min_length=1, max_length=15)


class QuizSet(BaseModel):
    """A validated set of multiple-choice questions from one generation call."""

    model_config = ConfigDict(extra="forbid")

    questions: list[MultipleChoiceQuestion] = Field(min_length=1, max_length=10)
