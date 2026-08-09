"""Tests for the P4-101 entity and relationship data model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.analysis import ImportantEntity
from app.domain.entity_relationship import (
    Entity,
    EntityMetadata,
    Relationship,
    RelationshipMetadata,
    SourceReference,
)
from app.domain.semantic_chunking import DocumentChunk

# ── SourceReference ───────────────────────────────────────────────────────


class TestSourceReference:
    def test_round_trip(self) -> None:
        ref = SourceReference(
            source="paper.pdf",
            source_type="pdf",
            chunk_id="paper.pdf::chunk_0",
            start_char=10,
            end_char=50,
            snippet="Some text",
        )
        data = ref.model_dump()
        restored = SourceReference.model_validate(data)
        assert restored == ref

    def test_defaults(self) -> None:
        ref = SourceReference(source="paper.pdf")
        assert ref.source_type == ""
        assert ref.chunk_id is None
        assert ref.section_id is None
        assert ref.start_char is None
        assert ref.end_char is None
        assert ref.snippet == ""

    def test_empty_source_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SourceReference(source="")

    def test_negative_start_char_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SourceReference(source="a.md", start_char=-1, end_char=10)

    def test_partial_offsets_rejected(self) -> None:
        with pytest.raises(ValidationError, match="together"):
            SourceReference(source="a.md", start_char=1)

    def test_end_before_start_rejected(self) -> None:
        with pytest.raises(ValidationError, match="end_char"):
            SourceReference(source="a.md", start_char=50, end_char=10)

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            SourceReference(source="a.md", page=3)  # type: ignore[call-arg]

    def test_from_chunk_preserves_offsets(self) -> None:
        chunk = DocumentChunk(
            chunk_id="doc.md::chunk_0",
            text="hello world",
            source="doc.md",
            source_type="md",
            chunk_index=0,
            start_char=0,
            end_char=11,
        )
        ref = SourceReference.from_chunk(chunk)
        assert ref.source == "doc.md"
        assert ref.source_type == "md"
        assert ref.chunk_id == "doc.md::chunk_0"
        assert ref.start_char == 0
        assert ref.end_char == 11
        assert ref.snippet == "hello world"

    def test_equality_is_value_based(self) -> None:
        a = SourceReference(source="a.md", start_char=0, end_char=5)
        b = SourceReference(source="a.md", start_char=0, end_char=5)
        assert a == b
        assert a is not b


# ── EntityMetadata / RelationshipMetadata ─────────────────────────────────


class TestEntityMetadata:
    def test_round_trip(self) -> None:
        meta = EntityMetadata(importance="high", confidence=0.95, extra={"page": 3})
        data = meta.model_dump()
        restored = EntityMetadata.model_validate(data)
        assert restored == meta

    def test_defaults(self) -> None:
        meta = EntityMetadata()
        assert meta.importance is None
        assert meta.confidence is None
        assert meta.extra == {}

    def test_importance_is_typed_literal(self) -> None:
        with pytest.raises(ValidationError):
            EntityMetadata(importance="critical")  # type: ignore[call-arg]

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            EntityMetadata(confidence=1.5)
        with pytest.raises(ValidationError):
            EntityMetadata(confidence=-0.1)

    def test_extra_must_be_json_safe(self) -> None:
        with pytest.raises(ValidationError, match="JSON-serializable"):
            EntityMetadata(extra={"bad": object()})  # type: ignore[dict-item]

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            EntityMetadata(unknown=1)  # type: ignore[call-arg]


class TestRelationshipMetadata:
    def test_round_trip(self) -> None:
        meta = RelationshipMetadata(confidence=0.7, extra={"source_sentence": 3})
        data = meta.model_dump()
        restored = RelationshipMetadata.model_validate(data)
        assert restored == meta

    def test_defaults(self) -> None:
        meta = RelationshipMetadata()
        assert meta.confidence is None
        assert meta.extra == {}

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            RelationshipMetadata(confidence=1.01)

    def test_extra_must_be_json_safe(self) -> None:
        with pytest.raises(ValidationError, match="JSON-serializable"):
            RelationshipMetadata(extra={"bad": set()})  # type: ignore[dict-item]

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            RelationshipMetadata(unknown=1)  # type: ignore[call-arg]


# ── Entity ────────────────────────────────────────────────────────────────


class TestEntity:
    def test_round_trip(self) -> None:
        entity = Entity(
            id="technology::python",
            label="Python",
            entity_type="technology",
            description="A programming language.",
            aliases=["Py"],
            metadata=EntityMetadata(importance="high"),
            sources=[SourceReference(source="doc.md", start_char=0, end_char=10)],
        )
        data = entity.model_dump()
        restored = Entity.model_validate(data)
        assert restored == entity

    def test_defaults(self) -> None:
        entity = Entity(id="person::ada", label="Ada", entity_type="person")
        assert entity.description == ""
        assert entity.aliases == []
        assert entity.metadata == EntityMetadata()
        assert entity.sources == []

    def test_make_id_is_deterministic(self) -> None:
        assert Entity.make_id("Python", "technology") == "technology::python"
        assert Entity.make_id("Python", "technology") == Entity.make_id("python", "technology")

    def test_empty_label_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Entity(id="technology::x", label="  ")

    def test_invalid_entity_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Entity(id="x", label="X", entity_type="robot")  # type: ignore[call-arg]

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Entity(id="x", label="X", foo="bar")  # type: ignore[call-arg]

    def test_equality_is_value_based(self) -> None:
        a = Entity(id="person::ada", label="Ada", entity_type="person")
        b = Entity(id="person::ada", label="Ada", entity_type="person")
        assert a == b
        assert a is not b

    def test_different_entities_not_equal(self) -> None:
        a = Entity(id="person::ada", label="Ada")
        b = Entity(id="person::grace", label="Grace")
        assert a != b

    def test_from_important_entity(self) -> None:
        ie = ImportantEntity(name="Python", type="technology", description="A language.")
        entity = Entity.from_important_entity(ie, source="doc.md")
        assert entity.label == "Python"
        assert entity.entity_type == "technology"
        assert entity.description == "A language."
        assert entity.id == "technology::python"
        assert [s.source for s in entity.sources] == ["doc.md"]


# ── Relationship ──────────────────────────────────────────────────────────


class TestRelationship:
    def test_round_trip(self) -> None:
        rel = Relationship(
            id="technology::python::depends_on::technology::numpy",
            source_id="technology::python",
            target_id="technology::numpy",
            relationship_type="depends_on",
            weight=0.8,
            metadata=RelationshipMetadata(confidence=0.9),
            sources=[SourceReference(source="doc.md")],
        )
        data = rel.model_dump()
        restored = Relationship.model_validate(data)
        assert restored == rel

    def test_defaults(self) -> None:
        rel = Relationship(
            id="a::related_to::b",
            source_id="a",
            target_id="b",
        )
        assert rel.relationship_type == "related_to"
        assert rel.weight == 1.0
        assert rel.metadata == RelationshipMetadata()
        assert rel.sources == []

    def test_make_id_is_deterministic(self) -> None:
        expected = "technology::python::depends_on::technology::numpy"
        assert (
            Relationship.make_id("technology::python", "technology::numpy", "depends_on")
            == expected
        )

    def test_empty_source_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Relationship(id="x", source_id="", target_id="b")

    def test_empty_target_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Relationship(id="x", source_id="a", target_id=" ")

    def test_self_loop_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must differ"):
            Relationship(id="x", source_id="a", target_id="a")

    def test_invalid_relationship_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Relationship(id="x", source_id="a", target_id="b", relationship_type="loves")  # type: ignore[call-arg]

    def test_weight_bounds(self) -> None:
        with pytest.raises(ValidationError):
            Relationship(id="x", source_id="a", target_id="b", weight=1.5)

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Relationship(id="x", source_id="a", target_id="b", foo="bar")  # type: ignore[call-arg]

    def test_equality_is_value_based(self) -> None:
        a = Relationship(id="a::related_to::b", source_id="a", target_id="b")
        b = Relationship(id="a::related_to::b", source_id="a", target_id="b")
        assert a == b
        assert a is not b


# ── Deterministic serialization ───────────────────────────────────────────


class TestDeterministicSerialization:
    def test_to_json_is_deterministic_across_instances(self) -> None:
        a = Entity(
            id="technology::python",
            label="Python",
            metadata=EntityMetadata(extra={"rank": 1, "nested": {"b": 2, "a": 1}}),
        )
        b = Entity(
            id="technology::python",
            label="Python",
            metadata=EntityMetadata(extra={"rank": 1, "nested": {"b": 2, "a": 1}}),
        )
        assert a.to_json() == b.to_json()

    def test_to_json_sorts_nested_keys(self) -> None:
        meta = EntityMetadata(extra={"nested": {"b": 2, "a": 1}})
        payload = meta.to_json()
        assert '"a": 1' in payload
        assert '"b": 2' in payload
        assert payload.index('"a"') < payload.index('"b"')

    def test_from_json_round_trip(self) -> None:
        entity = Entity(
            id="person::ada",
            label="Ada",
            entity_type="person",
            sources=[SourceReference(source="doc.md", start_char=0, end_char=5)],
        )
        restored = Entity.from_json(entity.to_json())
        assert restored == entity

    def test_relationship_from_json_round_trip(self) -> None:
        rel = Relationship(id="a::part_of::b", source_id="a", target_id="b")
        restored = Relationship.from_json(rel.to_json())
        assert restored == rel

    def test_source_reference_from_json_round_trip(self) -> None:
        ref = SourceReference(source="doc.md", start_char=0, end_char=5)
        restored = SourceReference.from_json(ref.to_json())
        assert restored == ref

    def test_metadata_from_json_round_trip(self) -> None:
        meta = EntityMetadata(importance="low", confidence=0.4)
        restored = EntityMetadata.from_json(meta.to_json())
        assert restored == meta

    def test_from_dict_round_trip(self) -> None:
        entity = Entity(id="concept::graphs", label="Graphs")
        restored = Entity.from_dict(entity.to_dict())
        assert restored == entity

    def test_relationship_from_dict_round_trip(self) -> None:
        rel = Relationship(id="a::related_to::b", source_id="a", target_id="b")
        restored = Relationship.from_dict(rel.to_dict())
        assert restored == rel
