"""V2 flashcard generation handler.

Retrieves nothing itself: it renders a structured prompt from the
``GenerationContext`` hits, calls the injected structured-output client
(one correction retry on malformed output), validates the cards, and
returns a ``GenerationResult``. Persistence belongs to the executor.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import ValidationError

from app.application.generation_errors import HandlerError
from app.domain.analysis import DifficultyLevel, Flashcard
from app.domain.artifacts import ArtifactKind, ProvenanceRecord, ProvenanceRole
from app.domain.generation import GenerationTaskType
from app.domain.generation_context import GenerationContext
from app.domain.generation_result import GenerationResult
from app.domain.generation_sets import FlashcardSet
from app.prompts.generation import (
    GENERATION_SYSTEM_PROMPT,
    add_generation_retry_instruction,
    build_flashcard_user_prompt,
)

MAX_FLASHCARD_COUNT = 15
DEFAULT_FLASHCARD_COUNT = 5

# (system prompt, user prompt, response model) -> parsed set. A thin lambda
# over OllamaClient.generate_json binds the real client without the handler
# importing provider code.
GenerateFlashcards = Callable[[str, str, "type[FlashcardSet]"], FlashcardSet]


@dataclass(slots=True, frozen=True)
class _FlashcardConfig:
    count: int
    difficulty: DifficultyLevel


def _parse_config(config: dict[str, object]) -> _FlashcardConfig:
    count = config.get("count", DEFAULT_FLASHCARD_COUNT)
    if isinstance(count, bool) or not isinstance(count, int):
        raise HandlerError("Flashcard 'count' must be an integer.")
    if not 1 <= count <= MAX_FLASHCARD_COUNT:
        raise HandlerError(
            f"Flashcard 'count' must be between 1 and {MAX_FLASHCARD_COUNT}."
        )
    difficulty = config.get("difficulty", "intermediate")
    if difficulty not in ("beginner", "intermediate", "advanced"):
        raise HandlerError(
            "Flashcard 'difficulty' must be beginner, intermediate, or advanced."
        )
    # NOTE: flashcards carry no explanation field (existing Flashcard model is
    # front/back only), so there is deliberately no 'explanation' option.
    # A supplied key is ignored like query/topic, which the adapter consumes.
    return _FlashcardConfig(
        count=count, difficulty=difficulty  # type: ignore[arg-type]
    )


def _validate_cards(cards: list[Flashcard], count: int) -> None:
    if len(cards) != count:
        raise HandlerError(
            f"Expected exactly {count} flashcards, got {len(cards)}."
        )
    seen: set[str] = set()
    for card in cards:
        front = card.front.strip()
        back = card.back.strip()
        if not front or not back:
            raise HandlerError("Flashcards must have non-empty front and back.")
        key = front.casefold()
        if key in seen:
            raise HandlerError(f"Duplicate flashcard front: {front!r}.")
        seen.add(key)


def _render(cards: list[Flashcard]) -> str:
    parts = ["# Flashcards", ""]
    for index, card in enumerate(cards, 1):
        parts.append(f"## Card {index}")
        parts.append("")
        parts.append(f"**Front:** {card.front.strip()}")
        parts.append("")
        parts.append(f"**Back:** {card.back.strip()}")
        parts.append("")
    return "\n".join(parts).rstrip()


def _provenance(context: GenerationContext) -> tuple[ProvenanceRecord, ...]:
    """One candidate per retrieved hit (set-level attribution).

    The model generates from the whole context, so per-item records reference
    every retrieved chunk rather than fabricating item-to-chunk mapping. The
    caller repeats these per generated item.
    """

    return tuple(
        ProvenanceRecord(
            artifact_id="pending",
            source_id=hit.source,
            role=ProvenanceRole.EVIDENCE_CHUNK,
            source_type=hit.source_type or None,
            chunk_id=hit.entry_id or None,
            chunk_index=hit.chunk_index,
            start_char=hit.start_char,
            end_char=hit.end_char,
        )
        for hit in context.hits
    )


class FlashcardTaskHandler:
    """Generate a flashcard set from retrieved memory context."""

    task_type = GenerationTaskType.FLASHCARDS

    def __init__(self, generate_json: GenerateFlashcards) -> None:
        self._generate_json = generate_json

    def handle(self, context: GenerationContext) -> GenerationResult:
        config = _parse_config(dict(context.request.config))
        prompt = build_flashcard_user_prompt(
            context, count=config.count, difficulty=config.difficulty
        )
        card_set = self._generate_with_retry(prompt, config)
        cards = list(card_set.cards)
        per_hit = _provenance(context)
        return GenerationResult(
            kind=ArtifactKind.FLASHCARDS,
            title=f"Flashcards ({len(cards)})",
            content=_render(cards),
            metadata={"cards": str(len(cards))},
            provenance=tuple(record for _ in cards for record in per_hit),
        )

    def _generate_with_retry(self, prompt: str, config: _FlashcardConfig) -> FlashcardSet:
        last_error: Exception | None = None
        current = prompt
        for _ in range(2):
            try:
                card_set = self._generate_json(
                    GENERATION_SYSTEM_PROMPT, current, FlashcardSet
                )
            except ValidationError as exc:
                last_error = exc
            except Exception as exc:
                raise HandlerError(f"Flashcard generation failed: {exc}") from exc
            else:
                try:
                    _validate_cards(list(card_set.cards), config.count)
                except HandlerError as exc:
                    last_error = exc
                else:
                    return card_set
            current = add_generation_retry_instruction(prompt)
        raise HandlerError(f"Flashcard generation failed after retry: {last_error}")
