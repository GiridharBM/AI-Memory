# P4-103 Engineering Review — Relationship Detection

**Task:** P4-103 — Relationship Detection
**Phase:** Phase 4 (relationship detection capability; no graph storage/retrieval)
**Date:** 2026-08-08
**Verdict:** **APPROVED**

---

## 1. Deliverable

New relationship-detection capability in `app/infrastructure/document_intelligence/relationships/`, wired into the ingestion enrichment stage:

| Artifact | Purpose |
|----------|---------|
| `detector.py` | Deterministic `RelationshipDetector` with `detect(entities)` (co-occurrence → `related_to` edges), `get_default_relationship_detector()` (composition root), and `analyze_document_relationships()` (public API) |
| `__init__.py` | Package exports (`RelationshipDetector`, `analyze_document_relationships`, `get_default_relationship_detector`) |
| `config/default.yaml` + `app/core/config.py` | `intelligence.relationships.enabled` toggle mirroring the `entities` block (rollback R-4) |
| `app/pipelines/ingest_workflow.py` | Enrichment stage now attaches `metadata.extra["relationships"]` alongside `extra["entities"]` |

The detector reuses the P4-101 `Relationship`/`SourceReference` models (`app.domain.entity_relationship`) and consumes P4-102 `Entity` objects — no new domain vocabulary, no re-parsing of source text.

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| 1. Identify the minimal deterministic relationship set with evidence | DONE | Only `related_to` is emitted (co-occurrence). `defined_in`/`part_of`/`depends_on` lack deterministic source evidence and are not fabricated; `mentioned_in` is already carried by `Entity.sources` (§7 rollback path of P4-101). Emitted edges are restricted to the existing `EdgeType` vocabulary (`app.domain.knowledge_graph`, line 17) so future graph ingestion can consume them without translation. |
| 2. Detect relationships deterministically | DONE | Pure function of the input entities: bucket by `(source, section_id)`; every entity pair sharing a bucket is related. Proven byte-stable across calls, instances, and reversed input order (`test_deterministic_across_runs_and_instances`). |
| 3. Preserve relationship type / source / offset / metadata | DONE | Each edge is a `Relationship` with `relationship_type`, `source_id`/`target_id` (entity ids), and merged `sources: list[SourceReference]` preserving `source`, `source_type`, `section_id`, `start_char`/`end_char`, and `snippet` — the invariant `text[start:end] == snippet` holds for every evidence reference (asserted in the integration tests). |
| 4. Handle duplicate and repeated references consistently | DONE | Multiple mentions collapse into one edge; evidence `SourceReference`s are merged across all shared-section occurrences, across sections, and across both endpoints (`test_repeated_mentions_..._merged_evidence`, `test_pair_shared_across_sections_collapses_to_one_edge`). |
| 5. Handle circular references | DONE | A→B and B→A collapse into a single canonical edge: the lexicographically smaller id is `source_id`; the reverse pair is deduplicated by the unordered key `(min, max)` (`test_circular_pair_collapses_to_single_canonical_edge`). |
| 6. Handle missing / malformed input safely | DONE | Empty input → `[]`; entities without references produce no edges; a reference with an empty `source` is skipped rather than crashing (`test_entity_without_sources_...`, `test_malformed_empty_source_reference_is_skipped`). All relationship endpoints are guaranteed to exist in the input (`test_all_relationship_endpoints_exist_in_input_entities`). |
| 7. Detection never crashes the ingestion pipeline | DONE | `detect()` is pure and contained (no I/O, no external calls). At the workflow boundary `_enrich_relationships` wraps detection in the established M2.2 lesson-L4 containment: a raised detector yields no `relationships` key and ingestion continues (`test_detector_failure_contained_and_ingestion_continues`). |
| 8. Feature isolated from unrelated Phase 1–3 functionality | DONE | Additive-only: new package + additive constructor/DI params and an enrichment key. `relationships.enabled: false` (and non-text kinds) omit the key entirely. Full regression suite unchanged for Phase 1–3 behavior. |
| 9. No external ML/NLP dependencies | DONE | Stdlib and existing domain models only; no new dependencies added. |

## 3. Design Notes

- **Co-occurrence as evidence.** The detector buckets entities by `(ref.source, ref.section_id)`. Two entities sharing a bucket co-occur in the same section of the same document and are related. When no section id is present (flat scan), the document source is the bucket, giving document-level co-occurrence.
- **Canonical edges.** Keys are unordered pairs `(min_id, max_id)` so the same pair never yields two directional duplicates, and circular pairs collapse to one edge with a stable direction. Output is sorted by `relationship.id`, making the result order a pure function of the input.
- **Evidence merging.** The `Relationship.sources` list is the union of both endpoints' references that fall into a shared bucket, preserving exact offsets into the original document (§5.2 frozen offsets reused from P4-102).
- **Single-pass consistency.** The workflow's enrichment stage extracts entities once (`_enrich_entities` now returns `Entity` objects), serializes them to `extra["entities"]`, and feeds the same objects to `_enrich_relationships` for `extra["relationships"]` — extraction and detection can never disagree.
- **Endpoints are existing entities only.** The detector emits edges only between entity ids it was given; it never invents nodes or references (§7 rollback path: graph builders stay safe when downstream phases run on `related_to` edges).

## 4. Testing

**24 focused tests** across `tests/unit/test_relationship_detector.py` (15) and `tests/integration/test_relationship_pipeline.py` (9), covering every mandated category:

- Single relationship (type, canonical id, direction); multiple entities in one section → complete graph; entities in different sections → no edge.
- Duplicate ids → no self-loops; repeated mentions → single edge with merged evidence; pair shared across sections → one edge with all evidence.
- Circular pair → single canonical edge, no reverse.
- Entity without sources → no edges; every emitted endpoint exists in the input.
- Empty input → `[]`; malformed (empty `source`) reference skipped without raising.
- Flat mode (no section ids) → document-level co-occurrence.
- Evidence preservation: `section_id`, `source`, `snippet`, and the `text[start:end] == snippet` invariant.
- Determinism: byte-stable `to_json` across runs, instances, and reversed input; sorted ids.
- Public API: `get_default_relationship_detector`, `analyze_document_relationships`.
- **Pipeline wiring (integration):** real `StructureAnalyzer` → `EntityExtractor` → `RelationshipDetector` (chained) — edges match the actual section structure and evidence offsets point into the original text; code-block content excluded.
- **Workflow wiring (integration):** `IngestionWorkflow.create_default` attaches `extra["relationships"]` for markdown; `enabled: false` and non-text kinds omit the key; a raising detector is contained and ingestion completes; the detector is wired by `create_default` even when disabled.

## 5. Verification (commands re-run this session)

| Gate | Result |
|------|--------|
| Focused tests | **24 passed** (15 unit + 3 chained + 6 workflow integration) |
| Full regression suite | **1222 passed / 0 failed / 45 deselected** (baseline 1204 + 18 new non-integration; 0 regressions) |
| Integration suite | **44 passed / 1 skipped** (Tesseract binary absent — pre-existing env skip) / 1222 deselected |
| Ruff | **All checks passed** (changed files: relationships package, config, workflow, both test files) |
| Mypy | **detector.py: 0 issues.** Remaining `ingest_workflow.py` errors are the pre-existing `object`-typed DI pattern (identical to sibling lines 660/698/706); full-repo mypy is blocked by an environment issue (numpy stub syntax under the Python 3.14 interpreter). |
| Coverage (`relationships` package) | **100%** (34 stmts, 0 miss; repo floor 80%) |
| Rollback | Additive-only: remove the `relationships/` package, the config toggle, the enrichment call, and its tests; `enabled: false` alone suffices for behavior rollback (R-4). Worktree uncommitted (per-task atomic commits pending), consistent with the M2.1–M4 convention. |

## 6. Files Changed

| File | Action |
|------|--------|
| `app/infrastructure/document_intelligence/relationships/detector.py` | **Created** — `RelationshipDetector`, `get_default_relationship_detector`, `analyze_document_relationships` |
| `app/infrastructure/document_intelligence/relationships/__init__.py` | **Created** — package exports |
| `app/infrastructure/document_intelligence/__init__.py` | **Modified** — export `analyze_document_relationships`, `get_default_relationship_detector` |
| `app/core/config.py` | **Modified** — `RelationshipSettings` model; `IntelligenceSettings.relationships` field |
| `config/default.yaml` | **Modified** — `intelligence.relationships.enabled: true` |
| `app/pipelines/ingest_workflow.py` | **Modified** — constructor/`from_runtime`/`create_default` DI param, `_relationships()` accessor, `_enrich_relationships()`, enrichment-stage `extra["relationships"]`; `_enrich_entities` refactored to return `Entity` objects |
| `tests/unit/test_relationship_detector.py` | **Created** — 15 focused tests |
| `tests/integration/test_relationship_pipeline.py` | **Created** — 3 chained + 6 workflow-integration tests |

## 7. Findings

**Blocking:** None.

**Non-blocking:**
- `related_to` is intentionally the only emitted type (requirement 1): the other `EdgeType` members lack deterministic evidence, and `mentioned_in` is already represented by `Entity.sources`. Co-occurrence-based detection is a deliberate heuristic — documented in the module docstring — and is deterministic, evidence-preserving, and dependency-free; a statistical relation extractor is out of scope (requirement 9).
- Per-task atomic commits pending (worktree uncommitted; consistent with M2.1–M3.2 convention).
- Phase 4 milestones ship additive-only; no MEDD version bump until Phase 4 is released as a whole.

## 8. Conclusion

P4-103 delivers deterministic, dependency-free relationship detection that reuses the P4-101 `Relationship` model and the P4-102 extracted entities: co-occurrence within a section yields canonical `related_to` edges with merged source/offset evidence, circular and duplicate pairs collapse consistently, malformed/empty input is safe, and the workflow wires detection as a single-pass enrichment stage gated by `relationships.enabled`. All gates pass (1222 passed, 0 regressions; ruff clean; detector mypy-clean; 100% package coverage; 44 integration tests pass).

**Verdict:** **APPROVED**
