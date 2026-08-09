# P2-605 Engineering Review — Notebook Parser + Ingestor Upgrade

**Reviewer:** Principal Engineering Reviewer
**Date:** 2026-08-04
**Task:** P2-605 — Notebook (ipynb) parser and notebook ingestor upgrade
**Spec:** Frozen §4.6 (PHASE_2_IMPLEMENTATION_SPECIFICATION.md §283 Risks, §288 Interfaces, §290 Public APIs, §293 Performance, §295 Backward Compatibility, §296 Failure Modes, §299 AC3, §300 Required Unit Tests; roadmap `## P2-605 — Notebook Parser + Ingestor Upgrade`)

---

## Verdict

**Approved**

---

## Verification Results

### 1. Frozen Specification & Roadmap Compliance

| Spec / roadmap requirement | Implementation | Verdict |
|----------------------------|---------------|---------|
| §288 / roadmap Files: `NotebookParser` with `parse(raw: dict) -> NotebookStructure`, `raw` = full `json.loads` output | `code/notebook.py:62` — exact signature; extracts cells + metadata internally | Pass |
| Roadmap: cell `id` (cell id or index-based) | `_cell_id()` — `id` field, falls back to 0-based index | Pass |
| Roadmap: ordered typed cells (`cell_type`) | `enumerate(raw_cells)` preserves order; `_VALID_CELL_TYPES = ("markdown", "code", "raw")` matches `NotebookCell.type` Literal exactly | Pass |
| Roadmap: `source` (joined source lines) | `_cell_source()` joins list-of-lines; tolerates single-string source | Pass |
| §293 / AC3 / roadmap: outputs capped at `max_cell_outputs` **during** `NotebookParser.parse()`, excess → `"[truncated]"` | `_cell_outputs()` caps and appends `_TRUNCATED` | Pass |
| Roadmap: `execution_count` preserved | `NotebookCell(execution_count=...)` — kept when a real `int`, else `None` (model-safe) | Pass |
| Roadmap: `metadata.kernelspec.display_name` → `kernel`; `metadata.language_info.name` → `language` | `notebook.py:101-107` | Pass |
| Roadmap: **never raises** on malformed cells — skip + log warning | Non-dict cells, missing/invalid `cell_type`, non-dict raw, non-list `cells` all skipped with `logger.warning`; `_output_text`/`_cell_source` fall through to safe strings | Pass |
| §290 / roadmap Files: public function `parse_notebook(raw: dict) -> NotebookStructure` | `notebook.py:110`, re-exported from `code/__init__.py` | Pass |
| Roadmap Files / §289: `NotebookIngestor.ingest()` calls `parse_notebook()` after `json.loads`, attaches to `metadata.extra["notebook_structure"]` (Option 2, `PdfIngestor` pattern) | `notebook_ingestor.py:9,76` — minimal 2-line delta (import + extra key) | Pass |
| Roadmap: keep existing flattened text in `text`; keep `cell_count`/`kernel`/`language` | All preserved verbatim; flat-text loop untouched | Pass |
| §295 Backward compatibility: text reorders only when `enabled=true` (P2-606 gate) | P2-605 does not touch `text` or processors — flattening byte-identical | Pass |
| §296 Failure mode: "notebook parse error → existing `IngestionError` path preserved" | `JSONDecodeError`/read-failure handlers untouched; `parse_notebook` never raises so it cannot perturb this path | Pass |
| §283 Risk: "notebook JSON schema drift (tolerant parsing)" | Missing cells key, non-list cells, malformed/unknown cells, string-vs-list source, non-dict outputs all tolerated | Pass |

### 2. Notebook Parser (independently verified)

| Case | Result |
|------|--------|
| 3-cell notebook (markdown, code, code) → ordered cells, correct types | ✅ `test_parse_valid_notebook` |
| `execution_count: 5` preserved | ✅ `test_parse_preserves_execution_count` |
| Outputs extracted (stream dict `text`) | ✅ `test_parse_extracts_outputs` |
| Capping: 20 outputs / cap 10 → first 10 + `"[truncated]"` marker | ✅ `test_parse_caps_outputs` (monkeypatched `_MAX_CELL_OUTPUTS=10`); exact semantics asserted (11 entries, marker last) |
| Empty notebook → empty structure | ✅ `test_parse_empty_notebook` |
| Malformed cell (missing `cell_type`) → skipped + warning, good cell still parsed | ✅ `test_parse_malformed_cell` |
| `kernelspec.display_name` → kernel | ✅ `test_parse_extracts_kernel` |
| `language_info.name` → language | ✅ `test_parse_extracts_language` |
| Never raises: garbage dict, non-list cells, non-dict raw | ✅ `test_never_raises` (incl. `parse("garbage")`) |
| Cell `id` fallback to index | ✅ `test_cell_id_falls_back_to_index` |
| Non-int `execution_count` ignored | ✅ `test_non_int_execution_count_ignored` |
| Single-string source (non-list) | ✅ `test_source_as_single_string` |
| Output shapes: plain string, dict w/ text, dict w/ data-only (fallback `str`) | ✅ `test_output_forms` |
| Pydantic safety: constructed `NotebookCell`/`NotebookStructure` never violate model constraints (`id` min_length, type Literal, extra="forbid") | ✅ reviewed — `_cell_id` can never return empty; type validated against the Literal tuple |

### 3. Notebook Ingestion (independently verified)

| Case | Result |
|------|--------|
| `.ipynb` ingested → `metadata.extra["notebook_structure"]` is a `NotebookStructure` | ✅ `test_ingest_calls_parser` |
| Flattened text still contains ` ```python ` fences (backward compat) | ✅ `test_ingest_preserves_flat_text` |
| `cell_count`/`kernel`/`language` still in `extra` | ✅ `test_ingest_populates_metadata` |
| Ingestor diff scope | ✅ `git diff` = 2 additive lines only (import + extra key); error handling and flat-text loop untouched |
| Extra-dict serialization | ✅ verified: `DocumentMetadata.model_dump()` serializes the nested `NotebookStructure` to a plain dict (Pydantic v2 recurses into `dict[str, Any]`) — no downstream serialization regression |

### 4. Tests (independently re-run)

| Gate | Result |
|------|--------|
| `tests/unit/test_notebook_parser.py` | **13/13 passed** |
| Roadmap P2-605 parser tests | All 9 present (`test_parse_valid_notebook` … `test_never_raises`); 4 extras added (id fallback, non-int exec count, string source, output forms) |
| `tests/unit/test_notebook_ingestor.py` | **3/3 passed** — exactly the 3 roadmap ingestor tests |
| Scoped coverage run | `notebook.py` **100%**; `notebook_ingestor.py` **84%** (above 80% floor) |
| Full suite | **935 passed, 28 deselected, 0 failed** (919 baseline + 16 new) |

### 5. Coverage

- `code/notebook.py`: **100%** statement coverage (57/57 stmts, 0 missed). Every branch exercised: valid/empty/malformed/unknown-type cells, list/string/missing source, all output shapes, capping + marker, non-dict raw, non-list cells, kernel/language, id fallback.
- `notebook_ingestor.py`: **84%** — above the repo floor. Uncovered lines (32-35, 45, 51) are **pre-existing** error/edge paths (JSON-decode/read-failure → `IngestionError`, single-string source, raw-cell branch in the flat-text loop) — none are part of the P2-605 delta, which is fully covered by `test_ingest_calls_parser`.

### 6. Regression Safety (independently re-run)

| Gate | Result |
|------|--------|
| Full suite | **935 passed, 28 deselected, 0 failed** — no regressions |
| Integration suite (28 normally deselected by default config) | **14 passed, 27 deselected** — `test_notebook_ingest_enriches_metadata_superset` intact: `cell_count == 1`, `kernel == "Python 3"`, `language == "python"`, and `disabled.document.metadata == phase1.metadata` (both sides use the upgraded ingestor, so the new extra key cancels) |
| Scoped `ruff check` (code/ + both test files) | Clean |
| Scoped `mypy` (`code/notebook.py`) | Success: no issues found |
| Scoped `mypy` (`notebook_ingestor.py --follow-imports=skip`) | Success: no issues found |

**mypy note:** bare `mypy app/infrastructure/ingestion/notebook_ingestor.py` remains blocked by pre-existing repo-wide env issues (`python-pptx` stub missing in `pptx_ingestor.py`; `numpy` stub requiring Python ≥3.12 under 3.14) — unrelated to this task and reported identically in prior reviews. The scoped run over the changed file is clean.

### 7. Code Quality Gates

| Tool | Result |
|------|--------|
| `ruff check` (scoped) | All checks passed |
| `mypy` (scoped) | Success: no issues found |
| Stdlib only | `json`, `logging` — no new dependencies (spec: tolerant parsing without `nbformat`) |
| `parse_notebook` re-export | Added to `code/__init__.py` `__all__` with `NotebookParser`; no circular imports (full suite proves importability) |

### 8. Public API

| Element | Verified |
|---------|----------|
| `NotebookParser.parse(raw: dict) -> NotebookStructure` | Matches §288 interface exactly |
| `parse_notebook(raw: dict) -> NotebookStructure` | Matches §290 public API; exported |
| `NotebookStructure` / `NotebookCell` | P2-601 models, populated per roadmap field spec |
| No config dependency introduced | Capping uses a module constant (see note 1) — config wiring is P2-606's scope by roadmap and user instruction |

---

## Notes (non-blocking)

1. **`max_cell_outputs` placeholder constant.** Roadmap Files row says "capped at `max_cell_outputs` from config", but `CodeSettings.max_cell_outputs` does not exist until P2-606 (roadmap P2-606 config row). Implementation uses `_MAX_CELL_OUTPUTS = 100` with a `ponytail:` comment deferring to P2-606 — correct task sequencing, and the capping *semantics* (the actual P2-605 AC) are pinned by `test_parse_caps_outputs` via monkeypatch. P2-606 will swap the constant for the config value; no remediation needed now.
2. **Unknown cell types are skipped, not coerced.** Roadmap says "skip cells with missing fields"; the implementation also skips cells whose `cell_type` is outside `{markdown, code, raw}` — a justified superset, since `NotebookCell.type` is a `Literal` with no fallback value. Consistent with the §283 tolerant-parsing mitigation.
3. **`language` divergence between ingestor and structure.** `metadata.extra["language"]` prefers `kernelspec.language` (falling back to `language_info.name`), while `notebook_structure.language` reads `language_info.name` per roadmap. Identical in all realistic fixtures; the divergence is pre-existing ingestor behavior and explicitly not in P2-605 scope.
4. **In-memory notebook dicts instead of committed `.ipynb` fixtures.** Matches the established M2.2 precedent (accepted deviation there) — real JSON is constructed in `tmp_path`. The full `IngestionWorkflow` + fixture integration test is P2-606's `test_code_pipeline.py` per roadmap.

---

## Summary

All verification dimensions pass. `code/notebook.py` is a faithful, never-raising implementation of the frozen spec: `NotebookParser.parse(raw)` / `parse_notebook(raw)` produce ordered typed `NotebookCell`s with execution counts and capped outputs (`[truncated]` marker), extract kernel/language from metadata, and tolerate schema drift exactly as §283 requires. The `NotebookIngestor` upgrade is a two-line Option-2 delta (`git diff`-verified) that attaches the structure to `metadata.extra["notebook_structure"]` while preserving flat text and all prior metadata keys, and the existing `IngestionError` paths remain untouched. Coverage is 100% on the parser, 84% on the ingestor (above the 80% floor; uncovered lines are pre-existing paths outside the delta), the full suite passes at 935 and the integration suite at 14 — no regressions. All observations are non-blocking and resolve naturally in P2-606. No findings require remediation.

---

**Signed:** Principal Engineering Reviewer
**Date:** 2026-08-04
