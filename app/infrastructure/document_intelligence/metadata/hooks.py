"""Ingestion hook protocol and registry (P2-206).

Frozen §2: ``IngestionHook`` has ``pre(source) -> SourceReference`` and
``post(document) -> SourceDocument``. Hooks are named plugins resolved from
``intelligence.metadata.hooks.pre`` / ``hooks.post``; ``register_hook()`` is
the public registration alias.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core.logging import get_logger
from app.domain.documents import SourceDocument

logger = get_logger(__name__)

SourceReference = str | Path


@runtime_checkable
class IngestionHook(Protocol):
    """Contract implemented by pre/post ingestion hooks (frozen §2)."""

    name: str

    def pre(self, source: SourceReference) -> SourceReference:
        """Transform (or reject) the source reference before ingestion."""
        ...

    def post(self, document: SourceDocument) -> SourceDocument:
        """Transform the ingested document."""
        ...


class HookRegistry:
    """Registry of named hooks used by the ingestion hook chain."""

    def __init__(self, hooks: list[IngestionHook] | None = None) -> None:
        self._hooks: dict[str, IngestionHook] = {}
        for hook in hooks or []:
            self.register(hook)

    def register(self, hook: IngestionHook) -> None:
        """Register a hook by name (idempotent)."""
        self._hooks[hook.name] = hook

    def get(self, name: str) -> IngestionHook | None:
        """Return the hook registered under ``name``, or ``None``."""
        return self._hooks.get(name)


_default_registry: HookRegistry | None = None


def get_default_hook_registry() -> HookRegistry:
    """Return the process-wide default hook registry, creating it lazily."""
    global _default_registry
    if _default_registry is None:
        _default_registry = HookRegistry()
    return _default_registry


def register_hook(hook: IngestionHook) -> None:
    """Register an ingestion hook on the default registry (public alias)."""
    get_default_hook_registry().register(hook)


__all__ = [
    "HookRegistry",
    "IngestionHook",
    "get_default_hook_registry",
    "register_hook",
]
