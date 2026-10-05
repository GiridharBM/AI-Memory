"""Prompt builder for V2-H image prompt planning.

The planner (qwen3:8b via the existing structured ``generate_json`` seam)
distills retrieved memory context into a concise visual prompt. The
diffusion model never sees raw chunks — only this distilled plan.
Follows the structured-JSON style of ``prompts/generation.py``.
"""

from __future__ import annotations

from app.domain.generation_context import GenerationContext


def _context_block(context: GenerationContext) -> str:
    """Render retrieved chunks deterministically for prompt inclusion."""

    if not context.hits:
        return "No source context was retrieved."
    parts: list[str] = []
    for index, hit in enumerate(context.hits, 1):
        parts.append(f"[chunk {index}] source: {hit.source}\n{hit.text.strip()}")
    return "\n\n".join(parts)


def build_image_plan_user_prompt(
    context: GenerationContext, *, title: str | None, detail: str
) -> str:
    """Build the user prompt requesting a structured visual plan."""

    title_rule = (
        f'The image must be titled "{title}".'
        if title
        else "Choose a concise image title from the context."
    )
    return f"""\
Plan a single AI-generated illustration ({detail} detail) from the source \
context below. {title_rule}

Return JSON with exactly this structure:
{{
  "prompt": "...",
  "negative_prompt": "...",
  "title": "..."
}}

Rules:
- "prompt" is one concise visual description (subject, setting, style, \
composition), at most 1000 characters, directly grounded in the context.
- "negative_prompt" lists artefacts to avoid (e.g. "blurry, watermark, \
garbled text"); it may be empty.
- Do not invent facts, names, or claims that are not supported by the \
context.
- Do not invent source identifiers.
- Describe only what the image should show, not the generation process.
- Return only valid JSON. Do not wrap the JSON in Markdown.

Source context:
{_context_block(context)}
"""
