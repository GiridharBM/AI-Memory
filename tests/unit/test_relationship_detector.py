"""Unit tests for the deterministic relationship detector (P4-103).

Covers the mandated categories: single/multiple relationships, duplicate and
repeated references, circular references, missing targets, empty/malformed
input, offset/source evidence preservation, determinism, and the public API
surface.
"""

from __future__ import annotations

from app.domain.entity_relationship import Entity, Relationship, SourceReference
from app.infrastructure.document_intelligence.entities import EntityExtractor
from app.infrastructure.document_intelligence.relationships import (
    RelationshipDetector,
    get_default_relationship_detector,
)


def _entity(
    entity_id: str,
    section: str | None = None,
    source: str = "a.md",
    *,
    start: int = 0,
    length: int = 8,
) -> Entity:
    return Entity(
        id=entity_id,
        label=entity_id.rsplit("::", 1)[-1].replace("_", " "),
        entity_type="organization",
        sources=[
            SourceReference(
                source=source,
                source_type="markdown",
                section_id=section,
                start_char=start,
                end_char=start + length,
                snippet="Acme Corp",
            )
        ],
    )


# ── 1. single relationship ────────────────────────────────────────────────


def test_single_relationship_two_entities_in_same_section() -> None:
    entities = [
        _entity("organization::acme_corporation", "s-1"),
        _entity("person::jane_smith", "s-1", start=20),
    ]
    rels = RelationshipDetector().detect(entities)
    assert len(rels) == 1
    rel = rels[0]
    assert rel.relationship_type == "related_to"
    assert rel.source_id == "organization::acme_corporation"
    assert rel.target_id == "person::jane_smith"
    assert rel.id == rel.source_id + "::related_to::" + rel.target_id


# ── 2. multiple relationships ─────────────────────────────────────────────


def test_multiple_entities_in_same_section_form_complete_graph() -> None:
    entities = [
        _entity("organization::acme_corporation", "s-1"),
        _entity("person::jane_smith", "s-1"),
        _entity("technology::python_3.12", "s-1"),
    ]
    rels = RelationshipDetector().detect(entities)
    pairs = {(r.source_id, r.target_id) for r in rels}
    assert len(rels) == 3
    assert pairs == {
        ("organization::acme_corporation", "person::jane_smith"),
        ("organization::acme_corporation", "technology::python_3.12"),
        ("person::jane_smith", "technology::python_3.12"),
    }


def test_entities_in_different_sections_are_not_related() -> None:
    entities = [
        _entity("organization::acme_corporation", "s-1"),
        _entity("person::jane_smith", "s-2", start=20),
    ]
    assert RelationshipDetector().detect(entities) == []


# ── 3. duplicate / repeated references ────────────────────────────────────


def test_repeated_mentions_produce_single_relationship_with_merged_evidence() -> None:
    acme = Entity(
        id="organization::acme_corporation",
        label="Acme Corporation",
        entity_type="organization",
        sources=[
            SourceReference(
                source="a.md",
                section_id="s-1",
                start_char=0,
                end_char=16,
                snippet="Acme Corporation",
            ),
            SourceReference(
                source="a.md",
                section_id="s-1",
                start_char=40,
                end_char=56,
                snippet="Acme Corporation",
            ),
        ],
    )
    jane = _entity("person::jane_smith", "s-1", start=20)
    rels = RelationshipDetector().detect([acme, jane])
    assert len(rels) == 1
    # all shared-section references preserved as evidence, no duplicate edge
    assert len(rels[0].sources) == 3


def test_duplicate_entity_ids_do_not_create_self_loops() -> None:
    entities = [
        _entity("organization::acme_corporation", "s-1"),
        _entity("organization::acme_corporation", "s-1", start=20),
    ]
    assert RelationshipDetector().detect(entities) == []


def test_pair_shared_across_sections_collapses_to_one_edge() -> None:
    acme = Entity(
        id="organization::acme_corporation",
        label="Acme Corporation",
        entity_type="organization",
        sources=[
            SourceReference(
                source="a.md",
                section_id="s-1",
                start_char=0,
                end_char=16,
                snippet="Acme Corporation",
            ),
            SourceReference(
                source="a.md",
                section_id="s-2",
                start_char=40,
                end_char=56,
                snippet="Acme Corporation",
            ),
        ],
    )
    jane = Entity(
        id="person::jane_smith",
        label="Jane Smith",
        entity_type="person",
        sources=[
            SourceReference(
                source="a.md",
                section_id="s-1",
                start_char=20,
                end_char=30,
                snippet="Jane Smith",
            ),
            SourceReference(
                source="a.md",
                section_id="s-2",
                start_char=60,
                end_char=70,
                snippet="Jane Smith",
            ),
        ],
    )
    rels = RelationshipDetector().detect([acme, jane])
    assert len(rels) == 1
    assert len(rels[0].sources) == 4  # evidence from both sections


# ── 4. circular references ────────────────────────────────────────────────


def test_circular_pair_collapses_to_single_canonical_edge() -> None:
    entities = [
        _entity("organization::acme_corporation", "s-1"),
        _entity("person::jane_smith", "s-1", start=20),
    ]
    rels = RelationshipDetector().detect(entities)
    assert len(rels) == 1
    # canonical direction: lexicographically smaller id is source_id; no reverse edge
    assert rels[0].source_id < rels[0].target_id
    reverse = {r.source_id: r.target_id for r in rels}
    assert rels[0].target_id not in reverse


# ── 5. missing targets / entities ─────────────────────────────────────────


def test_entity_without_sources_produces_no_relationships() -> None:
    orphan = Entity(
        id="person::ghost",
        label="Ghost",
        entity_type="person",
        sources=[],
    )
    rels = RelationshipDetector().detect(
        [_entity("organization::acme_corporation", "s-1"), orphan]
    )
    assert rels == []


def test_all_relationship_endpoints_exist_in_input_entities() -> None:
    entities = [
        _entity("organization::acme_corporation", "s-1"),
        _entity("person::jane_smith", "s-1", start=20),
        _entity("technology::python_3.12", "s-2"),
    ]
    rels = RelationshipDetector().detect(entities)
    ids = {e.id for e in entities}
    for rel in rels:
        assert rel.source_id in ids
        assert rel.target_id in ids


# ── 6. empty / malformed input ────────────────────────────────────────────


def test_empty_entities_yield_no_relationships() -> None:
    assert RelationshipDetector().detect([]) == []


def test_malformed_empty_source_reference_is_skipped() -> None:
    malformed = Entity(
        id="organization::acme_corporation",
        label="Acme Corporation",
        entity_type="organization",
        sources=[SourceReference.model_construct(source="", section_id="s-1")],
    )
    jane = _entity("person::jane_smith", "s-1", start=20)
    assert RelationshipDetector().detect([malformed, jane]) == []


def test_flat_mode_detects_document_level_cooccurrence() -> None:
    # no section ids: entities sharing the source document are related
    entities = [
        _entity("organization::acme_corporation", section=None),
        _entity("person::jane_smith", section=None, start=20),
    ]
    rels = RelationshipDetector().detect(entities)
    assert len(rels) == 1
    assert rels[0].relationship_type == "related_to"


# ── 7. evidence preservation ──────────────────────────────────────────────


def test_relationship_preserves_source_and_offset_evidence() -> None:
    acme = Entity(
        id="organization::acme_corporation",
        label="Acme Corporation",
        entity_type="organization",
        sources=[
            SourceReference(
                source="a.md",
                source_type="markdown",
                section_id="s-1",
                start_char=0,
                end_char=16,
                snippet="Acme Corporation",
            )
        ],
    )
    jane = _entity("person::jane_smith", "s-1", start=20)
    rel = RelationshipDetector().detect([acme, jane])[0]
    evidence = {ref.section_id: ref for ref in rel.sources}
    assert set(evidence) == {"s-1"}
    assert evidence["s-1"].source == "a.md"
    assert evidence["s-1"].snippet == "Acme Corp"


# ── 8. determinism ────────────────────────────────────────────────────────


def test_deterministic_across_runs_and_instances() -> None:
    entities = [
        _entity("organization::acme_corporation", "s-1"),
        _entity("person::jane_smith", "s-1", start=20),
        _entity("technology::python_3.12", "s-1", start=40),
    ]
    first = RelationshipDetector().detect(entities)
    second = RelationshipDetector().detect(list(reversed(entities)))
    assert [r.to_json() for r in first] == [r.to_json() for r in second]
    assert [r.id for r in first] == sorted(r.id for r in first)


# ── public API ────────────────────────────────────────────────────────────


def test_module_helpers() -> None:
    assert isinstance(get_default_relationship_detector(), RelationshipDetector)
    entities = EntityExtractor().extract(
        "Dr. Jane Smith at Acme Corporation.", "a.md", "markdown"
    )
    rels = RelationshipDetector().detect(entities)
    assert [r.id for r in rels] == [
        "organization::acme_corporation::related_to::person::jane_smith"
    ]
    assert isinstance(rels[0], Relationship)
