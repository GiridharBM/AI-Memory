"""Structural validation for V2 generation results.

Only infrastructure-level constraints: kind compatibility with the task,
provenance completeness under STRICT, and generous size guardrails. No
semantic quality assessment, no evidence verification, no model scoring —
the evidence-verification research track remains independent.
"""

from __future__ import annotations

from app.application.generation_errors import GenerationValidationError
from app.domain.artifacts import ArtifactKind
from app.domain.generation import GenerationRequest, GenerationTaskType, ProvenanceLevel
from app.domain.generation_result import GenerationResult

# Task types and the artifact kinds they may produce. ASK yields a grounded
# answer note; enrichment yields a mind-map artifact.
_TASK_KINDS: dict[GenerationTaskType, frozenset[ArtifactKind]] = {
    GenerationTaskType.ASK: frozenset({ArtifactKind.NOTE}),
    GenerationTaskType.FLASHCARDS: frozenset({ArtifactKind.FLASHCARDS}),
    GenerationTaskType.QUIZ: frozenset({ArtifactKind.QUIZ}),
    GenerationTaskType.IMAGE: frozenset({ArtifactKind.IMAGE}),
    GenerationTaskType.VIDEO: frozenset({ArtifactKind.VIDEO}),
    GenerationTaskType.PPT: frozenset({ArtifactKind.PPT}),
    GenerationTaskType.REPORT: frozenset({ArtifactKind.REPORT}),
    GenerationTaskType.MINDMAP_ENRICH: frozenset({ArtifactKind.MINDMAP}),
}

# Guardrails against runaway payloads, not quality judgments. Far above any
# legitimate card/quiz/report draft; adjustable per feature later.
MAX_RESULT_TITLE_CHARS = 1000
MAX_RESULT_CONTENT_CHARS = 1_000_000


def _record_locates_source(*, chunk_id: str | None, chunk_index: int | None,
                           kg_node_id: str | None, quote: str | None,
                           start_char: int | None, end_char: int | None) -> bool:
    return any(
        value is not None
        for value in (chunk_id, chunk_index, kg_node_id, quote, start_char, end_char)
    )


def validate_result(request: GenerationRequest, result: GenerationResult) -> None:
    """Validate a handler result against its request; raises on violation."""

    allowed = _TASK_KINDS[request.task_type]
    if result.kind not in allowed:
        raise GenerationValidationError(
            f"Task '{request.task_type.value}' cannot produce "
            f"'{result.kind.value}' artifacts."
        )
    if len(result.title) > MAX_RESULT_TITLE_CHARS:
        raise GenerationValidationError(
            f"Result title exceeds {MAX_RESULT_TITLE_CHARS} characters."
        )
    if result.content is not None and len(result.content) > MAX_RESULT_CONTENT_CHARS:
        raise GenerationValidationError(
            f"Result content exceeds {MAX_RESULT_CONTENT_CHARS} characters."
        )
    if request.provenance is ProvenanceLevel.STRICT:
        if not result.provenance:
            raise GenerationValidationError(
                "STRICT provenance requires at least one provenance record."
            )
        for record in result.provenance:
            if not _record_locates_source(
                chunk_id=record.chunk_id,
                chunk_index=record.chunk_index,
                kg_node_id=record.kg_node_id,
                quote=record.quote,
                start_char=record.start_char,
                end_char=record.end_char,
            ):
                raise GenerationValidationError(
                    "STRICT provenance requires each record to locate its "
                    "source beyond the source id."
                )
