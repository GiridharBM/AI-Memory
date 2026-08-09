# Milestone 2.2 Specification Review Report

**Reviewed document:** `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` (307 lines)
**Reviewer:** Principal Engineering Reviewer
**Date:** 2026-08-01
**Review method:** Line-by-line comparison against the frozen baseline (`docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` v1.1, `docs/PHASE_2_ENGINEERING_BASELINE.md`) plus verification of every code-level claim against the live codebase.
**Scope:** Architecture compliance, dependency correctness, task ordering, plugin architecture, metadata model completeness, testing strategy, rollback plans, backward compatibility, scalability, future extensibility.

---

## 1. Verdict Summary

| Dimension | Verdict |
|-----------|---------|
| Architecture compliance | ✅ Pass |
| Dependency correctness | ✅ Pass |
| Task ordering | ✅ Pass |
| Plugin architecture | ✅ Pass |
| Metadata model completeness | ⚠️ Pass with note |
| Testing strategy | ✅ Pass |
| Rollback plans | ✅ Pass |
| Backward compatibility | ✅ Pass |
| Scalability | ✅ Pass |
| Future extensibility | ✅ Pass |

---

## 2. Verified Findings

### 2.1 Code-fact verification (all claims checked against source)

| Claim in spec | Verified |
|---------------|----------|
| `PdfIngestor` fills title/author/dates/producer | ✅ `pdf_ingestor.py:55-72` (`metadata: dict(...)` read, `_clean_pdf_string` at :77, `_parse_pdf_datetime` at :84) |
| `classifier.py:84` uses `mimetypes.guess_type` | ✅ `mime_type, _ = mimetypes.guess_type(document.filename)` at :84 |
| `DocumentMetadata` has title/author/created_at/modified_at/page_count/mime_type/encoding/extra, `extra="forbid"` | ✅ `documents.py:12-24` |
| `ProcessedDocument.language` exists and is never set | ✅ field at `processed_document.py:26` (spec cites :19 — cosmetic line drift, points at `metadata` field) |
| `EmailIngestor` drops attachments | ✅ `.eml` only, headers+body, `msg.walk()` ignores `Content-Disposition: attachment` |
| `intelligence.metadata` config block absent today | ✅ not present in `config/default.yaml` (spec correctly adds it) |
| 508 tests collected / 506 passed / 2 deselected | ✅ `pytest --collect-only`: 508 collected, 2 deselected |

### 2.2 Findings requiring attention

**F-1 (Low, P2-208): `parent_id` identifier scheme is undefined.**
`ProcessedDocument.parent_id: str | None` is specified, but the codebase has **no stable document/note ID** today: `SourceDocument`/`ProcessedDocument` carry no `id`, notes are written as `{_safe_filename(title)}.md`, and the only digest available is `compute_file_hash` (SHA-256) in `app/infrastructure/state/hashing.py`. AC 6 (3 attachments → 1 parent + 3 children with `parent_id`) is not testable until the ID scheme is pinned. **Required:** define `parent_id` as the parent note's relative filename (or file hash) in P2-201's `ProcessedDocument` addendum so AC 6 has a concrete assertion.

**F-2 (Low, §8): stale test count.** Review checklist says "All 432 pre-existing tests pass unchanged"; the actual suite is **508 collected / 506 passed / 2 deselected** (M2.1 completion report already shows 506). The "432" figure is inherited from M2.1's engineering spec and predates both milestones. Update to the live count (or "the full suite at milestone start").

**F-3 (Low, §1): effort arithmetic.** Overview states "4–5 dev-days (addendum 4; tasks total ~5 d)" but the task table sums to **5.5 d** (0.5+1+0.5+0.5+0.5+1+0.5+1). Reconcile — either state 5.5 d including buffer or trim a task estimate — so the milestone gate budget is internally consistent with addendum 4 (4–5 d).

**F-4 (Info): package-layout split.** Frozen §7.2 places `MetadataExtraction` in `app/domain/document_intelligence.py`, which does **not exist yet** — M2.1 implemented `OcrResult`/`PageOcrResult` in `app/infrastructure/document_intelligence/ocr/models.py` instead. The engineering spec is faithful to the frozen §7.2 contract, but implementers should confirm placement before P2-201 to avoid later consolidation churn (a one-line note in P2-201 would suffice).

**F-5 (Info): metadata taxonomy boundary.** Design goals cover document-level / structural / processing metadata. The spec fully covers document-level and correctly defers structural (M2.3 `DocumentStructure`) and image (M2.5 `ImageInfo`, R-3). Processing metadata (extraction engine, version, warnings, timing) has no explicit home beyond the existing `ProcessedDocument.ocr`/`metadata`. Recommend a one-line mapping in P2-201 so the "complete metadata" objective is bounded at milestone scope.

None of F-1…F-5 block implementation. F-1 must be pinned during P2-201; F-2/F-3 are doc corrections; F-4/F-5 are implementer guidance.

---

## 3. Dimension-by-Dimension Review

### 3.1 Architecture compliance — ✅ Pass
- Matches frozen §4.2 task IDs (P2-201…P2-208) and acceptance criteria (AC 1–6) exactly; no task added, dropped, or re-scoped.
- "No pipeline stages added, no flow reordered" is respected: enrichment is a single post-`ingestor.ingest()` call site in `DocumentIngestionService` (verified: `ingest()` at `service.py:69`, `_ingest_source()` at :115); classifier gains only a MIME consult; P2-205 is prompt-string additive.
- Registry/protocol pattern mirrors the shipped M2.1 `DocumentOcrService`/`OcrEngine` shape (`ocr/__init__.py` `get_default_ocr_service`) — consistent with the frozen "register exactly like the existing processor router" rule and Baseline C-1.
- R-3 single-owner boundary (no second EXIF reader; image fields consumed from 2.5's `ImageInfo`) honored.

### 3.2 Dependency correctness — ✅ Pass
- Hard edges match frozen §4.2: P2-201→{202,206}, P2-204→205, {202,206}→207, {202,207}→208. No cycle; P2-203/P2-204 correctly independent.
- All new deps are optional (`python-magic`, `py3langid`) with import-guarded fallbacks; built-in extractors are stdlib-only (zipfile/ElementTree for docx/pptx core props, `json` for notebooks) — no new required dependency. Wheel-availability preflight (R-5/R11) is correctly placed as step 0.
- `email_ingestor.py` correctly marked "extend" — the frozen spec's "new" tag is stale (the file exists); the engineering spec is the accurate one.

### 3.3 Task ordering — ✅ Pass
- Critical path P2-201 → P2-202 → P2-207 → P2-208 is sound; parallel waves (P2-203 ‖ P2-204 ‖ P2-206; P2-202 ‖ P2-205) are valid — P2-206 needs only P2-201, P2-205 only P2-204.
- Cross-milestone constraint honored: P2-205 `{language}` slot lands before 2.1/2.5 prompt work (frozen §4.6, addendum 2).

### 3.4 Plugin architecture — ✅ Pass
- `MetadataExtractor` Protocol (source_types + extract) and `IngestionHook` Protocol (pre/post) match frozen §2.3 verbatim; registry exposes the required public APIs (`register_extractor`, `register_hook`, `detect_language`, `detect_mime`, `MetadataExtraction`, `DocumentMetadataService`).
- No-extractor-for-type returns empty merge (never raises) — correct fault-tolerant default for an offline-first tool.
- Config-driven plugin names (`extractors: "default"`, `hooks.pre/post`) keep the extension surface declarative.

### 3.5 Metadata model completeness — ⚠️ Pass with note (F-5)
- Document-level: complete and additive over `DocumentMetadata`'s eight fields; unknown keys route to `extra` (respects `extra="forbid"`).
- Structural/processing taxonomy boundary deferred correctly to M2.3/M2.5 and existing `ProcessedDocument` fields; a one-line mapping would remove ambiguity.
- `parent_id` (F-1) is the only true model gap.

### 3.6 Testing strategy — ✅ Pass
- Unit/integration/regression/perf/manual layers map to concrete files (`test_metadata_extraction.py`, `test_ingestion_metadata.py`) and existing suites; `@pytest.mark.integration` opt-in marker matches repo convention.
- AC-to-test traceability is explicit (AC 1→MIME, AC 2→prompt, AC 3→hooks, AC 4→superset, AC 5→warning-once, AC 6→email fixture).
- Absent-dependency paths (monkeypatched import) tested — the key risk for optional deps.
- **Correction (F-2):** the "432 pre-existing tests" baseline must read the live count (508 collected).

### 3.7 Rollback plans — ✅ Pass
- `intelligence.metadata.enabled: false` → Phase-1-identical documents, matching R-4's "no legacy branch" contract and the OCR milestone's proven pattern.
- Independent toggles (`mime_enabled`, `language_detection_enabled`, `email_attachments`) give granular rollback; additive fields only, no migration.

### 3.8 Backward compatibility — ✅ Pass
- All new fields additive with `None` defaults; metadata enrichment is a superset of Phase-1 values; MIME never overrides an explicit ingestor match for known extensions (ADR-001); English prompt path stays byte-identical (P2-205 regression test).

### 3.9 Scalability — ✅ Pass
- Perf ceilings are explicit and enforceable: MIME sniff ≤ first 512 bytes, language detection ≤ first 10 KB, extractors run once per document, hook chain short-circuits on reject.
- Attachment-bomb mitigation: `max_attachments` (20) cap + per-child `max_file_size_mb` reuse + recursion depth guard — directly addresses the milestone's largest blast radius.
- Appropriate for a local-first tool; no unbounded work introduced.

### 3.10 Future extensibility — ✅ Pass
- The registry + public `register_*` APIs are the documented extension seam for Phase 3+ and future document types; config-driven plugin names; pattern identical to M2.1's proven OCR registry.
- `{language}` prompt-slot contract is documented as the feed-forward dependency for 2.1/2.5 prompt config.

---

## 4. Non-blocking Recommendations
1. Pin the `parent_id` scheme (note relative path or SHA-256 file hash) in P2-201 (F-1).
2. Correct the test-count baseline to the live suite and fix the effort sum to 5.5 d or reconcile to 4–5 d (F-2, F-3).
3. Add a one-line note in P2-201 confirming `MetadataExtraction` placement in `app/domain/document_intelligence.py` despite the M2.1 precedent (F-4).
4. Optional: add a short metadata-taxonomy mapping (document/structural/processing → owner model) to bound scope (F-5).

---

## 5. Final Verdict

✅ **Ready for Implementation**

The specification is faithful to the frozen v1.1 baseline and the Engineering Baseline addenda, its dependency graph and task ordering are correct and cycle-free, it reproduces the proven M2.1 plugin pattern, and every code-level claim verified against the source. The five findings are low-severity: F-1 must be resolved as part of P2-201 (pin the `parent_id` scheme) and F-2/F-3 are documentation corrections; none alter scope, architecture, or interfaces. Proceed to implementation with F-1 tracked as an implementation-time requirement.
