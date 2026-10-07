"""Prompt builder for V2.1-B memory extraction.

Proposes candidate long-term memories from one conversation's messages. The
model supplies content proposals only — identifiers, timestamps, status, and
provenance links are assigned by the application service, never the model.
Follows the structured-JSON style of ``prompts/generation.py``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.domain.memory import MemoryCategory

EXTRACTION_SYSTEM_PROMPT = """\
You propose candidate long-term memories from a conversation transcript.
Return only valid JSON. Do not wrap the JSON in Markdown. Do not include \
commentary outside the JSON.
Propose only durable, user-origin facts: personal facts, preferences, goals, \
decisions, constraints, project facts, stable personal information, explicit \
corrections. Never propose questions, small talk, transient or time-bound \
statements, assistant-only claims, or inferences the user did not state.
Ground every candidate in a quoted span from a USER message. Assistant text \
may only corroborate a claim a later USER message explicitly confirms; in \
that case still ground the candidate in the confirming USER message.
Do not invent facts, identifiers, timestamps, or lifecycle states.
"""


class ProposedMemory(BaseModel):
    """One raw memory proposal from the extraction model.

    Deliberately narrow: no identifiers, no timestamps, no status, no
    review. The service assigns everything privileged after validation.
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    category: MemoryCategory
    confidence: float
    message_id: str
    seq: int
    quoted_text: str


class ProposedMemorySet(BaseModel):
    """Top-level structured-output contract for one extraction call."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[ProposedMemory] = []


def build_extraction_user_prompt(
    conversation_id: str, transcript: str, *, max_candidates: int = 10
) -> str:
    """Build the user prompt requesting memory proposals for one conversation."""

    return f"""\
Propose at most {max_candidates} candidate long-term memories from the \
conversation transcript below (conversation id: {conversation_id}).

Return JSON with exactly this structure:
{{
  "candidates": [
    {{
      "text": "...",
      "category": "fact | preference | goal | decision | constraint | project | correction",
      "confidence": 0.0,
      "message_id": "...",
      "seq": 0,
      "quoted_text": "..."
    }}
  ]
}}

Rules:
- "text" is one concise durable statement, at most 2000 characters.
- "category" is exactly one of the listed values.
- "confidence" is a number between 0.0 and 1.0.
- "message_id" and "seq" identify the USER message carrying the claim.
- "quoted_text" is the exact span from that USER message supporting the claim.
- Skip assistant messages entirely, including failed generations.
- Skip questions, small talk, and transient or time-bound statements.
- Return an empty "candidates" list when nothing durable is present.

Transcript:
{transcript}
"""
