"""Unit tests for the deterministic entity extractor (P4-102).

Covers the mandated categories: normal extraction, multiple entities,
duplicates, case variations, empty input, Unicode, long input, malformed
input, and offset/source mapping — plus determinism, structure reuse, and the
public API surface.
"""

from __future__ import annotations

import pytest

from app.domain.document_intelligence import (
    DocumentBlock,
    DocumentSection,
    DocumentStructure,
)
from app.domain.entity_relationship import Entity
from app.infrastructure.document_intelligence.entities import (
    EntityExtractor,
    get_default_entity_extractor,
)


def _extract(text: str, **kwargs: object) -> list[Entity]:
    return EntityExtractor().extract(text, "sample.md", "markdown", **kwargs)


# ── 1. normal extraction ─────────────────────────────────────────────────


def test_extracts_person_with_title() -> None:
    entities = _extract("Dr. Jane Smith wrote the paper.")
    labels = [(e.label, e.entity_type) for e in entities]
    assert ("Jane Smith", "person") in labels


def test_extracts_organization_with_suffix() -> None:
    entities = _extract("She works at Acme Corporation.")
    labels = [(e.label, e.entity_type) for e in entities]
    assert ("Acme Corporation", "organization") in labels


def test_extracts_technology_with_version() -> None:
    entities = _extract("Built with Python 3.12 and CUDA 11.8.")
    labels = [(e.label, e.entity_type) for e in entities]
    assert ("Python 3.12", "technology") in labels
    assert ("CUDA 11.8", "technology") in labels


def test_extracts_place_after_preposition() -> None:
    entities = _extract("The conference is in Berlin this year.")
    labels = [(e.label, e.entity_type) for e in entities]
    assert ("Berlin", "place") in labels


def test_extracts_paper_with_quoted_title() -> None:
    entities = _extract('Cited "Attention Is All You Need" (2017).')
    labels = [(e.label, e.entity_type) for e in entities]
    assert ("Attention Is All You Need", "paper") in labels


def test_extracts_concept_from_title_case_run() -> None:
    entities = _extract("The paper introduced Deep Neural Networks.")
    labels = [(e.label, e.entity_type) for e in entities]
    assert ("Deep Neural Networks", "concept") in labels


# ── 2. multiple entities ─────────────────────────────────────────────────


def test_multiple_distinct_entities_preserved() -> None:
    text = "Dr. Jane Smith at Acme Corporation presented Python 3.12 in Berlin."
    entities = _extract(text)
    ids = {e.id for e in entities}
    assert ids == {
        "person::jane_smith",
        "organization::acme_corporation",
        "technology::python_3.12",
        "place::berlin",
    }


def test_entities_sorted_in_document_order() -> None:
    text = "First: Acme Corporation. Second: Dr. Jane Smith."
    labels = [e.label for e in _extract(text)]
    assert labels == ["Acme Corporation", "Jane Smith"]


# ── 3. duplicates ────────────────────────────────────────────────────────


def test_duplicate_mention_merges_sources() -> None:
    text = "Acme Corporation won. Acme Corporation announced today."
    entities = _extract(text)
    assert len(entities) == 1
    entity = entities[0]
    assert entity.label == "Acme Corporation"
    assert len(entity.sources) == 2
    assert entity.sources[0].start_char == text.index("Acme Corporation")


# ── 4. case variations ───────────────────────────────────────────────────


def test_case_variation_merges_to_single_entity() -> None:
    text = "Python 3.12 is stable. PYTHON 3.12 powers the cluster."
    entities = _extract(text)
    tech = [e for e in entities if e.entity_type == "technology"]
    assert len(tech) == 1
    assert tech[0].id == "technology::python_3.12"
    assert len(tech[0].sources) == 2


# ── 5. empty input ───────────────────────────────────────────────────────


def test_empty_string_yields_no_entities() -> None:
    assert _extract("") == []


def test_whitespace_only_yields_no_entities() -> None:
    assert _extract("   \n\t  ") == []


# ── 6. Unicode ───────────────────────────────────────────────────────────


def test_unicode_text_does_not_raise() -> None:
    entities = _extract("Café Müller 3.2 launched in München. 日本語の文書です。")
    assert isinstance(entities, list)


def test_unicode_entity_extracted() -> None:
    entities = _extract("Bekannt ist Schmidt GmbH in Berlin.")
    labels = [(e.label, e.entity_type) for e in entities]
    assert ("Schmidt GmbH", "organization") in labels
    assert ("Berlin", "place") in labels


# ── 7. long input ────────────────────────────────────────────────────────


def test_long_input_does_not_raise_and_extracts() -> None:
    long_text = "The subject is Python 3.12. " + ("lorem ipsum dolor sit amet. " * 10_000)
    entities = _extract(long_text)
    tech = [e for e in entities if e.entity_type == "technology"]
    assert tech
    assert tech[0].label == "Python 3.12"


# ── 8. malformed input ───────────────────────────────────────────────────


@pytest.mark.parametrize("bad", [None, 123, b"bytes", ["list"], {"dict": 1}])
def test_non_string_text_returns_empty(bad: object) -> None:
    assert _extract(bad) == []  # type: ignore[arg-type]


def test_dangling_markdown_fences_do_not_raise() -> None:
    assert _extract("# Heading\n\n```python\nunclosed") == []


# ── 9. offset/source mapping ─────────────────────────────────────────────


def test_offsets_point_at_exact_source_slice() -> None:
    text = "We rely on Acme Corporation daily."
    entity = _extract(text)[0]
    ref = entity.sources[0]
    assert text[ref.start_char : ref.end_char] == "Acme Corporation"
    assert ref.snippet == "Acme Corporation"
    assert ref.source == "sample.md"
    assert ref.source_type == "markdown"


def test_offset_end_exclusive() -> None:
    text = "We rely on Acme Corporation here."
    entity = _extract(text)[0]
    ref = entity.sources[0]
    assert ref.end_char - ref.start_char == len("Acme Corporation")


# ── determinism ──────────────────────────────────────────────────────────


def test_deterministic_across_calls() -> None:
    text = "Dr. Jane Smith and Acme Corporation reviewed Python 3.12."
    first = _extract(text)
    second = _extract(text)
    assert [e.to_json() for e in first] == [e.to_json() for e in second]
    assert [e.id for e in first] == [e.id for e in second]


def test_same_input_identical_ids_across_instances() -> None:
    text = "Acme Corporation and Python 3.12."
    ids_a = [e.id for e in EntityExtractor().extract(text, "a.md", "markdown")]
    ids_b = [e.id for e in EntityExtractor().extract(text, "b.md", "markdown")]
    assert ids_a == ids_b


# ── structure reuse ──────────────────────────────────────────────────────


def _sample_structure() -> DocumentStructure:
    text = "Dr. Jane Smith works at Acme Corporation."
    return DocumentStructure(
        sections=[
            DocumentSection(
                id="s-1",
                title="Intro",
                level=1,
                parent_id=None,
                start_char=0,
                end_char=len(text),
                blocks=[
                    DocumentBlock(
                        block_id="b-s-1-1",
                        type="paragraph",
                        text=text,
                        start_char=0,
                        end_char=len(text),
                    )
                ],
            )
        ]
    )


def test_structure_reuse_attaches_section_and_offsets() -> None:
    text = "Dr. Jane Smith works at Acme Corporation."
    entities = _extract(text, structure=_sample_structure())
    labels = {(e.label, e.entity_type) for e in entities}
    assert ("Jane Smith", "person") in labels
    assert ("Acme Corporation", "organization") in labels
    for entity in entities:
        for ref in entity.sources:
            assert ref.section_id == "s-1"
            assert text[ref.start_char : ref.end_char] == ref.snippet


def test_code_blocks_are_excluded_from_extraction() -> None:
    structure = DocumentStructure(
        sections=[
            DocumentSection(
                id="s-1",
                title="Code",
                level=1,
                parent_id=None,
                start_char=0,
                end_char=len("Acme Corporation runs the org() in Python 3.12."),
                blocks=[
                    DocumentBlock(
                        block_id="b-s-1-1",
                        type="code",
                        text="Acme Corporation runs the org() in Python 3.12.",
                        start_char=0,
                        end_char=len("Acme Corporation runs the org() in Python 3.12."),
                    )
                ],
            )
        ]
    )
    assert _extract("ignored text", structure=structure) == []


def test_empty_structure_falls_back_to_flat_scan() -> None:
    structure = DocumentStructure(sections=[])
    entities = _extract("Dr. Jane Smith.", structure=structure)
    assert [(e.label, e.entity_type) for e in entities] == [("Jane Smith", "person")]


def test_structure_duplicate_mention_merges_sources() -> None:
    text = "Acme Corporation here. Acme Corporation again."
    structure = DocumentStructure(
        sections=[
            DocumentSection(
                id="s-1",
                title="Intro",
                level=1,
                parent_id=None,
                start_char=0,
                end_char=len(text),
                blocks=[
                    DocumentBlock(
                        block_id="b-s-1-1",
                        type="paragraph",
                        text=text,
                        start_char=0,
                        end_char=len(text),
                    )
                ],
            )
        ]
    )
    entities = _extract(text, structure=structure)
    assert len(entities) == 1
    assert entities[0].label == "Acme Corporation"
    assert len(entities[0].sources) == 2
    assert [r.section_id for r in entities[0].sources] == ["s-1", "s-1"]


# ── public API ───────────────────────────────────────────────────────────


def test_module_helpers() -> None:
    assert isinstance(get_default_entity_extractor(), EntityExtractor)
    entities = EntityExtractor().extract("Acme Corporation", "src.md", "text")
    assert [e.id for e in entities] == ["organization::acme_corporation"]
