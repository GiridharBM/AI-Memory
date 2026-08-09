# Phase 2 Engineering Baseline

**Baseline for:** `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` (v1.1)
**Classification:** 🔒 **FROZEN** — change requires a formal design revision (see §11).

---

## 1. Document Version

| Field | Value |
|-------|-------|
| Document | Phase 2 — Implementation Specification |
| Version | **1.1** (Frozen) |
| Baseline reference | `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` |
| Baseline companion docs | `docs/PHASE_2_SPECIFICATION_REVIEW.md`, `docs/PHASE_2_SPECIFICATION_RE_REVIEW.md` |
| Source of truth | `docs/MASTER_ENGINEERING_DESIGN_DOCUMENT.md` (MEDD) — architecture unchanged |

## 2. Approval Date

**2026-08-01**

## 3. Approval Status

**APPROVED FOR IMPLEMENTATION** — ✅
- Re-review verdict: **✅ APPROVED FOR IMPLEMENTATION** (`docs/PHASE_2_SPECIFICATION_RE_REVIEW.md`).
- All 8 Required (R-1…R-8) and all 5 Recommended (C-1…C-5) findings resolved in v1.1; 4 non-blocking editorial items carried forward as **binding addenda** (§10).
- Prerequisite satisfied: Phase 1 complete and approved (commit `4a8525e`; 432 tests passing; coverage 86.02%).

## 4. Included Milestones

| Milestone | Scope summary | Tasks | Est. effort |
|-----------|---------------|-------|-------------|
| 2.1 — OCR Engine | Pluggable OCR engines (vision default, optional Tesseract), shared preprocessing, PDF page-render, per-page confidence, configurable prompts | P2-101…P2-108 | 4–5 d |
| 2.2 — Metadata Extraction Framework | Extractors, MIME (G15), language (G16), prompt adaptation, pre/post hooks (FR-ING-5/6), size/time limits (FR-ING-7/8), **email attachment parsing** (P2-208) | P2-201…P2-208 | 4–5 d |
| 2.3 — Document Structure Analysis | `DocumentStructure` models, heading/block detectors, enrichment hook (P2-305) reused by 2.4/2.5/2.6 | P2-301…P2-306 | 3 d |
| 2.4 — Table Intelligence | Table models, CSV/spreadsheet/PDF extractors (pdfplumber default per ADR-002), Markdown renderer, dead-flag wiring | P2-401…P2-406 | 4–5 d |
| 2.5 — Image Intelligence | `ImageInfo`, sole EXIF reader (R-3), shared preprocessing, diagram → Mermaid, configurable prompts, multi-image | P2-501…P2-506 | 4 d |
| 2.6 — Code & Notebook Intelligence | `CodeStructure`/`NotebookStructure`, AST + heuristic parsers, language registry, notebook ingestor upgrade | P2-601…P2-606 | 3–4 d |

**Total: 6 milestones, 40 tasks (P2-101…P2-606 + P2-208).**

## 5. Excluded Scope (explicitly deferred)

Per spec §1.2 and milestone out-of-scope lists; **not part of this baseline**:
- NLP sentence segmentation (G12), token-aware chunking (G13), hierarchical chunk consumption (G14).
- BM25/RRF/retrieval (G08/G25), FAISS (G01), metadata search filtering (Phase 4), table embeddings/search, formula-aware cells.
- Layout preservation (Epic 8), Docker/UI/API (Epic 7).
- Multi-language OCR model selection, Tesseract-on-images tuning (covered by 2.1 engine), vision-heavy diagram semantic understanding.
- Tree-sitter / ML code parsing, notebook cell execution, output rendering beyond presence flags.
- Optional (deferred): `pam doctor` full intelligence health check (O-1), splitting P2-107 (O-2), property/round-trip fuzz loops (O-3), MEDD Appendix B + `EXTENSIONS.md` guide (O-5).

## 6. Dependencies

**Runtime required (existing, unchanged):** `PyMuPDF>=1.24.0`, `openpyxl`, `pypdf`, `OllamaVisionClient` (local Ollama).

**New optional (extras `intelligence`; zero new required deps):** `Pillow`, `pytesseract` (+ Tesseract binary), `pdfplumber` (default PDF table engine, ADR-002), `camelot` (optional plugin), `py3langid`, `python-magic` (+ libmagic). Absent optional deps degrade gracefully with a clear `ImportError`/logged warning (G06 pattern; optional-dep DoD clause, C-3).

**Environment:** Python **3.14.6** on Windows — optional deps must resolve as `cp314-win_amd64` wheels; verify at each milestone start (R11 / R-5).

**Phase prerequisite:** Phase 1 complete and approved; all 432 pre-existing tests remain green; coverage ≥ 80%.

## 7. Assumptions

1. The **MEDD remains the single source of truth**; any further architecture change requires a MEDD revision, not a spec edit.
2. **Zero new required runtime dependencies**; all additions are additive schema fields (default `None`) with feature-flag rollback.
3. **Local-first/offline-first**: the full pipeline runs with no network (vision-excluded envs use Tesseract/fallback).
4. Optional-dep wheels are available for `cp314-win_amd64`; verified at milestone start before code work.
5. The vision model is available in live environments; hermetic tests always mock it.
6. Extracted structures attach to `ProcessedDocument` and the note template **only** — never to the analysis prompt input unless opted in (§1.3, R-7).
7. Each task = one atomic commit; each milestone gates on its own review (Phase 1 conventions).
8. Notes may change for detected tables/code this phase; recorded as a changelogged, reviewed behavior change (C-2).

## 8. Risks (baseline-carried from spec §9)

| # | Risk | L/I | Mitigation (in baseline) |
|---|------|-----|--------------------------|
| R1 | Optional deps fail on Windows (Tesseract, camelot, python-magic/libmagic) | M/H | Optional-only + clear `ImportError`; pdfplumber pure-Python default; magic fallback table; `pam doctor` PATH check |
| R2 | Vision model unavailable | M/H | Preserve no-fallback raise for vision-required kinds; Tesseract fallback for printed text |
| R3 | OCR latency (10–30 s/page) | M/M | Page limit + `max_pages` cap; per-page timing logs; bounded sequential loop |
| R4 | Note output changes break vaults | M/H | Feature-flag defaults; `enabled: false` restores Phase-1 output; changelog + migration note (C-2) |
| R5 | `ProcessedDocument` growth | M/M | Size caps (5 MB structure skip; 100 KB code; cell output caps) |
| R6 | PDF table accuracy low on complex layouts | H/M | Plugin engine swap (pdfplumber→camelot); confidence threshold; flat fallback |
| R7 | Language mis-classification | M/M | Confidence threshold → `"en"`; heuristic fallback; log + manual override |
| R8 | Prompt adaptation degrades JSON reliability | M/M | Additive instruction; schema unchanged; unit-tested |
| R9 | Coverage < 80% | M/M | Per-milestone coverage check; `fail_under=80`; parser/engine suites ≥ 90% |
| R10 | Scope creep into Phase 3/4 | M/H | Explicit out-of-scope list (§5); review gates reject Phase-3 features |
| R11 | Optional-dep wheels unavailable on `cp314-win_amd64` | M/H | Milestone-start `pip download --only-binary` verification; pure-Python fallbacks (R-5) |

## 9. Architecture Compliance

- **No pipeline stages added; no existing flow reordered.** Enrichment attaches inside existing layers: `_run_routed_processor`, `DocumentIngestionService.ingest()`, `DocumentClassifier.classify()`.
- **Plugin pattern preserved.** New capabilities register behind small protocols exactly like the existing processor router; the registry covers extensible kinds (OCR engines, metadata extractors, table extractors); image/code components are fixed services (C-1).
- **Schema additive only.** `ProcessedDocument`/`DocumentMetadata`/`DocumentAnalysis` gain optional fields defaulting to `None`; no migration.
- **MEDD authoritative.** The single recorded deviation — `pdfplumber` default vs MEDD G35's Camelot/Tabula — is documented as **ADR-002** (spec §13) and flagged for MEDD G35 amendment at the next MEDD update.
- **Rollback = flag + additive schema + optional extras gating.** No deprecated code branches; no `legacy` engine value (R-4).

## 10. Binding addenda (editorial items from re-review — apply during implementation, no spec reopen)

1. Add `enabled: true` to the `intelligence.metadata` config block (2.2) so it matches its own rollback row.
2. Add `P2-205` to P2-505's Deps (language slot), consistent with §5/§6.3.
3. List `intelligence.structure.enrich_analysis_input: false` in the 2.3 config block (currently only §1.3/§11.9).
4. Update 2.2 Estimated Effort to 4–5 dev-days to reflect P2-208.

## 11. Change Control Policy

- This specification is **FROZEN** as of **2026-08-01**.
- Future implementation **must follow this document** (including §10 addenda) unless a **formal design revision** is approved.
- A formal design revision = new version bump → engineering review → approval → re-freeze. Unapproved changes to the frozen scope, interfaces, dependencies, or rollback contract are out of scope by definition.
- The MEDD is the architecture source of truth; architectural changes require a MEDD revision plus a corresponding design revision of this baseline.

## 12. Approval Checklist

- [x] Phase 1 complete and approved (432 tests, coverage 86.02%)
- [x] Specification v1.1 incorporates all 8 Required + 5 Recommended review findings
- [x] Re-review verified all 8 verification points → ✅ APPROVED FOR IMPLEMENTATION
- [x] Architecture compliance confirmed (no pipeline reordering, additive schema, MEDD authoritative)
- [x] Dependencies valid (no cycles; optional-only new deps; wheel risk mitigated)
- [x] Testing strategy complete (unit/integration/regression/perf/manual/benchmarking)
- [x] Acceptance criteria measurable at phase and milestone level
- [x] Rollback plans valid and verifiable (R-4 resolved)
- [x] Milestones ordered (2.1‖2.2 → 2.3 → 2.4‖2.6 → 2.5)
- [x] Editorial addenda (§10) recorded as binding
- [ ] **IMPLEMENTATION MAY BEGIN**

---

## Version History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-07-31 | Draft for review |
| 1.1 | 2026-08-01 | Incorporated R-1…R-8 + C-1…C-5; Change Log (§14); **approved** |
| **Baseline** | **2026-08-01** | **Frozen as Engineering Baseline** (this document) |

*End of Phase 2 Engineering Baseline.*
