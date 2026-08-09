"""Integration tests for P4-102 entity extraction pipeline wiring.

Chains the real ``StructureAnalyzer`` (M2.3) into the entity extractor: the
structure's exact character offsets are reused, so extracted entities carry
``start_char``/``end_char`` into the *original* document text (not the block
slice), and code blocks are excluded from extraction.
"""

from __future__ import annotations

from app.infrastructure.document_intelligence.entities import EntityExtractor
from app.infrastructure.document_intelligence.structure.detector import StructureAnalyzer


def test_extractor_consumes_analyzer_output_and_offsets_point_at_original_text() -> None:
    text = (
        "# Team\n\n"
        "Dr. Jane Smith works at Acme Corporation.\n\n"
        "## Tooling\n\n"
        "We run Python 3.12 in production.\n\n"
        "```python\n"
        "acme = Acme Corporation\n"
        "```\n"
    )
    structure = StructureAnalyzer().analyze(text, "team.md")

    entities = EntityExtractor().extract(text, "team.md", "markdown", structure)

    by_label = {e.label: e for e in entities}
    assert set(by_label) == {"Jane Smith", "Acme Corporation", "Python 3.12"}
    assert by_label["Jane Smith"].entity_type == "person"
    assert by_label["Acme Corporation"].entity_type == "organization"
    assert by_label["Python 3.12"].entity_type == "technology"

    for entity in entities:
        assert len(entity.sources) == 1
        ref = entity.sources[0]
        assert ref.section_id is not None
        assert ref.snippet == entity.label
        assert text[ref.start_char : ref.end_char] == entity.label


def test_code_block_entities_are_not_extracted_through_pipeline() -> None:
    text = "# Code\n\n```\nAcme Corporation\n```\n"
    structure = StructureAnalyzer().analyze(text, "code.md")

    entities = EntityExtractor().extract(text, "code.md", "markdown", structure)

    assert all(e.label != "Acme Corporation" for e in entities)
