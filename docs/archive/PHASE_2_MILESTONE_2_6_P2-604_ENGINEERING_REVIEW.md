# P2-604 Engineering Review — Heuristic Fallback Parser

**Reviewer:** Principal Engineering Reviewer
**Date:** 2026-08-04
**Task:** P2-604 — Heuristic fallback parser (other languages)
**Spec:** Frozen §4.6 (PHASE_2_IMPLEMENTATION_SPECIFICATION.md line 379, §283 Risks, §293 Performance, §296 Failure Modes, §300 Required Unit Tests)

---

## Verdict

**Approved**

---

## Verification Results

### 1. Frozen Specification Compliance

| Spec requirement | Implementation | Verdict |
|------------------|---------------|---------|
| P2-604 "Heuristic fallback parser (other languages)" | `_HeuristicCodeParser` in `code/parser.py` | Pass |
| §283 Risk mitigation: "AST fails on syntax-invalid files (fallback to heuristic)" | `parse_code()` catches `SyntaxError` → routes to heuristic with warning | Pass |
| §296 Failure mode: "Syntax error → heuristic fallback" | Now pinned (was the P2-603 interim raise) | Pass |
| §296 Failure mode: "language unknown → generic text structure" | Unknown extension → `CodeStructure(language="generic")`, never crashes | Pass |
| §293 Performance: "heuristic parsers line-based O(n)" | Single pass over `text.split("\n")` with anchored regexes | Pass |
| §293 Performance: "`max_code_chars` truncates oversized code at parse time" | Shared `_truncate()` applied in heuristic parse | Pass |
| §300 Required tests: "heuristic fallback" | 7 roadmap tests + 2 extras | Pass |
| Interfaces §288 / Public APIs §290 | `parse()` signature and `parse_code()` unchanged (protocol-compliant) | Pass |

### 2. Fallback Behavior (independently verified)

| Case | Result |
|------|--------|
| Syntax-invalid Python → heuristic, **no crash** | ✅ `test_heuristic_fallback_for_invalid_python`, `test_syntax_error_returns_heuristic` |
| Syntax-error Python containing a JS-style `function` → heuristic still extracts it | ✅ manual check: `'def broken(:\nfunction foo() {...}\n'` → `functions == ["foo"]`, warning logged |
| Non-Python dispatch (`.js` → heuristic, not AST) | ✅ `test_non_python_file_dispatch` |
| Never raises on garbage/binary input | ✅ `test_heuristic_never_raises` (`\x00\x01\x02 …`) |
| Conservative function regex: `function` / `export function` / `async function` / `export async function` | ✅ all modifiers verified |
| Class regex: `class` / `export class` | ✅ |
| Import regex: `import React`, `from typing import List` | ✅; `import { useState }` intentionally skipped (conservative) |
| Docstring triple-quote heuristic (single-line) | ✅; multi-line `"""…"""` spans intentionally not captured (conservative, documented) |
| Approximate offsets = match-line char span | ✅ `test_heuristic_offsets_are_approximate` |
| Last-line match `end_char == len(text)` | ✅ manual check |
| CRLF sources | ✅ `import React\r\n…function foo() {\r\n}` → 1 import + 1 function |
| Heuristic truncation (> cap) | ✅ manual check: 2-function file capped → 1 truncated parse + warning |
| Empty non-Python file | ✅ `CodeStructure(language="javascript")`, `char_end == 0`, no crash |
| Valid Python still routes to AST (no behavior regression) | ✅ docstring extraction intact |

### 3. Tests (independently re-run)

| Gate | Result |
|------|--------|
| `tests/unit/test_code_parser.py` | **27/27 passed** |
| Roadmap P2-604 tests | All 7 present: javascript functions, class detection, import extraction, never-raises, approximate offsets, invalid-python fallback, non-python dispatch |
| Cross-module code tests (parser + models + languages) | 85 passed |
| Full suite | **919 passed, 28 deselected, 0 failed** (910 baseline + 9 new) |

### 4. Coverage

- `parser.py`: **100%** statement coverage (113/113 stmts, 0 missed).
- Every heuristic branch exercised: function/class/import/docstring matches, all four `continue` paths, fall-through no-match, truncation, `SyntaxError` catch, empty input, last-line `end_char`.
- 80% repo floor satisfied.

### 5. Regression Safety (independently re-run)

| Gate | Result |
|------|--------|
| Full suite | **919 passed, 28 deselected, 0 failed** — no regressions |
| Scoped `ruff check` (code/ + test) | Clean |
| Scoped `mypy` (code/) | Success: no issues in 3 source files |

P2-604 modified only `code/parser.py` and `test_code_parser.py` (both in P2-603 scope). The single behavior change to existing tests — `test_syntax_error_raises` → `test_syntax_error_returns_heuristic` — is the roadmap-anticipated pinning of the previously deferred fallback behavior, not a regression. Repo-wide ruff/mypy findings remain exclusively pre-existing and unrelated to this milestone.

### 6. Documentation Consistency

| Document | Claim | Verified |
|----------|-------|----------|
| P2-604 implementation report | 9 new tests, 27 total, 100% coverage (113 stmts), full suite 919 pass | Confirmed |
| P2-604 report | "never raises; unparseable input → empty structure" | Confirmed |
| P2-603 report/review | Interim "SyntaxError propagates" claim | Consistent — both documents explicitly deferred the no-crash behavior to P2-604 ("behavior pinned by P2-604"); P2-604 now pins it. Historical record, not a defect. |
| Roadmap DoD: "handles all `CODE_EXTENSIONS` languages without crashing" | Verified via `.js`, `.jsx`, `.xyz` (unknown), and garbage inputs | Confirmed |
| Roadmap DoD: "`parse_code()` dispatches: Python → AST, others → heuristic" | Verified both directions + invalid-Python case | Confirmed |

### 7. Code Quality Gates

| Tool | Result |
|------|--------|
| `ruff check` (scoped) | All checks passed |
| `mypy` (scoped) | Success: no issues found |
| Pydantic constraints | Heuristic `CodeFunction`/`CodeClass`/`CodeImport` construction never violates model validators (line/char ordering and `min_length` verified) |

### 8. Public API

| Element | Verified |
|---------|----------|
| `parse_code(text, filename) -> CodeStructure` | Unchanged signature; now never raises for any input |
| `CodeParser` protocol | `_HeuristicCodeParser` satisfies it structurally (`languages: frozenset[str]`, `parse(...) -> CodeStructure`) |
| `language_from_filename` re-export | Unchanged |
| No new external dependencies | Stdlib only (`re` added) |

---

## Notes (non-blocking)

1. **Import regex superset of roadmap.** Roadmap specifies `^(?:import|from)\s+`; implementation adds a capture group `([\w.]+)` to populate the required `CodeImport.module` (`min_length=1`). This is a justified superset, not a deviation — the roadmap left module extraction unspecified.
2. **Multi-line docstrings not captured.** `_DOCSTRING_RE` is single-line-only (`""".*?"""`). Roadmap says only "heuristic triple-quote extraction" — conservative single-line is within that intent and keeps the parser O(n) line-based. If richer docstring capture is ever wanted, P2-606's enrichment is the natural home.
3. **`parse_code` catches `SyntaxError` only.** Any non-`SyntaxError` raised by the AST parser would propagate. The heuristic never raises, so the only reachable error path is correctly the AST syntax-error path. Matches spec.

---

## Summary

All verification dimensions pass. The heuristic fallback is spec-compliant (line-based, conservative regexes matching the roadmap exactly, never raises), the `parse_code()` dispatch and `SyntaxError` fallback are correct and independently exercised across syntax-error Python, non-Python, garbage, CRLF, and truncation inputs, coverage is 100% on `parser.py`, the full suite passes at 919 (no regressions), and documentation claims are consistent. All observations are non-blocking. No findings require remediation.

---

**Signed:** Principal Engineering Reviewer
**Date:** 2026-08-04
