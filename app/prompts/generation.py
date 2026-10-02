"""Prompt builders for V2 flashcard and quiz generation.

Follows the structured-JSON style of ``prompts/document_analysis.py``: the
system prompt states the exact JSON contract, the user prompt carries the
retrieved context deterministically. Prompts never ask the model to invent
provenance — item-to-chunk mapping is done deterministically afterwards.
"""

from __future__ import annotations

from app.domain.generation_context import GenerationContext

GENERATION_SYSTEM_PROMPT = """\
You generate study material from supplied source context.
Return only valid JSON. Do not wrap the JSON in Markdown. Do not include \
commentary outside the JSON.
Answer only from the supplied context. Do not invent facts, claims, or \
source identifiers that are not supported by the context.
"""


def _context_block(context: GenerationContext) -> str:
    """Render retrieved chunks deterministically for prompt inclusion."""

    if not context.hits:
        return "No source context was retrieved."
    parts: list[str] = []
    for index, hit in enumerate(context.hits, 1):
        parts.append(f"[chunk {index}] source: {hit.source}\n{hit.text.strip()}")
    return "\n\n".join(parts)


def build_flashcard_user_prompt(
    context: GenerationContext, *, count: int, difficulty: str
) -> str:
    """Build the user prompt requesting exactly ``count`` flashcards."""

    return f"""\
Generate exactly {count} flashcards ({difficulty} difficulty) from the \
source context below. Each card needs a front (term/question) and a back \
(definition/answer).

Return JSON with exactly this structure:
{{
  "cards": [
    {{"front": "...", "back": "..."}}
  ]
}}

Rules:
- Generate exactly {count} cards, no more, no fewer.
- Every front and back must be non-empty.
- Do not repeat the same front twice.
- Keep each back concise and directly supported by the context.

Source context:
{_context_block(context)}
"""


def build_quiz_user_prompt(
    context: GenerationContext,
    *,
    count: int,
    difficulty: str,
    options_per_question: int,
    explanation: bool,
) -> str:
    """Build the user prompt requesting exactly ``count`` MCQs."""

    explanation_rule = (
        "Include a brief explanation for each question."
        if explanation
        else "Leave the explanation field empty for each question."
    )
    return f"""\
Generate exactly {count} multiple-choice questions ({difficulty} difficulty) \
from the source context below. This is MCQ only.

Return JSON with exactly this structure:
{{
  "questions": [
    {{
      "question": "...",
      "options": ["...", "..."],
      "correct_answer": "...",
      "explanation": "..."
    }}
  ]
}}

Rules:
- Generate exactly {count} questions, no more, no fewer.
- Every question must have exactly {options_per_question} options.
- All options within one question must be unique.
- correct_answer must exactly match one of the options.
- Do not repeat the same question twice.
- {explanation_rule}
- Keep questions and explanations directly supported by the context.

Source context:
{_context_block(context)}
"""


def add_generation_retry_instruction(prompt: str) -> str:
    """Append a correction instruction after a malformed generation attempt."""

    return (
        f"{prompt}\n\n"
        "The previous response was not valid for the required schema. "
        "Return only corrected JSON with all required fields."
    )
