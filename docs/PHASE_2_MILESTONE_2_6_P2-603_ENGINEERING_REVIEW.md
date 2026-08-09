# P2-603 Engineering Review — Python AST Parser

**Reviewer:** Principal Engineering Reviewer
**Date:** 2026-08-04
**Task:** P2-603 — Python AST parser
**Spec:** Frozen §4.6 (PHASE_2_IMPLEMENTATION_SPECIFICATION.md line 378, Interfaces §288, Public APIs §290)

---

## Verdict

**Approved**

---

## Verification Results

### 1. Specification Compliance

| Spec requirement | Implementation | Verdict |
|------------------|---------------|---------|
| P2-603 "Python AST parser" | `_AstCodeParser` in `code/parser.py` | Pass |
| Interfaces §288: `class CodeParser(Protocol): languages: frozenset[str]; def parse(self, text: str, filename: str) -> CodeStructure` | `CodeParser` Protocol defined verbatim; `_AstCodeParser` satisfies it structurally (mypy-verified) | Pass |
| Public APIs §290: `parse_code(text, filename)` | Present; dispatched on `language_from_filename()` | Pass |
| Performance §293: "`max_code_chars` truncates oversized code at parse time" | `_MAX_CODE_CHARS` cap + `logger.warning` in `parse()`; config wiring deferred to P2-606 (per scope) | Pass |
| Failure modes §296: "language unknown → generic text structure" | Non-Python → `CodeStructure(language=<lang>)`, no crash | Pass |
| AC(1): Python file → imports/functions/classes with offsets and docstrings | Extracted with exact char spans; docstrings via `ast.get_docstring()` | Pass |
| DoD: "correctly extracts all top-level imports, functions, classes, docstrings" | Module-body iteration; nested definitions excluded | Pass |
| `languages = frozenset({"python"})` | `_AstCodeParser.languages == frozenset({"python"})` | Pass |

### 2. AST Parser Behavior (independently verified)

| Behavior | Result |
|----------|--------|
| Simple imports (`import os`, `from typing import List`) → 2 `CodeImport`s | ✅ 18/18 tests pass |
| Import forms: aliased, relative (`from . import x` → module `"."`, level 1) | ✅ |
| Function with docstring → `CodeFunction.docstring` populated | ✅ |
| `async def` parsed as function | ✅ |
| Nested functions excluded (top-level only) | ✅ |
| Class methods collected in `CodeClass.methods` (2 methods) | ✅ |
| `args` in declaration order incl. `*args`/`**kwargs` (`a, b, *args, c, **kw`) | ✅ |
| Bases rendered via `ast.unparse()` (`Base`, `mixins.Speaker`) | ✅ |
| Exact char offsets — `text[start_char:end_char]` equals source span (LF and CRLF, with and without trailing newline) | ✅ start/end verified against real spans |
| `char_start`/`char_end` span the whole file (`0..len(text)`) | ✅ |
| Docstrings collected in order: module, functions, classes, methods | ✅ |
| Empty file → empty structure, no crash | ✅ |
| Oversized file → truncated with logged warning | ✅ (100% branch coverage) |
| Syntax-error Python → `SyntaxError` propagates (roadmap-allowed; no-crash fallback pinned by P2-604) | ✅ |
| Non-Python → empty generic structure, never crashes | ✅ |

### 3. Tests (independently re-run)

| Gate | Result |
|------|--------|
| `tests/unit/test_code_parser.py` | **18/18 passed** |
| Roadmap-required tests | All 9 present: simple imports, functions w/ docstring, class w/ methods, nested functions, async function, offsets accurate, syntax-error (raises variant), empty file, large-file truncation |
| Cross-module tests (parser + models + languages) | **85 passed** |

### 4. Coverage

- `parser.py`: **100%** statement coverage (70/70 stmts, 0 missed) via `--cov` run.
- Every branch exercised: truncation path, both import kinds, async + sync functions, class methods, docstring ordering, syntax-error path, non-Python dispatch.
- 80% repo floor satisfied.

### 5. Regressions (independently re-run)

| Gate | Result |
|------|--------|
| Full suite | **910 passed, 28 deselected, 0 failed** (892 baseline + 18 new) |
| Scoped `ruff check` (code/ + new test) | Clean |
| Scoped `mypy` (code/) | Success: no issues in 3 source files |

P2-603 touched only new files (`code/parser.py`, `code/__init__.py` re-export, `test_code_parser.py`). The repo-wide ruff (61 findings) and mypy (3 findings) reports surface pre-existing issues exclusively in unrelated milestone files (docx/pptx/spreadsheet ingestors, whisper/vision clients, `test_e2e_complete.py`, numpy stub env, etc.) — none in P2-603 scope, none introduced by this change.

### 6. Public API

| Element | Verified |
|---------|----------|
| `parse_code(text: str, filename: str) -> CodeStructure` | Importable from `code/__init__.py` (`__all__`); dispatch verified |
| `CodeParser` Protocol | Exported; matches frozen §288 signature exactly |
| `language_from_filename` | Re-export preserved (no regression to P2-602 API) |
| No new external dependencies | Stdlib only (`ast`, `logging`, `typing`/`collections.abc`) |

### 7. Code Quality Gates

| Tool | Result |
|------|--------|
| `ruff check` (scoped) | All checks passed |
| `mypy` (scoped) | Success: no issues found |
| Pydantic model constraints | All `CodeStructure`/`CodeFunction`/`CodeClass`/`CodeImport` validators satisfied (verified via passing model tests + parser tests) |

### 8. Implementation Report Claims (cross-checked)

| Report claim | Verified |
|--------------|----------|
| 18 tests, full suite 910 pass | Confirmed |
| 100% coverage of `parser.py` | Confirmed |
| Offsets correct for LF and CRLF | Confirmed (dedicated CRLF test + manual span check) |
| Top-level-only extraction (nested excluded) | Confirmed |
| Non-Python → generic structure | Confirmed |

---

## Notes

1. **Roadmap `ast.walk()` vs top-level extraction.** The roadmap prose ("Uses `ast.parse()` + `ast.walk()`") conflicts with its own test list (`test_parse_nested_functions` — inner functions not extracted) and DoD ("all top-level imports, functions, classes"). `ast.walk()` visits nested nodes and would break both. The implementation resolves the inconsistency by iterating the module body (and class bodies for methods), which satisfies the tests and DoD exactly. Non-blocking; not a defect.
2. **Syntax error → raises (not heuristic fallback).** The frozen spec's AC(2) "invalid-Python → heuristic structure, no crash" is implemented by P2-604. The roadmap explicitly sanctions this interim: "or raises; behavior pinned by P2-604", and the task scope excluded the fallback parser. Behavior is documented in the module docstring and pinned by `test_syntax_error_raises`. Non-blocking.
3. **`max_code_chars` as module constant.** Spec puts the cap at parse time; config wiring (`CodeSettings`) is P2-606 per scope. Marked with a `ponytail:` comment naming the upgrade path. Non-blocking.
4. **`CodeParser` is not `@runtime_checkable`.** Deliberate — the frozen spec declares a plain `class CodeParser(Protocol)`, so `isinstance` checks are unsupported by design; conformance is structural (enforced by mypy). Matches spec verbatim. Non-blocking.

---

## Summary

All verification dimensions pass. The AST parser extracts top-level imports, functions, classes, and docstrings with exact char offsets (verified against real text spans, incl. CRLF and no-trailing-newline sources), 100% coverage, all roadmap-required tests present, and zero regressions (910 passed). Three roadmap/spec conflicts were resolved in the direction that satisfies the frozen tests and DoD; each is documented and non-blocking. No findings require remediation.

---

**Signed:** Principal Engineering Reviewer
**Date:** 2026-08-04
