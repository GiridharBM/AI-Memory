"""Runtime memory context for V2.1-C conversation/QA.

Approved durable memories participate in answers through this module only:
deterministic lexical retrieval over ACTIVE memories, formatted as delimited
context blocks appended after document context. No embeddings, no LLM calls,
no vector/BM25/RRF involvement — document RAG is untouched.

Only ACTIVE approved memories are ever returned here. Rejected candidates
never reach the memory store, and superseded versions are excluded by the
active-only read, so neither can become runtime context.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.memory import MAX_MEMORY_CHARS, Memory
from app.infrastructure.memories import MemoryStore
from app.infrastructure.search import SearchHit
from app.prompts.qa import MEMORY_CONTEXT_PREAMBLE

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

#: Default retrieval depth: memories are atomic facts, so a small cap keeps
#: prompt growth bounded inside the existing QA context budget.
DEFAULT_MEMORY_LIMIT = 3

#: Minimum token-overlap score for a memory to participate in an answer.
#: Calibrated by tests; deliberately conservative for the V2.1-C MVP.
DEFAULT_MEMORY_THRESHOLD = 0.5

#: Per-memory text cap inside context blocks. Mirrors the domain bound
#: (memories are validated to at most this length), kept as an explicit
#: guard so context assembly never depends on that invariant alone.
MAX_MEMORY_BLOCK_CHARS = MAX_MEMORY_CHARS


def _tokens(text: str) -> set[str]:
    """Lowercase alphanumeric tokens; deterministic and dependency-free."""

    return set(_TOKEN_PATTERN.findall(text.lower()))


@dataclass(slots=True, frozen=True)
class MemoryMatch:
    """One ACTIVE memory scored against a question."""

    memory: Memory
    score: float


def score_memory(question: str, memory: Memory) -> float:
    """Normalized token overlap: ``|Q ∩ M| / |Q|`` in ``[0.0, 1.0]``.

    Empty questions and empty memory texts score ``0.0`` (never divide by
    zero, never match on nothing).
    """

    question_tokens = _tokens(question)
    if not question_tokens:
        return 0.0
    memory_tokens = _tokens(memory.text)
    if not memory_tokens:
        return 0.0
    return len(question_tokens & memory_tokens) / len(question_tokens)


def retrieve_memories(
    question: str,
    store: MemoryStore,
    *,
    limit: int = DEFAULT_MEMORY_LIMIT,
    threshold: float = DEFAULT_MEMORY_THRESHOLD,
) -> list[MemoryMatch]:
    """Score ACTIVE memories against ``question``, best first.

    Only ``store.active_memories()`` is consulted, so superseded versions
    (and rejected candidates, which never reach the store) are excluded.
    Matches below ``threshold`` are discarded; at most ``limit`` are kept.
    Ordering is deterministic: score descending, then ``(approved_at, id)``.
    Pure local computation — no embeddings, LLM, BM25, RRF, or network.
    """

    if limit <= 0:
        return []
    if not question or not question.strip():
        return []
    matches: list[MemoryMatch] = []
    for memory in store.active_memories():
        score = score_memory(question, memory)
        if score < threshold:
            continue
        matches.append(MemoryMatch(memory=memory, score=score))
    matches.sort(key=lambda item: (-item.score, item.memory.approved_at, item.memory.id))
    return matches[:limit]


def memory_match_to_hit(match: MemoryMatch) -> SearchHit:
    """Project a memory match onto the existing hit shape for citations.

    The ``source``/``entry_id`` encoding is what flows into
    ``EvidenceCitation`` unchanged (no evidence-model changes required).
    Scores stay lexical: ``cosine_score``/``bm25_score`` are ``0.0`` because
    no document-retrieval leg produced this hit, and the abstention gates
    never evaluate these projections — they only see document hits.
    """

    memory = match.memory
    return SearchHit(
        text=memory.text,
        source=f"memory:{memory.logical_id}@v{memory.version}",
        score=match.score,
        entry_id=memory.id,
        metadata={
            "kind": "memory",
            "logical_id": memory.logical_id,
            "version": str(memory.version),
            "category": memory.category.value,
        },
    )


def build_memory_context(
    matches: Sequence[MemoryMatch],
    *,
    start_number: int,
    max_chars: int,
) -> str:
    """Render memory matches as ``[SOURCE N]`` blocks continuing doc numbering.

    ``start_number`` is ``len(document_hits) + 1`` so existing document
    citations never shift. ``max_chars`` is the caller's remaining QA
    context budget — blocks that do not fit are skipped, so the section
    never exceeds it. Each block carries the logical id, version, category,
    text (capped at ``MAX_MEMORY_BLOCK_CHARS``), and grounding quote with
    its source conversation/message, keeping provenance traceable.
    Empty matches (or no budget) produce an empty string.
    """

    if not matches or max_chars <= 0:
        return ""
    blocks: list[str] = []
    used = 0
    for offset, match in enumerate(matches):
        memory = match.memory
        text = " ".join(memory.text.split())
        if len(text) > MAX_MEMORY_BLOCK_CHARS:
            text = text[:MAX_MEMORY_BLOCK_CHARS]
        grounding = memory.source.grounding
        block = (
            f"[SOURCE {start_number + offset}]\n"
            f"Source: memory:{memory.logical_id}@v{memory.version}\n"
            f"Category: {memory.category.value}\n"
            f"Content:\n{text}\n"
            f'Grounding: "{grounding.quoted_text}" '
            f"(conversation {grounding.conversation_id}, "
            f"message {grounding.message_id}, seq {grounding.seq})"
        )
        if len(block) > max_chars - used:
            continue
        blocks.append(block)
        used += len(block)
    if not blocks:
        return ""
    return f"{MEMORY_CONTEXT_PREAMBLE}\n\n" + "\n\n".join(blocks)
