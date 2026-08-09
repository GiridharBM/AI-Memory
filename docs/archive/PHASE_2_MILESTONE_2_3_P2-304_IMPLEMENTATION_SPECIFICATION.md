# Milestone 2.3 — P2-304 Implementation Specification: Structure Tree Builder

**Milestone:** 2.3 — Document Structure Analysis
**Task:** P2-304 — Structure tree builder
**Status:** Implementation specification (no code implemented by this document)
**Governing contract:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` v1.1 (🔒 FROZEN 2026-08-01) — §4.1 (normative `StructureAnalyzer.analyze` + public APIs), §4.2 (domain models), §4.3 (package layout + composition root), §5.1/§6 (data flow), §7 (`MAX_SECTIONS`, C-4), §8 (R8 stable IDs), §10 R2/R8, §11.1 (P2-304 row), §12, §13, §14.
**Design decisions:** `docs/PHASE_2_MILESTONE_2_3_IMPLEMENTATION_ROADMAP.md` D1 (exact analyzed text + `split("\n")` seam), D4 (section ID scheme), D5 (block ID scheme), D6 (caps as code constants), D9 (heading rule).
**Predecessors:** P2-301 ✅ (`..._P2-301_ENGINEERING_REVIEW.md`), P2-302 ✅ (`..._P2-302_ENGINEERING_REVIEW.md`), P2-303 ✅ (`..._P2-303_ENGINEERING_REVIEW.md`) — `detector.py` now holds `_detect_headings` + `_detect_blocks` (132 stmts, 100% coverage); `app/domain/document_intelligence.py` holds `DocumentStructure`/`DocumentSection`/`DocumentBlock`/`BlockType`.

---

## 1. Objective

Combine the P2-302 heading hierarchy and the P2-303 block detector into the
milestone's **nested `DocumentStructure`**: heading-delimited sections that contain
their blocks, with stable path-style IDs (D4/D5), contiguous non-overlapping char
offsets, degenerate/empty input → empty structure, and the `MAX_SECTIONS` cap
truncating with a warning — never raising. P2-304 also delivers the **public entry
points** the frozen spec mandates: the `StructureAnalyzer` class, the
`analyze_document_structure` function, and the `get_default_structure_analyzer`
composition-root factory (frozen §4.1/§4.3), so P2-305 can wire enrichment with a
single import.

**This task delivers the tree builder + analyzer entry only.** `TEXT_BEARING_KINDS`,
`structure.enabled` plumbing, the `_run_routed_processor` hook, and the
`metadata.extra["structure"]` write are owned by P2-305; the 5 MB size cap and the
O(n) timing ceiling are owned by P2-306 (frozen §11.1 rows).

## 2. Scope

### 2.1 In scope

- `_build_tree(sections)` — wrap the assembled `DocumentSection` list into
  `DocumentStructure`, apply `MAX_SECTIONS` truncation with a warning, degenerate →
  empty (frozen §4.3 internal API list).
- `StructureAnalyzer` class with `analyze(self, text, source) -> DocumentStructure`
  (frozen §4.1 normative interface) — the orchestration that turns text into a tree:
  heading detection → line-start mapping → section assembly (IDs/parents/spans) →
  per-section block detection → `_build_tree`.
- `analyze_document_structure(text, source)` and `get_default_structure_analyzer()`
  (frozen §4.1/§4.3 public APIs) + their exposure from the composition root
  `app/infrastructure/document_intelligence/__init__.py`.
- `MAX_SECTIONS = 10_000` code constant (frozen §7 / D6 / C-4) with warn+truncate.
- Section ID assignment per D4 (`s-1`, `s-1-1`, …) and block ID assignment per D5
  (`b-<section.id>-<n>`).
- Unit tests appended to `tests/unit/test_structure_analysis.py` + the committed
  `tests/fixtures/structure/empty.md` fixture (frozen §13 list; P2-303 spec §8
  deferred it to "P2-304 (empty-tree)").

### 2.2 Out of scope (explicitly deferred — R10 guard)

- **Enrichment wiring, config plumbing, `metadata.extra["structure"]` writes,
  `TEXT_BEARING_KINDS`, `enabled` consumption** → P2-305 (frozen §11.1 P2-305 row).
- **5 MB size cap (`max_structure_text_bytes`), O(n) timing ceiling** → P2-306.
- **`ProcessedDocument`** — never modified (R-1, frozen §5.4).
- **Any change to `_detect_headings` / `_detect_blocks` / `Block` / `BlockKind` /
  `_HEADING_RE` / `MAX_HEADING_LEVEL`** — P2-302/303 code untouched. P2-304 is the
  **first production caller** of `_detect_blocks`.
- **`SemanticChunker` or its `_HEADING_PATTERN`** — byte-identical (AC5).
- **Phase-3/4 features** — hierarchical chunking, parent-child retrieval, structure-
  aware prompting (frozen §2.2, R10 guard).
- **A "preamble section" for text before the first heading** — no such concept exists
  in the frozen models (a `DocumentSection` requires `title`/`level` from a heading);
  preamble text is dropped from the tree (documented limitation, §5.6, pinned by a test).

## 3. Dependencies

| Dependency | Type | Detail |
|------------|------|--------|
| P2-301 models | Required, existing | `DocumentStructure` / `DocumentSection` / `DocumentBlock` / `BlockType` in `app/domain/document_intelligence.py` — the tree builder's output types; validators (`extra="forbid"`, offset integrity, `level ≤ 6`) are the boundary safety net. |
| P2-302 `_detect_headings` | Required, existing | Returns `list[Heading]` with `level`, `line_index`, `title`, `parent` (D4 linkage pre-resolved by the stack algorithm). `Heading` is **unhashable** (mutable dataclass) — see §5.5 note. |
| P2-303 `_detect_blocks` + `Block` | Required, existing | Per-section body-range block detection; `Block.type` is the `BlockKind` Literal whose values equal the `BlockType` strings. |
| `re`, `dataclasses`, `typing`, `warnings` (stdlib) | Required, existing | `warnings.warn` for the `MAX_SECTIONS` truncation (deterministic + `pytest.warns`-testable; pure module, no logger). |
| New dependencies | **None** | Zero new runtime or optional packages (frozen §3 — pure stdlib parsing). |

**Input-text contract (D1):** `analyze` receives `text` = the exact post-`clean_text`
text the pipeline will chunk (`result.extracted_text or document.text`, provided by
P2-305). The tree builder re-derives line positions with the **identical
`text.split("\n")` + `pos += len(line) + 1` offset accumulation** that P2-302 (via
`line_index`) and P2-303 (via char offsets) already pin — any other splitter is
forbidden (frozen R2, offsets-drift mitigation). `source` is a contract parameter
(frozen §4.1 signature) and is **accepted but not used** by the tree builder
(§5.6); future enrichment tasks (M2.4/2.5/2.6) may consume it at the same call site.

## 4. Architecture

- **Placement:** `_build_tree`, `StructureAnalyzer`, `analyze_document_structure`,
  `get_default_structure_analyzer`, and `MAX_SECTIONS` are **appended** to
  `app/infrastructure/document_intelligence/structure/detector.py` — the frozen §4.3
  layout ("analyzer + `_detect_headings` + `_detect_blocks` + `_build_tree`").
  P2-302/303 code is untouched.
- **Composition root:** `app/infrastructure/document_intelligence/__init__.py`
  (currently a one-line docstring) gains two re-exports — `analyze_document_structure`
  and `get_default_structure_analyzer` — per frozen §4.3. *Reconciliation: the frozen
  §11.1 P2-304 row lists only `structure/detector.py`, but §4.3 normatively requires
  the composition-root exposure; P2-303's spec explicitly deferred the composition
  root to "P2-304/305", and P2-304 owns the analyzer, so P2-304 lands it.*
- **Layer:** infrastructure parser producing domain models. The builder imports the
  pydantic models from `app/domain/` and the internal records (`Heading`, `Block`)
  from the same module — no new cross-layer edges.
- **Reentrancy (O-2):** `StructureAnalyzer` is **stateless**; `analyze` keeps all
  state call-local. `get_default_structure_analyzer()` returns a **fresh instance**
  per call (cheap, stateless, and free of any shared-singleton concern). Safe under
  future parallel ingestion.
- **Failure modes (frozen §3):** never raises. Every pathological input (empty,
  whitespace-only, no headings, malformed markup, unclosed fences, oversized section
  counts) degrades to a valid `DocumentStructure` — empty or truncated — never an
  exception.
- **Wiring:** `StructureAnalyzer` / `analyze_document_structure` are **not** called
  from production this task. P2-304's only consumers are its unit tests; P2-305 is
  the first production caller. Rollback (§13) is therefore a clean removal.

## 5. Algorithms

### 5.1 Section spans (normative — offsets, R2)

Given `lines = text.split("\n")` and `headings = _detect_headings(lines)`:

- `line_starts[i]` = char offset of the first char of `lines[i]`, computed by the
  standard accumulation `pos += len(line) + 1` (the `+1` for `\n`) — identical to
  P2-303's scan, so `Heading.line_index` maps to char space losslessly.
- For the heading at index `j` (in document order):
  - `start_char` = `line_starts[headings[j].line_index]` — the section begins at its
    **own heading line**.
  - `end_char` = `line_starts[headings[j+1].line_index]` when a next heading exists,
    else `len(text)` — the section ends where the next section begins.
  - **Body range** (passed to `_detect_blocks`): `[body_start, end_char)` with
    `body_start = min(line_starts[li] + len(lines[li]) + 1, len(text))` — the body
    **excludes the heading line itself** (heading lines are never blocks) and the
    next heading's line. If `body_start >= end_char` the body is empty → `[]` blocks.
- **Contiguity invariant:** `section[j].end_char == section[j+1].start_char` for all
  `j` — sections tile `[first_heading_start, len(text))` with no gaps and no overlap
  (frozen §9 "offsets contiguous"; §4.2 start-inclusive / end-exclusive).
- **Slice integrity:** `text[section.start_char:section.end_char]` contains the
  heading line; every block satisfies `text[block.start_char:block.end_char] ==
  block.text` (already asserted by P2-303 and re-exercised at the tree level).

### 5.2 Section assembly (normative — D4 IDs)

Process headings in document order (parents always precede children). Maintain
`child_counts: dict[str | None, int]` (keyed by parent section id; `None` = root):

- `n = child_counts[parent_id] + 1`; `child_counts[parent_id] = n`.
- Root section → `id = f"s-{n}"`; nested → `id = f"{parent_id}-{n}"`.
- `parent_id` = the section id assigned to `heading.parent` (from P2-302's
  pre-resolved D4 linkage; `None` for roots).
- `title` = `heading.title` (already inline-collapsed by P2-302); `level` =
  `heading.level` (already clamped by P2-302 — `MAX_HEADING_LEVEL` needs **no new
  code** here; the frozen §12 "caps enforced (C-4)" is satisfied by the P2-302 clamp
  plus the P2-301 `Field(ge=1, le=6)` validator).

Example (level-skip, per roadmap D4): `# A` then `### C` ⇒ `A = s-1`,
`C.parent_id = "s-1"`, `C = s-1-1` (path element count = tree depth 2).

### 5.3 Block assignment (normative — D5 IDs)

- For each section, one `_detect_blocks(text, [(body_start, end_char)])` call (empty
  body → no call, `[]`). Per-section calls are **behaviorally identical** to a single
  all-ranges call because **no range boundary falls inside a fence**: section
  boundaries sit on heading lines, headings are never inside a fence (P2-302), and an
  unclosed fence swallows any following `#` lines (they are not headings), so the
  fenced region belongs to the last detected heading's section — the P2-303
  fence/range invariant carries through. This keeps block attribution trivial and
  isolates sections.
- Each returned `Block` maps to a `DocumentBlock`:
  `block_id = f"b-{section.id}-{n}"` with `n` = 1-based index **within the section**
  (restarts per section, D5 — `s-1` block 1 → `b-s-1-1`; `s-1-1` block 1 →
  `b-s-1-1-1`, matching frozen §15.4); `type`/`text`/`start_char`/`end_char` copied
  verbatim (values are already slice-exact, validated by the P2-301 model).
- Blocks never span sections (single-range call + P2-303 flush-at-range-edges).

### 5.4 `_build_tree` (normative)

```python
MAX_SECTIONS = 10_000  # frozen §7 / D6 / C-4: warn + truncate in tree order, never raise

def _build_tree(sections: Sequence[DocumentSection]) -> DocumentStructure:
    """Wrap assembled sections into a DocumentStructure (frozen §4.3)."""
    if not sections:
        return DocumentStructure(sections=[])
    if len(sections) > MAX_SECTIONS:
        warnings.warn(
            f"structure: {len(sections)} sections exceed MAX_SECTIONS={MAX_SECTIONS}; "
            "truncating in tree order",
            UserWarning,
            stacklevel=2,
        )
        sections = sections[:MAX_SECTIONS]
    return DocumentStructure(sections=list(sections))
```

- Truncation takes the **first** `MAX_SECTIONS` in list order (= document/tree order).
  Because parents always precede their children in that order, every kept section's
  `parent_id` still references a kept section — no dangling parent references.
- Degenerate input → `DocumentStructure(sections=[])`. Never raises.

### 5.5 `analyze` orchestration (normative pseudocode)

```python
class StructureAnalyzer:
    """Detect and build the hierarchical structure of source text (frozen §4.1)."""

    def analyze(self, text: str, source: str) -> DocumentStructure:
        lines = text.split("\n")
        headings = _detect_headings(lines)
        if not headings:
            return DocumentStructure(sections=[])   # empty / whitespace-only / no headings

        line_starts: list[int] = []                  # D1 seam: identical split + accumulation
        pos = 0
        for line in lines:
            line_starts.append(pos)
            pos += len(line) + 1

        sections: list[DocumentSection] = []
        ids_by_heading: dict[int, str] = {}          # id(heading) -> section id
        child_counts: dict[str | None, int] = {}

        for j, heading in enumerate(headings):
            next_start = (line_starts[headings[j + 1].line_index]
                          if j + 1 < len(headings) else len(text))
            parent_id = ids_by_heading[id(heading.parent)] if heading.parent is not None else None
            child_counts[parent_id] = child_counts.get(parent_id, 0) + 1
            sid = f"s-{child_counts[parent_id]}" if parent_id is None \
                  else f"{parent_id}-{child_counts[parent_id]}"
            ids_by_heading[id(heading)] = sid

            body_start = min(line_starts[heading.line_index]
                             + len(lines[heading.line_index]) + 1, len(text))
            blocks: list[DocumentBlock] = []
            if body_start < next_start:
                for n, block in enumerate(_detect_blocks(text, [(body_start, next_start)]), start=1):
                    blocks.append(DocumentBlock(
                        block_id=f"b-{sid}-{n}", type=block.type, text=block.text,
                        start_char=block.start_char, end_char=block.end_char,
                    ))
            sections.append(DocumentSection(
                id=sid, title=heading.title, level=heading.level,
                parent_id=parent_id, start_char=line_starts[heading.line_index],
                end_char=next_start, blocks=blocks,
            ))

        return _build_tree(sections)
```

**Hashability note (implementation-critical):** `Heading` is a mutable `@dataclass`
(`eq=True, frozen=False`), hence **unhashable** — it cannot be a `dict` key. The
`ids_by_heading` map is therefore keyed by `id(heading)` (stable for the duration of
the loop; references are held by the `headings` list). An alternative (parallel
index list) is acceptable; the spec pins the semantics, not the key choice.

**Complexity:** `_detect_headings` O(n); `line_starts` O(n); per-section
`_detect_blocks` calls sum to O(n) total because the body ranges partition the body.
Whole `analyze` is **O(n) single linear scan** (frozen §3; asserted by P2-306).

### 5.6 `source` parameter and preamble (normative behavior)

- `source` is **accepted, not read** (frozen §4.1 signature fidelity; P2-305 passes
  `str(document.source)`). Documented so a reviewer does not flag it as dead code —
  it is a public-API contract parameter for the shared M2.4/2.5/2.6 call site.
- **Preamble** (text before the first heading) is **not** covered by any section and
  its lines are dropped from the tree. The frozen models define no heading-less
  section, and roadmap D4 roots IDs at the first heading. This is a **documented
  limitation** and is pinned by a test (`TestPreambleDropped`), not a defect.

### 5.7 Public entry points (normative pseudocode)

```python
def get_default_structure_analyzer() -> StructureAnalyzer:
    """Return a StructureAnalyzer (frozen §4.3 composition root)."""
    return StructureAnalyzer()          # stateless; fresh instance is reentrant-safe (O-2)

def analyze_document_structure(text: str, source: str) -> DocumentStructure:
    """Analyze source text into a DocumentStructure (frozen §4.1 public API)."""
    return get_default_structure_analyzer().analyze(text, source)
```

## 6. Public Interfaces

### 6.1 Normative public API (frozen §4.1 — do not alter)

```python
class StructureAnalyzer:
    """Detect and build the hierarchical structure of source text."""
    def analyze(self, text: str, source: str) -> DocumentStructure: ...

def analyze_document_structure(text: str, source: str) -> DocumentStructure: ...
def get_default_structure_analyzer() -> StructureAnalyzer: ...
```

- **Import paths:** tests and P2-305 use
  `from app.infrastructure.document_intelligence import analyze_document_structure, get_default_structure_analyzer`
  (composition root) or
  `from app.infrastructure.document_intelligence.structure.detector import StructureAnalyzer, analyze_document_structure, get_default_structure_analyzer, _build_tree, MAX_SECTIONS`.
- **Contract:** never raises; `text` is the exact post-`clean_text` analyzed text (D1);
  `source` accepted-unused; result is a valid `DocumentStructure` with D4/D5 IDs,
  contiguous section spans, per-section blocks, empty-on-degenerate, truncated at
  `MAX_SECTIONS` with a `UserWarning`. Output is deterministic (R8) — identical input
  → identical `model_dump`.

### 6.2 Internal API (frozen §4.3)

```python
def _build_tree(sections: Sequence[DocumentSection]) -> DocumentStructure: ...
```

- `sections` = ordered `DocumentSection` list (document order); empty → empty
  structure; `len > MAX_SECTIONS` → warn + truncate. Never raises.

### 6.3 Not introduced here

`TEXT_BEARING_KINDS`, `max_structure_text_bytes` (P2-305/306), `structure.enabled`
settings, the `_run_routed_processor` hook, and any change to `ProcessedDocument`
(R-1). No `__all__` beyond the composition root's two re-exports.

## 7. Data Flow

```mermaid
flowchart LR
    T[exact text<br/>post-clean_text<br/>D1] --> L[lines = text.split'\n' + line_starts]
    T --> H[_detect_headings lines]
    L --> A[StructureAnalyzer.analyze]
    H --> A
    A --> S[for each heading in order]
    S --> I[id / parent_id via D4<br/>start_char / end_char via spans]
    S --> B[_detect_blocks text, [body range]]
    I --> SEC[DocumentSection<br/>blocks via D5]
    B --> SEC
    SEC --> BT[_build_tree sections]
    BT --> DS[DocumentStructure<br/>MAX_SECTIONS truncate + warn]
    DS --> ROOT[app/infrastructure/document_intelligence/__init__.py<br/>analyze_document_structure / get_default_structure_analyzer]
    ROOT -. P2-305 .-> ENR[metadata.extra["structure"]]
    ROOT -. P2-306 .-> CAP[5 MB cap + timing]
```

**Invariants (frozen §6):**
- Analysis runs on the **exact analyzed text** (D1) — offsets never drift (R2).
- Sections tile `[first_heading, len(text))` contiguously, non-overlapping.
- Heading lines are never blocks; blocks never span sections; fenced content is never
  a heading **or** a block (P2-302/303 invariants preserved through the tree).
- Degenerate input (empty / whitespace-only / no headings / malformed markup) →
  valid empty `DocumentStructure`, never an exception.
- `MAX_SECTIONS` truncation warns and preserves parent-reference validity.
- Deterministic output (R8): identical text → identical IDs and structure.
- No production path touches the analyzer until P2-305; no ingestion wiring.

## 8. Files to Modify

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/structure/detector.py` | **modify (append)** — `MAX_SECTIONS`, `StructureAnalyzer`, `analyze_document_structure`, `get_default_structure_analyzer`, `_build_tree`, and the section-assembly logic (§5). **P2-302/303 code untouched** (`_detect_headings`, `_detect_blocks`, `Block`, `BlockKind`, `_HEADING_RE`, `MAX_HEADING_LEVEL` unchanged). |
| `app/infrastructure/document_intelligence/__init__.py` | **modify** — composition root (frozen §4.3): re-export `analyze_document_structure` + `get_default_structure_analyzer` from `structure.detector`; keep the package docstring. |
| `tests/unit/test_structure_analysis.py` | **append** P2-304 test classes (frozen §13 names this file for the milestone's structure unit tests; P2-301/302/303 already append here). |
| `tests/fixtures/structure/empty.md` | **new** — 0-byte committed fixture (frozen §13 list; P2-303 spec §8 deferred it to P2-304 empty-tree testing). |

**Explicitly not modified:** `app/domain/document_intelligence.py` (P2-301 models),
`app/domain/processed_document.py` (R-1), `app/infrastructure/semantic_chunking.py`
(AC5 — byte-identical), `app/infrastructure/document_intelligence/structure/__init__.py`
(docstring marker stays), `app/infrastructure/ingestion/utils.py`, `app/core/config.py`,
`config/default.yaml`, `app/pipelines/ingest_workflow.py` (all P2-305), any existing
test or fixture. `oversize_text.txt` is P2-306's (generated in-test).

## 9. Configuration Impact

**None.** P2-304 declares no config keys and consumes no settings (frozen §7 / L5).
`MAX_SECTIONS` is a code constant (`ponytail:` fixed default, D6 / C-4), not a
`default.yaml` key. `intelligence.structure.*` is untouched until P2-305;
`enrich_analysis_input` remains contract-only (C-5, consumed by no code this
milestone). No `default.yaml` change.

## 10. Acceptance Criteria

| # | Criterion | Source | Evidence |
|---|-----------|--------|----------|
| AC1 | Sections contain the correct blocks; block IDs follow D5 (`b-<section.id>-<n>`, `n` restarts per section). | frozen §9 / D5 | `TestSectionAssembly`, `TestBlockIDs` — `blocks.md`/`nested_headings.md` through `analyze()`. |
| AC2 | Offsets are contiguous and non-overlapping; section spans tile the heading region; body excludes heading lines. | frozen §9 / §4.2 / R2 | `TestOffsetsContiguity` — `section[j].end_char == section[j+1].start_char`; block offsets within span; slice integrity. |
| AC3 | Section IDs are stable path IDs per D4 (`s-1`, `s-1-1`, …), incl. level-skip; `parent_id` links correct. | frozen §8 R8 / D4 | `TestSectionAssembly` (nested, siblings, level-skip) + `TestIDStability` (same input twice → identical `model_dump`). |
| AC4 | Degenerate input (empty / whitespace-only / no headings) → empty `DocumentStructure`; never raises on malformed input. | frozen §9 / §6 / R6 | `TestDegenerate` + `empty.md` fixture. |
| AC5 | `MAX_SECTIONS` truncates with a warning, never raises; kept parent references stay valid. | frozen §7 / C-4 | `TestMaxSections` — `pytest.warns` + `len == MAX_SECTIONS` on > cap input; constant value asserted. |
| AC6 | `StructureAnalyzer.analyze`, `analyze_document_structure`, and `get_default_structure_analyzer` exist with the frozen signatures and are reachable via the composition root. | frozen §4.1 / §4.3 | `TestAnalyzerEntry` — both import paths; `source` accepted; result type. |
| AC7 | Preamble (text before the first heading) is not in any section (documented limitation). | frozen §4.2 / D4 | `TestPreambleDropped`. |
| AC8 | No changes outside the listed files; P2-302/303 code unchanged; chunker byte-identical; full existing suite green. | frozen §9/§12/AC5 | Gate: full `tests` suite passes; ruff/mypy zero new; `git status` shows only the listed files. |

## 11. Definition of Done

- [ ] `_build_tree(sections)`, `StructureAnalyzer.analyze`, `analyze_document_structure`,
      `get_default_structure_analyzer`, and `MAX_SECTIONS` implemented in
      `structure/detector.py` matching §5.1–§5.7; P2-302/303 code untouched.
- [ ] Composition root `app/infrastructure/document_intelligence/__init__.py` exposes
      `analyze_document_structure` + `get_default_structure_analyzer` (frozen §4.3).
- [ ] Section assembly (D4), block assignment (D5), contiguous offsets (§5.1), degenerate
      input → empty tree, and `MAX_SECTIONS` warn+truncate all unit-tested (AC1–AC7).
- [ ] `tests/fixtures/structure/empty.md` committed (frozen §13) and exercised; existing
      structure fixtures reused through `analyze()`.
- [ ] No production code outside `structure/detector.py` + the composition root changed;
      nothing wired; `SemanticChunker` byte-identical (AC5 / AC8).
- [ ] All existing tests pass unchanged; coverage ≥ 80% with `detector.py` parser suite
      ≥ 90% (frozen §12 / R7, P2-302/303 precedent); `ruff` zero new errors; `mypy`
      zero new type errors.
- [ ] Single atomic commit per the milestone rollback contract (frozen §14).

## 12. Test Strategy

| Layer | Scope | Details |
|-------|-------|---------|
| Unit — entry points | `analyze()` returns `DocumentStructure`; `analyze_document_structure` delegates; `get_default_structure_analyzer` returns a working analyzer; both composition-root and detector import paths work; `source` accepted | inline |
| Unit — section assembly | Nested `# A` → `## B` → `### C` ⇒ `s-1`/`s-1-1`/`s-1-1-1`; siblings `# A`/`# B` ⇒ `s-1`/`s-2`; level-skip `# A` → `### C` ⇒ `C.parent_id="s-1"`, `s-1-1`; titles/levels/parent_id on `nested_headings.md` | inline + `nested_headings.md` |
| Unit — block assignment | Block IDs per D5 (`b-s-1-1`, `b-s-1-1-1`, …) with per-section restart; blocks from `blocks.md` land in the correct sections; a fenced block is one `code` block inside one section | `blocks.md`, `fenced_code.md` |
| Unit — offsets | `section[j].end_char == section[j+1].start_char`; last section `end_char == len(text)`; section slice contains the heading line; block slices exact; heading lines never in block text | `nested_headings.md`, `blocks.md` |
| Unit — degenerate | empty text / whitespace-only / no headings → `sections == []`; `empty.md` → empty; never raises on odd inputs (lone ` ``` `, `\r` lines) | `empty.md`, inline |
| Unit — MAX_SECTIONS | constant == 10_000; generated `"# h\n" * (MAX_SECTIONS + 1)` → `pytest.warns(UserWarning)` + 10_000 sections; exactly `MAX_SECTIONS` → no warning; truncation preserves parent-reference validity | inline generated text |
| Unit — ID stability | same text analyzed twice → identical `model_dump` (R8) | inline |
| Unit — preamble | text before first heading not in any section (pinned limitation) | inline |
| Unit — R-1 readiness | `analyze(...).model_dump(mode="json")` round-trips via `DocumentStructure.model_validate` (P2-305 channel) | inline |
| Regression | Full existing suite unchanged (chunker AC5, M2.2 suites, P2-301/302/303 tests) | `python -m pytest tests -q -p no:cacheprovider --cov=app --cov-report=term` |

**Fixtures:** `tests/fixtures/structure/empty.md` (new, 0 bytes); existing
`nested_headings.md`, `fenced_code.md`, `blocks.md`, `lists_and_quotes.md`,
`table_block.md` are fed **through `analyze()`** (not `_detect_*` directly) to assert
end-to-end tree behavior. No integration tests this task (P2-305 owns the
ingestion-path integration); no performance tests (P2-306 owns cap/timing).

## 13. Rollback Strategy

| Level | Mechanism | Detail |
|-------|-----------|--------|
| Per-task | Git revert of the single atomic P2-304 commit | Additive-only: new functions + composition-root re-exports + tests + one fixture; **nothing in `app/` calls the analyzer yet** (first production caller is P2-305), so a revert is a clean removal with zero blast radius. |
| Data | No persistence touched | The builder writes nothing; no `metadata.extra` key exists until P2-305. |
| Code | No legacy branch | P2-302/303 code, `SemanticChunker`, and all domain models untouched (AC8); the composition root change is two additive re-exports. |
| Dependency | None | No new packages. |
| Process | Frozen §14 | `intelligence.structure.enabled: false` flag rollback is not applicable until P2-305; the §14 per-task atomic-commit mechanism applies now. |

## 14. Risks

| # | Risk | L/I | Mitigation |
|---|------|-----|------------|
| 1 | D4/D5 ID numbering errors (off-by-one on path depth / per-section block restart). | M/M | Deterministic counters with the exact `s-*`/`b-*` strings pinned by tests (nested, siblings, level-skip, multi-block sections); frozen §15.4 example re-asserted. |
| 2 | Section span semantics ambiguity (heading line inside the span; last-section `end_char`). | M/M | §5.1 pins start-inclusive-at-heading / end-exclusive-at-next-heading / `len(text)` for the last; `TestOffsetsContiguity` + slice checks lock it. |
| 3 | Unhashable `Heading` breaks the id map. | L/M | Explicit §5.5 note: key by `id(heading)` (or parallel index); semantics specified, not the key type. |
| 4 | Per-section `_detect_blocks` fence state diverges from the one-call equivalent (a fence straddling a section boundary). | M/M | §5.3 invariant argument (boundaries only on heading lines, never inside fences); analyzer-level test: a fence inside one section stays one `code` block, and an unclosed fence swallows following `#` into the last section. |
| 5 | Preamble text silently dropped surprises consumers. | M/M | Documented limitation (§5.6) + `TestPreambleDropped` pins the behavior; P2-305 integration uses heading-bearing files. |
| 6 | `MAX_SECTIONS` truncation creates dangling `parent_id` references. | L/M | §5.4: parents precede children in document order, so the first `MAX_SECTIONS` entries keep valid references; asserted by test. |
| 7 | `source` accepted-unused flagged as dead code. | L/L | §5.6 documents it as a frozen §4.1 contract parameter for the shared M2.4/2.5/2.6 call site. |
| 8 | Coverage drops below 80% with the new surface. | M/M | Parser suite targets ≥ 90% (frozen §12 / R7); per-milestone `fail_under=80`. |
| 9 | A pathological input raises instead of degrading. | L/M | All composed operations (`_detect_headings`, `_detect_blocks`, arithmetic, pydantic construction from already-valid data) are never-raises; `TestDegenerate` covers empty/odd inputs. |

## 15. Complexity Estimate

**Low — 0.5 dev-day** (frozen §11.1 P2-304 row). Split: ~0.25 d assembly logic
(section spans, D4/D5 IDs, per-section block mapping, `_build_tree` truncation) and
~0.25 d tests + the `empty.md` fixture. No infrastructure, no wiring, no config, no
dependency changes. The genuinely non-trivial pieces are the ID counters (D4/D5) and
the body-range seam (§5.1); everything else is straightforward orchestration over the
two approved detectors.

## 16. Consistency Verification (frozen M2.3 spec)

| Spec element | Frozen source | Consistency |
|--------------|---------------|-------------|
| Deliverable = tree builder; file = `structure/detector.py` | §11.1 P2-304 row | ✅ `_build_tree` + `StructureAnalyzer` + entry points appended; analyzer first production caller of `_detect_blocks` |
| Internal API `_build_tree(sections)` | §4.3 | ✅ name kept verbatim; takes the assembled `DocumentSection` list, returns `DocumentStructure` |
| Normative `StructureAnalyzer.analyze(text, source) -> DocumentStructure` | §4.1 | ✅ signature verbatim; `source` accepted-unused (§5.6) |
| Public APIs `analyze_document_structure`, `get_default_structure_analyzer` | §4.1 | ✅ module functions with frozen names; composition-root exposure (§4.3) |
| Sections contain blocks; offsets contiguous; degenerate → empty tree | §9 P2-304 DoD / §12 | ✅ §5.1–§5.3, AC1/AC2/AC4 |
| Stable section IDs (R8) + D4 path scheme | §10 R8 / roadmap D4 | ✅ §5.2, AC3 + `TestIDStability` |
| Block IDs `b-<section.id>-<n>` (D5) | roadmap D5 / §15.4 | ✅ §5.3, AC1 (`b-s-1-1`, `b-s-1-1-1` match the §15.4 diagram) |
| `MAX_SECTIONS` cap warn+truncate (C-4) | §7 / §12 (P2-304 row) | ✅ §5.4, AC5 — **reconciliation:** roadmap §4 P2-306 also lists `MAX_SECTIONS`; frozen §12 attributes it to the P2-304 tree-builder row, and truncation is inherently a tree-builder concern, so P2-304 owns it; P2-306 retains the 5 MB cap + timing only |
| `MAX_HEADING_LEVEL` enforced (C-4) | §12 (P2-304 row) | ✅ no new code — P2-302 clamp + P2-301 `Field(le=6)` already enforce; documented §5.2 |
| Composition root exposes the two functions | §4.3 | ✅ §8 (reconciliation vs §11.1 file list documented in §4) |
| Empty fixture `empty.md` committed | §13 fixture list | ✅ created (P2-303 spec §8 deferred it here) |
| `ProcessedDocument` untouched (R-1) | §5.4 | ✅ explicit not-modified §8 |
| Chunker byte-identical (AC5) | §8 AC5 / §9 / §14 | ✅ explicit not-modified §8 |
| No wiring / no `metadata.extra` writes this task | §11.1 DoD / §5.4 | ✅ §4 "wiring" + rollback §13 |
| No config keys; caps as code constants (L5) | §7 / D6 / C-5 | ✅ §9 |
| Test file + committed fixtures | §13 / L6 | ✅ `test_structure_analysis.py` append + `empty.md` (existing fixtures reused via `analyze()`) |
| Waves / ordering (P2-302 → P2-304, P2-303 → P2-304) | §11.2 | ✅ consumes both wave-2 detectors; wave 3 |
| Atomic commit + rollback | §14 | ✅ §13 |

---

*End of P2-304 Implementation Specification. No code implemented by this document.*
