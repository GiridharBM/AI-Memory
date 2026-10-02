"""Domain models for V2 memory scopes.

A memory scope is a query-time selection abstraction over the single shared
PAM memory. It resolves into existing identifiers and filters — it never
creates a second vector store, a second knowledge store, or a new index.

Resolution is a pure function of the scope (``resolve_memory_scope``): no
filesystem access, no network access, no retrieval execution, no mutation.
KG-backed expansion (topics/nodes to sources) is future work for the
feature that needs it; the resolver only represents what is supported now.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class MemoryScopeKind(StrEnum):
    """The selection dimension a memory scope restricts."""

    ALL = "all"
    DOCUMENTS = "documents"
    TOPICS = "topics"
    PROJECTS = "projects"
    NODES = "nodes"


def _clean_ids(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Strip, drop blanks, dedupe, and sort identifiers deterministically."""

    cleaned = {value.strip() for value in values}
    cleaned.discard("")
    return tuple(sorted(cleaned))


class MemoryScope(BaseModel):
    """An immutable, validated selection over shared PAM memory.

    Only the identifier set matching ``kind`` may be non-empty; every other
    combination is rejected at construction so invalid scopes cannot be built.
    ``projects`` is structural only: project grouping is undecided, so a
    project scope is representable but explicitly unresolvable.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: MemoryScopeKind
    source_ids: tuple[str, ...] = ()
    topic_ids: tuple[str, ...] = ()
    project_ids: tuple[str, ...] = ()
    node_ids: tuple[str, ...] = ()

    @field_validator("source_ids", "topic_ids", "project_ids", "node_ids", mode="before")
    @classmethod
    def _normalize_ids(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            value = (value,)
        if value is None:
            return ()
        if not isinstance(value, (tuple, list)):
            raise ValueError("Scope identifiers must be a sequence of strings.")
        if not all(isinstance(item, str) for item in value):
            raise ValueError("Scope identifiers must all be strings.")
        return _clean_ids(value)

    @model_validator(mode="after")
    def _validate_kind_matches_ids(self) -> MemoryScope:
        selections = {
            MemoryScopeKind.DOCUMENTS: self.source_ids,
            MemoryScopeKind.TOPICS: self.topic_ids,
            MemoryScopeKind.PROJECTS: self.project_ids,
            MemoryScopeKind.NODES: self.node_ids,
        }
        if self.kind is MemoryScopeKind.ALL:
            if any(selections.values()):
                raise ValueError("An 'all' scope takes no identifiers.")
            return self
        if not selections[self.kind]:
            raise ValueError(f"A '{self.kind.value}' scope needs at least one identifier.")
        for kind, ids in selections.items():
            if kind is not self.kind and ids:
                raise ValueError(
                    f"Identifiers for '{kind.value}' do not belong in a "
                    f"'{self.kind.value}' scope."
                )
        return self

    @classmethod
    def all(cls) -> MemoryScope:
        """Unrestricted scope: the whole shared memory."""

        return cls(kind=MemoryScopeKind.ALL)

    @classmethod
    def documents(cls, source_ids: tuple[str, ...] | list[str]) -> MemoryScope:
        """Scope to explicit document source identifiers (vector ``source`` values)."""

        return cls(kind=MemoryScopeKind.DOCUMENTS, source_ids=tuple(source_ids))

    @classmethod
    def topics(cls, topic_ids: tuple[str, ...] | list[str]) -> MemoryScope:
        """Scope to topic/concept knowledge-graph node identifiers."""

        return cls(kind=MemoryScopeKind.TOPICS, topic_ids=tuple(topic_ids))

    @classmethod
    def projects(cls, project_ids: tuple[str, ...] | list[str]) -> MemoryScope:
        """Scope to project identifiers (structural; resolution is TBD)."""

        return cls(kind=MemoryScopeKind.PROJECTS, project_ids=tuple(project_ids))

    @classmethod
    def nodes(cls, node_ids: tuple[str, ...] | list[str]) -> MemoryScope:
        """Scope to explicit knowledge-graph node identifiers."""

        return cls(kind=MemoryScopeKind.NODES, node_ids=tuple(node_ids))


class ResolvedScope(BaseModel):
    """A memory scope resolved against current PAM data (still pure, no I/O).

    ``restricted=False`` means unrestricted memory. When restricted, only the
    listed identifiers match; an empty ``source_ids`` on a node/topic scope
    matches no source (node identifiers need KG access to expand, which no
    V2-A consumer performs yet).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    restricted: bool
    source_ids: tuple[str, ...] = ()
    node_ids: tuple[str, ...] = ()

    def matches_source(self, source: str) -> bool:
        """Return whether a vector ``source`` value falls inside this scope."""

        if not self.restricted:
            return True
        return source in self.source_ids


class UnsupportedMemoryScopeError(ValueError):
    """A scope kind with no supported resolution (currently: projects)."""


def resolve_memory_scope(scope: MemoryScope) -> ResolvedScope:
    """Resolve a scope into matchable identifiers without touching storage.

    Project scopes raise :class:`UnsupportedMemoryScopeError` rather than
    falling back to unrestricted memory: an unresolvable scope must fail
    closed, never silently widen.
    """

    if scope.kind is MemoryScopeKind.ALL:
        return ResolvedScope(restricted=False)
    if scope.kind is MemoryScopeKind.PROJECTS:
        raise UnsupportedMemoryScopeError(
            "Project scopes have no supported resolution yet (project grouping "
            "is undecided); refusing to fall back to unrestricted memory."
        )
    if scope.kind is MemoryScopeKind.DOCUMENTS:
        return ResolvedScope(restricted=True, source_ids=scope.source_ids)
    if scope.kind is MemoryScopeKind.TOPICS:
        return ResolvedScope(restricted=True, node_ids=scope.topic_ids)
    return ResolvedScope(restricted=True, node_ids=scope.node_ids)
