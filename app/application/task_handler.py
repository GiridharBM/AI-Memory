"""Task-handler contract for V2 generation.

A handler is a narrow function of its context: it receives everything it
may legitimately need and returns a result. Handlers must not touch
stores, mutate jobs, perform persistence, or modify retrieval — the
executor owns orchestration and persistence. Mirrors the
``ProcessingWorkflow`` protocol precedent in ``app/queue/worker.py``.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.generation import GenerationTaskType
from app.domain.generation_context import GenerationContext
from app.domain.generation_result import GenerationResult


class TaskHandler(Protocol):
    """One generation capability behind the executor boundary."""

    task_type: GenerationTaskType

    def handle(self, context: GenerationContext) -> GenerationResult:
        """Generate a result from retrieved context (no side effects)."""
        ...


def register_handlers(*handlers: TaskHandler) -> dict[GenerationTaskType, TaskHandler]:
    """Build an explicit handler registry; duplicates fail closed."""

    registry: dict[GenerationTaskType, TaskHandler] = {}
    for handler in handlers:
        if handler.task_type in registry:
            raise ValueError(
                f"Duplicate handler for task '{handler.task_type.value}'."
            )
        registry[handler.task_type] = handler
    return registry
