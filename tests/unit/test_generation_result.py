"""Tests for the V2 generation-result domain model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.artifacts import ArtifactKind, ProvenanceRecord, ProvenanceRole
from app.domain.generation_result import GenerationResult


def _provenance() -> tuple[ProvenanceRecord, ...]:
    return (
        ProvenanceRecord(
            artifact_id="pending", source_id="a.md", role=ProvenanceRole.EVIDENCE_CHUNK
        ),
    )


def test_valid_content_result() -> None:
    result = GenerationResult(kind=ArtifactKind.FLASHCARDS, title="Deck", content="# q")

    assert result.content == "# q"
    assert result.content_ref is None


def test_valid_content_ref_result() -> None:
    result = GenerationResult(
        kind=ArtifactKind.REPORT, title="Report", content_ref="artifacts/r.md"
    )

    assert result.content is None
    assert result.content_ref == "artifacts/r.md"


def test_empty_result_is_rejected() -> None:
    with pytest.raises(ValidationError):
        GenerationResult(kind=ArtifactKind.QUIZ, title="Quiz")
    with pytest.raises(ValidationError):
        GenerationResult(kind=ArtifactKind.QUIZ, title="   ", content="# q")


def test_metadata_validation() -> None:
    result = GenerationResult(
        kind=ArtifactKind.QUIZ, title="Quiz", content="# q", metadata={"a": "b"}
    )

    assert result.metadata == {"a": "b"}
    with pytest.raises(ValidationError):
        GenerationResult(kind=ArtifactKind.QUIZ, title="Q", content="# q", metadata={"": "x"})
    with pytest.raises(ValidationError):
        GenerationResult(
            kind=ArtifactKind.QUIZ, title="Q", content="# q", metadata={"k": 1}
        )


def test_provenance_candidates() -> None:
    result = GenerationResult(
        kind=ArtifactKind.FLASHCARDS,
        title="Deck",
        content="# q",
        provenance=_provenance(),
    )

    assert result.provenance == _provenance()
    assert GenerationResult(
        kind=ArtifactKind.FLASHCARDS, title="Deck", content="# q"
    ).provenance == ()


def test_deterministic_serialization() -> None:
    result = GenerationResult(
        kind=ArtifactKind.FLASHCARDS,
        title="Deck",
        content="# q",
        metadata={"a": "b"},
        provenance=_provenance(),
    )

    assert GenerationResult.model_validate_json(result.model_dump_json()) == result
