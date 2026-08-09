"""Deterministic entity extraction over document text (P4-102).

Extracts named entities from source text using a small set of pre-compiled
regular-expression rules. Deterministic by construction: identical input
always yields identical output (same entities, same ids, same order, same
offsets). No ML/NLP dependencies, no external services, no I/O.

Rules reuse the existing ``EntityType`` vocabulary from ``app.domain.analysis``
and produce P4-101 ``Entity`` objects whose ``sources`` carry exact character
offsets (``SourceReference``). Extraction is case-sensitive at match time so
text casing is preserved in ``label``/``snippet``; dedup then normalizes via
``Entity.make_id`` (lowercase, spaces→underscores) so case variations and
repeated mentions collapse to a single entity with multiple sources.

Empty, whitespace-only, or non-string input never raises and returns ``[]``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.analysis import EntityType
from app.domain.document_intelligence import DocumentStructure
from app.domain.entity_relationship import Entity, SourceReference

# Rule set: (entity_type, regex, label_group). Each rule declares which capture
# group holds the canonical entity label (0 = whole match); offsets always
# point at exactly that group's span, so ``text[start:end] == label`` holds.
# Precedence is order of appearance (first rule wins overlaps).
_RULES: tuple[tuple[EntityType, re.Pattern[str], int], ...] = (
    (
        "technology",
        re.compile(r"\b[A-Z][A-Za-z0-9+.-]*\s+\d+(?:\.\d+)+\b"),
        0,
    ),
    (
        "person",
        re.compile(
            r"\b(?:Mr|Mrs|Ms|Dr|Prof|Professor|Sir|Lady|Miss)\.?\s+"
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
        ),
        1,
    ),
    (
        "organization",
        re.compile(
            r"\b[A-Z][a-zA-Z0-9&]+(?:\s+[A-Z][a-zA-Z0-9&]+)*\s+"
            r"(?:Inc|Corp|Corporation|Ltd|LLC|GmbH|University|Institute|Foundation|"
            r"Laboratories|Labs|Technologies|Systems|Group|Agency|Council|Association|"
            r"Society|Company)\b"
        ),
        0,
    ),
    (
        "place",
        re.compile(
            r"\b(?:in|at|from|to|near|throughout|across)\s+"
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
        ),
        1,
    ),
    (
        "paper",
        re.compile(r'"([A-Z][^"\n]{2,120})"\s*(?:\(\d{4}\))?'),
        1,
    ),
    (
        "concept",
        re.compile(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b"),
        0,
    ),
)


_TEXT_BEARING_BLOCK_TYPES: frozenset[str] = frozenset(
    {"paragraph", "list", "blockquote", "table"}
)


@dataclass(frozen=True)
class _Match:
    entity_type: EntityType
    label: str
    start: int
    end: int


def _scan(text: str) -> list[_Match]:
    """Find rule matches with overlap resolution (first rule wins).

    Offsets are the label group's span, so ``text[start:end] == label`` always
    holds. Higher-precedence rules claim their span first; a lower-precedence
    match overlapping a claimed span is dropped.
    """
    matches: list[_Match] = []
    covered: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < other_end and other_start < end for other_start, other_end in covered)

    for entity_type, pattern, label_group in _RULES:
        for match in pattern.finditer(text):
            start, end = match.span(label_group)
            if overlaps(start, end):
                continue
            covered.append((start, end))
            label = match.group(label_group)
            matches.append(_Match(entity_type=entity_type, label=label, start=start, end=end))
    matches.sort(key=lambda m: (m.start, m.end))
    return matches


def _is_text_bearing(block_type: str) -> bool:
    return block_type in _TEXT_BEARING_BLOCK_TYPES


def _extract_from_text(text: str, source: str, source_type: str) -> list[Entity]:
    """Extract entities from a flat text scan."""
    by_id: dict[str, Entity] = {}
    for match in _scan(text):
        entity_id = Entity.make_id(match.label, match.entity_type)
        reference = SourceReference(
            source=source,
            source_type=source_type,
            start_char=match.start,
            end_char=match.end,
            snippet=text[match.start : match.end],
        )
        entity = by_id.get(entity_id)
        if entity is None:
            by_id[entity_id] = Entity(
                id=entity_id,
                label=match.label,
                entity_type=match.entity_type,
                sources=[reference],
            )
        else:
            entity.sources.append(reference)
    return list(by_id.values())


def _extract_from_structure(
    structure: DocumentStructure, source: str, source_type: str
) -> list[Entity]:
    """Extract entities from the text-bearing blocks of a DocumentStructure.

    Reuses the structure analyzer's offsets: each block already carries exact
    ``start_char``/``end_char`` into the analyzed text, so per-block scans are
    stitched onto the same global coordinate space the structure subsystem uses
    (frozen §5.2). Code blocks are excluded; entities inside them are not
    extracted.
    """
    by_id: dict[str, Entity] = {}
    for section in structure.sections:
        for block in section.blocks:
            if not _is_text_bearing(block.type):
                continue
            for match in _scan(block.text):
                entity_id = Entity.make_id(match.label, match.entity_type)
                start = block.start_char + match.start
                end = block.start_char + match.end
                reference = SourceReference(
                    source=source,
                    source_type=source_type,
                    section_id=section.id,
                    start_char=start,
                    end_char=end,
                    snippet=block.text[match.start : match.end],
                )
                entity = by_id.get(entity_id)
                if entity is None:
                    by_id[entity_id] = Entity(
                        id=entity_id,
                        label=match.label,
                        entity_type=match.entity_type,
                        sources=[reference],
                    )
                else:
                    entity.sources.append(reference)
    return list(by_id.values())


class EntityExtractor:
    """Deterministic rule-based entity extractor (P4-102).

    Stateless and reentrant-safe: a fresh instance is equivalent to any other.
    ``extract`` never raises for empty/whitespace-only/non-string text.
    """

    def extract(
        self,
        text: str,
        source: str,
        source_type: str = "",
        structure: DocumentStructure | None = None,
    ) -> list[Entity]:
        if not isinstance(text, str):
            return []
        if not text.strip():
            return []
        if structure is not None and structure.sections:
            return _extract_from_structure(structure, source, source_type)
        return _extract_from_text(text, source, source_type)


def get_default_entity_extractor() -> EntityExtractor:
    """Return an EntityExtractor (P4-102 composition root)."""
    return EntityExtractor()  # stateless; fresh instance is reentrant-safe (O-2)
