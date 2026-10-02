"""Tests for the V2 memory-scope domain abstraction."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.scopes import (
    MemoryScope,
    MemoryScopeKind,
    UnsupportedMemoryScopeError,
    resolve_memory_scope,
)


def test_all_scope_matches_everything() -> None:
    scope = MemoryScope.all()

    assert scope.kind is MemoryScopeKind.ALL
    resolved = resolve_memory_scope(scope)

    assert resolved.restricted is False
    assert resolved.matches_source("anything.md") is True
    assert resolved.matches_source("https://example.com/r") is True


def test_document_scope_matches_listed_sources_only() -> None:
    scope = MemoryScope.documents(["b.md", "a.md"])

    assert scope.kind is MemoryScopeKind.DOCUMENTS
    assert scope.source_ids == ("a.md", "b.md")
    resolved = resolve_memory_scope(scope)

    assert resolved.restricted is True
    assert resolved.matches_source("a.md") is True
    assert resolved.matches_source("b.md") is True
    assert resolved.matches_source("c.md") is False


def test_topic_scope_carries_node_identifiers() -> None:
    scope = MemoryScope.topics(["t2", "t1"])

    assert scope.kind is MemoryScopeKind.TOPICS
    assert scope.topic_ids == ("t1", "t2")
    resolved = resolve_memory_scope(scope)

    assert resolved.restricted is True
    assert resolved.node_ids == ("t1", "t2")
    # Node identifiers need KG access to expand; they never claim sources.
    assert resolved.matches_source("t1") is False


def test_node_scope_carries_node_identifiers() -> None:
    scope = MemoryScope.nodes(["n1"])

    assert scope.kind is MemoryScopeKind.NODES
    resolved = resolve_memory_scope(scope)

    assert resolved.restricted is True
    assert resolved.node_ids == ("n1",)
    assert resolved.matches_source("n1") is False


def test_project_scope_is_representable_but_unresolvable() -> None:
    scope = MemoryScope.projects(["p1"])

    assert scope.kind is MemoryScopeKind.PROJECTS
    assert scope.project_ids == ("p1",)
    with pytest.raises(UnsupportedMemoryScopeError):
        resolve_memory_scope(scope)


def test_project_resolution_never_falls_back_to_unrestricted() -> None:
    with pytest.raises(UnsupportedMemoryScopeError):
        resolve_memory_scope(MemoryScope.projects(["p1"]))


def test_empty_selections_are_rejected() -> None:
    with pytest.raises(ValidationError):
        MemoryScope.documents([])
    with pytest.raises(ValidationError):
        MemoryScope.topics([])
    with pytest.raises(ValidationError):
        MemoryScope.projects([])
    with pytest.raises(ValidationError):
        MemoryScope.nodes([])


def test_invalid_scope_values_are_rejected() -> None:
    with pytest.raises(ValidationError):
        MemoryScope.documents(["  "])
    with pytest.raises(ValidationError):
        MemoryScope(kind=MemoryScopeKind.DOCUMENTS, topic_ids=("t1",))
    with pytest.raises(ValidationError):
        MemoryScope(kind=MemoryScopeKind.ALL, source_ids=("a.md",))
    with pytest.raises(ValidationError):
        MemoryScope(kind="everything")  # type: ignore[arg-type]


def test_identifiers_are_normalized_deterministically() -> None:
    first = MemoryScope.documents(["b.md", " a.md ", "b.md"])
    second = MemoryScope.documents(["a.md", "b.md"])

    assert first == second
    assert hash(first) == hash(second)
    assert first.source_ids == ("a.md", "b.md")


def test_serialization_round_trip() -> None:
    scope = MemoryScope.documents(["b.md", "a.md"])

    restored = MemoryScope.model_validate_json(scope.model_dump_json())

    assert restored == scope
    assert resolve_memory_scope(restored).matches_source("a.md") is True
