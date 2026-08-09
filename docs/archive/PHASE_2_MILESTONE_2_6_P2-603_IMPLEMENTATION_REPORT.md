# P2-603 Implementation Report — Python AST Parser

**Task:** P2-603 — Python AST parser
**Spec:** `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` (frozen §4.6, Interfaces §288 / Public APIs §290)
**Date:** 2026-08-04
**Status:** COMPLETE

---

## Summary

Implemented the Python AST parser in a new `code/parser.py`. The `_AstCodeParser` class uses the stdlib `ast` module to extract top-level imports, functions, classes, and docstrings from Python source, with accurate line and char offsets. A `parse_code(text, filename)` public function dispatches Python files to the AST parser; non-Python files currently yield an empty generic structure until the heuristic fallback lands (P2-604). The `CodeParser` protocol from the frozen §4.6 Interfaces section is defined and exported.

## Files Changed

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/code/parser.py` | New — `CodeParser` protocol, `_AstCodeParser`, `parse_code()`, `_MAX_CODE_CHARS` cap |
| `app/infrastructure/document_intelligence/code/__init__.py` | Extended — re-exports `parse_code` and `CodeParser` |
| `tests/unit/test_code_parser.py` | New — 18 unit tests |

## Implementation

`_AstCodeParser` (implements the `CodeParser` protocol: `languages: frozenset[str] = frozenset({"python"})`, `parse(text, filename) -> CodeStructure`):

- **Extraction** — iterates the module body only: `Import`/`ImportFrom` → `CodeImport`; top-level `FunctionDef`/`AsyncFunctionDef` → `CodeFunction`; `ClassDef` → `CodeClass` with direct method definitions in `methods`. Nested functions/classes are **not** extracted (top-level only, per DoD).
- **Docstrings** — via `ast.get_docstring()` (dedented/cleaned); collected into `CodeStructure.docstrings` in order: module, top-level functions, classes, methods.
- **Offsets** — `start_char`/`end_char` computed from `lineno`/`col_offset`/`end_lineno`/`end_col_offset` (Python 3.12+ `end_*` attrs) against a line-start table; correct for both `\n` and `\r\n` sources. `end_char` is exclusive (matches the `DocumentBlock` convention). `char_start`/`char_end` span the whole file.
- **Imports** — `import a, b.c` → one `CodeImport` per alias (module + optional alias name); `from x import y as z` → module `x`, names `["z"]`, `level` from `node.level`; `from . import y` → module `"."` (current package), preserving the `min_length=1` model constraint.
- **Functions** — `args` lists every parameter in declaration order (positional-only, positional, `*vararg`, keyword-only, `**kwarg`).
- **Classes** — `bases` rendered via `ast.unparse()` (`Base`, `mixins.Speaker`, `Generic[T]`).
- **Truncation** — sources exceeding `_MAX_CODE_CHARS` (module constant, `1_000_000`) are truncated with a logged warning. Config wiring is deliberately out of scope (P2-606).

`parse_code(text, filename)`:
- Python (`language_from_filename() == "python"`) → `_AstCodeParser().parse()`.
- Other languages → `CodeStructure(language=<lang>)` (empty) — the interim no-crash path until P2-604 substitutes the heuristic parser.
- A `SyntaxError` on invalid Python propagates to the caller; the no-crash fallback behavior is pinned by P2-604 per the roadmap ("or raises; behavior pinned by P2-604").

## Acceptance Criteria Met

| Criterion | Status |
|-----------|--------|
| Python file → `CodeStructure` lists imports, functions, classes with line/char offsets and docstrings | `test_parse_simple_imports`, `test_parse_functions_with_docstring`, `test_parse_class_with_methods`, `test_offsets_are_accurate` |
| Syntax error → raises (fallback behavior pinned by P2-604) | `test_syntax_error_raises` |
| Empty file → empty structure (no crash) | `test_empty_file` |
| Files exceeding `max_code_chars` → truncated with logged warning | `test_large_file_truncation` |
| `languages = frozenset({"python"})` | `test_ast_parser_languages` |

## Verification

| Check | Result |
|-------|--------|
| `ruff check` | All checks passed |
| `mypy` | Success: no issues found in 3 source files |
| New tests (18) | All passed |
| Affected code tests (parser + models + languages) | **85 passed** |
| Full suite | **910 passed, 28 deselected, 0 failed** (baseline 892 + 18 new) |
| Regressions | None |

## Downstream Dependencies (not implemented)

- **P2-604** — heuristic fallback parser: `_HeuristicCodeParser`, wired into `parse_code()` for non-Python and syntax-invalid Python.
- **P2-605** — notebook parser (separate module, no overlap with `parser.py`).
- **P2-606** — config wiring: `_MAX_CODE_CHARS` replaced by `CodeSettings.max_code_chars`.
