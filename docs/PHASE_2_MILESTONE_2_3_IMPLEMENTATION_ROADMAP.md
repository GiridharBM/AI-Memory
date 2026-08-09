# Milestone 2.3 — Document Structure Analysis: Implementation Roadmap

**Source of truth:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` (v1.0, FROZEN — the implementation contract).
**Upstream chain:** MEDD → `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` v1.1 (FROZEN) → `docs/PHASE_2_ENGINEERING_BASELINE.md` (addenda §10, item 3) → Milestone 2.3 Engineering Spec.
**Baseline (verified live 2026-08-01):** M2.2 approved; 605 unit + 14 integration tests passing; coverage ≥ 80%; `ProcessedDocument` is a mutable `@dataclass(slots=True)` at `app/domain/processed_document.py:10-11`; `app/domain/document_intelligence.py` exists (holds `MetadataExtraction`); `tests/fixtures/` exists (empty, `.gitkeep` only).
**Status:** Implementation plan. No code is implemented by this document.

---

## 1. Task Summary

| ID | Title | Priority | Deps | Complexity | Est. | Risk |
|----|-------|----------|------|------------|------|------|
| P2-301 | Structure domain models | P0 | — | Low | 0.5 d | L |
| P2-302 | Heading hierarchy detector | P0 | P2-301 | Medium | 1 d | M |
| P2-303 | Block detector (paragraph/list/fence/blockquote/table) | P0 | P2-301 | Medium | 1 d | M |
| P2-304 | Structure tree builder | P0 | P2-302, P2-303 | Low | 0.5 d | L |
| P2-305 | Enrichment into `ProcessedDocument` | P0 | P2-304 | Low | 0.5 d | M |
| P2-306 | Performance + cap guard | P1 | P2-305 | Low | 0.25 d | L |

**Total:** 6 tasks, ~3.75 d → milestone budget **4 dev-days** (rounded with buffer; reconciled against the frozen 3 d nominal target).

---

## 2. Implementation Order (binding)

| Wave | Tasks | Rationale |
|------|-------|-----------|
| 0 | Preflight (not a task): confirm M2.2 gate closed (completion report on file; 605 unit + 14 integration green; coverage ≥ 80%). No wheel check — zero new dependencies. |
| 1 | P2-301 | Models first; every other task consumes them. |
| 2 | P2-302 ‖ P2-303 | Heading and block detectors are independent once models exist. |
| 3 | P2-304 | Tree builder consumes both detectors. |
| 4 | P2-305 | Enrichment wiring — the milestone integration point. |
| 5 | P2-306 | Cap + timing ceiling on the completed analyzer. |

**Critical path:** P2-301 → P2-302 → P2-304 → P2-305 (and P2-301 → P2-303 → P2-304).
**Parallel:** P2-302 ‖ P2-303 (wave 2).
**Cross-milestone gate (R-2, hard):** P2-305 must land **before** any M2.4/M2.5/M2.6 wiring task (P2-406, P2-506, P2-606) — it establishes the shared enrichment call site they all reuse.

---

## 3. Key Implementation Decisions (resolved in the frozen spec)

| # | Decision | Detail |
|---|----------|--------|
| D1 | **Analyzer input text** | `result.extracted_text or document.text` — the **exact text later chunked** at `ingest_workflow.py:514-516` (`self._chunker.chunk(document.text, ...)` on the enriched document). Guarantees offset fidelity (offsets-drift mitigation). |
| D2 | **Enrichment hook location** | Inside `_run_routed_processor` (`ingest_workflow.py:421-477`), after `result = processor.process(document)` succeeds and after the `result.language`/`result.parent_id` assignments (lines 457-462), before the return at line 477. One call site covers every processor; reused by M2.4/2.5/2.6 (R-2). `result` is a `ProcessedDocument` (mutable slots dataclass) → assign `result.structure = ...` directly. |
| D3 | **Text-bearing kinds** | Default `TEXT_BEARING_KINDS = frozenset({"markdown", "text"})` — a module constant in `detector.py`, **not** a config key (L5: no dead config). PDF/OCR-prose kinds are excluded this milestone (matches AC4 wording; extends later when consumers exist). |
| D4 | **Section ID scheme** | Path-style by traversal order: top-level sections `s-1`, `s-2`, …; nested sections `s-1-1`, `s-1-2`, …. Depth in the path = tree depth (level-skip: `# A` then `### C` ⇒ `C.parent_id = A.id`, C's path element count is 2). Stable across runs on identical text. |
| D5 | **Block ID scheme** | `f"b-{section.id}-{n}"` with `n` = 1-based index within the section. Example: block 1 of section `s-1-1` ⇒ `b-s-1-1-1`. |
| D6 | **Caps (code constants, `ponytail:` fixed defaults)** | `MAX_HEADING_LEVEL = 6` (ATX); `MAX_SECTIONS = 10_000` (exceeded → warn + truncate, never raise); `max_structure_text_bytes = 5_000_000` (analyzer skipped with one warning above this). |
| D7 | **Config plumbing** | `StructureSettings(enabled=True, enrich_analysis_input=False)` added to `IntelligenceSettings` (`config.py:285`); `intelligence.structure:` block added to `config/default.yaml`; `enabled` consumed through `from_runtime` → `IngestionWorkflow` → `_run_routed_processor` (M2.2 L1/L2 pattern). `enrich_analysis_input` is **contract-only** (baseline addendum 3 / R-7) — declared but not read by any code this milestone. |
| D8 | **Fault containment (L4)** | The analyzer call is wrapped in `try/except`; a raised analyzer is logged and `structure=None`, ingestion continues. Never raises. |
| D9 | **Heading rule** | `^#{1,6}\s+\S` at line start, after fence state. Divergence from `SemanticChunker._HEADING_PATTERN` (`^#{1,6}\s+.+`, no fence awareness) is intentional and permanent this phase: the chunker stays unchanged (AC5); the detector must be fence-correct (AC2). |

---

## 4. Per-Task Plan

---

### P2-301 — Structure domain models

| Field | Detail |
|-------|--------|
| **Task ID** | P2-301 |
| **Objective** | Define `DocumentStructure` / `DocumentSection` / `DocumentBlock` in `app/domain/document_intelligence.py` with IDs, levels, parent IDs, and char offsets; add the additive `structure: DocumentStructure \| None = None` field to `ProcessedDocument`; expose composition-root stubs. |
| **Dependencies** | None (milestone foundation). |
| **Estimated complexity** | Low. |
| **Files expected to change** | `app/domain/document_intelligence.py` (new models, next to existing `MetadataExtraction`); `app/domain/processed_document.py` (additive field, default `None`); `app/infrastructure/document_intelligence/__init__.py` (expose `analyze_document_structure` + `get_default_structure_analyzer` stubs). |
| **Tests required** | Model round-trip (construct → dump → reconstruct via pydantic); ID scheme unit tests per D4/D5; `ProcessedDocument.structure` defaults `None`; existing `ProcessedDocument` constructor call sites unaffected (additive-field regression). |
| **Acceptance Criteria** | `DocumentStructure.sections` is `list[DocumentSection]`; `DocumentSection` carries `id`, `title`, `level`, `parent_id`, `start_char`, `end_char`, `blocks`; `DocumentBlock` carries `block_id`, `type` (`paragraph`/`list`/`code`/`blockquote`/`table`), `text`, `start_char`, `end_char`; `ProcessedDocument` gains `structure: DocumentStructure | None = None`. |
| **Definition of Done** | Models reviewed, unit-tested, not wired into ingestion; placement matches M2.2 precedent (`MetadataExtraction` at `document_intelligence.py:10`). |

---

### P2-302 — Heading hierarchy detector

| Field | Detail |
|-------|--------|
| **Task ID** | P2-302 |
| **Objective** | Detect nested ATX headings from a line scan of the source text; build the heading list with levels and line positions; track fence state so `#` inside fenced code blocks is never treated as a heading; normalize heading level > 6 to 6. |
| **Dependencies** | P2-301. |
| **Estimated complexity** | Medium. |
| **Files expected to change** | `app/infrastructure/document_intelligence/structure/detector.py` (new — `_detect_headings(lines)`). |
| **Tests required** | Heading hierarchy (nested `#` → `##` → `###` ⇒ correct parent chain); level-skip (`# A` then `### C` ⇒ C attaches to A, per D4); fence disambiguation (fenced block containing `# not a heading`); depth cap (level > 6 → 6); empty/whitespace-only input → no headings; heading requires content (`^#{1,6}\s+\S`, D9). |
| **Acceptance Criteria** | Nested ATX headings produce the correct parent/child hierarchy (AC1); code fences and fenced `#` lines are not mis-split as headings (AC2). |
| **Definition of Done** | Hierarchy tests green; fence-state machine proven; heading rule matches D9. |

---

### P2-303 — Block detector

| Field | Detail |
|-------|--------|
| **Task ID** | P2-303 |
| **Objective** | Detect blocks — paragraph, list, code fence, blockquote, Markdown table — over the text ranges belonging to each heading section; every block carries an accurate `start_char`/`end_char` into the exact input text. |
| **Dependencies** | P2-301. |
| **Estimated complexity** | Medium. |
| **Files expected to change** | `app/infrastructure/document_intelligence/structure/detector.py` (new — `_detect_blocks(text, ranges)`). |
| **Tests required** | Block-type detection for each of the five types; offset-accuracy on a committed fixture (`tests/fixtures/structure/blocks.md`) asserting exact `start_char`/`end_char`; list nesting (indented sub-lists); blockquote continuation; pipe-table detection **after** `clean_text` normalization (M2.2 normalized tables); fenced code blocks span multiple lines as one block; paragraph splitting on blank lines. |
| **Acceptance Criteria** | Blocks (paragraph/list/fence/blockquote/table) are detected with accurate `start_char`/`end_char` (AC3). |
| **Definition of Done** | Block-type tests green; offset accuracy verified against the committed fixture. |

---

### P2-304 — Structure tree builder

| Field | Detail |
|-------|--------|
| **Task ID** | P2-304 |
| **Objective** | Combine the heading hierarchy (P2-302) and blocks (P2-303) into a nested `DocumentStructure`: sections contain their blocks, offsets are contiguous and non-overlapping, section IDs are stable path IDs (D4), degenerate/empty input yields an empty structure, and the `MAX_SECTIONS` cap truncates with a warning (never raises). |
| **Dependencies** | P2-302, P2-303. |
| **Estimated complexity** | Low. |
| **Files expected to change** | `app/infrastructure/document_intelligence/structure/detector.py` (new — `_build_tree(sections)` + `analyze(text, source)` public entry). |
| **Tests required** | Sections contain the correct blocks; offsets contiguous across the section's block range; empty text → empty `DocumentStructure`; invalid/malformed markup → best-effort tree, no exception; `MAX_SECTIONS` truncation path; ID stability (same input twice → identical IDs). |
| **Acceptance Criteria** | Sections contain blocks; offsets contiguous; degenerate input → empty tree; stable section IDs (R8). |
| **Definition of Done** | Builder tests green; tree output verified against sample documents; `analyze(text, source)` never raises. |

---

### P2-305 — Enrichment into `ProcessedDocument`

| Field | Detail |
|-------|--------|
| **Task ID** | P2-305 |
| **Objective** | Wire `StructureAnalyzer` into `_run_routed_processor` (D2): after a processor succeeds, when `intelligence.structure.enabled` is true and the result's kind is in `TEXT_BEARING_KINDS` (D3), analyze `result.extracted_text or document.text` (D1) and assign `result.structure`; define `StructureSettings` and plumb `enabled` through the full production chain (L1/L2); contain analyzer failures (L4). |
| **Dependencies** | P2-304. |
| **Estimated complexity** | Low. |
| **Files expected to change** | `app/pipelines/ingest_workflow.py` (enrichment hook inside `_run_routed_processor`, lines 457-477; `StructureAnalyzer` injected via `__init__`/`from_runtime`/`create_default`); `app/core/config.py` (`StructureSettings` added to `IntelligenceSettings`, line 285); `config/default.yaml` (`intelligence.structure:` block); `app/domain/processed_document.py` only if the field was not added in P2-301. |
| **Tests required** | **Wiring test (both config paths):** `enabled: true` + text-bearing kind → analyzer invoked and `structure` populated; `enabled: false` → skipped, `structure` stays `None` (behavior-level, mirroring the P2-203 `mime_enabled` remediation); kind not in `TEXT_BEARING_KINDS` → skipped; analyzer raising → logged + `structure=None`, ingestion continues (L4); CLI path (`entry.py:372`) and queue worker path (`worker.py:84`) both reach the hook (L2). |
| **Acceptance Criteria** | `ProcessedDocument.structure` is populated for markdown/text kinds when `enabled: true` (AC4); `enabled: false` returns M2.2-identical documents (R-4). |
| **Definition of Done** | Wiring test green for both config paths and both entry points; shared call site ready for M2.4/M2.5/M2.6 (R-2); `enrich_analysis_input` left unconsumed (D7). |

---

### P2-306 — Performance + cap guard

| Field | Detail |
|-------|--------|
| **Task ID** | P2-306 |
| **Objective** | Enforce the size cap and timing ceiling on the completed analyzer: skip analysis for input text > 5 MB with a single warning; assert O(n) single-linear-scan behavior within the frozen ceiling (≤ 1 s per 1 MB). No new config keys (cap is a code constant, D6). |
| **Dependencies** | P2-305. |
| **Estimated complexity** | Low. |
| **Files expected to change** | `app/infrastructure/document_intelligence/structure/detector.py` (`max_structure_text_bytes` early-exit guard in `analyze`). Note: the frozen task row also lists `core/config.py`; resolved to P2-305 (settings live there — see D7), so this task changes only `detector.py`. |
| **Tests required** | Oversize test: generated > 5 MB text (in-test, `tests/fixtures/` not required) → analyzer returns empty structure + single warning, no scan; timing test: 1 MB fixture → `time.perf_counter` assertion ≤ 1 s (generous ceiling, per Baseline §8.4). |
| **Acceptance Criteria** | Skip > 5 MB text; O(n) timing test passes (frozen §3 performance). |
| **Definition of Done** | Cap + timing tests green; guard never raises (D8). |

---

## 5. Tests Required (milestone-level map)

| Layer | Files | Covers |
|-------|-------|--------|
| Unit | `tests/unit/test_structure_analysis.py` (new) | P2-301 models + IDs; P2-302 hierarchy/fence/depth; P2-303 block types + offsets; P2-304 tree/caps/IDs; P2-306 cap + timing |
| Integration | `tests/integration/test_structure_pipeline.py` (new, `@pytest.mark.integration`, opt-in `-m integration`) | Markdown + text files through `IngestionWorkflow` ⇒ non-empty `document.structure`, stable section IDs across repeated runs; `enabled: false` ⇒ `structure is None`; CLI and worker paths both populate structure |
| Regression | existing suites unchanged | `test_knowledge_engine.py` (overlap suite), `test_text_preprocessing.py` — chunker byte-identical (AC5); M2.2 ingestion/metadata/workflow suites; note generation byte-identical (template does not consume `structure` yet) |
| Performance | within unit suite | ≤ 1 s / 1 MB; 5 MB skip |

**Fixtures (committed to `tests/fixtures/structure/`):** `nested_headings.md`, `fenced_code.md`, `lists_and_quotes.md`, `blocks.md`, `table_block.md`, `empty.md`. Oversize text is generated in-test (not committed).

---

## 6. Cross-Milestone Dependencies

- **Feeds forward (R-2):** the P2-305 enrichment hook is the shared attachment point M2.4 (P2-406), M2.5 (P2-506), and M2.6 (P2-606) each depend on. M2.3 must not be considered "done for consumers" until P2-305's wiring test proves both config paths and both entry points.
- **Feeds forward (contract):** `DocumentStructure` is the documented input contract for Phase 3 hierarchical chunking (MEDD G14 / §7.3 target architecture) and Phase 4 parent-child retrieval. No Phase-3/4 code ships this milestone (R10 guard).
- **Receives:** nothing new — consumes only M2.2 state (`_run_routed_processor`, settings plumbing, `ProcessedDocument`, `document_intelligence.py` models).

---

## 7. Milestone Gate Checklist (from frozen spec §12)

- [ ] P2-301 models reviewed; `ProcessedDocument.structure` additive with `None` default.
- [ ] P2-302 nested ATX → correct tree (AC1); fenced `#` not mis-split (AC2).
- [ ] P2-303 five block types with accurate offsets (AC3).
- [ ] P2-304 sections contain blocks; offsets contiguous; empty input → empty tree; `MAX_SECTIONS` cap.
- [ ] P2-305 `structure.enabled` consumed via full production chain; both config paths + both entry points tested; `enabled: false` → M2.2-identical (AC4).
- [ ] P2-306 > 5 MB skip; O(n) timing ceiling.
- [ ] Chunker regression (AC5) + note-generation byte-identical regression green.
- [ ] All 605 unit + 14 integration tests pass; coverage ≥ 80% (parser suite ≥ 90%); `ruff`/`mypy` zero new errors.
- [ ] Per-task atomic commits; rollback via `intelligence.structure.enabled: false` verified.
- [ ] Documentation: `changelog.md` + MEDD §7.3 input contract + 01 report updated.
- [ ] Milestone 2.3 completion report produced before Milestone 2.4 begins.

---

*End of Milestone 2.3 Implementation Roadmap.*
