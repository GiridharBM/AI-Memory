"""Tests for the V2 artifact and provenance foundation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.artifacts import (
    Artifact,
    ArtifactKind,
    ProvenanceRecord,
    ProvenanceRole,
    note_to_artifact,
)
from app.domain.generation import GenerationRequest
from app.domain.jobs import GenerationJob
from app.domain.notes import ObsidianNote
from app.domain.scopes import MemoryScope
from app.infrastructure.artifacts import ArtifactStore, ProvenanceStore


def _request() -> GenerationRequest:
    return GenerationRequest(
        task_type="flashcards", memory_scope=MemoryScope.documents(["a.md"])
    )


def _artifact(**overrides: object) -> Artifact:
    values: dict[str, object] = {
        "kind": ArtifactKind.FLASHCARDS,
        "title": "Deck",
        "job_id": "job-1",
        "request": _request(),
        "content": "# cards",
    }
    values.update(overrides)
    return Artifact.create(**values)  # type: ignore[arg-type]


def _artifact_store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "artifacts" / "artifacts.json")


def _provenance_store(tmp_path: Path) -> ProvenanceStore:
    return ProvenanceStore(tmp_path / "artifacts" / "provenance.json")


def _record(artifact_id: str, source_id: str = "a.md") -> ProvenanceRecord:
    return ProvenanceRecord(
        artifact_id=artifact_id, source_id=source_id, role=ProvenanceRole.EVIDENCE_CHUNK
    )


# ── Artifact ──────────────────────────────────────────────────────────


def test_artifact_creation() -> None:
    artifact = _artifact()

    assert artifact.artifact_id
    assert artifact.kind is ArtifactKind.FLASHCARDS
    assert artifact.title == "Deck"


def test_artifact_id_is_stable_and_unique() -> None:
    first = _artifact()
    second = _artifact()

    assert first.artifact_id
    assert first.artifact_id != second.artifact_id


def test_artifact_kind_validation() -> None:
    with pytest.raises(ValidationError):
        _artifact(kind="slideshow")
    assert _artifact(kind="quiz").kind is ArtifactKind.QUIZ


def test_first_version_is_one() -> None:
    artifact = _artifact()

    assert artifact.version == 1
    assert artifact.parent_artifact_id is None
    assert artifact.parent_version is None
    assert artifact.logical_id == artifact.artifact_id


def test_explicit_version_increment_and_linkage() -> None:
    first = _artifact()
    job = GenerationJob.create(_request())

    second = first.new_version(job_id=job.job_id, request=_request())

    assert second.version == 2
    assert second.logical_id == first.logical_id
    assert second.parent_artifact_id == first.artifact_id
    assert second.parent_version == 1
    assert second.artifact_id != first.artifact_id


def test_version_must_start_at_parent_plus_one() -> None:
    first = _artifact()
    job = GenerationJob.create(_request())

    second = first.new_version(job_id=job.job_id, request=_request())
    third = second.new_version(job_id=job.job_id, request=_request())

    assert [row.version for row in (first, second, third)] == [1, 2, 3]


def test_generation_job_binding() -> None:
    job = GenerationJob.create(_request())

    artifact = _artifact(job_id=job.job_id)

    assert artifact.job_id == job.job_id


def test_generation_request_preserved() -> None:
    request = _request()

    artifact = _artifact(request=request)

    assert artifact.request == request


def test_memory_scope_preserved() -> None:
    artifact = _artifact()

    assert artifact.memory_scope == MemoryScope.documents(["a.md"])


def test_model_role_preserved() -> None:
    request = GenerationRequest(
        task_type="quiz", memory_scope=MemoryScope.all(), model_role="vision"
    )

    artifact = _artifact(request=request)

    assert artifact.model_role == "vision"
    assert artifact.request.model_role == "vision"


def test_metadata_round_trip() -> None:
    artifact = _artifact()

    restored = Artifact.model_validate_json(artifact.model_dump_json())

    assert restored == artifact
    assert restored.metadata == {}


def test_payload_and_reference_round_trip() -> None:
    inline = _artifact(content="# cards", content_ref=None)
    assert Artifact.model_validate_json(inline.model_dump_json()) == inline

    referenced = _artifact(content=None, content_ref="artifacts/deck-v1.md")
    assert Artifact.model_validate_json(referenced.model_dump_json()) == referenced

    with pytest.raises(ValidationError):
        _artifact(content=None, content_ref=None)


def test_multiple_artifacts_and_list_ordering(tmp_path: Path) -> None:
    store = _artifact_store(tmp_path)
    first = store.create(_artifact(title="B"))
    second = store.create(_artifact(title="A"))

    listed = store.list_artifacts()

    assert {item.artifact_id for item in listed} == {first.artifact_id, second.artifact_id}
    assert [item.artifact_id for item in store.list_artifacts()] == [
        item.artifact_id for item in listed
    ]


def test_persistence_across_new_store_instance(tmp_path: Path) -> None:
    store = _artifact_store(tmp_path)
    artifact = store.create(_artifact())

    fresh = _artifact_store(tmp_path)

    assert fresh.get(artifact.artifact_id) == artifact


# ── Provenance ────────────────────────────────────────────────────────


def test_single_provenance_record(tmp_path: Path) -> None:
    provenance = _provenance_store(tmp_path)
    artifact = _artifact_store(tmp_path).create(_artifact())

    record = provenance.add(_record(artifact.artifact_id))

    assert provenance.for_artifact(artifact.artifact_id) == [record]


def test_multiple_provenance_records(tmp_path: Path) -> None:
    provenance = _provenance_store(tmp_path)
    artifact = _artifact_store(tmp_path).create(_artifact())
    first = provenance.add(_record(artifact.artifact_id, "a.md"))
    second = provenance.add(_record(artifact.artifact_id, "b.md"))

    assert provenance.for_artifact(artifact.artifact_id) == [first, second]


def test_source_reference() -> None:
    record = _record("art-1", "notes/a.md")

    assert record.source_id == "notes/a.md"
    assert record.chunk_id is None
    assert record.kg_node_id is None


def test_chunk_reference() -> None:
    record = ProvenanceRecord(
        artifact_id="art-1",
        source_id="a.md",
        role=ProvenanceRole.EVIDENCE_CHUNK,
        chunk_id="a.md::chunk_3",
        chunk_index=3,
    )

    assert record.chunk_id == "a.md::chunk_3"
    assert record.chunk_index == 3


def test_span_reference() -> None:
    record = ProvenanceRecord(
        artifact_id="art-1",
        source_id="a.md",
        role=ProvenanceRole.EVIDENCE_CHUNK,
        start_char=10,
        end_char=42,
    )

    assert (record.start_char, record.end_char) == (10, 42)
    with pytest.raises(ValidationError):
        ProvenanceRecord(
            artifact_id="art-1",
            source_id="a.md",
            role=ProvenanceRole.EVIDENCE_CHUNK,
            start_char=42,
            end_char=10,
        )


def test_kg_node_reference() -> None:
    record = ProvenanceRecord(
        artifact_id="art-1",
        source_id="a.md",
        role=ProvenanceRole.KNOWLEDGE_CONCEPT,
        kg_node_id="concept::rag",
    )

    assert record.kg_node_id == "concept::rag"


def test_optional_quote_handling() -> None:
    assert _record("art-1").quote is None
    quoted = ProvenanceRecord(
        artifact_id="art-1",
        source_id="a.md",
        role=ProvenanceRole.EVIDENCE_CHUNK,
        quote="  grounded span  ",
    )
    assert quoted.quote == "grounded span"
    blank = ProvenanceRecord(
        artifact_id="art-1",
        source_id="a.md",
        role=ProvenanceRole.EVIDENCE_CHUNK,
        quote="   ",
    )
    assert blank.quote is None


def test_provenance_role() -> None:
    assert _record("art-1").role is ProvenanceRole.EVIDENCE_CHUNK
    with pytest.raises(ValidationError):
        ProvenanceRecord(artifact_id="art-1", source_id="a.md", role="maybe")


def test_provenance_deterministic_ordering(tmp_path: Path) -> None:
    provenance = _provenance_store(tmp_path)
    artifact = _artifact_store(tmp_path).create(_artifact())
    for source_id in ("c.md", "a.md", "b.md"):
        provenance.add(_record(artifact.artifact_id, source_id))

    assert [r.source_id for r in provenance.for_artifact(artifact.artifact_id)] == [
        "c.md",
        "a.md",
        "b.md",
    ]


def test_provenance_persists_across_reload(tmp_path: Path) -> None:
    provenance = _provenance_store(tmp_path)
    artifact = _artifact_store(tmp_path).create(_artifact())
    provenance.add(_record(artifact.artifact_id, "a.md"))

    fresh = _provenance_store(tmp_path)

    assert fresh.for_artifact(artifact.artifact_id) == provenance.for_artifact(
        artifact.artifact_id
    )


def test_artifact_provenance_association(tmp_path: Path) -> None:
    artifacts = _artifact_store(tmp_path)
    provenance = _provenance_store(tmp_path)
    first = artifacts.create(_artifact(title="one"))
    second = artifacts.create(_artifact(title="two"))
    provenance.add(_record(first.artifact_id, "a.md"))

    assert [r.source_id for r in provenance.for_artifact(first.artifact_id)] == ["a.md"]
    assert provenance.for_artifact(second.artifact_id) == []


# ── Integration ───────────────────────────────────────────────────────


def test_artifact_linked_to_generation_job() -> None:
    job = GenerationJob.create(_request())

    artifact = _artifact(job_id=job.job_id)

    assert artifact.job_id == job.job_id


def test_artifact_preserves_generation_request() -> None:
    request = GenerationRequest(
        task_type="report",
        memory_scope=MemoryScope.topics(["t1"]),
        config={"depth": "brief"},
        model_role="general_text",
        provenance="strict",
        metadata={"client": "cli"},
    )

    artifact = _artifact(request=request)

    assert artifact.request == request


def test_artifact_preserves_memory_scope() -> None:
    scope = MemoryScope.topics(["t1", "t2"])
    request = GenerationRequest(task_type="ppt", memory_scope=scope)

    artifact = _artifact(request=request)

    assert artifact.memory_scope == scope


def test_artifact_preserves_model_role_and_config() -> None:
    request = GenerationRequest(
        task_type="quiz",
        memory_scope=MemoryScope.all(),
        config={"count": 5},
        model_role="vision",
    )

    artifact = _artifact(request=request)

    assert artifact.model_role == "vision"
    assert artifact.request.config == {"count": 5}


def test_versioned_artifact_preserves_parent_relationship(tmp_path: Path) -> None:
    store = _artifact_store(tmp_path)
    first = store.create(_artifact(title="v1"))
    second = store.create(first.new_version(job_id="job-2", request=_request()))

    versions = store.list_versions(first.logical_id)

    assert [row.version for row in versions] == [1, 2]
    assert versions[1] == second
    assert versions[1].parent_artifact_id == first.artifact_id
    assert versions[1].logical_id == first.logical_id


def test_new_version_does_not_mutate_original() -> None:
    first = _artifact(title="v1", content="# one")

    second = first.new_version(job_id="job-2", request=_request(), content="# two")

    assert first.title == "v1"
    assert first.content == "# one"
    assert first.version == 1
    assert second.content == "# two"


# ── Obsidian compatibility ────────────────────────────────────────────


def test_note_to_artifact_adapter() -> None:
    note = ObsidianNote(
        title="Note",
        filename="Note.md",
        markdown="# Note",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        tags=["t"],
        source="a.md",
        source_type="markdown",
    )
    job = GenerationJob.create(_request())

    artifact = note_to_artifact(note, job_id=job.job_id, request=_request())

    assert artifact.kind is ArtifactKind.NOTE
    assert artifact.title == "Note"
    assert artifact.content == "# Note"
    assert artifact.version == 1
    assert artifact.job_id == job.job_id
    assert artifact.metadata["filename"] == "Note.md"
