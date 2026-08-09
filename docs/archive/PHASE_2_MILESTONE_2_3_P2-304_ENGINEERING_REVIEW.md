# P2-304 Engineering Review Report — Structure tree builder + analyzer entry

**Reviewer:** Principal Engineering Reviewer
**Task:** P2-304 (Milestone 2.3 — Document Structure Analysis; wave 3)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` v1.1 (🔒 FROZEN 2026-08-01) — §4.1 (normative `StructureAnalyzer.analyze` + public APIs), §4.2 (domain models), §4.3 (package layout + composition root), §5.1/§6 (data flow), §7 (`MAX_SECTIONS`, C-4), §8 (R8 stable IDs), §9 (offsets contiguous, degenerate → empty), §10 R2/R8, §11.1 (P2-304 row), §12 (parser suite ≥ 90%), §13, §14
**Implementation spec:** `docs/PHASE_2_MILESTONE_2_3_P2-304_IMPLEMENTATION_SPECIFICATION.md`
**Spec review:** `docs/PHASE_2_MILESTONE_2_3_P2-304_SPECIFICATION_REVIEW.md` (✅ Ready for Implementation; findings O1–O6 non-blocking)
**Implementation report:** `docs/PHASE_2_MILESTONE_2_3_P2-304_IMPLEMENTATION_REPORT.md`
**Date:** 2026-08-02
**Scope:** P2-304 only. Review-only — no code modified.

## Verdict

✅ **Approved** — the implementation delivers the frozen §4.1/§4.3 analyzer
contract exactly: D4/D5 stable IDs, contiguous section spans, per-section
block assignment, degenerate input → empty structure, `MAX_SECTIONS` warn +
truncate (never raising), and the three public entry points reachable from the
composition root. The one deviation from the §5.5 pseudocode (a single
all-ranges `_detect_blocks` call instead of per-section calls) was
**independently reproduced as necessary and correct**: the pseudocode's
per-section calls leak a closed fence from an earlier section into a later
one's block attribution, and the implementation instead implements §5.3's own
stated invariant ("behaviorally identical to a single all-ranges call"),
satisfying AC1/AC2. Every gate passes on independent re-run (AC1–AC8, DoD,
ruff, mypy, 88.45% coverage with the parser suite at 99%). Backward
compatibility holds by construction: append-only file, composition-root
re-exports additive, `SemanticChunker` and all domain models byte-identical,
nothing wired in `app/`. No remediation required.

---

## Verification by Area

### 1. Specification compliance — ✅ PASS

| Spec element | Implemented | Verdict |
|--------------|-------------|---------|
| §4.1 `StructureAnalyzer.analyze(self, text, source) -> DocumentStructure` | `detector.py:222` — signature verbatim; `source` accepted-unused (§5.6, tested) | ✅ |
| §4.1 public APIs `analyze_document_structure` / `get_default_structure_analyzer` | `detector.py:305` / `detector.py:300` — module functions, frozen names, composition-root exposure (§4.3) | ✅ |
| §4.3 internal API `_build_tree(sections) -> DocumentStructure` | `detector.py:204` — name verbatim; empty → empty; `> MAX_SECTIONS` → warn + truncate in list (tree) order, never raises | ✅ |
| §4.3 composition root exposure | `__init__.py:3–8` — re-exports the two functions, keeps the package docstring, `__all__` limited to the two (impl spec §6.3) | ✅ |
| §7 / D6 / C-4 `MAX_SECTIONS = 10_000` | `detector.py:201` — code constant, not a config key (§9); `warnings.warn(UserWarning, stacklevel=2)` + `sections[:MAX_SECTIONS]` | ✅ |
| §5.1 section spans (start at heading line, end at next heading / `len(text)`) | lines 240–241, 259 — `next_start` from `line_starts[headings[j+1].line_index]` else `len(text)`; contiguity verified by test and probe | ✅ |
| §5.1 body range excludes heading line | lines 252–255 — `min(line_starts[li] + len(lines[li]) + 1, len(text))`; blocks never include heading lines (`TestOffsetsContiguity`) | ✅ |
| §5.2 D4 IDs via `child_counts` keyed by parent id (`None` = root) | lines 235–250 — `s-{n}` / `{parent_id}-{n}`; level-skip `# A → ### C` ⇒ `C = s-1-1`, parent `s-1` | ✅ |
| §5.2 `MAX_HEADING_LEVEL` (C-4) needs no new code | confirmed — P2-302 clamp + P2-301 `Field(ge=1, le=6)` already enforce (impl spec §5.2 reconciliation) | ✅ |
| §5.3 block assignment per D5 (`b-<section.id>-<n>`, restart per section) | lines 287–295 — `n` = 1-based within section; `b-s-1-1` … `b-s-1-5`, `b-s-2-1` on `blocks.md` (matches frozen §15.4 scheme) | ✅ |
| §5.4 `_build_tree` pseudocode | lines 204–216 — line-for-line match | ✅ |
| §5.5 hashability note (`id(heading)` key) | line 243/250 — `Heading` is unhashable (mutable `@dataclass`); `ids_by_heading` keyed by `id()`, all references held by `headings` list for the loop's duration | ✅ |
| §5.6 `source` accepted-unused; preamble dropped | `test_source_accepted_unused`; `TestPreambleDropped` (documented limitation, not a defect) | ✅ |
| §5.7 entry points pseudocode | lines 300–307 — match | ✅ |
| O-2 reentrancy (fresh stateless instance) | `test_factory_returns_fresh_instance` — `get_default_structure_analyzer()` returns a new instance per call; all state call-local | ✅ |

### 2. Architecture — ✅ PASS

- **Layer correctness:** infrastructure parser produces P2-301 domain models;
  imports `DocumentBlock`/`DocumentSection`/`DocumentStructure` from `app/domain/`
  and the internal `Heading`/`Block` records from the same module — no new
  cross-layer edges. No pydantic import in `_detect_*` (P2-303 invariant kept).
- **Stateless + reentrant:** `StructureAnalyzer` holds no instance state; every
  accumulator (`sections`, `ranges`, `child_counts`, `ids_by_heading`, block
  pointer) is call-local. Safe for P2-305's future parallel ingestion.
- **Two-pass assembly:** pass 1 assigns D4 IDs/parents and section spans (bodies
  tiled in document order); pass 2 makes **one** `_detect_blocks` call over the
  body partition and attributes blocks with a single advancing pointer. This is
  O(n) — matching the frozen §3 complexity claim — and implements the §5.3
  invariant verbatim (see Finding O1).
- **No wiring:** nothing in `app/` imports the analyzer except the composition
  root itself; the only production consumer of `_detect_blocks` is `analyze`.
  P2-305 is the first call site, so rollback (§13) is a clean removal.
- **`ponytail:` comment** at lines 256–258 documents the deviation with its
  rationale at the point of divergence — a reviewer can trace intent without
  the report.

### 3. Regression safety — ✅ PASS

`git status` confirms P2-304 changed exactly three paths:
`app/infrastructure/document_intelligence/` (new package content: `detector.py`
append + composition-root re-exports), `tests/fixtures/structure/` (new +
`empty.md`), `tests/unit/test_structure_analysis.py` (append), plus the P2-304
docs. All are untracked new-milestone files consistent with the prior-wave
convention. The P2-302/303 code (lines 22–196) is byte-identical to its shipped
state — the sole additions at the top are the additive `import warnings` (line 6)
and the `from app.domain.document_intelligence import (…)` block (lines 11–15),
which cannot affect the existing detectors. `app/infrastructure/semantic_chunking.py`
and `app/domain/document_intelligence.py` show **no diff** (AC5 byte-identical;
R-1 untouched). The 89 P2-301/302/303 tests pass unchanged inside the 124-test
run. No existing production file outside `document_intelligence/` was touched.

### 4. Test coverage — ✅ PASS

35 new tests across 9 classes; every impl-spec §12 row and AC exercised:

| Area | Tests |
|------|-------|
| Entry points (both import paths, delegation, fresh instance, `source` accepted) | `TestAnalyzerEntry` (5) |
| Section assembly (nested, siblings, level-skip, full 11-section fixture tree) | `TestSectionAssembly` (4) |
| Block IDs (per-section restart, `blocks.md` exact IDs + types, fence-as-one-code-block, unclosed fence swallow) | `TestBlockIDs` (5) |
| Offsets (tile-without-gaps, last-section `end_char == len(text)`, heading-line slice, block slices exact, heading lines never in non-code blocks, blocks within span) | `TestOffsetsContiguity` (6) |
| Degenerate (`_build_tree([])`, empty, whitespace-only, no headings, `empty.md`, lone ` ``` `, `\r` lines) | `TestDegenerate` (7) |
| `MAX_SECTIONS` (constant == 10_000, exactly-at-cap no warning, over-cap warns + truncates, parent-reference validity) | `TestMaxSections` (4) |
| R8 determinism | `TestIDStability` (1) |
| Preamble dropped (incl. preamble fence discarded) | `TestPreambleDropped` (2) |
| R-1 round-trip (`model_dump(mode="json")` → `model_validate`) | `TestSerializationRoundTrip` (1) |

Fixtures: `empty.md` committed and exercised; existing `nested_headings.md`,
`blocks.md`, `fenced_code.md`, `lists_and_quotes.md`, `table_block.md` are fed
**through `analyze()`** per spec §12 (end-to-end, not `_detect_*` direct).
`detector.py` coverage independently measured at **99% (181/182 statements)** —
see Finding O1/O2 for the single uncovered line.

### 5. Acceptance Criteria (impl spec §10) — ✅ PASS

| # | Criterion | Evidence |
|---|-----------|----------|
| AC1 | Sections contain correct blocks; D5 block IDs | `TestSectionAssembly` + `TestBlockIDs` (incl. `blocks.md`: `s-1` → `b-s-1-1..5`, `s-2` → `b-s-2-1`) |
| AC2 | Offsets contiguous; spans tile; body excludes heading lines | `TestOffsetsContiguity` (6 assertions incl. slice integrity) |
| AC3 | Stable D4 path IDs incl. level-skip; `parent_id` correct | `TestSectionAssembly` (incl. `# A → ### C` ⇒ `s-1-1`) + `TestIDStability` (R8) |
| AC4 | Degenerate → empty; never raises | `TestDegenerate` + `empty.md` fixture |
| AC5 | `MAX_SECTIONS` warn+truncate, never raises; parent refs valid | `TestMaxSections` (4) |
| AC6 | Entry points exist, frozen signatures, reachable via composition root | `TestAnalyzerEntry` (5) |
| AC7 | Preamble not in any section | `TestPreambleDropped` (2) |
| AC8 | Only listed files changed; P2-302/303 unchanged; chunker byte-identical; suite green | `git status` + full-suite gate (below) |

### 6. Definition of Done (impl spec §11) — ✅ PASS (one pending process item)

All code-side checkboxes verified: `_build_tree`, `StructureAnalyzer.analyze`,
`analyze_document_structure`, `get_default_structure_analyzer`, and
`MAX_SECTIONS` implemented matching §5.1–§5.7 (with the single documented,
behavior-preserving deviation — Finding O1); composition root exposes the two
functions; D4/D5, contiguous offsets, degenerate → empty, and `MAX_SECTIONS`
warn+truncate all unit-tested (AC1–AC7); `empty.md` committed and exercised;
no production code outside `structure/detector.py` + the composition root
changed, nothing wired, `SemanticChunker` byte-identical; all existing tests
pass, coverage ≥ 80% (**detector 99%**, exceeding the frozen §12 parser-suite
≥ 90% target), ruff/mypy zero new. The final checkbox (single atomic commit,
§14) is pending — Finding O3, a commit-time step consistent with the P2-302/303
precedent. Spec-review findings O1 (P2-305 fixture note), O2 (preamble /
Phase-3), O3 (`_build_tree` literal reading — assembly correctly lives in
`analyze`), O4 (`MAX_SECTIONS` reconciliation), O5 (`source` accepted-unused),
O6 (timing-test sample note) are all correctly reflected in code and/or the
report; O6 is now moot as a per-section-call concern since the implementation
makes a single call.

### 7–9. Ruff / Mypy / Coverage — ✅ PASS (independently re-run)

| Gate | Independent result |
|------|--------------------|
| `python -m ruff check` (3 changed files) | **All checks passed** |
| `python -m ruff format --check` (3 changed files) | **3 files already formatted** |
| `python -m mypy app/infrastructure/document_intelligence/structure/detector.py` | **Success: no issues found** |
| `python -m pytest tests/unit/test_structure_analysis.py --cov=.../structure` | **124 passed** (89 P2-301/302/303 + 35 P2-304); `detector.py` **99%** (181/182) |
| `python -m pytest tests -q -p no:cacheprovider --cov=app --cov-report=term` | **743 passed, 8 deselected**, total coverage **88.45%** ≥ 80% gate (baseline 708/88.36%; +35, +0.09pp) |

### 10. Backward compatibility — ✅ PASS

Additive-only by construction: `detector.py` appended (P2-302/303 byte-unchanged),
composition root gains two re-exports (previously a one-line docstring), tests
and one 0-byte fixture added, docs added. `SemanticChunker`, `ProcessedDocument`
(R-1), the P2-301 models, config, and all other production files byte-identical
(`git status` clean). M2.1/M2.2 suites green inside the full run. The analyzer is
unreferenced in production, so a §14 revert is a zero-blast-radius removal. No
config keys, no `metadata.extra` writes, no new dependencies, no `__all__`
beyond the two re-exports (impl spec §6.3).

---

## Findings

### O1 — Pseudocode deviation (per-section → single all-ranges call) is necessary and correct — ✅

The implementation deviates from the impl-spec §5.5 pseudocode ("one
`_detect_blocks(text, [(body_start, end_char)])` call per section") in favor of
one all-ranges call with containment attribution. I **independently reproduced**
the bug the deviation avoids: running the §5.5 per-section calls against the
`blocks.md` fixture yields a spurious `code` block (start 170) attributed to
`Next Section` (which starts at 282), because `_detect_blocks` scans from `pos
0` with a document-global fence toggle that runs *before* range membership and
emits on fence close regardless of where the fence opened. The implemented
single call returns the correct partition (paragraph/list/blockquote/code/table
→ `s-1`; paragraph → `s-2`). This implements impl-spec §5.3's own stated
invariant ("behaviorally identical to a single all-ranges call"), satisfies
AC1/AC2, and is pinned by `TestBlockIDs.test_blocks_md_fixture_section_blocks`
(the fixture test that caught the leak during development). Documented in the
report's deviations section and at `detector.py:256–258` via a `ponytail:`
comment. The attribution guard at `detector.py:282–285` (`break` when a block
starts past the last range end — the single uncovered line) is defensively
unreachable: the last section's range ends at `len(text)` and block starts are
always `< len(text)`; kept as a regression guard. ✅

### O2 — Coverage: 99% (not 100%) — ✅ within gate

`detector.py` measured at 181/182 statements; the uncovered line is the
defensive `break` in O1 (line 283). This exceeds the frozen §12 parser-suite
target (≥ 90%) and the P2-303 precedent (100%) by a comfortable margin; the
line is unreachable-by-construction, so chasing it would add dead-code tests.
Report accuracy verified: the report's 99% claim and the "1 missed at line 283"
attribution match the collected output.

### O3 — Atomic commit pending (process, not code)

No git commit exists for P2-304 yet — `document_intelligence/`,
`tests/fixtures/structure/`, `test_structure_analysis.py`, and the P2-304 docs
are untracked, held in the working tree alongside the milestone's earlier
waves. The DoD's final checkbox and §14's per-task atomic-commit mechanism are
satisfied at commit time, per the convention established for P2-301/302/303.
Non-blocking.

### O4 — Forward notes to P2-305 (non-blocking, inherited from spec review)

- **Spec-review O1:** P2-305's integration fixtures must contain ATX headings —
  the frozen AC4 assertion `extra["structure"]` non-empty requires them.
- **Preamble consequence (spec-review O2):** Phase-3 hierarchical chunking must
  not expect a preamble node; text before the first heading is absent from the
  tree by design (`TestPreambleDropped`).
- **`source` contract (spec-review O5):** P2-305 passes `str(document.source)`
  at the shared M2.4/2.5/2.6 call site; the parameter is accepted-unused today.

---

## Summary

The frozen §4.1/§4.3 analyzer contract is implemented exactly: D4/D5 stable
IDs, contiguous non-overlapping spans, per-section D5 block IDs, degenerate →
empty, and `MAX_SECTIONS` warn+truncate — never raising — with the three public
entry points exposed from the composition root. The single deviation from the
§5.5 pseudocode was independently verified as a necessary bug fix that
implements the spec's own §5.3 invariant, and the originally-buggy per-section
behavior is pinned by a fixture test. Every gate passes on independent re-run —
AC1–AC8, the full DoD checklist, ruff (zero new), mypy (zero new), 88.45%
coverage with the parser suite at 99% (≥ 90% frozen target). Backward
compatibility holds by construction (append-only file, additive re-exports,
chunker byte-identical, P2-302/303 intact, nothing wired). No remediation
required.
