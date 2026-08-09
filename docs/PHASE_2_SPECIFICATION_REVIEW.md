# Phase 2 Implementation Specification — Engineering Review

**Date:** 2026-08-01
**Scope:** Independent review of `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` against the MEDD (`MASTER_ENGINEERING_DESIGN_DOCUMENT.md`), Phase 1 artifacts, and the current source tree. Implementation-perspective review; **no code was modified.**
**Method:** Cross-check of all 15 verification dimensions; every finding verified against source (dead-flag wiring, `language` field population, URL timeout/size-limit enforcement, hardcoded prompt locations, Python 3.14.6 runtime, MEDD Phase 2 scope table). `requires_table_extraction`/`requires_ocr`/`requires_vision`/`requires_code_parsing` confirmed set-but-never-read (`classifier.py:97-100` vs. no consumer). `DocumentClassification.language`/`ProcessedDocument.language` confirmed never populated. `DocumentIngestionService.ingest()` confirmed to have no URL timeout or size-limit enforcement (`service.py:69-98`).

---

## Verdict

# ❌ CONDITIONALLY APPROVED — 8 Required findings must be resolved before execution

The specification is fundamentally sound: architecture-preserving, additive, plugin-based, correctly mapped to MEDD gaps, with a strong testing strategy and layered rollback. However, it cannot be executed as-is: it **omits one MEDD Phase 2 deliverable** (email attachment parsing), **silently deviates from MEDD's named table tool** (Camelot) without an ADR, **declares a rollback config value it never defines**, **misses the Python 3.14 wheel risk**, and contains **internal inconsistencies** (cross-milestone dependencies, duplicated preprocess/EXIF modules, prompt-config scope gap). All findings are spec-level fixes (~0.5 day); none require an architecture change.

---

## Verification matrix (15 dimensions)

| # | Dimension | Status | Reference |
|---|-----------|--------|-----------|
| 1 | Milestones logically ordered | ✅ PASS | §6 order justified; 2.1‖2.2 wave is sound; see note (largest milestone) |
| 2 | Dependencies complete | ❌ FAIL | Hook dependency missing from P2-406/P2-506/P2-606 (R-2) |
| 3 | No milestone too large | ✅ PASS | 2.1 largest (8 tasks / 4–5 d); acceptable, note in O-2 |
| 4 | Every task implementable | ✅ PASS* | Concrete tasks; optional-dep absent behavior under-specified (C-4) |
| 5 | Interfaces consistent | ❌ FAIL | Duplicate preprocess modules + EXIF ownership overlap (R-3) |
| 6 | Plugin architecture consistent | ⚠️ PASS* | Registries for OCR/metadata/tables, not for image/code (C-1) |
| 7 | Configuration complete | ❌ FAIL | `legacy` engine undefined (R-4); OCR/Handwriting prompts unconfigured (R-6) |
| 8 | Testing strategy complete | ✅ PASS | 6 layers covered; enhancements in C-5/O-3 |
| 9 | Rollback plans sufficient | ⚠️ PASS* | Layered; one unverifiable mechanism (R-4) |
| 10 | Risks correctly identified | ❌ FAIL | Python 3.14 Windows wheels missing (R-5) |
| 11 | Acceptance criteria measurable | ⚠️ PASS* | Two criteria qualitative (C-6) |
| 12 | No architecture conflicts with MEDD | ❌ FAIL | Email attachment parsing omitted (R-1); camelot→pdfplumber unrecorded (R-8) |
| 13 | No unnecessary complexity | ⚠️ PASS* | Duplicate modules (R-3); structure unused this phase (O-4) |
| 14 | Backward compatibility maintained | ⚠️ PASS* | Additive schema sound; default-true toggles change notes (C-3) |
| 15 | Future extensibility preserved | ✅ PASS | Registries + register() extension points; consistency noted (C-1) |

`*` = pass with required/recommended clarification, detailed below.

---

## What passed

- **Architecture preserved.** No pipeline stages added, no flow reordered; enrichment attaches inside existing layers (`_run_routed_processor`, `DocumentIngestionService.ingest`, `DocumentClassifier.classify`). Consistent with MEDD §7.2 and §2.4 goals.
- **Gap mapping is accurate.** G15/G16/G33/G34/G35/G36/G37 and FR-ING-4…8 map correctly; the "dead flags" finding is verified (classifier sets 4 flags, none read).
- **`language` gap is real and correctly targeted.** Both `DocumentClassification.language` and `ProcessedDocument.language` are never set today; only the LLM's `ExtractedMetadata.language` defaults to `"en"`.
- **Additive, backward-compatible schema.** New fields on `ProcessedDocument` default to `None`; no field removed or re-typed.
- **Local-first discipline.** All new dependencies are optional extras with the established clear-`ImportError` pattern; pdfplumber default is lighter than camelot.
- **Testing strategy** covers unit/integration/regression/perf/manual/benchmarking with hermetic conventions carried over from Phase 1 (mocked vision, `-m integration` opt-in).
- **Task decomposition** is concrete and complete enough to execute autonomously; every task carries AC + DoD.
- **Rollback is layered** (feature flag / optional dep / additive schema / deprecation branch / atomic commits / milestone gates).

---

## Required findings (must resolve before execution)

### R-1 — MEDD Phase 2 deliverable omitted: email attachment parsing
- MEDD Phase 2 roadmap (lines 1394–1418) lists **"Email attachment parsing — 1 week"**; Epic 2 acceptance is *"PDF with 3 attachments produces 4 notes (1 parent + 3 children)."* The spec covers MIME, language, hooks, tables, table-to-Markdown but **omits email attachment parsing entirely** — no task, no explicit deferral.
- Fix: add a task (natural home: Milestone 2.2 as a recursive-ingestion/enrichment deliverable, or a small standalone task) **or** record an explicit, MEDD-amended deferral with rationale. Since the MEDD is the single source of truth and Phase 2 is scoped to include it, omission is a scope defect, not a preference.

### R-2 — Cross-milestone dependency on the enrichment hook is missing from task tables
- The dependency graph (§5) states the 2.3 enrichment hook is reused by tables/code/image, but the **task dependency columns contradict it**: P2-406, P2-506, P2-606 list no dependency on P2-305 (or on Milestone 2.3 at all). An executor that follows only task deps would start table/code/image wiring before the hook exists.
- Fix: add P2-305 (or Milestone 2.3) to the deps of P2-406, P2-506, P2-606 and update the §6 wave table to make the hard ordering explicit.

### R-3 — Duplicated cross-milestone components (preprocessing, EXIF)
- **Preprocessing:** P2-104 creates `ocr/preprocess.py` while P2-503 creates `images/preprocess.py`, yet the spec itself says P2-503 "reuses the OCR preprocessor." Two modules for one function = unnecessary complexity (dimension 13) and two interface signatures (`preprocess_image(path)` vs `Preprocessor.process(path) -> Path`).
- **EXIF:** Milestone 2.2 P2-202 lists an "image/EXIF" metadata extractor **and** Milestone 2.5 P2-502 is an "EXIF/metadata extractor" — the same capability claimed by two milestones with no ownership boundary.
- Fix: one shared preprocess module (e.g., `infrastructure/document_intelligence/imaging/preprocess.py`), one owner for EXIF (recommend 2.5 owns `ImageInfo` detail; 2.2 owns only the `DocumentMetadata` fields derived from it), with the other milestone referencing it as a dependency.

### R-4 — Rollback mechanism references an undefined config value
- §10 Rollback cites `intelligence.ocr.engine="legacy"` ("pre-refactor `_ocr_extract` path kept behind a deprecation branch"), but §3.1's configuration block defines only `engine: "auto"`. The rollback is unverifiable as written.
- Fix: define `"legacy"` in the config reference (and have P2-107/P2-108 honor it), **or** drop the legacy-branch claim and rely on the feature flag + additive-schema rollback (simpler; recommended).

### R-5 — Python 3.14.6 (Windows) wheel risk missing from the risk table
- The runtime is **Python 3.14.6** (`site-packages\Python314`, verified). Milestones 2.1/2.2/2.4/2.5 add optional deps (Pillow, pytesseract, pdfplumber, camelot, py3langid, python-magic) that must resolve as `cp314-win_amd64` wheels. This can halt a milestone before any code runs.
- Fix: add a risk row (e.g., R-11: "Optional dep wheel availability on cp314-win_amd64 — verify at milestone start via `pip index`/`pip download`; fall back to pure-Python alternatives or vendor the pure-Python impls"). Also note `python-magic` needs libmagic on Windows (already mitigated via the fallback table, but the wheel check must include it).

### R-6 — OCRProcessor/HandwritingProcessor prompts never de-hardcoded
- The spec's 2.1 refactoring claims "remove hardcoded prompt strings into prompt/config constants," and P2-505 covers the **VisionProcessor** prompt — but `OCRProcessor` (`processor_impls.py:373-376`) and `HandwritingProcessor` (`processor_impls.py:406-410`) prompts are also hardcoded and are passed to the engine by the caller. No task de-hardcodes them.
- Fix: extend P2-505 (or add a small task in 2.1) to move all three processor prompts (vision, OCR, handwriting) into config/prompt constants, including the `{language}` slot.

### R-7 — Data-flow contract for extracted structures is undefined
- The spec does not state whether extracted structures/tables/code render into `document.text` (which feeds the **LLM analysis prompt and chunking/embeddings**) or attach only to `ProcessedDocument` and notes. If tables render into the analysis input, prompts grow unbounded — with no token counting until Phase 3 (G02 deferred). This is a pipeline-correctness contract, not a preference.
- Fix: state explicitly per milestone — default recommendation: extracted structures attach to `ProcessedDocument` and the **note template only**; the analysis prompt input remains raw/OCR text plus the existing metadata fields, with a config flag if a milestone author wants structure-aware prompting.

### R-8 — Silent tool deviation from MEDD (pdfplumber default for G35) must be recorded as an ADR
- MEDD G35 names **Camelot/Tabula** for PDF table detection. The spec defaults to **pdfplumber** with camelot optional. This is defensible (pure-Python, ADR-001's local-first bias) but it is a **deviation from the named tool in the source-of-truth document** and no ADR/amendment records it.
- Fix: add an ADR (e.g., ADR-002, following the MEDD's existing ADR-001 pattern) recording the decision, context (camelot pulls heavy transitive deps; pdfplumber pure-Python), and consequence; or amend the MEDD G35 row. The spec should cross-reference it.

---

## Recommended findings

### C-1 — Plugin architecture is inconsistent across milestones
OCR (`DocumentOcrService`), metadata (`register_extractor`), and tables (`TableExtractor` registry) are registered plugins; **image** (`ImageAnalyzer`/`Preprocessor`/`DiagramParser` are singular services) and **code/notebook** (singular parsers) are not. This contradicts Phase Goal 4 ("every new capability is a registered plugin").
- Recommend a shared base (`base.py` already proposed): one `Extractor[T]` protocol + one `DocumentIntelligenceService` registry used by all six milestones, or an explicit note that image/code are fixed (non-pluggable) services with the registry reserved for genuinely extensible kinds.

### C-2 — Default-true `tables.enabled` / `code.enabled` changes note output out of the box
CSV/spreadsheet/notebook notes will render differently on first run. This is a real user-visible behavior change under a backward-compatibility banner.
- Recommend one of: (a) default both to `false` this phase and ratify enablement in Phase 3, giving the cleanest backward-compat story (2.4 AC5 already guarantees no-table inputs are unchanged); or (b) keep default true but record it as a reviewed, changelogged behavior change in the completion report (Phase 1 precedent: the latency-metric change).

### C-3 — Optional-dependency absence behavior should be a per-task DoD clause
P2-105 specifies the absent-dep path (clear `ImportError`), but P2-104 (preprocessing), P2-405 (pdfplumber/camelot), P2-502 (Pillow EXIF), P2-503 do not. Add to each optional-dep task's DoD: "with the dependency absent, the task degrades to <X> with a logged warning" so no executor invents the fallback.

### C-4 — Commit real fixtures + golden outputs
§8.2 lists a fixtures dir; add a requirement to **commit the fixtures** (scanned PDF >5 pages, ruled-table PDF, EXIF JPEG, `.drawio`, `.ipynb`) and add a **golden-file test** for CSV→Markdown note rendering in 2.4 so renderer escaping regressions are caught exactly.

### C-5 — Sharpen two qualitative acceptance criteria
- 2.1 AC5 "byte-identical in behavior to Phase 1" is unverifiable; replace with: "default config selects the same engine and page limit, and the full existing `test_processors.py` OCR suite passes unchanged."
- 2.5 AC3 "valid Mermaid skeleton" needs a validity check (e.g., output passes a Mermaid syntax guard or a fixed regex/fixture comparison).

---

## Optional findings

### O-1 — Extend `pam doctor` to a full intelligence health check
P2-108 mentions a doctor hint for OCR engines only. Consider one task adding: OCR engine availability (vision model, Tesseract binary), language-detection lib, optional deps presence — mirroring the Phase 1 §7.1 "embedding model check" recommendation.

### O-2 — Milestone 2.1 is at the size limit; P2-107 is the single highest-risk task
2.1 has 8 tasks / 4–5 days. If it grows during implementation, split P2-107 (processor integration) into per-processor sub-tasks (OCRProcessor, HandwritingProcessor, VisionProcessor) to bound blast radius.

### O-3 — Property/round-trip fuzz loops for pure parsers
No test framework added (Phase 1 convention). Small self-contained loops suffice: structure offsets round-trip, table renderer escaping (inject `|`, newlines), language heuristic on mixed scripts, notebook JSON with schema drift.

### O-4 — Structure milestone artifact is unused this phase
`DocumentStructure` is built and stored but nothing consumes it until Phase 3. The milestone is mandated, so keep it — but consider a minimal this-phase consumer (e.g., populate the note TOC from structure) to avoid carrying speculative weight; otherwise state the "validates the enrichment hook" justification explicitly (it's implied, not stated).

### O-5 — Documentation targets: add MEDD Appendix B and plugin-authoring guide
The documentation updates list changelog, MEDD §7.2, and the 01 report — but MEDD **Appendix B (Configuration Reference)** must also gain the `intelligence` block. Separately, an `EXTENSIONS.md` (how to add a new extractor/engine/ingestor) directly serves the "easy to extend with future document types" principle.

---

## Remediation checklist (before Phase 2 execution)

1. **R-1:** Add email-attachment parsing task (or record an approved MEDD-amended deferral).
2. **R-2:** Add P2-305/Milestone 2.3 to deps of P2-406, P2-506, P2-606; align §6.
3. **R-3:** Consolidate to one preprocess module; assign a single EXIF owner.
4. **R-4:** Define `legacy` in config or remove the legacy-branch rollback claim.
5. **R-5:** Add the Python 3.14 Windows wheel risk + milestone-start validation.
6. **R-6:** Extend prompt-config scope to OCRProcessor/HandwritingProcessor.
7. **R-7:** State the structures→prompt/chunk data-flow contract explicitly.
8. **R-8:** Record ADR-002 for the pdfplumber default (or amend MEDD G35).
9. **C-1…C-5, O-1…O-5:** Adopt as approved where they reduce risk; none block execution.

After items R-1…R-8, the specification is ready to approve and execute.

---

*End of Phase 2 Specification Review.*
