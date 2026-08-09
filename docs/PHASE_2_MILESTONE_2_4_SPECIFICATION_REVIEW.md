# Milestone 2.4 — Table Intelligence: Specification Review

**Reviewer:** Principal Engineering Reviewer
**Date:** 2026-08-02
**Scope reviewed:** The M2.4 contract as frozen in `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` v1.1 — §2.4 narrative, §4.4 task table (P2-401…P2-406), §5 (dependency graph), §6 (pre-flight/blocking notes), §7.1 (file impact), §9 (parallel waves), §11 (config), §12.4 (docs gate), §13 ADR-002 — cross-checked against the draft `docs/PHASE_2_MILESTONE_2_4_IMPLEMENTATION_ROADMAP.md` and the **live codebase** (verified 2026-08-02). No code modified.

**Baseline facts verified live:**
- `requires_table_extraction` set by classifier at `classifier.py:94,106` for kinds `{"csv","spreadsheet","database"}` — **does not include `pdf`**.
- `TableProcessor` (`processor_impls.py:228-236`) is a passthrough; `supported_kinds = {"csv","spreadsheet"}` (`processors.py:35`); PDF routes to `PDFProcessor` (kind `pdf`).
- `ProcessedDocument` (`processed_document.py`) has **no** `tables` field; note generator receives `SourceDocument` and does **not** read `metadata.extra` today (`obsidian_note.py`).
- `openpyxl 3.1.5` installed but **declared nowhere in `pyproject.toml`** (not core deps lines 15-27, not `intelligence` extras lines 30-36). `pdfplumber`/`camelot` not installed, not declared.
- `IntelligenceSettings` has `extra="forbid"` (`config.py:303`); `default.yaml` has `intelligence.structure:` but **no** `intelligence.tables:` block.
- Verified empirically: **openpyxl `read_only=True` worksheets have no `merged_cells` attribute** (`AttributeError`); merged cells yield value only at the top-left cell, `None` elsewhere.

---

## Verdict

**NOT APPROVED — 4 required (R) findings, 7 recommended (C), 3 optional (O).** The architecture is sound and consistent with the M2.2/M2.3 patterns (plugin registry, enrichment hook, optional-dep degraded paths). The blockers are all resolvable spec-text amendments or explicit trigger/scope definitions; none require re-architecting. After R1–R4 are resolved in the spec (or documented as accepted deviations in the roadmap), the milestone may proceed.

---

## R — Required (blockers; must resolve before implementation)

### R1. P2-404 AC is internally contradictory: merged-cell flattening vs `read_only=True`

- **Location:** spec §4.4 P2-404 AC: *"Per-sheet tables; merged cells flattened (value propagated); read_only=True"*.
- **Problem:** Verified against openpyxl 3.1.5: a worksheet loaded with `read_only=True` raises `AttributeError: 'ReadOnlyWorksheet' object has no attribute 'merged_cells'`, and `iter_rows(values_only=True)` returns the value only at the top-left of a merged range (`None` for the rest). "Merged cells flattened (value propagated)" is **impossible to distinguish from genuinely empty cells** without the merged-range metadata, which read-only mode does not expose. The two halves of the AC cannot both be satisfied.
- **Remediation:** Amend P2-404 AC to drop the strict `read_only=True` requirement for the extractor, e.g. *"Per-sheet tables; merged cells flattened (value propagated) using `merged_cells.ranges`; workbook loaded normally (non-read-only) with `data_only=True`"* — acceptable because the ingestion size cap (`max_file_size_mb: 50`) and `max_rows: 200`/`max_cols: 30` caps bound memory. Alternatively state a documented heuristic limitation if read-only must be kept.

### R2. No specified trigger for PDF table extraction — the `requires_table_extraction` flag excludes `pdf`

- **Location:** spec §4.4 P2-405 (PDF extractor) + P2-406 AC *"`requires_table_extraction` consumed"* + §2.4 AC4 *"flag now reaches the enrichment stage"*; classifier flag set at `classifier.py:94`.
- **Problem:** The flag is set only for `{"csv","spreadsheet","database"}`. PDFs classify as kind `pdf` → `PDFProcessor`, flag **false**. The spec never states what gates the PDF extractor (P2-405). The roadmap's D1 invents the OR-gate `requires_table_extraction OR source_type == "pdf"` — a behavior the frozen spec does not authorize. An implementer following the spec literally has no defined trigger for the highest-risk task.
- **Remediation:** Amend §4.4 P2-406 AC/DoD to state the enrichment gate explicitly, e.g. *"enrichment runs when `tables.enabled` and (`requires_table_extraction` OR kind is `pdf`)"* — or extend the classifier flag set to include `pdf` (then existing `test_routing.py` assertions at lines 424/430/490 must be reviewed). Record whichever is chosen in the roadmap's decision table.

### R3. `spreadsheet_ingestor.py` "structured (non-flat) extraction when enabled" contradicts AC5 and the backward-compat guarantee

- **Location:** spec §7.1 line 462 (`spreadsheet_ingestor.py | 2.4 | Structured (non-flat) extraction when enabled`) vs §2.4 AC5 *"no-table inputs render exactly as Phase 1"* and §2.4 Backward Compatibility *"CSV/spreadsheet without detected tables keep current flat text"*.
- **Problem:** The ingestor runs at ingestion time, **before** classification and before any table detection. If it emits structured/non-flat text whenever `tables.enabled: true`, then spreadsheets **without** detectable tables also produce changed `document.text` → changed analysis input → changed notes, violating AC5 and the rollback guarantee (`enabled: false` restores Phase-1 output exactly). The two statements cannot both hold.
- **Remediation:** Resolve scope explicitly. Recommended: **do not change the ingestor's text output at all** — the ingestor keeps producing flat pipe-joined rows; table extraction runs only at the enrichment stage and attaches tables to `metadata.extra["tables"]` (matching the M2.3 R-1 `structure` channel). Amend §7.1 line 462 to read *"unchanged — flat text preserved; structured tables attach at enrichment stage (2.4)"*, or if the ingestor must change, delete AC5's Phase-1-identical claim for spreadsheets.

### R4. `openpyxl` is an undeclared dependency the milestone relies on

- **Location:** spec §2.4 Dependencies *"Existing: `openpyxl`"*; `pyproject.toml` (core deps 15-27, `intelligence` extras 30-36) — verified **no `openpyxl` declaration anywhere**; yet `spreadsheet_ingestor.py:42` imports it and P2-404/P2-406 depend on it.
- **Problem:** "Existing" is false in the packaging record. A clean install (including CI) fails on the spreadsheet path today, and the C-3 optional-dep DoD clause cannot be satisfied for openpyxl because there is no declared dependency to be "absent". P2-404 inherits a latent packaging bug.
- **Remediation:** Before P2-404 implementation, declare `openpyxl` in `pyproject.toml` — either in core `dependencies` (it is already a hard runtime import in `spreadsheet_ingestor.py`) or in the `intelligence` extras. Update the spec's Dependencies line accordingly.

---

## C — Recommended (should fix; not blocking)

### C1. `min_confidence: 0.5` config key has no consumer; `Table` model has no confidence field
- **Location:** spec §2.4 Config block (`min_confidence: 0.5`) vs Interfaces block (`class Table (title, header, rows, source_position)` — no confidence).
- **Problem:** The config key is dead unless the PDF extractor consumes it; the `Table` model as specified carries no confidence to compare against. Violates the project's no-dead-config principle (M2.3 D6).
- **Remediation:** Either (a) add an optional `confidence: float` to `Table` and a `min_confidence` gate in P2-405/406 DoD, or (b) state that `min_confidence` is consumed internally by the PDF extractor (tables below threshold are dropped before model construction) and document it. Pick one in the spec.

### C2. Naming inconsistency: `TableRenderer` vs `MarkdownTableRenderer`
- **Location:** spec §2.4 Interfaces (`class TableRenderer`) vs Public APIs (`MarkdownTableRenderer`) vs §4.4 P2-406 files (`tables/render.py`).
- **Remediation:** Standardize on `MarkdownTableRenderer` in both blocks.

### C3. P2-406 file list says `router.py` consumes the flag; roadmap says no router change
- **Location:** spec §4.4 P2-406 files (includes `router.py`) + §7.1 line 456 (*"`router.py`, `processors.py` | 2.4 | Consume `requires_table_extraction` (no new model keys required)"*) vs roadmap D1 (*"no router change required"*).
- **Remediation:** The flag reaches the enrichment stage via the `classification` object already available at `_process_document` (`ingest_workflow.py:273`); `router.py` needs no functional change. Amend §4.4/§7.1 to drop `router.py` from the file list, or note a documented no-op.

### C4. Parallel M2.4 ∥ M2.6 (wave 4) edits overlapping files concurrently
- **Location:** spec §9 line 439 (parallel wave 4) vs §4.4 P2-406 and §4.6 P2-606 — both list `ingest_workflow.py`, `processor_impls.py`, `core/config.py`.
- **Problem:** Two milestones editing the same enrichment region and config classes in parallel → high merge-conflict risk in the exact `_run_routed_processor`/`_enrich_*` area.
- **Remediation:** In the roadmap, sequence the shared-file edits (P2-406 and P2-606 landed in the same branch/commit or one immediately after the other), or split `_run_routed_processor` enrichment into per-feature helper methods explicitly to localize diffs.

### C5. `ProcessedDocument.tables` (spec §2.4 BC + §7.1 line 450) vs `metadata.extra["tables"]` (roadmap D2)
- **Location:** spec §2.4 Backward Compatibility *"`ProcessedDocument` gains optional `tables: list[Table]`"* + §7.1 line 450 vs roadmap D2 (tables ride `metadata.extra["tables"]`, no `ProcessedDocument` field).
- **Problem:** Same deviation the M2.3 roadmap made for `structure` (R-1) — the note generator receives `SourceDocument`, so a `ProcessedDocument.tables` field would be invisible to rendering. §7.1 line 450 is already stale post-M2.3 (lists `structure` as a `ProcessedDocument` field that was never added).
- **Remediation:** Record the deviation explicitly (R-1 precedent) in the roadmap and completion report; amend §7.1 line 450 to remove `tables` from the `ProcessedDocument` additive-field list or mark it *"via `metadata.extra` per R-1"*.

### C6. `enabled: true` default is a user-visible change requiring a recorded review sign-off
- **Location:** spec §2.4 Backward Compatibility *"Default `enabled: true` is a reviewed, changelogged user-visible behavior change"* (C-2 precedent).
- **Problem:** No sign-off record exists yet; this review is part of that gate but the spec text asserts it as already reviewed.
- **Remediation:** Keep the milestone gate: changelog entry + completion-report note (already in roadmap §7 gate checklist). Re-word the spec line to *"default `enabled: true` pending M2.4 review sign-off"* for accuracy.

### C7. Spec cites `classifier.py:88`; live line is 94/106
- **Location:** spec §2.4 line 205 *"set by the classifier (`classifier.py:88`)"*.
- **Problem:** Line drift (post-M2.2 edits). Trivial.
- **Remediation:** Update to `classifier.py:94` (computation) / `:106` (assignment), or drop the line number.

---

## O — Optional

### O1. Extending the classifier flag set to include `pdf` would require updating `test_routing.py` lines 424/430/490
Only relevant if R2's alternative remediation is chosen. The three existing assertions assert `requires_table_extraction is True` for csv/spreadsheet/database kinds; adding `pdf` to the set should also assert pdf ⇒ True.

### O2. `TableHeader` is listed in P2-401 AC but absent from the §2.4 Interfaces block
Clarify `header`'s type in `Table` (e.g. `header: TableHeader` or `header: list[str]`) so P2-401 and P2-406 agree.

### O3. `source_position` in the `Table` interface
The Interfaces block lists `source_position` but no task AC or DoD references it. Either add an AC (page/row provenance for PDF, sheet for spreadsheets) or drop it.

---

## Verified-clean areas (no action)

- **Dependency graph / ordering:** P2-401 → 402 → {403‖404‖405} → 406; P2-406 correctly depends on P2-305 (landed M2.3, R-2 satisfied). Critical path via P2-405 is correct. Effort 4.5 d ≈ "4–5 dev-days" claim.
- **Integration points:** enrichment hook inside `_run_routed_processor` (`ingest_workflow.py:435-517`, `_enrich_structure` at 518-549) is the correct shared call site; tables enrichment mirrors it. Both production entry points (`entry.py:372`, `queue/worker.py:84`) route through `create_default` — L2 wiring test requirement is reachable.
- **Fault containment:** optional-dep degraded paths (C-3) applied to P2-405 in the roadmap; extractor-failure containment follows the M2.2 L4 / structure precedent.
- **Rollback:** `intelligence.tables.enabled: false` restores Phase-1 output — consistent with R-4 and the `structure.enabled` pattern (`config.py:285-297`), provided R3's ingestor-scope question is resolved as recommended.
- **ADR-002** (pdfplumber default, camelot optional) is correctly cross-referenced and consistent with config `pdf_engine` and the P2-405 file list.
- **Golden-file (C-4)** and **wheel preflight (R11)** are correctly captured in roadmap P2-406 DoD and wave-0 preflight.
- **Config plumbing:** `IntelligenceSettings` `extra="forbid"` means `TableSettings` must land in `config.py` in the same commit as the `intelligence.tables` yaml block — roadmap D4 already pairs them.
- **Public APIs** (`extract_tables(document)`, `TableExtractor`, `MarkdownTableRenderer`, `Table`) are coherent with the P2-402/P2-406 task rows.

---

*End of Milestone 2.4 Specification Review. Stop point reached — no code modified.*
