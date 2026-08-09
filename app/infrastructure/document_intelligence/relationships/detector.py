"""Deterministic relationship detection between extracted entities (P4-103).

Consumes P4-102 ``Entity`` objects (each carrying ``SourceReference``
provenance) and emits ``Relationship`` objects typed against the existing
``EdgeType`` vocabulary (``app/domain/knowledge_graph.py``). Detection is
evidence-based and deterministic by construction: identical input always
yields identical output (same relationships, same ids, same order, same
source references).

Only relationships supported by the source/document evidence are detected:

- ``related_to`` — co-occurrence. Two entities observed in the same section
  (structure mode, shared ``section_id``) or the same document (flat mode,
  same ``source``) are ``related_to`` each other. The shared section/document
  references are preserved verbatim as the relationship's evidence.

The remaining ``EdgeType`` members (``defined_in``, ``mentioned_in``,
``part_of``, ``depends_on``) are not emitted: ``mentioned_in`` is already
carried by ``Entity.sources``, and the others require evidence (definition
text, containment hierarchy, dependency analysis) that deterministic
regex extraction does not provide.

Duplicates collapse to a single relationship: each unordered entity pair
yields exactly one canonical edge (regardless of how many sections/references
share the evidence), with all evidence references merged. Direction is
canonical (lexicographically smaller id is ``source_id``), which also makes
circular ``A↔B`` pairs impossible. Output is sorted by relationship id.

Missing entities and malformed references never raise: an entity with no
document evidence contributes nothing, and a reference with an empty source
string is skipped. Empty input yields ``[]``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from app.domain.entity_relationship import Entity, Relationship, SourceReference

_RELATIONSHIP_TYPE = "related_to"


class RelationshipDetector:
    """Deterministic evidence-based relationship detection (P4-103).

    Stateless and reentrant-safe: a fresh instance is equivalent to any other.
    ``detect`` never raises for empty input or entities without document
    references, and only emits relationships between entity ids it was given.
    """

    def detect(self, entities: Sequence[Entity]) -> list[Relationship]:
        """Detect ``related_to`` relationships from entity co-occurrence.

        Entities are grouped by document reference (``source`` + ``section_id``
        when the structure subsystem provided one). Any two distinct entities
        sharing a reference are related; the shared reference is kept as the
        relationship's evidence. Each unordered pair emits exactly one
        canonical edge.
        """
        # (source, section_id) -> entity_id -> [evidence references]
        buckets: dict[tuple[str, str | None], dict[str, list[SourceReference]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for entity in entities:
            for ref in entity.sources:
                if not ref.source:  # malformed reference: no document evidence
                    continue
                buckets[(ref.source, ref.section_id)][entity.id].append(ref)

        relationships: dict[tuple[str, str], Relationship] = {}
        for refs_by_id in buckets.values():
            ids = sorted(refs_by_id)
            for i, source_id in enumerate(ids):
                for target_id in ids[i + 1 :]:
                    key = (source_id, target_id)
                    evidence = [
                        *refs_by_id[source_id],
                        *refs_by_id[target_id],
                    ]
                    relationship = relationships.get(key)
                    if relationship is None:
                        relationships[key] = Relationship(
                            id=Relationship.make_id(source_id, target_id, _RELATIONSHIP_TYPE),
                            source_id=source_id,
                            target_id=target_id,
                            relationship_type=_RELATIONSHIP_TYPE,
                            sources=evidence,
                        )
                    else:
                        relationship.sources.extend(evidence)

        return sorted(relationships.values(), key=lambda r: r.id)


def get_default_relationship_detector() -> RelationshipDetector:
    """Return a RelationshipDetector (P4-103 composition root)."""
    return RelationshipDetector()  # stateless; fresh instance is reentrant-safe
