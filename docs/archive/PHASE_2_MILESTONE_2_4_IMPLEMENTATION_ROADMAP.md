# Milestone 2.4 — Table Intelligence: Implementation Roadmap

**Source of truth:** `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` v1.1 (FROZEN — the implementation contract), §4.4 (task table), §2.4 (milestone narrative), §6 (pre-flight + blocking notes), §7.1 (file impact), §9 (parallel wave 4), §11 (config), §12.4 (docs gate).
**Upstream chain:** MEDD G35/G36 → `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` v1.1 → `docs/PHASE_2_ENGINEERING_BASELINE.md` (C-3 optional-dep DoD clause, C-4 golden-file tests) → Milestone 2.4 roadmap. **ADR-002** records the Camelot→pdfplumber engine deviation (MEDD G35 consequence).
**Baseline (verified live 2026-08-02):** M2.3 approved (completion + sync reports on file); **747 unit + 9 structure integration tests passing; coverage 88.43%**. `TableProcessor` is a pure passthrough (`app/infrastructure/routing/processor_impls.py:228-236`), registered for `{"csv","spreadsheet"}` (`processors.py:35`). The classifier sets `requires_table_extraction = kind in {"csv","spreadsheet","database"}` (`classifier.py:94,106`) — **consumed nowhere**. `ProcessedDocument` has **no** `tables` field; `ObsidianMarkdownGenerator.generate` has no tables parameter. Deps: **openpyxl installed** (core dependency, used `read_only=True` in `spreadsheet_ingestor.py:44`); **pdfplumber NOT installed**; **camelot NOT installed**. No `intelligence.tables` config block exists yet. No `test_table_intelligence.py` / `test_table_pipeline.py` exist.
**Status:** Implementation plan. No code is implemented by this document.

---

## 1. Task Summary

| ID | Title | Priority | Deps | Complexity | Est. | Risk |
|----|-------|----------|------|------------|------|------|
| P2-401 | Table domain models | P0 | — | Low | 0.25 d | L |
| P2-402 | `TableExtractor` interface + registry | P0 | P2-401 | Low | 0.25 d | L |
| P2-403 | CSV/TSV extractor + header sniffing | P0 | P2-402 | Low | 0.5 d | M |
| P2-404 | Spreadsheet extractor (multi-sheet, merged cells) | P0 | P2-402 | Medium | 1 d | M |
| P2-405 | PDF table extractor (pdfplumber default, camelot optional) | P1 | P2-402 | High | 1.5 d | H |
| P2-406 | Markdown renderer + wiring (flag + note rendering) | P0 | P2-305, P2-403–405 | Medium | 1 d | M |

**Total:** 6 tasks, **4.5 d** (frozen §4.4 sum) → milestone budget **5 dev-days** (rounded with buffer).

---

## 2. Implementation Order (binding)

| Wave | Tasks | Rationale |
|------|-------|-----------|
| 0 | Preflight (not a task): confirm M2.3 gate closed (completion report on file; 747 unit + 9 structure integration green; coverage 88.43%). **Wheel check (R11):** `pip download --only-binary :all: pdfplumber` must succeed on `cp314-win_amd64`; camelot checked as optional only. Record result before P2-405. |
| 1 | P2-401 | Models first; the registry and every extractor consume them. |
| 2 | P2-402 | Interface + registry — all three extractors depend on it. |
| 3 | P2-403 ‖ P2-404 ‖ P2-405 | CSV/TSV, spreadsheet, and PDF extractors are independent once the registry exists. |
| 4 | P2-406 | Renderer + wiring — the milestone integration point; must wait for all extractors AND the P2-305 enrichment hook (landed in M2.3). |

**Critical path:** P2-401 → P2-402 → P2-405 → P2-406 (PDF is the longest, highest-risk task).
**Parallel:** P2-403 ‖ P2-404 ‖ P2-405 (wave 3).
**Cross-milestone (frozen §9, wave 4):** M2.4 runs **parallel with M2.6**; P2-406 wiring must not start before P2-305 (already landed — R-2 satisfied).

---

## 3. Key Implementation Decisions (resolved in the frozen spec + live-code verification)

| # | Decision | Detail |
|---|----------|--------|
| D1 | **Enrichment gate (flag + PDF)** | Add `requires_table: bool = False` to `_run_routed_processor` (`ingest_workflow.py:435`); caller `_process_document` passes `classification.requires_table_extraction` (line 286). The new `_enrich_tables` gate = `tables.enabled AND (requires_table OR source_type == "pdf")`. The flag is thereby **consumed** (P2-406 AC / §2.4 AC4) while the PDF path (not covered by the classifier flag set) still triggers. |
| D2 | **Where tables attach (R-1 precedent)** | Follow the M2.3 R-1 deviation: tables ride **`metadata.extra["tables"]`** on the enriched `SourceDocument`, **not** a `ProcessedDocument.tables` field. The note generator only receives `SourceDocument` (`obsidian_note.py:24`), so it must read `document.metadata.extra` — same channel as `structure`. Deviation from §7.1's additive-field list is documented in the completion report (mirrors M2.3's `structure`). |
| D3 | **Renderer** | New `tables/render.py` with `MarkdownTableRenderer` (public API per §2.4). Escapes `\|` and newlines per P2-406 AC; renders `Table` → Markdown pipe table. Golden-file test (C-4): committed CSV fixture + expected note output. |
| D4 | **Config plumbing** | `TableSettings` added to `IntelligenceSettings` (`config.py:300`), with `extra="forbid"`; `intelligence.tables:` block in `config/default.yaml` with frozen §2.4 defaults: `enabled: true`, `pdf_engine: "pdfplumber"`, `max_rows: 200`, `max_cols: 30`, `header_sniffing: true`, `min_confidence: 0.5`. Enabled default is a **reviewed, changelogged user-visible behavior change** (C-2). |
| D5 | **Extractor registry** | `tables/extractor.py`: `TableExtractor` interface + registry keyed by source type/kind; public `extract_tables(document)`. **Empty registry → empty list, never raises** (P2-402 AC). Note: `database` kind sets the flag but has **no extractor this milestone** → registry miss → no tables, flat text preserved. |
| D6 | **Fault containment (L4)** | Follow the M2.3 structure pattern (`_enrich_structure`, `ingest_workflow.py:518-549`): extractor failures caught → `logger.warning(...exc_info=True)` → no `tables` key → ingestion continues. Never raises. |
| D7 | **Optional-dependency degraded path (C-3)** | P2-405 DoD: **with pdfplumber absent → flat fallback + logged warning** (current Phase-1 behavior). pdfplumber added to `[project.optional-dependencies] intelligence` in `pyproject.toml`; camelot stays an optional plugin behind the same interface (ADR-002). |
| D8 | **Spreadsheet extraction** | Reuse the existing `openpyxl.read_only=True` pattern (`spreadsheet_ingestor.py:44`); per-sheet tables; merged cells flattened by propagating the top-left value (P2-404 AC). |
| D9 | **Performance caps** | `max_rows`/`max_cols` from config truncate with warning; PDF page cap **reuses the OCR page budget** (`intelligence.ocr.max_pages` default 200, frozen §2.4 perf note). Row/col caps are config keys (frozen §2.4), not code constants. |

---

## 4. Per-Task Plan

### P2-401 — Table domain models

| Field | Detail |
|-------|--------|
| **Task ID** | P2-401 |
| **Objective** | Define `Table`, `TableCell`, `TableRow`, `TableHeader` in `app/domain/document_intelligence.py` (next to the M2.3 models). |
| **Dependencies** | None (milestone foundation). |
| **Estimated complexity** | Low. |
| **Files expected to change** | `app/domain/document_intelligence.py` (new models, pydantic `BaseModel`, `extra="forbid"` like `DocumentBlock`). |
| **Tests required** | Model round-trip (construct → dump → reconstruct); per-field validation (max_rows/max_cols caps; header/cell typing); `Table` defaults. |
| **Acceptance Criteria** | `Table`, `TableCell`, `TableRow`, `TableHeader` exist (frozen §4.4). |
| **Definition of Done** | Model tests green; no ingestion wiring. |

---

### P2-402 — `TableExtractor` interface + registry

| Field | Detail |
|-------|--------|
| **Task ID** | P2-402 |
| **Objective** | Define the `TableExtractor` interface and a registry keyed by source kind; `extract_tables(document)` public entry (frozen §2.4 public API). Empty registry → empty result. |
| **Dependencies** | P2-401. |
| **Estimated complexity** | Low. |
| **Files expected to change** | `app/infrastructure/document_intelligence/tables/extractor.py` (new — interface, registry, `extract_tables`); `app/infrastructure/document_intelligence/__init__.py` (expose `extract_tables` + `get_default_table_extractor`, mirroring the structure package pattern). |
| **Tests required** | Register/select per source kind; unknown kind → empty result; **empty registry handled** (P2-402 AC) — no extractor for `database` must yield no tables, no exception. |
| **Acceptance Criteria** | Register/select per source kind; empty registry handled (frozen §4.4). |
| **Definition of Done** | Interface test green; public entry exported; no concrete extractors yet. |

---

### P2-403 — CSV/TSV extractor + header sniffing

| Field | Detail |
|-------|--------|
| **Task ID** | P2-403 |
| **Objective** | CSV/TSV extractor: parse delimiters (stdlib `csv`), sniff header row (frozen §2.4 `header_sniffing: true`), type-hint cells. |
| **Dependencies** | P2-402. |
| **Estimated complexity** | Low. |
| **Files expected to change** | `app/infrastructure/document_intelligence/tables/extractor.py` (CSV extractor + registry registration for `csv`). |
| **Tests required** | CSV tests incl. **quoted/escaped fields**, comma and TSV (`\t`) delimiters, header-row sniffing on/off, cell type hints, `max_rows`/`max_cols` truncation, no-data input → empty table. |
| **Acceptance Criteria** | Parses delimiters, sniffs header row, type-hints cells (frozen §4.4). |
| **Definition of Done** | CSV tests incl. quoted/escaped green. |

---

### P2-404 — Spreadsheet extractor (multi-sheet, merged cells)

| Field | Detail |
|-------|--------|
| **Task ID** | P2-404 |
| **Objective** | Spreadsheet extractor: per-sheet tables; merged cells flattened (top-left value propagated); `openpyxl.read_only=True` (D8); row cap. |
| **Dependencies** | P2-402. |
| **Estimated complexity** | Medium. |
| **Files expected to change** | `app/infrastructure/document_intelligence/tables/extractor.py` (spreadsheet extractor + registry registration for `spreadsheet`); `app/infrastructure/ingestion/spreadsheet_ingestor.py` (structured, non-flat extraction when enabled — frozen §7.1). |
| **Tests required** | `xlsx` fixture tests: multi-sheet → per-sheet tables; merged-cell range → value propagated; `read_only=True` path; empty sheet; row-cap truncation; corrupt file → contained failure (D6). |
| **Acceptance Criteria** | Per-sheet tables; merged cells flattened (value propagated); `read_only=True` (frozen §4.4). |
| **Definition of Done** | xlsx fixture tests green; ingestor regression unchanged for `enabled: false`. |

---

### P2-405 — PDF table extractor (pdfplumber default, camelot optional)

| Field | Detail |
|-------|--------|
| **Task ID** | P2-405 |
| **Objective** | Ruled-table PDF → Markdown table via **pdfplumber** (default engine, ADR-002); camelot remains an optional plugin behind the same interface. Engine missing → flat fallback + logged warning (C-3). PDF page cap reuses OCR budget (D9). |
| **Dependencies** | P2-402. |
| **Estimated complexity** | High. |
| **Files expected to change** | `app/infrastructure/document_intelligence/tables/extractor.py` (pdfplumber extractor + registry registration for `pdf`); `pyproject.toml` (`pdfplumber` added to `[project.optional-dependencies] intelligence`; camelot noted as optional plugin). |
| **Tests required** | PDF fixture test (integration-gated, `@pytest.mark.integration` — engine-dependent); **absent-engine DoD test**: pdfplumber import blocked → flat fallback + warning, no exception; ruled-table fixture → Markdown table; borderless/complex layout → confidence below `min_confidence` → no table. |
| **Acceptance Criteria** | Ruled-table PDF → Markdown table; engine missing → flat fallback + warning (frozen §4.4). |
| **Definition of Done** | **Optional-dependency DoD clause (C-3):** "with pdfplumber absent, the task degrades to flat text fallback with a logged warning." Integration test green on engine-present runs; degraded path proven in CI runs. |

---

### P2-406 — Markdown renderer + wiring (flag + note rendering)

| Field | Detail |
|-------|--------|
| **Task ID** | P2-406 |
| **Objective** | Wire the whole milestone: `_enrich_tables` in `_run_routed_processor` (D1) writes `metadata.extra["tables"]` (D2); `MarkdownTableRenderer` (D3) renders tables into the note body; `\|`/newline escaping; no-table inputs unchanged (AC5). |
| **Dependencies** | P2-305 (landed M2.3 — R-2 satisfied), P2-403–405. |
| **Estimated complexity** | Medium. |
| **Files expected to change** | `app/infrastructure/document_intelligence/tables/render.py` (new — `MarkdownTableRenderer`); `app/pipelines/ingest_workflow.py` (`_enrich_tables` beside `_enrich_structure` at line 518; `requires_table` param on `_run_routed_processor` line 435; caller line 286 passes the classification flag); `app/templates/obsidian_note.py` (optional Markdown-table section in note body, reads `document.metadata.extra.get("tables")`); `app/infrastructure/routing/processor_impls.py` (optional — TableProcessor stays passthrough; extraction lives in enrichment, D1); `app/core/config.py` + `config/default.yaml` (D4). Note: `router.py`/`processors.py` listed in §7.1 — the flag already flows via `classification`, so **no router change is required**; if the spec list is read strictly, a documented no-op suffices. |
| **Tests required** | **Escaping tests**: `\|`, newlines in cells; **wiring tests**: `tables.enabled: true` + csv/spreadsheet → `extra["tables"]` populated; `enabled: false` → no key, Phase-1-identical note (R-4); flag reaches enrichment (both config paths + CLI `entry.py` and worker `worker.py` entry points, mirroring P2-305); **golden-file test (C-4)**: committed CSV fixture + expected Markdown note output; no-table inputs → byte-identical Phase-1 note; note generator regression suite unchanged. |
| **Acceptance Criteria** | `\|`/newline escaping; `requires_table_extraction` consumed; note shows tables; no-table inputs unchanged (frozen §4.4). |
| **Definition of Done** | Escaping + wiring + golden-file tests green; `tables.enabled: false` restores Phase-1 note output exactly (rollback R-4); changelog entry for the default-enabled user-visible change (C-2). |

---

## 5. Tests Required (milestone-level map)

| Layer | Files | Covers |
|-------|-------|--------|
| Unit | `tests/unit/test_table_intelligence.py` (new) | P2-401 models; P2-402 registry (incl. empty); P2-403 CSV/TSV parsing + header sniffing; P2-404 spreadsheet; P2-406 escaping + wiring config paths |
| Integration | `tests/integration/test_table_pipeline.py` (new, `@pytest.mark.integration`) | CSV/`.xlsx`/ruled-table PDF through `IngestionWorkflow` ⇒ `extra["tables"]` present + rendered note; `enabled: false` ⇒ Phase-1-identical; CLI and worker paths both enrich; PDF path engine-gated |
| Golden-file (C-4) | committed CSV fixture + expected note output | CSV→Markdown note rendering exactly (escaping regressions) |
| Regression | existing suites unchanged | note generation byte-identical when no tables; `test_knowledge_engine.py`, M2.2/2.3 ingestion + workflow suites |

**Fixtures (committed to `tests/fixtures/tables/`):** `sample.csv` (quoted/escaped fields), `sample.tsv`, `multi_sheet.xlsx` (merged-cell ranges), `ruled_table.pdf` (small, integration-gated), expected golden note output. Oversized/`max_rows`-exceeded data generated in-test.

---

## 6. Cross-Milestone Dependencies

- **Receives (hard, R-2):** the P2-305 enrichment hook inside `_run_routed_processor` (landed M2.3) — P2-406 reuses the exact call-site pattern (`_enrich_structure` → `_enrich_tables`). Satisfied; no 2.4 task can start before it (it is done).
- **Receives (contract):** `DocumentStructure`/`metadata.extra` precedent from M2.3 (R-1 deviation) — tables ride the same channel (D2).
- **Feeds forward (soft, §5):** notebook code cells reuse the language registry in 2.6 (P2-602) — not a hard block; M2.4 runs parallel with M2.6 (wave 4).
- **Runs parallel with:** M2.6 (frozen §9, wave 4). 2.5 consumes completed 2.1/2.2 outputs; independent of 2.4.

---

## 7. Milestone Gate Checklist (frozen spec §4.4 + §12.4 + ADR-002)

- [ ] P2-401 models reviewed (`Table`/`TableCell`/`TableRow`/`TableHeader`).
- [ ] P2-402 interface + registry; empty registry returns empty, never raises.
- [ ] P2-403 CSV/TSV parsing incl. quoted/escaped; header sniffing; type hints.
- [ ] P2-404 per-sheet tables; merged cells flattened; `read_only=True`.
- [ ] P2-405 ruled-table PDF → Markdown; **absent-engine DoD**: flat fallback + logged warning; wheel check (R11) recorded.
- [ ] P2-406 `requires_table_extraction` consumed (wiring test, both config paths + CLI/worker); `\|`/newline escaping; golden-file test; no-table inputs byte-identical (AC5); `tables.enabled: false` → Phase-1 output (R-4).
- [ ] `ProcessedDocument` untouched (R-1 deviation documented); tables ride `metadata.extra["tables"]`.
- [ ] Full suite green: 747 unit + 9 structure integration + new 2.4 tests; coverage ≥ 80%; `ruff`/`mypy` zero new errors.
- [ ] Per-task atomic commits; rollback via `intelligence.tables.enabled: false` verified.
- [ ] Documentation: `changelog.md` (default-enabled tables change — C-2); MEDD §7.3 input contract + G35/G36 amended/cross-referenced (ADR-002 consequence); `docs/01_Current_Implementation_Report.md` Tables status section; README if CLI/config changed.
- [ ] Milestone 2.4 completion report produced before Milestone 2.5 begins.

---

*End of Milestone 2.4 Implementation Roadmap.*
