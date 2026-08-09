# Milestone 2.6 — Code & Notebook Intelligence: Implementation Roadmap

**Spec:** `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` (frozen section 4.6, lines 270-303)
**Review:** `docs/PHASE_2_MILESTONE_2_6_SPECIFICATION_REVIEW.md` (APPROVED — all 10 REQ resolved)
**Dependency chain:** `P2-601 → P2-602 → P2-603 → P2-604`; `P2-601 → P2-605`; `P2-305 + P2-602 + P2-603 + P2-605 → P2-606`
**Estimated effort:** 3–4 dev-days (6 tasks)

---

## P2-601 — `CodeStructure` / `NotebookStructure` Models

| Field | Value |
|-------|-------|
| **Objective** | Define the domain models that carry parsed code/notebook structure through the pipeline. These are the foundational data contracts consumed by all downstream M2.6 tasks. |
| **Dependencies** | None (standalone) |
| **Complexity** | Low · 0.25 d · Risk L |

### Files to modify

| File | Change |
|------|--------|
| `app/domain/document_intelligence.py` | Add `CodeFunction`, `CodeImport`, `CodeClass`, `CodeStructure`, `NotebookCell`, `NotebookStructure` pydantic models after `ImageInfo` (line 139). Follow the existing `extra="forbid"` + `ConfigDict` convention. |

### Tests to create

| File | Tests |
|------|-------|
| `tests/unit/test_document_intelligence.py` (extend) | `test_code_structure_round_trip` — construct `CodeStructure` with imports/functions/classes/docstrings, serialize, deserialize, assert equality. `test_notebook_cell_round_trip` — same for `NotebookCell`. `test_notebook_structure_round_trip` — same for `NotebookStructure`. `test_code_function_offsets_validation` — `start_char < end_char` enforced. `test_notebook_cell_type_literal` — only `"markdown"`, `"code"`, `"raw"` accepted. |

### Acceptance Criteria

- `CodeStructure` carries: `language: str`, `imports: list[CodeImport]`, `functions: list[CodeFunction]`, `classes: list[CodeClass]`, `docstrings: list[str]`, `char_start: int`, `char_end: int`.
- `CodeImport` carries: `module: str`, `names: list[str]`, `level: int` (relative import depth).
- `CodeFunction` carries: `name: str`, `args: list[str]`, `docstring: str | None`, `start_line: int`, `end_line: int`, `start_char: int`, `end_char: int`.
- `CodeClass` carries: `name: str`, `bases: list[str]`, `methods: list[CodeFunction]`, `docstring: str | None`, `start_line: int`, `end_line: int`, `start_char: int`, `end_char: int`.
- `NotebookCell` carries: `id: str`, `type: Literal["markdown", "code", "raw"]`, `source: str`, `outputs: list[str]`, `execution_count: int | None`.
- `NotebookStructure` carries: `cells: list[NotebookCell]`, `kernel: str`, `language: str`.
- All offset fields validate `end >= start`.
- Serialization round-trip preserves all fields.

### Definition of Done

- Models defined, `extra="forbid"`, consistent with existing `DocumentStructure`/`ImageInfo` convention.
- All unit tests pass.
- No existing tests broken.

---

## P2-602 — Language Registry

| Field | Value |
|-------|-------|
| **Objective** | Map file extensions to human-readable language names, enabling downstream parsers to select the correct strategy. |
| **Dependencies** | P2-601 |
| **Complexity** | Low · 0.25 d · Risk L |

### Files to create / modify

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/code/languages.py` (new) | Create the `code/` subpackage. Define `_EXTENSION_TO_LANGUAGE: dict[str, str]` mapping each suffix in `extensions.CODE_EXTENSIONS` to a language name (e.g. `".py"` → `"python"`, `".js"` → `"javascript"`). Define `language_from_filename(filename: str) -> str` (returns `"generic"` for unknown). |
| `app/infrastructure/document_intelligence/code/__init__.py` (new) | Empty or re-export `language_from_filename`. |

### Tests to create

| File | Tests |
|------|-------|
| `tests/unit/test_code_languages.py` (new) | `test_python_mapping` — `language_from_filename("main.py") == "python"`. `test_javascript_mapping` — `language_from_filename("app.js") == "javascript"`. `test_unknown_extension` — `language_from_filename("file.xyz") == "generic"`. `test_all_code_extensions_mapped` — every entry in `CODE_EXTENSIONS` has a mapping (no orphan suffixes). `test_case_insensitive` — `language_from_filename("Main.PY") == "python"`. |

### Acceptance Criteria

- Every extension in `extensions.CODE_EXTENSIONS` maps to a language name.
- Unknown extensions return `"generic"`.
- Case-insensitive lookup (`.PY` → `"python"`).
- No external dependencies (pure dict).

### Definition of Done

- `language_from_filename()` works for all `CODE_EXTENSIONS`.
- All unit tests pass.
- No existing tests broken.

---

## P2-603 — Python AST Parser

| Field | Value |
|-------|-------|
| **Objective** | Parse Python source files using `ast` stdlib to extract imports, functions, classes, and docstrings with accurate line/char offsets. |
| **Dependencies** | P2-602 |
| **Complexity** | Medium · 1 d · Risk M |

### Files to create / modify

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/code/parser.py` (new) | Implement `_AstCodeParser` (class, implements a `CodeParser`-like protocol). Methods: `parse(text: str, filename: str) -> CodeStructure`. Uses `ast.parse()` + `ast.walk()` to extract `Import`, `ImportFrom`, `FunctionDef`, `AsyncFunctionDef`, `ClassDef`. Docstrings extracted via `ast.get_docstring()`. Offsets computed from `lineno`, `end_lineno`, `col_offset`, `end_col_offset` (Python 3.12+). Class attribute: `languages: frozenset[str] = frozenset({"python"})`. Implement `parse_code(text: str, filename: str) -> CodeStructure` public function that dispatches to `_AstCodeParser` for Python files and `_HeuristicCodeParser` for others (after P2-604). |
| `app/infrastructure/document_intelligence/code/__init__.py` | Re-export `parse_code`, `CodeParser` protocol. |

### Tests to create

| File | Tests |
|------|-------|
| `tests/unit/test_code_parser.py` (new) | `test_parse_simple_imports` — `import os; from typing import List` → 2 imports. `test_parse_functions_with_docstring` — function with docstring → `CodeFunction` with docstring populated. `test_parse_class_with_methods` — class with 2 methods → `CodeClass.methods` length 2. `test_parse_nested_functions` — inner functions are not extracted (only top-level). `test_parse_async_function` — `async def` parsed as function. `test_offsets_are_accurate` — `start_char`/`end_char` match the actual text span. `test_syntax_error_returns_heuristic` — invalid Python → falls back to `_HeuristicCodeParser` (or raises; behavior pinned by P2-604). `test_empty_file` — empty string → empty `CodeStructure`. `test_large_file_truncation` — file exceeding `max_code_chars` → truncated with logged warning. |

### Acceptance Criteria

- Python file → `CodeStructure` lists imports, functions, classes with line/char offsets and docstrings.
- Syntax error → heuristic fallback (or raises; P2-604 clarifies).
- Empty file → empty structure (no crash).
- Files exceeding `max_code_chars` → truncated with logged warning.
- `languages = frozenset({"python"})`.

### Definition of Done

- `_AstCodeParser.parse()` correctly extracts all top-level imports, functions, classes, docstrings.
- Offsets are accurate for Python 3.12+ (end_lineno/end_col_offset available).
- All unit tests pass.
- No existing tests broken.

---

## P2-604 — Heuristic Fallback Parser

| Field | Value |
|-------|-------|
| **Objective** | Provide a line-based fallback parser for non-Python code files and syntax-invalid Python, ensuring no code file causes a crash. |
| **Dependencies** | P2-603 |
| **Complexity** | Medium · 0.5 d · Risk M |

### Files to modify

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/code/parser.py` | Add `_HeuristicCodeParser` class. Class attribute: `languages: frozenset[str] = frozenset()` (handles all unknown languages). Methods: `parse(text: str, filename: str) -> CodeStructure`. Uses line-based regex patterns: `^(?:export\s+)?(?:async\s+)?function\s+(\w+)` for functions; `^(?:export\s+)?class\s+(\w+)` for classes. Imports extracted via `^(?:import|from)\s+` pattern. Docstrings: heuristic triple-quote extraction. Offsets: line numbers only (char offsets approximated from line starts). **Never raises** — returns empty structure on unparseable input. Wire `parse_code()` to dispatch: `_AstCodeParser` if language == `"python"`, else `_HeuristicCodeParser`. |

### Tests to create

| File | Tests |
|------|-------|
| `tests/unit/test_code_parser.py` (extend) | `test_heuristic_javascript_functions` — JS file with `function foo()` → 1 function. `test_heuristic_class_detection` — `class Bar` → 1 class. `test_heuristic_import_extraction` — `import React` → 1 import. `test_heuristic_never_raises` — garbage input → empty `CodeStructure`, no exception. `test_heuristic_offsets_are_approximate` — char offsets are best-effort (line-based). `test_heuristic_fallback_for_invalid_python` — syntax-error Python → heuristic structure, not crash. `test_non_python_file_dispatch` — `parse_code(text, "app.js")` → heuristic parser, not AST. |

### Acceptance Criteria

- Non-Python file → line-based fallback, no crash.
- Invalid-Python file → heuristic structure, no crash.
- Heuristic parser **never raises** — always returns a `CodeStructure`.
- Functions/classes detected via conservative regex patterns.
- `parse_code()` correctly dispatches based on language from registry.

### Definition of Done

- `_HeuristicCodeParser.parse()` handles all `CODE_EXTENSIONS` languages without crashing.
- `parse_code()` dispatches: Python → AST, others → heuristic.
- All unit tests pass (including P2-603 tests).
- No existing tests broken.

---

## P2-605 — Notebook Parser + Ingestor Upgrade

| Field | Value |
|-------|-------|
| **Objective** | Parse Jupyter notebook JSON into `NotebookStructure` with ordered typed cells, and upgrade `NotebookIngestor` to call the parser and attach the structure (Option 2). |
| **Dependencies** | P2-601 |
| **Complexity** | Medium · 1 d · Risk M |

### Files to create / modify

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/code/notebook.py` (new) | Implement `NotebookParser` class. Method: `parse(raw: dict) -> NotebookStructure`. `raw` is the full notebook dict (output of `json.loads`). Extracts `cells` array: for each cell, create `NotebookCell` with `id` (cell id or index-based), `type` (cell_type), `source` (joined source lines), `outputs` (capped at `max_cell_outputs` from config; entries beyond cap replaced with `"[truncated]"`), `execution_count`. Extracts `metadata.kernelspec.display_name` as `kernel`, `metadata.language_info.name` as `language`. **Never raises** on malformed cells — skip cells with missing fields, log warning. Public function: `parse_notebook(raw: dict) -> NotebookStructure`. |
| `app/infrastructure/ingestion/notebook_ingestor.py` | Upgrade `NotebookIngestor.ingest()`: after reading `notebook = json.loads(raw)`, call `parse_notebook(notebook)` and store the result in `metadata.extra["notebook_structure"]`. Keep existing flattened text in `text` field for backward compatibility (Phase 1 behavior preserved when code enrichment is disabled). Add `cell_count`, `kernel`, `language` to `metadata.extra` as before. |

### Tests to create

| File | Tests |
|------|-------|
| `tests/unit/test_notebook_parser.py` (new) | `test_parse_valid_notebook` — 3-cell notebook (markdown, code, code) → `NotebookStructure` with 3 cells, correct types. `test_parse_preserves_execution_count` — code cell with `execution_count: 5` → preserved. `test_parse_extracts_outputs` — code cell with outputs → `NotebookCell.outputs` populated. `test_parse_caps_outputs` — code cell with 20 outputs + `max_cell_outputs=10` → first 10 preserved, rest `"[truncated]"`. `test_parse_empty_notebook` — no cells → empty `NotebookStructure`. `test_parse_malformed_cell` — cell missing `cell_type` → skipped with warning, other cells parsed. `test_parse_extracts_kernel` — `metadata.kernelspec.display_name` → `NotebookStructure.kernel`. `test_parse_extracts_language` — `metadata.language_info.name` → `NotebookStructure.language`. `test_never_raises` — garbage dict → empty structure, no exception. |
| `tests/unit/test_notebook_ingestor.py` (extend) | `test_ingest_calls_parser` — `.ipynb` file ingested → `metadata.extra["notebook_structure"]` is a `NotebookStructure`. `test_ingest_preserves_flat_text` — ingested text still contains ```` ```python ```` fences (backward compat). `test_ingest_populates_metadata` — `cell_count`, `kernel`, `language` still in `metadata.extra`. |

### Acceptance Criteria

- `NotebookParser.parse(raw)` accepts full notebook dict; extracts cells + metadata internally.
- Ordered typed cells with execution counts preserved.
- Outputs capped at `max_cell_outputs` during parsing; entries beyond cap replaced with `[truncated]` marker.
- `NotebookIngestor.ingest()` calls `NotebookParser.parse()` and attaches result to `metadata.extra["notebook_structure"]`.
- Existing flattened text output preserved for backward compatibility.
- Parser never raises on malformed input.

### Definition of Done

- `parse_notebook()` parses valid notebooks correctly.
- Output capping enforced in parser.
- `NotebookIngestor` attaches structure via Option 2 pattern.
- All unit tests pass.
- Existing `test_notebook_ingestor` tests (if any) still pass.

---

## P2-606 — Processor + Pipeline Enrichment

| Field | Value |
|-------|-------|
| **Objective** | Wire code/notebook structure into the ingestion pipeline: add `CodeSettings` config, implement `_enrich_code()` hook, and ensure `ProcessedDocument` carries structures. Processors remain passthrough (M2.4 TableProcessor pattern). |
| **Dependencies** | P2-305, P2-602, P2-603, P2-605 |
| **Complexity** | Low · 0.5 d · Risk M |

### Files to modify

| File | Change |
|------|--------|
| `app/core/config.py` | Add `CodeSettings` pydantic model after `ImageSettings` (line 337): `enabled: bool = True`, `languages: Literal["default"] = "default"`, `max_cell_outputs: int = 10`, `max_code_chars: int = 100000`, `include_docstrings: bool = True`. Add `code: CodeSettings = Field(default_factory=CodeSettings)` to `IntelligenceSettings` (line 349). |
| `config/default.yaml` | Add `code:` block under `intelligence:` (after `images:` at line 163): `enabled: true`, `languages: "default"`, `max_cell_outputs: 10`, `max_code_chars: 100000`, `include_docstrings: true`. |
| `app/pipelines/ingest_workflow.py` | Add `_enrich_code(document, kind)` method to `IngestionWorkflow` following the `_enrich_tables()`/`_enrich_images()` pattern. Call it from `_run_routed_processor()` after `images_dict` (line 530), gated by `self._settings.intelligence.code.enabled` and `kind in {"code", "notebook"}`. For `kind == "code"`: call `parse_code(text, filename)` and attach `code_structure` to `extra`. For `kind == "notebook"`: read `metadata.extra["notebook_structure"]` (already attached by `NotebookIngestor`) and pass through. |
| `app/infrastructure/routing/processor_impls.py` | `CodeProcessor` and `NotebookProcessor` remain passthrough — no changes required (confirmed by REQ-1). |

### Tests to create

| File | Tests |
|------|-------|
| `tests/unit/test_config.py` (extend) | `test_code_settings_defaults` — `CodeSettings()` has `enabled=True`, `max_cell_outputs=10`, `max_code_chars=100000`. `test_intelligence_settings_has_code` — `IntelligenceSettings().code` is a `CodeSettings`. |
| `tests/unit/test_enrich_code.py` (new) | `test_enrich_code_skips_when_disabled` — `code.enabled=False` → no `code_structure` in extra. `test_enrich_code_skips_unknown_kind` — `kind="markdown"` → no enrichment. `test_enrich_code_attaches_python_structure` — `kind="code"`, Python source → `code_structure` in extra with imports/functions. `test_enrich_code_passes_notebook_structure` — `kind="notebook"`, notebook_structure already in extra → preserved. |
| `tests/unit/test_ingest_workflow.py` (extend) | `test_code_file_through_workflow` — `.py` file through full `_run_routed_processor` → `ProcessedDocument` has `code_structure` in metadata extra. `test_notebook_file_through_workflow` — `.ipynb` file → `ProcessedDocument` has `notebook_structure` in metadata extra. |
| `tests/integration/test_code_pipeline.py` (new) | `test_python_file_end_to_end` — real `.py` fixture through `IngestionWorkflow` → structure attached, all 825 existing tests still pass. `test_notebook_file_end_to_end` — real `.ipynb` fixture through `IngestionWorkflow` → structure attached. `test_rollback_enabled_false` — `code.enabled=False` → output identical to pre-M2.6 passthrough. |

### Acceptance Criteria

- `ProcessedDocument` carries `code_structure` (for code) and `notebook_structure` (for notebooks) in `metadata.extra`.
- Processors remain passthrough (consistent with M2.4 TableProcessor).
- Structure attachment happens in `_enrich_code()` at the P2-305 shared hook.
- `_enrich_code()` gated by `intelligence.code.enabled` and `kind in {"code", "notebook"}`.
- `CodeSettings` added to `IntelligenceSettings` and `default.yaml`.
- Rollback test passes: `enabled=false` produces identical output to pre-M2.6 passthrough.

### Definition of Done

- `_enrich_code()` implemented following `_enrich_tables()`/`_enrich_images()` pattern.
- `CodeSettings` wired through config → workflow → enrichment hook.
- Processors unchanged (passthrough).
- All unit + integration + regression tests pass (825+ existing green).
- Rollback test passes.
- No new lint errors.

---

## Dependency Graph

```
P2-601 (models) ──────────┬──→ P2-602 (language registry) → P2-603 (AST parser) → P2-604 (heuristic)
                          │
                          └──→ P2-605 (notebook parser + ingestor)
                                 │
P2-305 (enrichment hook) ───────┼──→ P2-606 (wiring + config)
P2-602 (language registry) ─────┤
P2-603 (AST parser) ───────────┤
P2-605 (notebook parser) ──────┘
```

## Execution Order

| Wave | Task | Rationale |
|------|------|-----------|
| 1 | P2-601 | Foundation models; no deps; all downstream tasks depend on this |
| 2 | P2-602, P2-605 | Parallel — both depend only on P2-601; no shared files |
| 3 | P2-603 | Depends on P2-602 (needs language dispatch) |
| 4 | P2-604 | Depends on P2-603 (extends parser.py) |
| 5 | P2-606 | Depends on P2-305 + P2-602 + P2-603 + P2-605; sequenced after M2.4 in wave 4 (shared files) |
