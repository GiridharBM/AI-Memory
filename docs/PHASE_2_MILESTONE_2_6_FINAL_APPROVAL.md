# Milestone 2.6 Final Approval — Code & Notebook Intelligence

**Reviewer:** Principal Engineering Reviewer (independent)
**Date:** 2026-08-05 (full independent re-run — no prior report trusted)
**Basis:** Independent re-verification against the frozen specification (`docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` §4.6, lines 372-381) and the implementation roadmap. Every gate re-run from the live tree in this session: full-suite pytest, coverage, ruff, mypy, direct source inspection of every M2.6 file.

---

## Verdict: APPROVED

The engineering implementation is **correct, complete, regression-safe, and matches the frozen specification** — all six tasks, acceptance criteria, definitions of done, configuration, runtime wiring, and the rollback contract independently re-verified. The single gate finding (F-7: 3 new ruff errors in `tests/fixtures/code/sample.py`) was **remediated and re-verified**: the fixture now imports `os`/`pathlib.Path` *and uses them* (module-level `CWD`/`HOME` assignments), so no ruff rules are suppressed and the extracted structure the integration test asserts is unchanged. All gates now PASS.

---

## 1. Gate Matrix (re-run independently this session)

| Gate | Result | Evidence (re-run 2026-08-05) |
|------|--------|----------------------------------|
| **P2-601 models** | PASS | `app/domain/document_intelligence.py` 142-239: `CodeStructure`, `CodeImport`, `CodeFunction`, `CodeClass`, `NotebookCell`, `NotebookStructure`; `extra="forbid"`; `end >= start` validators (168-174, 191-197); 33 model tests pass |
| **P2-602 language registry** | PASS | `code/languages.py`: 26-suffix dict + startup `RuntimeError` guard verifying `CODE_EXTENSIONS` fully mapped (line 44-46); `PurePosixPath(...).suffix.lower()` case-insensitive; `"generic"` fallback; 34 registry tests pass |
| **P2-603 AST parser** | PASS | `code/parser.py` `_AstCodeParser` (123-164): stdlib `ast`, top-level imports/functions (incl. `async def`)/classes+methods, `ast.get_docstring`, exact offsets via `end_lineno`/`end_col_offset`; 28 parser tests pass |
| **P2-604 heuristic parser** | PASS | `_HeuristicCodeParser` (167-243): line-based regex, never raises; `parse_code` dispatch (254-262) Python→AST, all others + `SyntaxError`→heuristic; covered incl. garbage/CRLF/truncation |
| **P2-605 notebook parser + ingestor** | PASS | `code/notebook.py` `NotebookParser`/`parse_notebook`: ordered typed cells, `execution_count`, outputs capped at `max_cell_outputs` → `"[truncated]"`, kernel/language, never raises (non-dict/skipped-cell guards); `NotebookIngestor` attaches `metadata.extra["notebook_structure"]` (Option 2) and preserves fenced flat text; 14 parser + 4 ingestor tests pass |
| **P2-606 config + enrichment wiring** | PASS | `CodeSettings` (config.py 339, 357-361, `ge=1` caps) mounted at `IntelligenceSettings.code` (375); `default.yaml` `intelligence.code:` block (164-169); `_enrich_code` (ingest_workflow.py 693-730) at shared P2-305 call site (537-547); gated by `code.enabled` **and** `kind in {"code", "notebook"}`; `DocumentIngestionService._code()` threads caps (service.py 70, 100-102); `CodeProcessor`/`NotebookProcessor` passthrough (`processor_impls.py`, REQ-1); 6 enrich + 3 config tests pass |
| **Acceptance criteria (frozen §4.6)** | PASS | (1) Python → imports/functions/classes+offsets+docstrings; (2) invalid Python → heuristic, no crash; (3) `.ipynb` → ordered cells, execution counts, outputs capped in `NotebookParser.parse()`; (4) non-Python → line-based fallback. All verified in code + integration tests |
| **Definitions of done (frozen §4.6)** | PASS | Models/parsers/registry/ingestor/wiring complete; tests green; processors unchanged; rollback test passes; **no new lint errors** — F-7 remediated (see §3) and re-verified |
| **Spec interface conformance** | PASS | `CodeParser` Protocol (parser.py 41-46) matches frozen §4.6; `parse_code(text, filename, max_chars=None)`, `parse_notebook(raw, max_cell_outputs=None)` — positional-or-keyword, superset-compatible with Public APIs |
| **Full test suite** | PASS | `pytest tests` → **947 passed / 31 deselected / 0 failed** (re-run, 9.0s) |
| **M2.6 unit suites** | PASS | `pytest <6 code files>` → **119 passed**; +3 CodeSettings in `test_config.py` = **122 new unit tests across 7 files** |
| **Unit subtree** | PASS | `pytest tests/unit` → **933 passed / 1 deselected** (re-run) |
| **Integration suite** | PASS | `pytest tests/integration -m integration` → **29 passed, 1 skipped (Tesseract not installed), 14 deselected** (independent re-run this session, 144s) — zero failures. The live-Ollama smoke test (`smoke_test.py`) passed this run because a server was available; it is environmental either way (passes with Ollama up, fails without) and is not an M2.6 defect. M2.6 `test_code_pipeline.py` → **3 passed** (py e2e, ipynb e2e, rollback) |
| **Coverage** | PASS | `pytest tests/unit --cov=app` → **87.80%** (independent re-run, floor 80%); full `pytest tests --cov` documented at **88.88%**. Both ≥ 80% floor |
| **Ruff** | PASS | `ruff check` on the full M2.6 file set (code + unit tests + fixtures + integration) → **All checks passed** after F-7 remediation. `ruff check app/ tests/unit/` → 21 errors, all in pre-existing untouched files (docx/pptx/spreadsheet ingestors, vision_client, whisper_transcriber, search, semantic_chunking, worker, templates, old tests) — pre-existing debt, unchanged, zero new |
| **Mypy** | PASS | `mypy app/infrastructure/document_intelligence/code/ app/domain/document_intelligence.py` → **0 issues**. `mypy` on touched pipeline/config files → only pre-existing errors in untouched modules (faster_whisper/pptx stubs, numpy syntax) — none on M2.6 lines |
| **Configuration** | PASS | `CodeSettings` defaults match frozen spec exactly (`True`/`"default"`/`10`/`100000`/`True`); `extra="forbid"` preserved; env `PAM_INTELLIGENCE__CODE__*` via nested delimiter |
| **Runtime wiring** | PASS | Enrichment at shared P2-305 call site after tables/images; `code_structure` for kind `code`, `notebook_structure` passthrough for kind `notebook`; L4 best-effort failure (parse error → `None`, key absent, ingestion continues) |
| **Rollback contract (R-4)** | PASS | `intelligence.code.enabled: false` → no `code_structure`/`notebook_structure` keys; `extra.pop("notebook_structure", None)` in disabled path (ingest_workflow.py 543-547); **proven live** by `test_code_pipeline.py::test_rollback_enabled_false` (both keys asserted absent) |
| **Regression safety** | PASS | 947/31 full suite green; processors unchanged; classifier map additive (code/notebook kinds); schema additive; no new required dependencies (`ast`, `re`, `json` stdlib only) |
| **Documentation accuracy** | PASS | F-1…F-6 remediated and re-verified; final sweep corrected parser decomposition (17 AST-path + 11 heuristic-path = 28) and integration count (28 + 1 environmental smoke + 1 skip) across completion report/changelog/release notes/sync report/review doc; ruff claims now scoped and verified. Docs match live implementation |

---

## 2. Frozen-Spec Adherence (verified line-by-line against §4.6)

- **In-scope/out-of-scope** (§4.6 Scope): all in-scope items delivered; no tree-sitter/ML parsing, no cell execution, no output rendering added. ✓
- **No new required dependencies** (§4.6 Dependencies): `code/` uses stdlib `ast`, `re`, `json` only. ✓
- **Security** (§4.6 Security): AST is read-only (no `exec`/`eval`); output caps enforced; tolerant JSON. ✓
- **Failure modes** (§4.6): syntax error → heuristic; unknown language → generic; notebook parse error → preserved `IngestionError` path. ✓
- **Rollback strategy** (§4.6): `enabled: false` restores Phase-1 flattening/passthrough. ✓
- **Backward compatibility** (§4.6): additive `ProcessedDocument` fields; flat fenced text preserved; `enabled: true` default is the documented, changelogged user-visible change. ✓
- **Performance** (§4.6): AST <50 ms/100 KB; heuristic O(n); `max_code_chars` truncation at parse time with logged warning; `_MAX_CODE_CHARS` default 1 MB. ✓

---

## 3. F-7 (Remediated) — New ruff errors in `tests/fixtures/code/sample.py`

`tests/fixtures/code/sample.py` (new M2.6 file used by `test_code_pipeline.py`) originally introduced **3 ruff errors**: F401 (`os` unused), F401 (`pathlib.Path` unused), I001 (unsorted import block). The scoped §8 lint command in the completion report excluded fixtures, so its "All checks passed" claim did not cover this file.

**Remediation applied (2026-08-05):** the import block was de-blanked and the imports are now *used* — the fixture gained module-level `CWD = os.getcwd()` and `HOME = Path.home()` assignments. No ruff rule is suppressed, no production code changed, no test changed, and the fixture's semantics are preserved exactly: the AST parser extracts only imports/functions/classes, so the module-level assignments are invisible to the extracted structure (`imports == ["os", "pathlib"]`, `functions == ["greet"]`, `classes == ["Greeter"]` — still asserted green by `test_code_pipeline.py`).

**Re-verified this session:**
- `python -m ruff check tests/fixtures/code/sample.py` → **All checks passed**; `ruff format --check` → clean.
- `ruff check` on the full M2.6 set (code + unit tests + fixtures + integration) → **All checks passed**, zero new errors for the M2.6 scope.
- `pytest tests/integration/test_code_pipeline.py -m integration` → **3 passed** (py e2e, ipynb e2e, rollback) — extracted structure unchanged.

---

## 4. Sign-off

- **Engineering gates:** PASS — milestone 2.6 implementation is correct, complete, regression-safe, and matches the frozen specification. Every task AC/DoD, rollback contract, config, runtime wiring, and the full test suite were re-verified independently.
- **Documentation gates:** PASS — prior findings F-1…F-6 remediated and re-verified; final sweep corrections (parser decomposition, integration count, ruff claim scoping) applied and consistent; stale F-7 "open" claims in the completion report, release notes, sync report, and review doc corrected to "remediated" this session to match the live state.
- **Lint gate:** PASS — F-7 remediated without suppressing rules or changing production code; zero new ruff errors in the M2.6 scope.
- **Integration note:** `pytest tests/integration -m integration` re-ran this session → **29 passed, 1 skipped (Tesseract), 14 deselected** — zero failures; the live-Ollama smoke test passed because a server was available. The smoke test is environmental (requires a running Ollama server) and is not an M2.6 defect regardless of outcome.

**Final status: APPROVED** — the milestone proceeds to release-time atomic commits per spec §14. No production code, config, or test changes were made during this review beyond the fixture fix required to clear F-7.