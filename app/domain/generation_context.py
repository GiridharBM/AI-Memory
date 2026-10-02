"""Domain models for V2 generation context.

A generation context is the immutable input bundle a task handler receives:
the request, the resolved scope, and the retrieved evidence. It carries no
filesystem handles, stores, service containers, or mutable state.

``RetrievedChunk`` is the domain-safe projection of a retrieval hit. It
exists because ``SearchHit`` lives in infrastructure (``app.infrastructure``),
which domain must not import; the retrieval adapter converts hits into these
values at the application boundary.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.generation import GenerationRequest
from app.domain.knowledge_graph import KnowledgeNode
from app.domain.scopes import ResolvedScope


class RetrievedChunk(BaseModel):
    """One retrieved evidence chunk, projected into domain vocabulary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    text: str = ""
    entry_id: str = ""
    source_type: str = ""
    score: float = 0.0
    cosine_score: float = 0.0
    chunk_index: int = Field(default=0, ge=0)
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)
    metadata: dict[str, str] = Field(default_factory=dict)


class GenerationContext(BaseModel):
    """Everything a task handler may legitimately need. Immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: GenerationRequest
    scope: ResolvedScope
    hits: tuple[RetrievedChunk, ...] = ()
    nodes: tuple[KnowledgeNode, ...] = ()
