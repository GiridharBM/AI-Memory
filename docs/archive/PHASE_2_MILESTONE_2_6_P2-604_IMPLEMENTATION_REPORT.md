# P2-604 Implementation Report — Heuristic Fallback Parser

**Task:** P2-604 — Heuristic fallback parser (other languages)
**Spec:** `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` (frozen §4.6, line 379)
**Date:** 2026-08-04
**Status:** COMPLETE

---

## Summary

Added `_HeuristicCodeParser` to `code/parser.py` — a line-based, conservative regex parser that handles non-Python code files and syntax-invalid Python. It never raises: unparseable input yields an empty `CodeStructure`. `parse_code()` now dispatches Python → `_AstCodeParser`, everything else → `_HeuristicCodeParser`, with a `SyntaxError` catch that routes invalid Python to the heuristic parser. This pins the no-crash behavior that P2-603 deferred.

## Files Changed

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/code/parser.py` | Extended — `_HeuristicCodeParser` class, `parse_code()` fallback wiring, shared `_truncate()` helper |
| `tests/unit/test_code_parser.py` | Extended — 9 heuristic tests; `test_syntax_error_raises` → `test_syntax_error_returns_heuristic` |

## Implementation

`_HeuristicCodeParser` (class attribute `languages: frozenset[str] = frozenset()` — handles all unknown languages; `parse(text, filename) -> CodeStructure`):

- **Functions** — `^(?:export\s+)?(?:async\s+)?function\s+(\w+)` (per roadmap): handles `function foo`, `export function foo`, `async function bar`, `export async function baz`.
- **Classes** — `^(?:export\s+)?class\s+(\w+)`.
- **Imports** — `^(?:import|from)\s+([\w.]+)`: captures the first module token (`import React` → module `React`; `from typing import List` → module `typing`; `from . import x` → module `.`). Conservative — `import { useState }` is intentionally skipped.
- **Docstrings** — heuristic triple-quote extraction: any line containing `"""…"""` or `'''…'''` contributes its inner content to `CodeStructure.docstrings`.
- **Offsets** — line numbers only; `start_char`/`end_char` are line-start approximations (the match line's char span, exclusive of the following line).
- **Never raises** — pure line scan; unmatched/odd input falls through to an empty structure. `_truncate()` (shared with the AST parser) caps oversized sources with a logged warning.
- **Language** — taken from `language_from_filename(filename)` (`"generic"` for unknown extensions).

`parse_code(text, filename)`:

```
language == "python"  → _AstCodeParser
                        (SyntaxError → logged warning → _HeuristicCodeParser)
otherwise             → _HeuristicCodeParser
```

## Acceptance Criteria Met

| Criterion | Status |
|-----------|--------|
| Non-Python file → line-based fallback, no crash | `test_heuristic_javascript_functions`, `test_non_python_file_dispatch` |
| Invalid-Python file → heuristic structure, no crash | `test_heuristic_fallback_for_invalid_python`, `test_syntax_error_returns_heuristic` |
| Heuristic parser **never raises** — always returns a `CodeStructure` | `test_heuristic_never_raises` (garbage binary input) |
| Functions/classes detected via conservative regex patterns | Function/class/import/from-import/docstring tests |
| `parse_code()` correctly dispatches based on language from registry | `test_non_python_file_dispatch` (`.js` → heuristic, not AST) |

## Verification

| Check | Result |
|-------|--------|
| `ruff check` | All checks passed |
| `mypy` | Success: no issues found in 3 source files |
| New tests (9) | All passed |
| `test_code_parser.py` (total) | **27 passed**, `parser.py` at **100% coverage** (113/113 stmts) |
| Full suite | **919 passed, 28 deselected, 0 failed** (910 baseline + 9 new) |
| Regressions | None — P2-603 tests preserved (only the interim syntax-error assertion updated to the now-pinned fallback behavior) |

## Downstream Dependencies (not implemented)

- **P2-605** — notebook parser (separate module, no overlap with `parser.py`).
- **P2-606** — config wiring: `_MAX_CODE_CHARS` replaced by `CodeSettings.max_code_chars`; enrichment hook consumes `parse_code()` output.
