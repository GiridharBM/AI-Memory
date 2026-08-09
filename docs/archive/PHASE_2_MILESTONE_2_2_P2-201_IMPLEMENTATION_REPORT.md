# Milestone 2.2 — P2-201 Implementation Report

**Task:** P2-201 — Metadata extractor interface + registry
**Status:** DONE — implemented, tested, not wired into ingestion (per DoD)
**Date:** 2026-08-01
**Contract:** `docs/PHASE_2_MILESTONE_2_2_SPECIFICATION_FREEZE.md` + `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` §4 (P2-201)
**Scope rule honored:** ONLY P2-201 implemented; no future task work (P2-202 extractors remain empty; P2-203/204/206/207/208 not started).

---

## 1. What Was Implemented

Per the frozen task block (Objective / Interfaces / Implementation Steps):

| Deliverable | Location | Notes |
|-------------|----------|-------|
| `MetadataExtraction` model | `app/domain/document_intelligence.py` (new) | `source_type: str`, `values: dict[str, Any]`, `extractor: str`; `extra="forbid"` per frozen §7.2 layout (review F-4: placement confirmed in `domain/` per frozen §7.2) |
| `MetadataExtractor` Protocol | `app/infrastructure/document_intelligence/metadata/__init__.py` | `source_types: tuple[str, ...]` + `extract(document) -> dict[str, Any]`; `@runtime_checkable` — mirrors `OcrEngine` protocol (M2.1 `ocr/base.py:19`) |
| `DocumentMetadataService` registry | `app/infrastructure/document_intelligence/metadata/__init__.py` | `register` (idempotent), `extractors_for(source_type)`, `extract(document)` (merged extraction), static `merge(metadata, extraction)` |
| Empty-registry path | `DocumentMetadataService.extract` | No matching extractor → empty `MetadataExtraction`, `logger.debug`, **never raises** |
| `register_extractor()` public alias | `app/infrastructure/document_intelligence/metadata/__init__.py` | Registers onto the lazy default service |
| `extractors.py` placeholder | `app/infrastructure/document_intelligence/metadata/extractors.py` (new) | Empty until P2-202 (per spec: "new, empty until P2-202") |

### Merge rule (exactly as frozen)
- Known `DocumentMetadata` fields (`title, author, created_at, modified_at, page_count, mime_type, encoding`) written directly; **all other keys routed into `extra`**.
- Original `metadata.extra` keys preserved (additive, superset contract).
- Implemented via `model_copy(update=...)` — pure function, original unchanged.

### Package layout (matches frozen §7.2)
```
app/domain/document_intelligence.py                      # MetadataExtraction (shared domain model)
app/infrastructure/document_intelligence/metadata/
├── __init__.py   # registry + DocumentMetadataService + register_extractor()
└── extractors.py # empty placeholder (P2-202 fills this)
```

## 2. Design Decisions

- **`@runtime_checkable` protocol** — allows `isinstance` tests and mirrors the M2.1 `OcrEngine` protocol exactly (review C-1: register exactly like the existing processor router).
- **`extract(document)` returns a single merged `MetadataExtraction`** — runs all matching extractors in registration order, later values override earlier for shared keys; extractor names comma-joined into `extractor` field. This is the one deterministic metadata path the milestone's design principle requires.
- **Idempotent `register`** — duplicate registration of the same instance is a no-op (avoids double-extraction if P2-207 wires a registry that was already populated); distinct instances with the same `source_types` are both kept (registration order).
- **No-extractor path never raises** — returns empty extraction + debug log (frozen step 5, "no-extractor-for-type path returns an empty extraction + debug log, never raises").
- **Placement per review F-4** — `MetadataExtraction` lives in `app/domain/document_intelligence.py` per frozen §7.2 (not in `infrastructure/` like M2.1's OCR models); noted in the freeze contract Risk 6.

## 3. Test Results

**New tests:** `tests/unit/test_metadata_extraction.py` — **14 passed**.

Coverage (target module scope):
```
app/domain/document_intelligence.py                   8 stmts  100%
app/infrastructure/document_intelligence/metadata/    51 stmts 100%
```

**Full suite:** `python -m pytest tests` → **520 passed, 2 deselected** (baseline 506 passed / 2 deselected; +14 net new, 0 regressions).

| Gate | Result |
|------|--------|
| Unit tests (P2-201) | 14/14 passed |
| Full suite | 520 passed / 2 deselected (no regressions) |
| Coverage (new modules) | 100% (repo floor 80%) |
| Ruff | 64 errors — identical to baseline (64 pre-existing); **0 new** |
| Mypy | No errors in new files (only pre-existing `yaml` stub gap in `config.py`) |

Test coverage of the frozen testing strategy:
- Register/select per `source_types` ✅ (`test_register_and_select_by_source_type`)
- Merge writes known fields only, unknown → `extra` ✅ (`test_merge_writes_known_fields_and_routes_unknown_to_extra`, `test_merge_only_routes_unknown_keys_to_extra`)
- No-extractor type → empty merge, never raises ✅ (`test_extract_with_no_matching_extractor_returns_empty`, `test_extract_never_raises_for_unknown_source_type`)
- Duplicate-registration behavior defined ✅ (`test_duplicate_registration_is_idempotent`)
- Public alias `register_extractor()` ✅ (`test_register_extractor_public_alias`)
- Registration order preserved ✅ (`test_extractors_for_returns_registration_order`)

## 4. Acceptance Criteria / DoD Verification

| Criterion (frozen) | Status |
|--------------------|--------|
| `MetadataExtractor` protocol + registry + merge work | ✅ unit-tested |
| No ingestion behavior change yet (not wired) | ✅ no changes to `ingestion/`, `routing/`, `pipelines/`, `config/` |
| Interface reviewed (DoD) | ✅ awaiting engineering review |
| Unit-tested (DoD) | ✅ 14 tests |

## 5. Files Changed

| File | Action |
|------|--------|
| `app/domain/document_intelligence.py` | **new** — `MetadataExtraction` model |
| `app/infrastructure/document_intelligence/metadata/__init__.py` | **new** — protocol, registry, service, `register_extractor()` |
| `app/infrastructure/document_intelligence/metadata/extractors.py` | **new** — empty placeholder (P2-202) |
| `tests/unit/test_metadata_extraction.py` | **new** — 14 unit tests |

No configuration changes (P2-207 owns `intelligence.metadata` consumption, per frozen task).

## 6. Rollback Plan

Pure addition, not wired into any ingestion path — removal is a safe revert (frozen P2-201 rollback row). No config, no schema, no behavior change outside the new package.

## 7. Next Steps (NOT part of this task)

Awaiting engineering review of P2-201. Then, in milestone order: P2-203 ‖ P2-204 ‖ P2-206 (wave 2) → P2-202 ‖ P2-205 (wave 3) → P2-207 → P2-208.

---

*End of P2-201 implementation report. Implementation stopped — awaiting engineering review.*
