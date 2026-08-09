# P2-602 Implementation Report — Language Registry

**Task:** P2-602 — Language registry (filename → language)
**Spec:** `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` (frozen §4.6)
**Date:** 2026-08-04
**Status:** COMPLETE

---

## Summary

Created the `code/` subpackage with a standalone language registry mapping file extensions to language names. The registry is fully independent of parsing, ingestion, and configuration — it is a pure dict lookup keyed by suffix, sourced from the canonical `CODE_EXTENSIONS` set in `app/core/extensions.py`.

---

## Files Changed

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/code/__init__.py` | New — re-exports `language_from_filename` |
| `app/infrastructure/document_intelligence/code/languages.py` | New — `_EXTENSION_TO_LANGUAGE` dict + `language_from_filename()` + import-time consistency guard |
| `tests/unit/test_code_languages.py` | New — 34 unit tests |

## Implementation

`language_from_filename(filename: str) -> str`:
- Lowercases the suffix (case-insensitive: `.PY` → `"python"`).
- Uses `PurePosixPath(filename).suffix` so directory paths work (`src/utils/helpers.py` → `"python"`).
- Returns `"generic"` for unknown or absent extensions.
- All 28 `CODE_EXTENSIONS` suffixes mapped to language names (`.jsx` → `"javascript"`, `.tsx` → `"typescript"`, `.sh`/`.bash` → `"shell"`, `.m` → `"objective-c"`, etc.).

**Import-time consistency guard:** the module raises `RuntimeError` at import if any `CODE_EXTENSIONS` entry lacks a mapping, enforcing the "maps via extensions.py" contract from the frozen spec (the registry can never silently drift from the canonical set).

## Acceptance Criteria Met

| Criterion | Status |
|-----------|--------|
| Every extension in `CODE_EXTENSIONS` maps to a language name | Verified by guard + `test_all_code_extensions_mapped` |
| Unknown extensions return `"generic"` | `test_unknown_extension_returns_generic` |
| Case-insensitive lookup (`.PY` → `"python"`) | `test_case_insensitive` |
| No external dependencies (pure dict) | Yes — stdlib only |
| Independent of parsing/ingestion/config | Yes — no imports from parser/ingestor/config modules |

## Verification

| Check | Result |
|-------|--------|
| `ruff check` | All checks passed |
| `mypy` | Success: no issues found |
| New tests (34) | All passed |
| Full suite | **892 passed, 28 deselected, 0 failed** |
| Regressions | None |

## Downstream Dependencies (not implemented)

- **P2-603** — AST parser dispatches Python files via `language_from_filename()`
- **P2-604** — Heuristic parser handles all other languages
- **P2-606** — Enrichment hook uses registry for notebook code-cell language
