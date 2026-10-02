"""V2 quiz generation handler (MCQ only).

Same shape as the flashcard handler: structured prompt from context hits,
one correction retry on malformed output, strict MCQ validation, and a
``GenerationResult``. Persistence belongs to the executor.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import ValidationError

from app.application.generation_errors import HandlerError
from app.domain.analysis import DifficultyLevel, MultipleChoiceQuestion
from app.domain.artifacts import ArtifactKind, ProvenanceRecord, ProvenanceRole
from app.domain.generation import GenerationTaskType
from app.domain.generation_context import GenerationContext
from app.domain.generation_result import GenerationResult
from app.domain.generation_sets import QuizSet
from app.prompts.generation import (
    GENERATION_SYSTEM_PROMPT,
    add_generation_retry_instruction,
    build_quiz_user_prompt,
)

MAX_QUIZ_COUNT = 10
DEFAULT_QUIZ_COUNT = 5
DEFAULT_OPTIONS_PER_QUESTION = 4

# (system prompt, user prompt, response model) -> parsed set. A thin lambda
# over OllamaClient.generate_json binds the real client without the handler
# importing provider code.
GenerateQuiz = Callable[[str, str, "type[QuizSet]"], QuizSet]


@dataclass(slots=True, frozen=True)
class _QuizConfig:
    count: int
    difficulty: DifficultyLevel
    options_per_question: int
    explanation: bool


def _parse_config(config: dict[str, object]) -> _QuizConfig:
    count = config.get("count", DEFAULT_QUIZ_COUNT)
    if isinstance(count, bool) or not isinstance(count, int):
        raise HandlerError("Quiz 'count' must be an integer.")
    if not 1 <= count <= MAX_QUIZ_COUNT:
        raise HandlerError(f"Quiz 'count' must be between 1 and {MAX_QUIZ_COUNT}.")
    difficulty = config.get("difficulty", "intermediate")
    if difficulty not in ("beginner", "intermediate", "advanced"):
        raise HandlerError(
            "Quiz 'difficulty' must be beginner, intermediate, or advanced."
        )
    question_type = config.get("question_type", "mcq")
    if question_type != "mcq":
        raise HandlerError("Quiz 'question_type' must currently equal \"mcq\".")
    options = config.get("options_per_question", DEFAULT_OPTIONS_PER_QUESTION)
    if isinstance(options, bool) or not isinstance(options, int):
        raise HandlerError("Quiz 'options_per_question' must be an integer.")
    if not 2 <= options <= 6:
        raise HandlerError("Quiz 'options_per_question' must be between 2 and 6.")
    explanation = config.get("explanation", True)
    if not isinstance(explanation, bool):
        raise HandlerError("Quiz 'explanation' must be a boolean.")
    return _QuizConfig(
        count=count,
        difficulty=difficulty,  # type: ignore[arg-type]
        options_per_question=options,
        explanation=explanation,
    )


def _validate_questions(
    questions: list[MultipleChoiceQuestion], config: _QuizConfig
) -> list[MultipleChoiceQuestion]:
    if len(questions) != config.count:
        raise HandlerError(
            f"Expected exactly {config.count} questions, got {len(questions)}."
        )
    seen: set[str] = set()
    validated: list[MultipleChoiceQuestion] = []
    for question in questions:
        text = question.question.strip()
        if not text:
            raise HandlerError("Quiz questions must be non-empty.")
        options = [option.strip() for option in question.options]
        if not 2 <= len(options) <= 6:
            raise HandlerError("Each quiz question needs 2–6 options.")
        if len(set(options)) != len(options):
            raise HandlerError(f"Duplicate quiz options in: {text!r}.")
        if question.correct_answer.strip() not in options:
            raise HandlerError(
                f"Correct answer must exactly match one option in: {text!r}."
            )
        key = text.casefold()
        if key in seen:
            raise HandlerError(f"Duplicate quiz question: {text!r}.")
        seen.add(key)
        explanation = question.explanation.strip() if config.explanation else ""
        validated.append(
            question.model_copy(
                update={
                    "question": text,
                    "options": options,
                    "correct_answer": question.correct_answer.strip(),
                    "explanation": explanation,
                }
            )
        )
    return validated


def _render(questions: list[MultipleChoiceQuestion]) -> str:
    parts = ["# Quiz", ""]
    for index, question in enumerate(questions, 1):
        parts.append(f"## Question {index}")
        parts.append("")
        parts.append(question.question.strip())
        parts.append("")
        for option_index, option in enumerate(question.options):
            parts.append(f"{chr(65 + option_index)}. {option}")
        parts.append("")
        parts.append(f"**Answer:** {question.correct_answer.strip()}")
        if question.explanation.strip():
            parts.append("")
            parts.append(f"**Explanation:** {question.explanation.strip()}")
        parts.append("")
    return "\n".join(parts).rstrip()


def _provenance(context: GenerationContext) -> tuple[ProvenanceRecord, ...]:
    """One candidate per retrieved hit (set-level attribution).

    The model generates from the whole context, so per-item records reference
    every retrieved chunk rather than fabricating item-to-chunk mapping. The
    caller repeats these per generated question.
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


class QuizTaskHandler:
    """Generate a multiple-choice quiz set from retrieved memory context."""

    task_type = GenerationTaskType.QUIZ

    def __init__(self, generate_json: GenerateQuiz) -> None:
        self._generate_json = generate_json

    def handle(self, context: GenerationContext) -> GenerationResult:
        config = _parse_config(dict(context.request.config))
        prompt = build_quiz_user_prompt(
            context,
            count=config.count,
            difficulty=config.difficulty,
            options_per_question=config.options_per_question,
            explanation=config.explanation,
        )
        quiz_set = self._generate_with_retry(prompt, config)
        questions = _validate_questions(list(quiz_set.questions), config)
        per_hit = _provenance(context)
        return GenerationResult(
            kind=ArtifactKind.QUIZ,
            title=f"Quiz ({len(questions)} questions)",
            content=_render(questions),
            metadata={
                "questions": str(len(questions)),
                "question_type": "mcq",
            },
            provenance=tuple(record for _ in questions for record in per_hit),
        )

    def _generate_with_retry(self, prompt: str, config: _QuizConfig) -> QuizSet:
        last_error: Exception | None = None
        current = prompt
        for _ in range(2):
            try:
                quiz_set = self._generate_json(GENERATION_SYSTEM_PROMPT, current, QuizSet)
            except ValidationError as exc:
                last_error = exc
            except Exception as exc:
                raise HandlerError(f"Quiz generation failed: {exc}") from exc
            else:
                try:
                    _validate_questions(list(quiz_set.questions), config)
                except HandlerError as exc:
                    last_error = exc
                else:
                    return quiz_set
            current = add_generation_retry_instruction(prompt)
        raise HandlerError(f"Quiz generation failed after retry: {last_error}")
