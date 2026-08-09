# P2-201 Engineering Review Report

**Task:** P2-201 — Metadata extractor interface + registry
**Reviewer:** Principal Software Architect and Engineering Reviewer
**Date:** 2026-08-01
**Scope:** Review ONLY P2-201 implementation. **No code modified.**
**Reviewed against:** MEDD, frozen Phase 2 Implementation Specification v1.1, Milestone 2.2 Engineering Specification (v1.0 FROZEN), Milestone 2.2 Specification Freeze, P2-201 Implementation Report, live source + tests.

---

## 1. Verification Matrix

| # | Review criterion | Result |
|---|------------------|--------|
| 1 | `MetadataExtraction` model matches spec | ✅ Pass |
| 2 | `MetadataExtractor` protocol correct | ✅ Pass |
| 3 | `DocumentMetadataService` registry follows approved architecture | ✅ Pass |
| 4 | Registry behavior deterministic | ✅ Pass |
| 5 | Merge strategy follows spec | ✅ Pass |
| 6 | Public interfaces stable | ✅ Pass |
| 7 | Backward compatibility preserved | ✅ Pass |
| 8 | Tests sufficiently cover implementation | ✅ Pass |
| 9 | No unnecessary complexity introduced | ✅ Pass (1 observation) |
| 10 | Documentation matches implementation | ✅ Pass |

---

## 2. Criterion-by-Criterion Findings

### 1. `MetadataExtraction` model — ✅ Pass
Spec (frozen §2.3 interfaces + §4.2 step 2): `MetadataExtraction(source_type, values: dict[str, Any], extractor: str)`.
Implementation (`app/domain/document_intelligence.py:10-17`): `source_type: str`, `values: dict[str, Any] = Field(default_factory=dict)`, `extractor: str`, `extra="forbid"`.
- ✅ Exact field names, types, and order match the frozen contract.
- ✅ Placement in `app/domain/document_intelligence.py` matches frozen §7.2 (shared domain models) and the freeze contract Risk 6 (review F-4 dispositioned).

### 2. `MetadataExtractor` protocol — ✅ Pass
Spec (§2 normative): `source_types: tuple[str, ...]` + `def extract(self, document: SourceDocument) -> dict[str, Any]`.
Implementation (`__init__.py:26-34`): identical signature, plus `@runtime_checkable`.
- ✅ Signature matches exactly; `@runtime_checkable` is additive and mirrors the shipped M2.1 `OcrEngine` protocol (`ocr/base.py:19`), satisfying "register exactly like the existing processor router" (C-1).
- ✅ No `name` field required by the contract; implementation handles optional `name` via `getattr(..., type(e).__name__)` — tolerant of the contract.

### 3. `DocumentMetadataService` registry — ✅ Pass
Spec step 4: `register(extractor)` + `extractors_for(source_type)` + `merge(metadata, extraction)`.
Implementation (`__init__.py:37-110`):
- ✅ `register` (idempotent — duplicate instance is a no-op), `extractors_for` (registration-order filter), static `merge` — all present with the exact frozen signatures.
- ✅ `extract(document)` added as the natural home of frozen step 5 (the "no-extractor path returns an empty extraction" requirement) — runs matching extractors in registration order, returns one merged `MetadataExtraction`. This is the "one deterministic metadata path" the milestone Objective/Purpose requires, not scope creep.
- ✅ Mirrors M2.1 `DocumentOcrService` structure (`ocr/base.py:31-87`) — registry, register, snapshot property, select/run split. Consistent with the approved architecture.

### 4. Deterministic behavior — ✅ Pass
- ✅ Registration order preserved and observable (`extractors` snapshot property, `extractors_for` filter).
- ✅ `extract` merges values in registration order; later extractors override earlier shared keys — documented in docstring, deterministic.
- ✅ Empty-registry / no-match path returns `MetadataExtraction(source_type, values={}, extractor="<none>")` + `logger.debug` — **never raises** (frozen step 5, test-verified).
- ✅ Duplicate registration is defined: same instance → idempotent no-op; distinct instances → both kept in order. Test-verified.

### 5. Merge strategy — ✅ Pass
Spec step 4 + §2.3: "extracted keys map to `DocumentMetadata` fields, unknown keys go to `extra`"; additive.
Implementation (`__init__.py:92-110`):
- ✅ `_KNOWN_METADATA_FIELDS` = the 7 `DocumentMetadata` fields (`title, author, created_at, modified_at, page_count, mime_type, encoding`) — verified complete against `documents.py:17-24` (`extra` handled separately).
- ✅ Known keys written directly; unknown keys routed into a copy of `metadata.extra`; original `extra` keys preserved (additive superset contract).
- ✅ Pure function via `model_copy(update=...)` — original `DocumentMetadata` never mutated (test-verified).

### 6. Public interfaces stable — ✅ Pass
- ✅ Exposes exactly the P2-201 subset of the frozen public API: `MetadataExtraction`, `DocumentMetadataService`, `register_extractor()`, plus `MetadataExtractor` (the protocol the task must define). `detect_language`/`detect_mime`/`register_hook` correctly deferred to P2-204/203/206.
- ✅ `__all__` explicit and complete; `register_extractor()` public alias registers onto the lazy `get_default_metadata_service()` singleton (the minimal target for the alias — same idiom as M2.1 `get_default_ocr_service`).
- ✅ Config intentionally untouched (P2-207 owns `intelligence.metadata`).

### 7. Backward compatibility — ✅ Pass
- ✅ Verified via `git status`: new files only (`app/domain/document_intelligence.py`, `app/infrastructure/document_intelligence/metadata/`), plus `tests/unit/test_metadata_extraction.py`.
- ✅ Grep confirms **no wiring** into `ingestion/service.py`, `routing/classifier.py`, `pipelines/ingest_workflow.py`, `config/default.yaml` — zero behavior change to the live pipeline (DoD "not wired into ingestion" honored).
- ✅ Full suite: **520 passed / 2 deselected** (baseline 506/2; +14 net new; 0 regressions).

### 8. Test coverage — ✅ Pass
`tests/unit/test_metadata_extraction.py` — **14 tests**, 100% coverage on both new modules (`domain/document_intelligence.py` 8 stmts, `metadata/__init__.py` 51 stmts).
Frozen testing strategy coverage:
- Register/select per `source_types` ✅ (`test_register_and_select_by_source_type`)
- Merge writes known fields only, unknown → `extra` ✅ (`test_merge_writes_known_fields_and_routes_unknown_to_extra`, `test_merge_only_routes_unknown_keys_to_extra`)
- No-extractor type → empty merge ✅ (`test_extract_with_no_matching_extractor_returns_empty`, `test_extract_never_raises_for_unknown_source_type`)
- Duplicate-registration behavior defined ✅ (`test_duplicate_registration_is_idempotent`)
- Extras verified: registration order, in-order merge/override, original immutability, public alias, singleton. Strong coverage for a Low-complexity foundation task.

### 9. No unnecessary complexity — ✅ Pass (1 observation)
- ✅ No speculative abstractions, no config, no dependency, no schema change. Implementation is ~135 lines including docstrings.
- **Observation (non-blocking):** `merge` uses `model_copy(update=...)`, which performs no pydantic re-validation, so a non-typed value for a known field (e.g., `created_at` as a bare string) would be stored unvalidated. Not a defect today: extractors are internal and P2-207 wraps extraction in try/except per frozen step 4. If type-safety at the boundary is wanted, construct a fresh `DocumentMetadata(**...)` to re-validate — defer to P2-207 if needed.

### 10. Documentation matches implementation — ✅ Pass
- ✅ Implementation Report §1 tables match the live code exactly (model fields, protocol signature, service methods, `extractors.py` placeholder, package layout).
- ✅ Report §2 design decisions accurately document the runtime_checkable choice, `extract()` rationale, idempotent register, never-raises path, and F-4 placement.
- ✅ Report §3/§4 test results and acceptance/DoD status re-verified independently (520 passed, 100% coverage, ruff 64 = baseline, mypy no new errors).
- ✅ Scope claim "ONLY P2-201" verified — no P2-202+ work present.

---

## 3. Verdict

The implementation is a faithful, minimal realization of the frozen P2-201 contract. Every interface matches the normative signatures, the registry mirrors the approved M2.1 `DocumentOcrService` architecture, merge behavior is exactly the frozen additive rule, the no-extractor path never raises, and the task is correctly isolated from ingestion (backward compatible, rollback-safe). The single observation on `model_copy` validation is non-blocking and already covered by the P2-207 failure-isolation contract.

✅ **Approved**
