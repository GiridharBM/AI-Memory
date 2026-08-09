# Milestone 2.2 Specification Freeze — Version 1.0

**Frozen by:** Principal Engineering Reviewer (on behalf of the project)
**Date:** 2026-08-01
**Source document:** `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` (**Version 1.0, FROZEN**)
**Source of truth chain:** MEDD → `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` v1.1 (🔒 FROZEN, Engineering Baseline 2026-08-01) → `docs/PHASE_2_ENGINEERING_BASELINE.md` (binding addenda §10) → this document.
**Review record:** `docs/PHASE_2_MILESTONE_2_2_SPECIFICATION_REVIEW.md` — ✅ Ready for Implementation (5 low-severity findings; none blocking).
**Contract scope rule:** **This document is the implementation contract for Milestone 2.2.** No code is implemented by this document. Future work must follow this contract unless a formal design revision is approved per the Change Control Policy (Baseline §11). Only change-control-approved deviations are permitted.

---

## 1. Version

| Attribute | Value |
|-----------|-------|
| Document | Milestone 2.2 — Metadata Extraction Framework |
| Semantic version | **1.0** |
| Status | 🔒 **FROZEN** (2026-08-01) |
| Prerequisite | Milestone 2.1 complete and approved (8/8 tasks; 506 passed / 2 deselected; coverage 87.02%) |
| Upstream | Phase 2 Implementation Specification v1.1 (FROZEN) + Engineering Baseline addenda §10 (1, 4) |
| Estimated effort | 4–5 dev-days (addendum 4); task-table sum 5.5 d — budget treated as 5 d ± buffer |
| Rollback contract | `intelligence.metadata.enabled: false` returns Phase-1-identical documents; no legacy branch (R-4) |

---

## 2. Scope

### In scope
- `MetadataExtractor` protocol + registry (`DocumentMetadataService`) + `MetadataExtraction` model; merge into `DocumentMetadata` (unknown keys → `extra`).
- Five stdlib-only built-in extractors: pdf/audio/email/docx/pptx/notebook; PDF metadata logic moved out of `PdfIngestor` (behavior byte-identical).
- MIME detection service (G15): magic-number sniff (first 512 bytes) + fallback table; optional `python-magic` (ADR-001 warning-only); extensionless Markdown detected.
- Language detection service (G16): optional `py3langid` + pure-heuristic fallback; confidence threshold → `"en"` default.
- Language propagation (`DocumentClassification.language`, `ProcessedDocument.language`) + analysis-prompt adaptation (respond-in-`{language}`; English path byte-identical).
- Pre/post `IngestionHook` chain + size/time enforcement (FR-ING-5/6/7/8): pre-hook rejects >50 MB before read; post-hook modifies document; hook errors never break ingestion.
- Metadata enrichment wiring in `DocumentIngestionService.ingest()` — single call site, no flow reordering; result is a superset of Phase-1 metadata.
- Email attachment parsing (**P2-208**, R-1): RFC822 parent note + recursive child-document ingestion with `ProcessedDocument.parent_id`; `max_attachments` cap; per-child size limit; recursion depth guard.
- Image EXIF: **document-level fields only** — raw EXIF read and `ImageInfo` are owned by M2.5 P2-502 (single-owner boundary, R-3); no second EXIF reader.

### Out of scope
- Metadata *search filtering* (Phase 4).
- Remote URL timeout deep-tuning beyond the `url_timeout_seconds: 30` default.
- Structural metadata (`DocumentStructure`, sections, headings hierarchy) — Milestone 2.3.
- Table intelligence, image intelligence (`ImageInfo`), code/notebook structure — Milestones 2.4/2.5/2.6.
- Layout preservation and ML handwriting recognition (carried from M2.1).

---

## 3. Included Tasks

| Task | Title | Priority | Deps | Effort | Risk |
|------|-------|----------|------|--------|------|
| P2-201 | Metadata extractor interface + registry | P0 | — | 0.5 d | L |
| P2-202 | Built-in extractors (pdf/audio/email/docx/pptx/notebook) | P0 | P2-201 | 1 d | M |
| P2-203 | MIME detection service (G15) | P0 | — | 0.5 d | M |
| P2-204 | Language detection service (G16) | P0 | — | 0.5 d | M |
| P2-205 | Language propagation + prompt adaptation | P0 | P2-204 | 0.5 d | M |
| P2-206 | Hook chain (pre/post) + limits (FR-ING-5/6/7/8) | P1 | P2-201 | 1 d | M |
| P2-207 | Metadata enrichment wiring in ingestion service | P0 | P2-202, P2-206 | 0.5 d | M |
| P2-208 | Email attachment parsing (recursive ingestion) | P1 | P2-202, P2-207 | 1 d | M |

**Total: 8 tasks.** Acceptance criteria per task are those in the frozen engineering spec §4 (AC 1–6 at milestone level; per-task criteria in each task block).

**Implementation order (binding):** P2-201 → wave-2 ‖ {P2-203, P2-204, P2-206} → wave-3 ‖ {P2-202, P2-205} → P2-207 → P2-208. Critical path: P2-201 → P2-202 → P2-207 → P2-208. P2-205 must land **before** 2.1/2.5 prompt-config work (frozen §4.6, addendum 2).

---

## 4. Excluded Tasks

| Excluded item | Reason / owner |
|---------------|----------------|
| Metadata search filtering | Phase 4 |
| Remote URL timeout deep-tuning | Out of scope; default `30 s` is the contract |
| `DocumentStructure` / sections / heading hierarchy | Milestone 2.3 (P2-301…) |
| `ImageInfo` / EXIF image fields | Milestone 2.5 (P2-501, P2-502) — single-owner boundary R-3 |
| Table extraction / rendering | Milestone 2.4 (P2-401…) |
| Code/notebook structure models | Milestone 2.6 (P2-601…) |
| New required dependencies | All new deps are optional (`python-magic`, `py3langid`) with graceful `ImportError` fallbacks |
| Structural data into the analysis prompt | R-7: structures attach to `ProcessedDocument`/note template only; opt-in via `intelligence.structure.enrich_analysis_input` |

---

## 5. Assumptions

1. **Optional-dependency wheels are verified at milestone start** on `cp314-win_amd64`, including `python-magic`'s libmagic DLL and `py3langid` (R-5 / Baseline R11); absence degrades to stdlib fallbacks, never to failure.
2. **MIME detection never overrides an explicit ingestor match** for known extensions (ADR-001).
3. **`intelligence.metadata.enabled: true` by default** (addendum 1); `false` ⇒ Phase-1-identical documents (R-4).
4. **`parent_id` identifier scheme is pinned during P2-201** (review F-1): the parent identifier is the parent note's relative filename (Obsidian-safe slug, `_safe_filename(title).md`) — the codebase has no other stable document ID today. AC 6 is asserted against this scheme.
5. **No schema migration:** all new fields additive with `None`/default values (`ProcessedDocument.parent_id`, `ProcessedDocument.language`); no field re-typed or removed.
6. **Extractor failures are isolated:** a failing extractor/hook logs and is skipped; ingestion continues with the document unchanged (fault-tolerant default).
7. **Live-Ollama integration smoke test may be flaky** (pre-existing model-output variance, carried from M2.1); not a gate item for M2.2.
8. **Test baseline for regression gates** is the live suite at milestone start (**508 collected / 506 passed / 2 deselected**, coverage 87.02%), not the stale "432" figure (review F-2).

---

## 6. Dependencies

### Intra-milestone (hard edges, cycle-free)
```
P2-201 → P2-202 → P2-207 → P2-208
P2-201 → P2-206 → P2-207
P2-204 → P2-205
P2-202 -. email extractor .-> P2-208
P2-203 -. consulted by classifier .-> P2-205
```

### Cross-milestone
- **Feeds:** the `{language}` prompt-slot contract (P2-205) is consumed by 2.1/2.5 prompt templates — must exist before those prompt-config tasks.
- **Receives:** image `DocumentMetadata` fields are populated by 2.5's `ImageInfo` once it lands (R-3) — M2.2 consumes, does not duplicate.
- **Runtime deps:** PyMuPDF (present), stdlib `zipfile`/`ElementTree`/`json` for docx/pptx/notebook core properties; `email` stdlib for RFC822.
- **Optional (add to `intelligence` extra):** `python-magic` (ADR-001), `py3langid` (P2-204). Neither required for default behavior.

---

## 7. Risks

| # | Risk | Severity | Mitigation (binding) |
|---|------|----------|----------------------|
| 1 | P2-208 recursive email ingestion is the largest blast radius (loop/temp leaks/attachment bombs) | High | `max_attachments: 20` cap + per-child `max_file_size_mb` reuse + recursion depth guard; temp files cleaned in `finally`; `email_attachments: false` restores single-document behavior |
| 2 | libmagic `python-magic` wheel unavailable on `cp314-win_amd64` | Medium | Preflight at milestone start (step 0); stdlib `_magic_fallback` sniff table covers common signatures incl. Markdown |
| 3 | Language mis-classification of short/technical text (R7) | Medium | Confidence threshold → `("en", 0.0)` default + warning; first ≤ 10 KB only; independent `language_detection_enabled` toggle |
| 4 | French prompt adaptation degrades structured-JSON reliability (R8) | Medium | Instruction is additive and appended only when `language != "en"`; English path byte-identical; unit-tested prompt string + field-completeness check |
| 5 | `enabled: false` rollback drift | Medium | Integration test asserts Phase-1-identical documents; no legacy branch retained (R-4) |
| 6 | M2.1 package-layout precedent vs frozen §7.2 (models in `infrastructure/` vs `domain/`) | Low | P2-201 confirms placement of `MetadataExtraction` in `app/domain/document_intelligence.py` per frozen §7.2 (review F-4) |
| 7 | Metadata taxonomy boundary ambiguity | Low | Document-level metadata in scope; structural → M2.3, image → M2.5, processing → existing `ProcessedDocument` fields (review F-5) |

---

## 8. Approval Checklist

- [x] Spec versioned **1.0** and status set to **FROZEN** (this document + engineering spec header).
- [x] Reviewed by Principal Engineering Reviewer — ✅ Ready for Implementation (review report on file).
- [x] All 5 review findings dispositioned: F-1 bound into Assumption 4, F-2 into Assumption 8, F-3 into §1 effort note, F-4/F-5 bound into Risk 6/7.
- [x] Scope (in/out) matches frozen Phase 2 v1.1 Milestone 2.2 row exactly.
- [x] 8/8 included tasks (P2-201…P2-208) carry per-task acceptance criteria and DoD from the frozen engineering spec.
- [x] Dependency graph verified cycle-free; implementation order binding.
- [x] Rollback contract (`enabled: false` → Phase-1-identical; independent mime/language/email toggles) confirmed.
- [x] Backward compatibility contract (additive fields only, no migration) confirmed.
- [x] Performance ceilings bound: MIME sniff ≤ 512 B, language ≤ 10 KB, extractors run once, hook chain short-circuits.
- [x] No code implemented by this freeze.

**Approved:** Milestone 2.2 Specification v1.0 is FROZEN and is the binding implementation contract. Any deviation requires Change Control approval per Baseline §11.
