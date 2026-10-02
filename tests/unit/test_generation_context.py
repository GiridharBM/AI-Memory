"""Tests for the V2 generation-context domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.generation import GenerationRequest
from app.domain.generation_context import GenerationContext, RetrievedChunk
from app.domain.knowledge_graph import KnowledgeNode
from app.domain.scopes import MemoryScope, resolve_memory_scope


def _request() -> GenerationRequest:
    return GenerationRequest(task_type="flashcards", memory_scope=MemoryScope.all())


def _chunk(source: str = "a.md") -> RetrievedChunk:
    return RetrievedChunk(source=source, text="body", entry_id=f"{source}::0")


def _node(node_id: str = "concept::rag") -> KnowledgeNode:
    return KnowledgeNode(id=node_id, label="rag", node_type="concept", source="a.md")


def test_context_is_immutable() -> None:
    context = GenerationContext(
        request=_request(), scope=resolve_memory_scope(MemoryScope.all())
    )

    with pytest.raises(ValidationError):
        context.request = _request()  # type: ignore[misc]


def test_context_preserves_request_scope_hits_and_nodes() -> None:
    request = _request()
    hits = (_chunk("a.md"), _chunk("b.md"))
    nodes = (_node(),)
    context = GenerationContext(
        request=request,
        scope=resolve_memory_scope(MemoryScope.all()),
        hits=hits,
        nodes=nodes,
    )

    assert context.request == request
    assert context.scope.restricted is False
    assert context.hits == hits
    assert context.nodes == nodes


def test_context_defaults_to_empty_evidence() -> None:
    context = GenerationContext(
        request=_request(), scope=resolve_memory_scope(MemoryScope.all())
    )

    assert context.hits == ()
    assert context.nodes == ()


def test_context_serialization_round_trip() -> None:
    context = GenerationContext(
        request=_request(),
        scope=resolve_memory_scope(MemoryScope.documents(["a.md"])),
        hits=(_chunk("a.md"),),
        nodes=(_node(),),
    )

    restored = GenerationContext.model_validate_json(context.model_dump_json())

    assert restored == context
