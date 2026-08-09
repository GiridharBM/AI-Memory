# Milestone 2.4 — Specification Review Remediation Verification

**Date:** 2026-08-02
**Scope:** Verification that the M2.4 engineering specification (`docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` §2.4, §4.4, §6.3, §7.1, §14.5) resolves every **Required** finding (R1–R4) from `PHASE_2_MILESTONE_2_4_SPECIFICATION_REVIEW.md`, and incorporates the clarity-only **Recommended** findings.
**Method:** Full re-read of the updated M2.4 sections + cross-check against the review, live code (`classifier.py`, `spreadsheet_ingestor.py`, `ingest_workflow.py`, `pyproject.toml`), and the M2.3 R-1 channel precedent.
**Verdict:** ALL REQUIRED FINDINGS RESOLVED. Recommended clarity findings applied. No production code modified.

---

## 1. Required findings (R1–R4) — all resolved

| Finding | Requirement | Resolution | Spec location | Status |
|---------|-------------|-----------|----------------|--------|
| R1 | Merged-cell flattening vs `read_only=True` contradiction (empirically: `ReadOnlyWorksheet` has no `merged_cells`) | Extractor loads the workbook **non-read-only** (`read_only=False`, `data_only=True`) so `merged_cells.ranges` is available; value propagated across the merge range. `read_only=True` retained only for the ingestor's flat-text pass. Memory bounded by `max_file_size_mb: 50` + `max_rows: 200`/`max_cols: 30`. | §2.4 Performance (line 219); P2-404 row (line 357); §7.1 `spreadsheet_ingestor.py` (line 463); §14.5 R1 | ✅ Resolved |
| R2 | No PDF table-extraction trigger; spec's PDF claim didn't match routing architecture | PDF extraction triggers on the **existing** classifier `kind == "pdf"` (produced by `EXTENSION_KIND_MAP`, `classifier.py:94`) — the flag and `kind` travel on the existing `DocumentClassification`; **no new routing conditions invented**; no router change. | §2.4 Scope (202), Refactoring (215), AC4 (225); P2-406 row (359); §7.1 router row (457); §14.5 R2 | ✅ Resolved |
| R3 | §7.1 `spreadsheet_ingestor.py` "Structured (non-flat) extraction when enabled" contradicted AC5 (Phase-1-identical output) | Ingestor preserves flat pipe-joined text in **both** `enabled` modes; structured tables attach only at the enrichment stage via `metadata.extra["tables"]`. | §2.4 Backward Compatibility (221); §7.1 `spreadsheet_ingestor.py` (463); §14.5 R3 | ✅ Resolved |
| R4 | `openpyxl` (3.1.5) installed but undeclared in `pyproject.toml` | `openpyxl` explicitly required as a **core dependency** (hard runtime import of `spreadsheet_ingestor.py`), to be declared in `pyproject.toml` as part of P2-404. | §2.4 Dependencies (208); P2-404 row (357); §7.1 `pyproject.toml` (466); §14.5 R4 | ✅ Resolved |

---

## 2. Recommended findings (C1–C7) — applied where they improve clarity without changing architecture

| Finding | Resolution | Spec location |
|---------|------------|----------------|
| C1 | `min_confidence: 0.5` now has a documented consumer: PDF extractor discards low-confidence candidate lines (pdfplumber `table_settings` tuning); **no** `Table.confidence` field. | §2.4 Configuration (218) |
| C2 | Renderer standardized as `MarkdownTableRenderer` everywhere. | §2.4 Interfaces (214), Public APIs (216) |
| C3 | `router.py` removed from P2-406 files; flag + `kind` travel on `DocumentClassification`, consumed at enrichment stage — router/processors documented as "no functional change". | §2.4 Scope (202), Files (212); P2-406 row (359); §7.1 router row (457); §14.5 C3 |
| C4 | Wave-4 (M2.4 ∥ M2.6) shared-file edits (`ingest_workflow.py`, `processor_impls.py`, `core/config.py`) coordinated: self-contained helper methods + distinct config keys, no cross-edits to the other milestone's helpers. | §6.3 Wave-4 note (440); §14.5 C4 |
| C5 | Tables attach to `metadata.extra["tables"]` per the M2.3 R-1 precedent; **no** `ProcessedDocument.tables` field added. | §2.4 Backward Compatibility (221); §7.1 `processed_document.py` (451); §14.5 C5 |
| C6 | Default-true wording no longer claims pre-existing sign-off; recorded as changelogged behavior change pending the M2.4 review gate. | §2.4 Backward Compatibility (221); §14.5 C6 |
| C7 | Classifier line ref corrected to `classifier.py:94` (the `requires_table_extraction` assignment; `:106` for the database-branch assignment). | §2.4 Current Implementation (205); §14.5 C7 |

## 3. Optional findings — adopted

| Finding | Resolution | Spec location |
|---------|------------|----------------|
| O2 | `TableHeader` added to §2.4 Interfaces block (`header: TableHeader`, wraps `list[TableCell]`). | §2.4 Interfaces (214) |
| O3 | `source_position` given provenance semantics in AC1 (row provenance for CSV). | §2.4 AC1 (225) |

O1 (extend classifier flag set to include `pdf`) is **superseded** by the R2 resolution (trigger on existing `kind == "pdf"`); no classifier change and no `test_routing.py` updates required. Documented in §14.5 R2.

---

## 4. Consistency checks

- **Dependency graph intact:** P2-406 still depends on P2-305 (shared enrichment hook, R-2) + P2-403–405; P2-404 depends on P2-402. No task's dependency set changed.
- **AC/DoD aligned:** AC4 (flag reaches enrichment stage) and P2-406 DoD ("`requires_table_extraction` consumed") are mutually consistent; P2-406 AC adds "PDF tables trigger on existing `kind == \"pdf\"`".
- **§14.5 changelog** records R1–R4 + all C/O items; §14.4 (prior v1.1 disposition) untouched.
- **No production code modified** — only `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` edited (§2.4, §4.4 P2-404/406, §6.3, §7.1, §14.5).
- **Note generator contract:** tables render from `document.metadata.extra["tables"]` (C5) — consistent with the existing `ObsidianMarkdownGenerator`, which reads `SourceDocument` (not `ProcessedDocument`); no `ProcessedDocument.tables` field to wire.

## 5. Remaining (out of scope, tracked elsewhere)

- `pyproject.toml` core-dependency declaration for `openpyxl` ships **during implementation** (P2-404), not now — this task was spec-only.
- The M2.4 roadmap's D1 note (`source_type == "pdf"` OR-gate invention) is superseded by the spec's R2 wording; the roadmap is an implementation plan and may be aligned at execution time.
