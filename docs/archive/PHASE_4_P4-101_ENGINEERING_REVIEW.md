# P4-101 Engineering Review — Entity and Relationship Data Model

**Task:** P4-101 — Entity and Relationship Data Model
**Phase:** Phase 4 (foundational data model; no graph storage/retrieval)
**Date:** 2026-08-08
**Verdict:** **APPROVED**

---

## 1. Deliverable

New domain models in `app/domain/entity_relationship.py`, exported from `app/domain/__init__.py`:

| Model | Purpose | Reuses |
|-------|---------|--------|
| `SourceReference` | Provenance into a source document (source path, type, chunk/section id, character offsets, snippet) | `DocumentChunk` provenance fields |
| `EntityMetadata` | Typed entity metadata (`importance`, `confidence`, JSON-safe `extra`) | `ImportanceLevel` |
| `RelationshipMetadata` | Typed relationship metadata (`confidence`, JSON-safe `extra`) | — |
| `Entity` | Named entity with stable `id`, label, type, description, aliases, metadata, source references | `EntityType` |
| `Relationship` | Typed directed relationship between two `Entity.id`s | `EdgeType` |

All models share a `_EntityRelationshipModel` base providing deterministic serialization (`to_json` sorts keys), `from_json`/`from_dict`, and `extra="forbid"` strictness matching the domain conventions (`analysis.py`, `documents.py`, `document_intelligence.py`).

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| 1. Identify existing document/domain models | DONE | Reused `EntityType`/`ImportanceLevel` (`analysis.py`), `EdgeType` (`knowledge_graph.py`), `DocumentChunk` provenance fields (`semantic_chunking.py`), `ImportantEntity` (`analysis.py`). No new type vocabulary invented. |
| 2. Smallest representation for Entity/Relationship/Source ref/Entity metadata/Relationship metadata | DONE | Five focused models above; base class carries shared serialization; metadata `extra: dict[str, Any]` (JSON-safe) addresses TD-14's `dict[str, str]` limitation without a schema change. |
| 3. Stable identifiers + deterministic serialization | DONE | `Entity.make_id` / `Relationship.make_id` are deterministic (same normalization as `_make_id` in `app/infrastructure/knowledge_graph.py`); `to_json()` emits byte-stable sorted-key JSON (tests prove cross-instance determinism and nested key sorting). |
| 4. Preserve source offsets/references | DONE | `SourceReference` carries `start_char`/`end_char` (ge=0, end>=start, both-or-neither); `SourceReference.from_chunk` preserves a `DocumentChunk`'s offsets verbatim. |
| 5. Validation for malformed/incomplete relationship data | DONE | Blank endpoints rejected; self-loops rejected (`source_id == target_id`); invalid `EdgeType` rejected; weight bounds `[0, 1]`; `extra` must be JSON-serializable. |
| 6. Extensible for later graph construction | DONE | `Relationship.relationship_type` reuses `EdgeType` so it maps 1:1 onto `KnowledgeEdge`; `Entity.sources`/`Relationship.sources` carry provenance for future nodes/edges; metadata `extra` is open. |
| 7. No graph storage/retrieval | DONE | No storage, persistence, or query API added. `KnowledgeNode`/`KnowledgeEdge`/`KnowledgeGraph` untouched. |

## 3. Backward Compatibility

- `KnowledgeGraph`, `KnowledgeNode`, `KnowledgeEdge`, `KnowledgeGraphBuilder`, and all Phase 1–3 modules are **unchanged** (only additive edits to `app/domain/__init__.py`).
- Existing domain models (`DocumentChunk`, `ImportantEntity`, `DocumentAnalysis`) are consumed via `SourceReference.from_chunk` and `Entity.from_important_entity` with no modification to those models.
- No config schema, no pipeline wiring, no public API removed or altered.

## 4. Testing

**47 tests in `tests/unit/test_entity_relationship.py`:**

- Valid round-trips (model_dump → model_validate, to_json/from_json, to_dict/from_dict) for every model.
- Invalid data: empty source; blank label; blank/self-loop/typed-invalid relationship endpoints; invalid `EntityType`/`EdgeType`; weight/confidence out of bounds; partial or inverted char offsets; non-JSON-safe `extra`; `extra="forbid"` enforcement.
- Deterministic serialization: identical `to_json()` across equal instances; nested key sorting.
- Equality/identity: `==` is value-based, distinct objects are not identical.
- Backward compatibility: `SourceReference.from_chunk(DocumentChunk)` preserves offsets; `Entity.from_important_entity(ImportantEntity)` maps fields and derives the deterministic id.

## 5. Verification (commands re-run this session)

| Gate | Result |
|------|--------|
| New module tests | **47 passed** |
| Full default regression suite | **1172 passed / 0 failed / 39 deselected** (baseline 1125 + 47 new; 0 regressions) |
| Ruff | **All checks passed** (0 findings on changed files) |
| Mypy (`--ignore-missing-imports`) | **Success: no issues found** |
| Coverage (`app/domain/entity_relationship.py`) | **100%** (105 stmts, 0 miss; repo floor 80%) |

## 6. Files Changed

| File | Action |
|------|--------|
| `app/domain/entity_relationship.py` | **Created** — the five P4-101 models |
| `app/domain/__init__.py` | **Updated** — export `Entity`, `EntityMetadata`, `Relationship`, `RelationshipMetadata`, `SourceReference` |
| `tests/unit/test_entity_relationship.py` | **Created** — 47 focused tests |

## 7. Findings

**Blocking:** None.

**Non-blocking:**
- Per-task atomic commits pending (worktree uncommitted; consistent with M2.1–M3.2 convention).
- Milestone work is additive-only; no MEDD version bump is required until Phase 4 milestones are released as a whole.

## 8. Conclusion

P4-101 delivers the foundational entity/relationship data model as a strictly additive domain layer: five validated, deterministically serializable models that reuse the existing type vocabulary and provenance conventions, with no graph storage/retrieval and no change to any Phase 1–3 behavior. All gates pass (1172 passed, 0 regressions; ruff/mypy clean; 100% module coverage).

**Verdict:** **APPROVED**
