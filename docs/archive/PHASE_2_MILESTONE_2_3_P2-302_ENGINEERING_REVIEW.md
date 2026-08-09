# P2-302 Engineering Review Report — Heading hierarchy detector

**Reviewer:** Principal Engineering Reviewer
**Task:** P2-302 (Milestone 2.3 — Document Structure Analysis; wave 1)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` v1.1 (🔒 FROZEN 2026-08-01) — §4.3 (internal API `_detect_headings`), §6 (data flow), §7 (D6 `MAX_HEADING_LEVEL`), §8 AC1/AC2, §10 R1 (D9 rule), §11.1 (P2-302 row), §12 (parser suite ≥ 90%), §13, §14
**Implementation spec:** `docs/PHASE_2_MILESTONE_2_3_P2-302_IMPLEMENTATION_SPECIFICATION.md` (spec-review ✅ Ready for Implementation)
**Implementation report:** `docs/PHASE_2_MILESTONE_2_3_P2-302_IMPLEMENTATION_REPORT.md`
**Date:** 2026-08-01
**Scope:** P2-302 only. Review-only — no code modified.

## Verdict

✅ **Approved** — the implementation matches the frozen §4.3 `_detect_headings`
contract exactly (D9 heading rule, `clean_text`-consistent fence machine, D4
stack hierarchy, D6 clamp), passes every gate on independent re-run (AC1–AC7,
DoD, ruff, mypy, coverage), and introduces zero blast radius. One non-blocking
fixture-content observation (O1) requires no code change to the detector.

---

## Verification by Area

### 1. Specification compliance — ✅ PASS

Line-by-line against the frozen spec and the implementation spec:

| Spec element | Implemented | Verdict |
|--------------|-------------|---------|
| §4.3 internal API `_detect_headings(lines)` | `detector.py:35` — exact name, `Sequence[str]` → `list[Heading]` | ✅ |
| §4.3 package layout `structure/detector.py` | present; `__init__.py` is docstring-only marker | ✅ |
| §10 R1 / D9 rule `^#{1,6}\s+\S` | `_HEADING_RE = r"^(#{1,6})\s+(\S.*)$"` (line 11), line-anchored, no `re.M` | ✅ |
| §8 AC2 fence machine | toggle on `stripped.startswith("```")` (line 48) — byte-identical to `clean_text._protect_code_blocks` (`utils.py:59`) | ✅ |
| D4 hierarchy scan | pop-while-`>=`, attach to `stack[-1]` (lines 59–61) — matches spec §5.3 pseudocode exactly | ✅ |
| §7 / D6 `MAX_HEADING_LEVEL = 6` clamp | module constant (line 9); `_normalize_heading_level = min(max(level,1),6)` (line 22) | ✅ |
| §4.3 `Heading` record (4 fields, mutable) | `@dataclass` lines 25–32, `parent: Heading \| None = None`, forward ref safe via `from __future__ import annotations` | ✅ |
| §6.2 import path | `from app.infrastructure.document_intelligence.structure.detector import _detect_headings, Heading, MAX_HEADING_LEVEL, _normalize_heading_level` | ✅ |
| §6.2 deferred APIs (analyzer/blocks/tree/config) | none introduced — grep confirms only `structure/` + tests + fixtures touched | ✅ |

**Pseudocode fidelity:** the implemented `_detect_headings` is character-for-character
equivalent to spec §5.5 (toggle → skip-fenced → D9 match → clamp → collapse →
D4 stack → append), including the `continue` after a fence toggle so a fence line is
never evaluated as a heading. **Never raises:** the only operations after the None-guard
are `group(1)`/`group(2)`, `len`, `strip`, and dataclass construction — no indexing or
slicing that can fail; every non-matching line is skipped. Traced all five AC1 table
rows from spec §5.3 against the code — identical outcomes.

### 2. Architecture — ✅ PASS

- Pure module, **no module-level mutable state** (reentrant per frozen O-2); `stack`
  and `in_fence` are call-local.
- `Heading` is deliberately **not** a pydantic model and is **not** exported
  publicly — the domain surface stays `DocumentSection` (P2-301). The four-field
  freeze (impl-spec risk 7) prevents surface creep.
- **No wiring:** nothing in `app/` references `_detect_headings`; the only consumers
  are the unit tests. Correctly matches frozen §11.1 ("detector not wired").
- The only stdlib-vs-spec note: spec §3 said `typing.Sequence`; the implementation
  uses `collections.abc.Sequence` (line 6) — the modern stdlib location that `ruff`
  UP035 mandates, behaviorally identical. Accepted, not a deviation.

### 3. Regression safety — ✅ PASS

`git status` confirms P2-302 changed exactly: `app/infrastructure/document_intelligence/structure/`
(new), `tests/fixtures/structure/` (new), `tests/unit/test_structure_analysis.py`
(append-only). No existing file in `app/` or `tests/` was modified. `SemanticChunker`
is byte-identical (`semantic_chunking.py:13` still
`_HEADING_PATTERN = re.compile(r"^#{1,6}\s+.+", re.MULTILINE)` — AC5 confirmed).
`MetadataExtraction`/P2-301 models, `processed_document.py`, config, and `default.yaml`
untouched. The 19 P2-301 tests pass unchanged inside the 46-test file run.

### 4. Test coverage — ✅ PASS

27 new tests across the frozen-spec file (spec §12 matrix, every row exercised):

| Spec §12 row | Tests |
|--------------|-------|
| Hierarchy (chain, siblings, level-skip, re-root, fixture) | 6 |
| Fence (`#` suppressed, language-tagged, toggle, unclosed, before/after, `> ``` `, fixture) | 7 |
| D9 rule (content req, no-space, 7 marks, indented, collapse, extraction) | 8 |
| Depth cap (helper bounds 7→6/6→6/1→1/0→1, `######`→6, constant) | 3 |
| Seam (`line_index` vs split, empty→`[]`, never-raises odd input) | 3 |

Each test independently traced against the algorithm (including `test_blockquote_backticks_not_a_fence`:
`> ``` ` → stripped `> ```` ` does not `startswith("```")` → non-toggle, correct) —
all assertions hold. `detector.py` coverage independently measured at **100%
(39/39 statements)**.

### 5. Acceptance Criteria (impl spec §10) — ✅ PASS

| # | Criterion | Evidence |
|---|-----------|----------|
| AC1 | Nested headings → correct parent/child hierarchy | `TestHeadingHierarchy` (chain, siblings, re-root) |
| AC2 | Fences / fenced `#` not mis-split | `TestFenceDisambiguation` incl. `fenced_code.md` fixture |
| AC3 | D9 — content required | `TestHeadingRule` (negatives + `### A` level 3) |
| AC4 | Level-skip → nearest lower parent | `test_level_skip_attaches_to_nearest_lower` |
| AC5 | Depth ≤ 6 clamp; empty input → no headings | `TestDepthCap` + `test_whitespace_only_input_no_headings` |
| AC6 | `line_index` stable into `split("\n")` | `TestLineIndexOffsets` |
| AC7 | No changes outside listed files; chunker byte-identical | `git status` + full-suite green (below) |

### 6. Definition of Done (impl spec §11) — ✅ PASS (one pending process item)

All five code-side checkboxes verified: `_detect_headings` matches D9 + fence machine
with the 4-field `Heading`; every criterion unit-tested; both fixtures committed and
each exercised by ≥1 test; no production code outside `structure/detector.py` +
`structure/__init__.py` changed, `SemanticChunker` byte-identical; all tests pass,
coverage ≥ 80% (**detector 100%**, exceeding the frozen §12 parser-suite ≥ 90% target —
spec-review finding O3 honored). The final checkbox (single atomic commit, §14) is
pending — see O2, a post-review commit-time step consistent with the milestone
convention. Spec-review findings O1/O2 (wording-only) are correctly documented as
non-code in the report's Known Limitations; the implemented normative rules are correct.

### 7–9. Ruff / Mypy / Coverage — ✅ PASS (independently re-run)

| Gate | Independent result |
|------|--------------------|
| `python -m ruff check` (3 changed files) | **All checks passed** |
| `python -m ruff format --check` (3 changed files) | **3 files already formatted** |
| `python -m mypy app/infrastructure/document_intelligence/structure/detector.py` | **Success: no issues found** |
| `python -m mypy app` | exactly **4 errors** — all pre-existing environment errors in untouched files (`fitz`/`pptx`/`faster_whisper` missing stubs; numpy `.pyi` Python-version syntax); **zero new from P2-302** |
| `python -m pytest tests/unit/test_structure_analysis.py --cov=.../structure` | **46 passed** (19 P2-301 + 27 P2-302); `detector.py` **100%**, `__init__.py` 100% |
| `python -m pytest tests --cov=app --cov-report=term` | **665 passed, 8 deselected**, total coverage **88.13%** ≥ 80% gate (baseline 638/88.04%, +27, +0.09pp) |

Repo-wide `ruff check app tests` surfaces 64 findings — every one in untouched
pre-existing files (`docx/pptx/spreadsheet_ingestor` B904, `vision_client`,
`whisper_transcriber`, `obsidian_note`, `test_e2e_complete.py`, `intelligence_test.py`,
etc.), consistent with the pre-task workspace baseline. None touch P2-302 files.

### 10. Backward compatibility — ✅ PASS

Additive-only by construction: new package + tests + fixtures; nothing else read or
written. `SemanticChunker` (AC5) and P2-301 models byte-identical; M2.1/M2.2 suites
green inside the full run; `_detect_headings` is unreferenced in production, so a
revert (frozen §14) is a zero-blast-radius removal. No config keys, no `metadata.extra`
writes, no new dependencies.

---

## Findings

### O1 — `fenced_code.md` fixture: trailing fence is closed, not unclosed

Impl spec §8 and the implementation report both describe `fenced_code.md` as
containing an **unclosed fence** ("unclosed trailing fence"). The committed fixture
(`tests/fixtures/structure/fenced_code.md`) does **not** contain one: the trailing
```` ```txt ```` fence (line 24) is **closed** at line 27, and the final paragraph
(line 29) — which reads "This file ends inside an unclosed fence." — sits *outside*
any fence, so the sentence is factually false about the fixture's own content.

This does **not** affect detection correctness: the unclosed-fence behavior is fully
covered by the inline `test_unclosed_fence_suppresses_rest` (`_detect("# A\n```\n# not a heading\n## also not\n")`
→ `["A"]`), and the fixture as-written still exercises fenced-`#` suppression and
language-tagged fences (AC2). The discrepancy is fixture-content-vs-record only.

**Recommended fix (one line, non-blocking):** delete the closing ```` ``` ```` at
line 27 so the trailing fence is genuinely unclosed per spec §8 (test output is
unchanged — `["Top Level", "After Fences"]` either way), or amend the line-29 prose
to describe the actual content. Either makes the committed artifact match its
spec/record. No detector or test logic changes.

### O2 — Atomic commit pending (process, not code)

No git commit exists for P2-302 yet (`structure/`, `tests/fixtures/structure/`, and
`test_structure_analysis.py` all untracked). The DoD's final checkbox and §14's
"each task = one atomic commit" are satisfied at commit time; the engineer creates
the single atomic commit after this review, per the M2.2/M2.3 convention (P2-301
reviewed the same way). Non-blocking.

### O3 — Report accuracy — ✅

Every gate number in the report was independently reproduced: 46 tests (19+27),
665 passed / 8 deselected, 88.13% total, `detector.py` 100% (39/39), ruff check +
format clean on changed files, mypy zero-new (app-wide exactly 4 pre-existing).
The test-count arithmetic and the known-limitations text are accurate and consistent
with the collected output.

---

## Summary

The frozen §4.3 `_detect_headings` contract is implemented exactly: the D9 heading
rule, the `clean_text`-consistent fence machine, the D4 stack hierarchy, and the D6
clamp are all present and behaviorally verified by trace; the pseudocode (§5.5) and
the code are identical. Every gate passes on independent re-run — AC1–AC7, the full
DoD checklist, ruff (zero new), mypy (zero new), and 88.13% coverage with the
parser suite at 100% (≥ 90% frozen target). Backward compatibility holds by
construction (chunker byte-identical, P2-301 models untouched, nothing wired).
O1 (fixture trailing fence closed vs. spec's "unclosed") is a non-behavioral
content-of-record gap with a one-line fix; O2 (commit) is a post-review process
step. No remediation required.
