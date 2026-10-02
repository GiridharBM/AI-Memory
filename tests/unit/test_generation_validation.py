"""Tests for V2 structural generation validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.application.generation_errors import GenerationValidationError
from app.application.generation_validation import (
    MAX_RESULT_CONTENT_CHARS,
    MAX_RESULT_TITLE_CHARS,
    validate_result,
)
from app.domain.artifacts import ArtifactKind, ProvenanceRecord, ProvenanceRole
from app.domain.generation import GenerationRequest
from app.domain.generation_result import GenerationResult
from app.domain.scopes import MemoryScope


def _request(**overrides: object) -> GenerationRequest:
    values: dict[str, object] = {"task_type": "flashcards", "memory_scope": MemoryScope.all()}
    values.update(overrides)
    return GenerationRequest(**values)  # type: ignore[arg-type]


def _result(**overrides: object) -> GenerationResult:
    values: dict[str, object] = {
        "kind": ArtifactKind.FLASHCARDS,
        "title": "Deck",
        "content": "# q",
    }
    values.update(overrides)
    return GenerationResult(**values)  # type: ignore[arg-type]


def _located() -> tuple[ProvenanceRecord, ...]:
    return (
        ProvenanceRecord(
            artifact_id="pending",
            source_id="a.md",
            role=ProvenanceRole.EVIDENCE_CHUNK,
            chunk_id="a.md::chunk_0",
        ),
    )


def test_valid_result_passes() -> None:
    validate_result(_request(), _result())


def test_empty_result_rejected_at_construction() -> None:
    with pytest.raises(ValidationError):
        GenerationResult(kind=ArtifactKind.FLASHCARDS, title="Deck")


def test_invalid_title_rejected_at_construction() -> None:
    with pytest.raises(ValidationError):
        GenerationResult(kind=ArtifactKind.FLASHCARDS, title="   ", content="# q")


def test_incompatible_task_and_kind_rejected() -> None:
    with pytest.raises(GenerationValidationError):
        validate_result(_request(task_type="quiz"), _result(kind=ArtifactKind.FLASHCARDS))
    validate_result(_request(task_type="quiz"), _result(kind=ArtifactKind.QUIZ))
    validate_result(_request(task_type="ask"), _result(kind=ArtifactKind.NOTE))


def test_standard_provenance_allows_best_effort() -> None:
    validate_result(_request(provenance="standard"), _result())
    validate_result(
        _request(provenance="standard"),
        _result(
            provenance=(
                ProvenanceRecord(
                    artifact_id="pending",
                    source_id="a.md",
                    role=ProvenanceRole.SOURCE_DOCUMENT,
                ),
            )
        ),
    )


def test_strict_provenance_requires_located_records() -> None:
    with pytest.raises(GenerationValidationError):
        validate_result(_request(provenance="strict"), _result())
    with pytest.raises(GenerationValidationError):
        validate_result(
            _request(provenance="strict"),
            _result(
                provenance=(
                    ProvenanceRecord(
                        artifact_id="pending",
                        source_id="a.md",
                        role=ProvenanceRole.SOURCE_DOCUMENT,
                    ),
                )
            ),
        )
    validate_result(_request(provenance="strict"), _result(provenance=_located()))


def test_structural_size_limits() -> None:
    with pytest.raises(GenerationValidationError):
        validate_result(_request(), _result(title="t" * (MAX_RESULT_TITLE_CHARS + 1)))
    with pytest.raises(GenerationValidationError):
        validate_result(
            _request(), _result(content="x" * (MAX_RESULT_CONTENT_CHARS + 1))
        )
    validate_result(_request(), _result(title="t" * MAX_RESULT_TITLE_CHARS))
