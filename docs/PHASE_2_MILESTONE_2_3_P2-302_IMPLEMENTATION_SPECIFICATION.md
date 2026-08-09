# Milestone 2.3 — P2-302 Implementation Specification: Heading Hierarchy Detector

**Milestone:** 2.3 — Document Structure Analysis
**Task:** P2-302 — Heading hierarchy detector
**Status:** Implementation specification (no code implemented by this document)
**Governing contract:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` v1.1 (🔒 FROZEN 2026-08-01) — §4.1/§4.3 (internal API `_detect_headings`), §6 (data flow), §7 (D6 `MAX_HEADING_LEVEL`), §8 AC1/AC2, §10 R1 (D9 heading rule), §11.1 (P2-302 row), §12, §13, §14.
**Design decisions:** `docs/PHASE_2_MILESTONE_2_3_IMPLEMENTATION_ROADMAP.md` D1 (analyzer input text), D4 (level-skip hierarchy), D6 (caps), D9 (heading rule).
**Predecessor:** P2-301 implemented and ✅ approved (`docs/PHASE_2_MILESTONE_2_3_P2-301_ENGINEERING_REVIEW.md`). `DocumentStructure`/`DocumentSection`/`DocumentBlock`/`BlockType` live in `app/domain/document_intelligence.py`.

---

## 1. Objective

Detect nested ATX headings from a single linear scan of the exact analyzed text and
produce a heading list — each with a level (1–6), a 0-based line index, a title, and a
resolved parent linkage — such that a later tree builder (P2-304) can turn the list
into the `DocumentStructure` section tree. The detector tracks fenced-code state so
`#` lines inside fenced blocks are **never** mis-split as headings (frozen AC2), and
applies the frozen heading rule `^#{1,6}\s+\S` (D9) which is deliberately stricter
than `SemanticChunker._HEADING_PATTERN` — the chunker stays byte-identical (AC5).

**This task delivers the heading detector only.** `StructureAnalyzer.analyze(text, source)`,
`_detect_blocks`, `_build_tree`, the composition-root functions
(`analyze_document_structure` / `get_default_structure_analyzer`), and all enrichment
wiring are owned by P2-304 / P2-305 and are **not** introduced here (frozen §11.1
P2-302 row files = `structure/detector.py`).

## 2. Scope

### 2.1 In scope

- `_detect_headings(lines)` — line classification + fence-state machine + heading records.
- `Heading` internal record: `level`, `line_index`, `title`, `parent` (resolved per D4).
- Level normalization clamp to `MAX_HEADING_LEVEL` (defense-in-depth, frozen §7/D6).
- The `app/infrastructure/document_intelligence/structure/` package (minimal `__init__.py`).
- Unit tests appended to `tests/unit/test_structure_analysis.py` + committed fixtures
  `tests/fixtures/structure/nested_headings.md` and `fenced_code.md` (frozen §13 / L6).

### 2.2 Out of scope (explicitly deferred — R10 guard)

- Block detection (paragraph/list/fence/blockquote/table) → P2-303.
- Tree building, section IDs (`s-1`/`s-1-1`), section spans, empty-tree handling → P2-304.
- `StructureAnalyzer` / `analyze()` entry point and composition-root stubs → P2-304.
- `enabled` config plumbing, `TEXT_BEARING_KINDS`, enrichment into
  `metadata.extra["structure"]`, fault containment → P2-305.
- 5 MB size cap and O(n) timing ceiling → P2-306.
- Any change to `SemanticChunker` or its `_HEADING_PATTERN` (frozen AC5 — the chunker
  keeps its internal heading-split copy, fence-unaware, byte-identical).
- HTML/markup, `~~~`-fenced blocks, closing-sequence (`# Title #`) handling beyond
  best-effort (frozen §2.2).

## 3. Dependencies

| Dependency | Type | Detail |
|------------|------|--------|
| P2-301 models | Required, existing | Conceptual prerequisite (milestone order); `_detect_headings` does **not** import the pydantic models — it returns plain `Heading` records. P2-304 maps records → `DocumentSection`. |
| `re` (stdlib) | Required, new use | Heading rule + inline-whitespace collapse (frozen §3). |
| `dataclasses` / `typing.Sequence` (stdlib) | Required, new use | `Heading` record + `lines` typing. |
| `app/core/logging` | Existing | Optional — single `logger.debug` on fence-state transitions is permitted; no new logging surface required. |
| New dependencies | **None** | Zero new runtime or optional packages; no wheel verification (frozen §3). |

**Input-text contract (D1):** `_detect_headings` receives `lines = exact_text.split("\n")`
where `exact_text` is the post-`clean_text` text that the pipeline will chunk
(`result.extracted_text or document.text`). This pins the `line_index` seam: P2-304
re-splits the identical text (same `split("\n")`) with offset accumulation to map
`Heading.line_index` → `start_char`. Any other splitter is forbidden (frozen R2).

## 4. Architecture

- **Placement:** `app/infrastructure/document_intelligence/structure/detector.py` — the
  frozen §4.3 package layout. `structure/__init__.py` is a one-line docstring package
  marker (importability only; no exports this task).
- **Layer:** infrastructure parser over domain models. This task holds **no** domain
  model changes — it consumes nothing from `app/domain/` and adds nothing there.
- **Shape:** one pure module. `_detect_headings(lines: Sequence[str]) -> list[Heading]`
  is the only function; `Heading` is a plain mutable dataclass (parent linkage is
  assigned during the scan, so it is deliberately **not** frozen).
- **Reentrancy (O-2):** pure function, no module-level mutable state — all state
  (`stack`, `in_fence`) is local to the call.
- **Failure modes (frozen §3):** never raises. Every non-matching line is skipped;
  there is no input that raises. Malformed/unclosed fences degrade to "rest is code",
  never an exception.
- **No wiring:** nothing in `app/` calls `_detect_headings` this task; the only
  consumers are its unit tests. P2-303/304 import it from the same module.

## 5. Algorithms

### 5.1 Heading rule (D9 — normative)

A line is a heading iff it matches, at the **first character of the raw line**
(no leading whitespace allowed — post-`clean_text` headings are dedented, D1):

```python
_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*)$")
```

- `level = len(group(1))` — number of leading `#` marks (1–6 by construction).
- `title = _collapse_inline_whitespace(group(2))`, where
  `_collapse_inline_whitespace(s) = re.sub(r"\s+", " ", s.strip())` — defensive;
  on post-`clean_text` input the title is already collapsed.
- A line with no `\S` content after the marks (`#`, `# `, `#\t`) is **not** a heading.
- `#NoSpace` (no whitespace after marks) is **not** a heading.
- `####### X` (7 marks) is **not** a heading — D9 is deliberately stricter than the
  chunker's `^#{1,6}\s+.+`, per frozen §10 R1. (The chunker's pattern also fails to
  match 7 marks, so the two agree here; the divergence is on the `\s+` vs `\s+.\S`
  content requirement, which is frozen-mandated.)
- Indented `  # X` is **not** a heading (D9 anchors at line start; post-`clean_text`
  text has no indented headings).

### 5.2 Fence-state machine (AC2 — normative)

Fence toggling follows the M2.2 `clean_text._protect_code_blocks` convention exactly
(`utils.py:57-82`): a line whose **stripped** form starts with `` ``` `` toggles the
fence; the opening fence may carry an info string (`` ```python ``); the closing fence
is bare (or any trailing chars — best-effort). While `in_fence` is true, **no** line is
evaluated for headings. An unclosed fence treats the remainder of the text as code
(headings after the fence are suppressed) — never raises.

- Only triple-backtick fences toggle state. `~~~` blocks are **not** recognized
  (matching `clean_text`, which does not protect them) — a `#` inside a `~~~` block is
  treated as a heading. Documented best-effort limitation (frozen §2.2).
- ```` ``` ```` inside a blockquote/list line (e.g. `> ``` `) is **not** a fence toggler
  because `clean_text` strips then checks `startswith("```")` on the whole line — the
  post-`clean_text` text cannot contain such a line, so the machine and the input are
  consistent by construction.

### 5.3 Hierarchy scan (D4 — normative)

Single linear pass maintaining a stack of open headings. For each heading `H` of level
`L` (after the `MAX_HEADING_LEVEL` clamp):

1. Pop the stack while `stack[-1].level >= L` (a shallower-or-equal ancestor removes
   the current branch).
2. `H.parent = stack[-1] if stack else None` — attach to the **nearest preceding
   heading with a strictly lower level** (D4 level-skip).
3. Push `H`.

Resulting invariants (these are the AC1 assertions):

| Input | Outcome |
|-------|---------|
| `# A` → `## B` → `### C` | `A.parent=None`, `B.parent=A`, `C.parent=B` |
| `# A` → `### C` (level skip) | `C.parent=A` (no virtual level-2 section; D4) |
| `# A` → `## B` → `# D` | `D.parent=None` (branch `A/B` closed, new root) |
| `## B` → `# A` → `## C` | `A.parent=None` (shallower than B), `C.parent=A` |

### 5.4 Level clamp (D6 — defensive)

```python
MAX_HEADING_LEVEL = 6  # module constant in detector.py (frozen §7 / D6)

def _normalize_heading_level(level: int) -> int:
    """Clamp heading level to 1..MAX_HEADING_LEVEL (frozen §7)."""
    return min(max(level, 1), MAX_HEADING_LEVEL)
```

Under D9 no parsed heading can exceed 6 (7+ marks is not a heading), so the clamp is
**defense-in-depth** per frozen §7 ("levels deeper than 6 normalize to 6"); it is made
directly unit-testable through the helper so the requirement is verified, not assumed.

### 5.5 Pseudocode (normative shape)

```python
def _detect_headings(lines: Sequence[str]) -> list[Heading]:
    headings: list[Heading] = []
    stack: list[Heading] = []
    in_fence = False
    for line_index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_RE.match(line)
        if match is None:
            continue
        level = _normalize_heading_level(len(match.group(1)))
        title = _collapse_inline_whitespace(match.group(2))
        heading = Heading(level=level, line_index=line_index, title=title)
        while stack and stack[-1].level >= level:
            stack.pop()
        heading.parent = stack[-1] if stack else None
        stack.append(heading)
        headings.append(heading)
    return headings
```

Empty/whitespace-only text → zero lines match → `[]` (degenerate input handled by the
caller in P2-304; the detector itself simply returns `[]`).

## 6. Public Interfaces

### 6.1 Internal record (module-scoped, not exported)

```python
@dataclass
class Heading:
    """A detected ATX heading with resolved parent linkage (P2-302)."""

    level: int            # 1..6 (clamped, D6)
    line_index: int       # 0-based index into `lines = exact_text.split("\n")` (D1)
    title: str            # heading text without '#' marks, inline whitespace collapsed
    parent: Heading | None = None   # nearest preceding lower-level heading (D4); None = root
```

Mutable by design: `parent` is assigned during the hierarchy scan. Not a pydantic model —
it is an internal parser record; the domain surface stays `DocumentSection` (P2-301).

### 6.2 Internal API (frozen §4.3 name)

```python
def _detect_headings(lines: Sequence[str]) -> list[Heading]: ...
```

- **Import path (tests and later tasks):** `from app.infrastructure.document_intelligence.structure.detector import _detect_headings, Heading, MAX_HEADING_LEVEL, _normalize_heading_level`.
- **Contract:** never raises; input is any sequence of strings (convention: `exact_text.split("\n")`, D1); output order is document order (stable, R8).
- **Deferred (NOT this task):** `StructureAnalyzer`, `analyze(text, source)`,
  `_detect_blocks(text, ranges)`, `_build_tree(sections)`, `TEXT_BEARING_KINDS`,
  `MAX_SECTIONS`, `max_structure_text_bytes` — P2-303/304/305/306.
- **No `__all__` and no public name added to any existing module** — the only public
  surface change in the repository is the two new files under `structure/`.

## 7. Data Flow

```mermaid
flowchart LR
    T[exact text<br/>post-clean_text<br/>D1] --> S[lines = text.split('&#10;')]
    S --> D[_detect_headings lines]
    D --> F{fence-state machine}
    F -- in fence --> SKIP[skip line]
    F -- not heading --> SKIP2[skip line]
    F -- D9 match --> H[Heading: level / line_index / title]
    H --> ST[stack-based hierarchy D4]
    ST --> PARENT[parent linkage resolved]
    PARENT --> OUT[list[Heading] in document order]
    OUT -. P2-304 .-> TREE[DocumentSection tree / s-1, s-1-1 ...]
```

**Invariants (frozen §6):**

- Headings are detected on the **exact analyzed text** (post-ingestion), not the source
  file — offset/line fidelity (R2). This task consumes lines; P2-304 maps line→char.
- Fenced `#` content is never a heading (AC2).
- Degenerate input (empty/whitespace-only) → `[]`, never an exception.
- No production path touches this function until P2-304; no ingestion wiring, no
  `metadata.extra` writes (those arrive with P2-305).

## 8. Files to Modify

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/structure/__init__.py` | **new** — minimal package marker (docstring only). |
| `app/infrastructure/document_intelligence/structure/detector.py` | **new, the only substantive file** — `MAX_HEADING_LEVEL`, `_HEADING_RE`, `_collapse_inline_whitespace`, `_normalize_heading_level`, `Heading`, `_detect_headings`. |
| `tests/unit/test_structure_analysis.py` | **append** P2-302 test classes (frozen §13 names this file for the milestone's structure unit tests; P2-301 already appends here). |
| `tests/fixtures/structure/nested_headings.md` | **new** — committed fixture (frozen §13 / L6): nested `#`/`##`/`###`, level skip, same-level siblings. |
| `tests/fixtures/structure/fenced_code.md` | **new** — committed fixture (frozen §13 / L6): fenced blocks containing `# not a heading`, language-tagged fence, unclosed fence. |

**Explicitly not modified:** `app/domain/document_intelligence.py` (P2-301 models),
`app/domain/processed_document.py`, `app/infrastructure/semantic_chunking.py` (AC5 —
byte-identical), `app/infrastructure/document_intelligence/__init__.py` (composition
root is P2-304/305), `app/core/config.py`, `config/default.yaml`, any existing test.

## 9. Configuration Impact

**None.** P2-302 declares no config keys and consumes no settings (frozen §7 / L5:
no dead config). `MAX_HEADING_LEVEL = 6` is a module-level code constant in
`detector.py` (D6 `ponytail:` fixed default). `intelligence.structure.enabled` /
`enrich_analysis_input` are untouched until P2-305; `enrich_analysis_input` remains
contract-only (frozen §7, C-5). No `default.yaml` change.

## 10. Acceptance Criteria

| # | Criterion | Source | Evidence |
|---|-----------|--------|----------|
| AC1 | Nested ATX headings produce the correct parent/child hierarchy. | frozen §8 AC1 | `TestHeadingHierarchy`: `# A`→`## B`→`### C` ⇒ `A.parent=None, B.parent=A, C.parent=B`; siblings detach; level-skip `# A`→`### C` ⇒ `C.parent=A` (D4). |
| AC2 | Code fences and fenced `#` lines are **not** mis-split as headings. | frozen §8 AC2 | `TestFenceDisambiguation` incl. the `fenced_code.md` fixture: `# not a heading` inside a fence yields no heading. |
| AC3 | Heading rule matches D9 — content required. | roadmap D9 / frozen §10 R1 | `TestHeadingRule`: `#`, `# `, `#NoSpace`, `####### X`, indented `  # X` are not headings; `### A` is level 3. |
| AC4 | Level-skip attaches to the nearest lower level (no virtual sections). | roadmap D4 | `TestHeadingHierarchy.test_level_skip`. |
| AC5 | Heading levels are normalized to ≤ 6 (defensive clamp); empty/whitespace-only input yields no headings. | frozen §7 / D6 | `TestDepthCap` (helper + `######` = 6), `TestHeadingRule.test_whitespace_only_input` → `[]`. |
| AC6 | `line_index` is a stable, unambiguous index into `exact_text.split("\n")` (D1 seam). | frozen §6 / D1 | `TestLineIndexOffsets` asserts indices against a hand-split string; never raises on malformed input. |
| AC7 | No changes outside the listed files; chunker and full existing suite byte-identical. | frozen §9/§12 | Gate: full `tests` suite passes unchanged; ruff/mypy zero new. |

## 11. Definition of Done

- [ ] `_detect_headings(lines)` implemented in `structure/detector.py` matching D9 and
      the fence-state machine (AC2), with `Heading` (level, line_index, title, parent).
- [ ] Hierarchy (AC1), fence (AC2), D9 rule (AC3), level-skip (AC4), depth cap +
      empty input (AC5), line-index seam (AC6) all unit-tested.
- [ ] Fixtures `tests/fixtures/structure/nested_headings.md` + `fenced_code.md`
      committed (frozen §13 / L6) and exercised by at least one test each.
- [ ] No production code outside `structure/detector.py` + `structure/__init__.py`
      changed; nothing wired; `SemanticChunker` byte-identical (AC5 / AC7).
- [ ] All existing tests pass unchanged; coverage ≥ 80%; `ruff` zero new errors;
      `mypy` zero new type errors (annotated dataclass + typed `Sequence[str]`).
- [ ] Single atomic commit per the milestone rollback contract (frozen §14).

## 12. Test Strategy

| Layer | Scope | Details |
|-------|-------|---------|
| Unit — hierarchy | Nested chain; sibling detachment; level-skip (D4); shallower-after-deeper re-rooting | `tests/unit/test_structure_analysis.py` — inline strings (committed `nested_headings.md` read for one integration-style assertion) |
| Unit — fence | `# not a heading` inside fence suppressed; language-tagged fence; open/close toggle; unclosed fence → remainder is code; headings before/after fence | inline + `fenced_code.md` fixture |
| Unit — D9 rule | content required (`#`/`# `/`#\t`); no-space (`#NoSpace`); 7 marks; indented; inline-whitespace collapse; title extraction | inline |
| Unit — depth cap | `_normalize_heading_level` direct: (7→6, 6→6, 1→1, 0→1); `###### X` → level 6 | inline |
| Unit — seam | `line_index` matches `text.split("\n")` enumeration; empty/whitespace-only → `[]`; never raises on odd input (lone ```, `\r` inside line) | inline |
| Regression | Full existing suite unchanged (chunker AC5, M2.2 suites, P2-301 tests) | `python -m pytest tests -q -p no:cacheprovider --cov=app --cov-report=term` |

**Fixtures:** `tests/fixtures/structure/nested_headings.md`, `fenced_code.md` (committed).
No integration tests this task (P2-305 owns the ingestion-path integration). No
performance tests this task (P2-306 owns cap/timing).

## 13. Rollback Strategy

| Level | Mechanism | Detail |
|-------|-----------|--------|
| Per-task | Git revert of the single atomic P2-302 commit | Additive-only: new package + tests + fixtures; **nothing in `app/` references `_detect_headings` yet** (consumers arrive with P2-303/304), so a revert is a clean removal with zero blast radius. |
| Data | No persistence touched | The detector writes nothing; no `metadata.extra` key exists yet. |
| Code | No legacy branch | No existing component's behavior changes; `SemanticChunker` untouched (AC5); P2-301 models untouched. |
| Dependency | None | No new packages. |
| Process | Frozen §14 | `intelligence.structure.enabled: false` flag rollback is not applicable until P2-305; the §14 per-task atomic-commit mechanism applies now. |

## 14. Risks

| # | Risk | L/I | Mitigation |
|---|------|-----|------------|
| 1 | Fence edge cases: ```` ``` ```` inside blockquote/list, `~~~` fences, unclosed fences, fence marker in prose. | M/M | Fence rule mirrors `clean_text._protect_code_blocks` exactly (`stripped.startswith("```")`), so machine and input are consistent by construction; `~~~`/HTML handling documented best-effort (frozen §2.2); never raises (frozen §3). |
| 2 | Detector/chunker heading divergence surprises downstream. | M/L | Divergence is frozen-mandated (D9 vs `_HEADING_PATTERN`, §10 R1); `SemanticChunker` is **not** touched and its tests are the AC5 gate; a line the chunker splits on but the detector rejects (e.g. `# ` empty heading) simply produces no section. |
| 3 | Depth-cap requirement (frozen §7 ">6 → 6") appears untestable under D9 (7+ marks is not a heading). | L/M | Clamp extracted into the pure helper `_normalize_heading_level` and tested directly; the code documents it as defense-in-depth. |
| 4 | `line_index` seam broken if a later task re-splits differently. | M/M | D1 convention pinned here: `lines = exact_text.split("\n")`, and P2-304 must use the identical split with offset accumulation; AC6 tests pin the enumeration; flagged in the P2-304 handoff. |
| 5 | Offsets drift if text is normalized elsewhere (R2). | M/M | Detector never normalizes input; it reads the exact analyzed text (post-`clean_text`); offsets stay relative to that text (frozen R2). |
| 6 | Level-skip ambiguity (skipped levels → where does a deeper heading attach?). | M/M | D4 stack algorithm pins "nearest preceding strictly-lower level"; AC1/AC4 tests freeze the behavior. |
| 7 | `Heading` dataclass surface creep (extra fields for future tasks). | L/M | Spec fixes the four fields now; any addition becomes a frozen-spec deviation. |

## 15. Complexity Estimate

**Medium — 1 dev-day** (frozen §11.1 P2-302 row). Split: ~0.5 d algorithm
(fence-state machine + D4 hierarchy scan + D9 rule), ~0.5 d tests + fixtures. No
infrastructure, no wiring, no config, no dependency changes. The fence-state machine
and level-skip hierarchy are the only genuinely non-trivial logic; everything else is
single-pass line classification.

---

## 16. Consistency Verification (frozen M2.3 spec)

| Spec element | Frozen source | Consistency |
|--------------|---------------|-------------|
| Deliverable = heading detector only, file = `structure/detector.py` | §11.1 P2-302 row | ✅ `_detect_headings(lines)` in the frozen package path; analyzer/block/builder/composition-root deferred |
| Internal API name `_detect_headings` | §4.3 | ✅ kept verbatim |
| Heading rule `^#{1,6}\s+\S` | §10 R1 mitigation + roadmap D9 | ✅ `^(#{1,6})\s+(\S.*)$` — D9-equivalent, content required |
| Fence-state before heading match | §10 R1 / §8 AC2 | ✅ §5.2 |
| `MAX_HEADING_LEVEL = 6`, levels > 6 → 6 | §7 code constants / D6 | ✅ §5.4 clamp (defense-in-depth) |
| Level-skip parent attachment | roadmap D4 (frozen addenda) | ✅ §5.3 stack scan |
| No chunker change (AC5) | §8 AC5 / §9 / §14 | ✅ explicit not-modified list §8 |
| No wiring, no `metadata.extra` writes this task | §11.1 DoD / §5.4 | ✅ §4 "no wiring"; rollback §13 |
| No config keys, caps as code constants | §7 / L5 / D6 | ✅ §9 |
| Test file + committed fixtures | §13 | ✅ `test_structure_analysis.py` + `nested_headings.md`/`fenced_code.md` |
| Waves / ordering (P2-302 ‖ P2-303 after P2-301) | §11.2 | ✅ depends on P2-301 only; no intra-milestone deps introduced |
| Atomic commit + rollback | §14 | ✅ §13 |

---

*End of P2-302 Implementation Specification. No code implemented by this document.*
