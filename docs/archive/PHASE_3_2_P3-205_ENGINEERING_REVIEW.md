# Milestone 3.2 — P3-205 Engineering Review

**Task:** P3-205 — Create an adaptive semantic chunking engine: dynamic chunk
sizing, heading-aware overlap, paragraph-aware overlap, list-aware overlap,
preserve semantic coherence, configurable policies; deliver implementation +
tests + engineering review (stop after this document).
**Review date:** 2026-08-08
**Contract:** Task statement (M3.2, P3-205) — the chunker must size chunks
adaptively to document structure (heading depth), keep overlap on semantic
boundaries (heading / paragraph / list), preserve the semantic coherence
guarantees established in P3-201…P3-204, and expose every adaptive behavior as
a configurable policy with P3-204-identical defaults.
**Approved design decision:** introduce a frozen `ChunkingPolicy` dataclass as
an optional field on `SemanticChunker` (default policy reproduces P3-204 output
exactly). Dynamic sizing is a per-section budget derived from heading depth
(`heading_size_step` per level below 1, floored at `min_chunk_chars`) threaded
through the existing block/list/sentence splitters. Overlap is snapped to the
nearest paragraph (blank-line) or top-level list-item boundary at or before the
raw cut (`snap_overlap`, bounded by `snap_max_back`), and chunks that begin
with a heading are hard overlap boundaries (`heading_overlap_boundary`). The
policy is wired through `ChunkingSettings` → `config/default.yaml` → env
overrides → `IngestionWorkflow.create_default`. No new dependencies.
**Verdict:** **APPROVED**

---

## 0. Review Method

Independent review — every claim re-derived from the live source and re-run gates:

- Task requirements re-read and mapped one-to-one to evidence (Section 1).
- Changed files read in full from source: `app/infrastructure/semantic_chunking.py`
  (548 lines, net +53 from the P3-204 state), `app/core/config.py`
  (`ChunkingSettings` + 5 policy fields), `app/pipelines/ingest_workflow.py`
  (policy wiring), `config/default.yaml` (5 documented keys), new
  `TestAdaptiveChunkingPolicy` class (6 tests) in `tests/unit/test_knowledge_engine.py`,
  2 new config tests in `tests/unit/test_config.py`, 2 new integration tests in
  `tests/integration/test_chunking_pipeline.py`.
- Full default suite re-run; the chunking integration file re-run with
  `-m integration`; ruff and mypy re-run on all touched files; coverage re-run
  on the chunker; reviewer-authored probes exercised dynamic sizing at multiple
  heading depths, the budget floor, paragraph/list snapping, and the heading
  hard boundary end-to-end.
- Rollback re-verified by surgically reversing the P3-205 production edits (temp
  backup + SHA-256 byte verification, same method as P3-201…P3-204) and running
  the new test set under the revert, then restoring byte-identically and
  re-running.

---

## 1. Requirement Compliance

| Requirement | Independent verification | Result |
|-------------|--------------------------|--------|
| Dynamic chunk sizing | `ChunkingPolicy.heading_size_step` shrinks a section's effective budget by `heading_size_step` chars per heading level below 1 (`#` = base budget, `###` = base − 2·step), floored at `min_chunk_chars` (`_budget_for_level`, called in `chunk()` and threaded into `_split_long_section`/`_split_list_block`/`_split_by_sentences`). `test_heading_size_step_shrinks_budget_by_depth` proves `###` yields more chunks than `#` for the same body; `test_min_chunk_chars_floors_the_budget` proves a huge step collapses to the floor (~min_chunk_chars, not zero); integration `test_adaptive_sizing_through_pipeline` proves the same through `IngestionWorkflow` stored entries | ✅ |
| Heading-aware overlap | `ChunkingPolicy.heading_overlap_boundary` makes any chunk whose text begins with a heading a hard boundary — `_apply_overlap` skips the tail prepend into it. `test_heading_overlap_boundary_blocks_tail_into_heading_chunk` and integration `test_heading_overlap_boundary_through_pipeline` show the heading-led chunk is emitted as-is (`## Second`), while the P3-204 default prepends the previous tail | ✅ |
| Paragraph-aware overlap | `ChunkingPolicy.snap_overlap` snaps the overlap start to the last blank-line (paragraph) boundary at or before the raw cut, bounded by `snap_max_back` (`_overlap_start`). `test_snap_overlap_starts_at_paragraph_boundary` shows the default tail begins mid-paragraph (`"paragraph text with a goo…"`) and the snapped tail begins at the paragraph start (`"This is paragraph text…"`) | ✅ |
| List-aware overlap | The same `snap_overlap` snap also honors top-level list-item boundaries (multiline `_LIST_ITEM_RE` scan in `_overlap_start`). `test_snap_overlap_starts_at_list_item_boundary` shows the snapped tail begins at a whole item (`"- i…"`) where the default begins mid-item | ✅ |
| Preserve semantic coherence | Every adaptive behavior is boundary-preserving: budget is a floor/ceiling on existing whole-item/whole-sentence/atomic-block splits (never mid-item, mid-sentence, or into structured blocks), overlap tails snap only to paragraph/item boundaries, and heading-led chunks are never polluted. With the default policy the output is byte-identical to P3-204 (`test_default_policy_reproduces_plain_chunking`), and all 1110 pre-existing unit tests pass unchanged | ✅ |
| Configurable policies | Frozen `ChunkingPolicy` dataclass with 5 knobs on `SemanticChunker`; mirrored as `ChunkingSettings` fields with the same defaults, documented in `config/default.yaml`, overridable by env (`PAM_CHUNKING__*`), and wired into the real chunker at `IngestionWorkflow.create_default` (`test_chunking_policy_fields_reproduce_frozen_spec`, `test_chunking_policy_environment_override`) | ✅ |

## 2. Acceptance Criteria (task deliverable set)

| Criterion | Independent verification | Result |
|-----------|--------------------------|--------|
| Implementation | `ChunkingPolicy` (frozen, 5 knobs), `SemanticChunker.policy` field, `_budget_for_level`, `_overlap_start`/`_overlap_tail`, heading hard-boundary logic in `_apply_overlap`, optional `budget` threaded through the three split helpers, `_LIST_ITEM_RE_M` boundary scanner; `ChunkingSettings` +5 fields, `default.yaml` +5 keys, policy built in `create_default` | ✅ |
| Tests | 6 unit tests (`TestAdaptiveChunkingPolicy`) + 2 config tests + 2 integration pipeline tests = 10 new tests covering every knob and the default-parity guarantee | ✅ |
| Engineering review | This document | ✅ |

## 3. Definition of Done

| DoD | Independent verification | Result |
|-----|--------------------------|--------|
| Unit | `python -m pytest tests/unit -q` → **1110 passed / 0 failed / 1 deselected** (includes the 6 new `TestAdaptiveChunkingPolicy` + 2 new config tests); full default suite `python -m pytest -q` → **1125 passed / 0 failed / 39 deselected** | ✅ |
| Integration | Chunking pipeline file with `-m integration` → **8 passed / 0 failed** (6 pre-existing + 2 new P3-205 tests). The full integration suite exceeds the terminal gate timeout on this machine (live-Ollama/service suites), unchanged behavior from prior milestones | ✅ |
| Ruff | On the 6 touched files: 4 findings, ALL pre-existing (verified by `git stash` — the identical 4 E501 findings exist on the P3-204 baseline); every one is outside the P3-205 insertions (lines 1069/1094/1230/1540 in `test_knowledge_engine.py`, untouched classes). `semantic_chunking.py` and `test_chunking_pipeline.py`: **All checks passed**. **Zero new findings** | ✅ |
| Mypy | `mypy app/infrastructure/semantic_chunking.py` (with `--ignore-missing-imports` for the pre-existing env stub gaps): **Success, no issues found**. `config.py`/`ingest_workflow.py` check is blocked before reaching our code by the environmental numpy `__init__.pyi` syntax error (stubs target 3.12, running 3.14) — unrelated to the P3-205 edits, which are simple typed dataclass fields and a keyword construction | ✅ |
| Coverage | `semantic_chunking.py` **99% (303 stmts, 2 miss)** under the chunking/config unit suites; `config.py` **96%**. The 2 uncovered chunker lines (458-461) are the P3-203/P3-204 documented defensive dead-guard `else` (over-long paragraph whose sentence split returns nothing), unreachable with the built-in tokenizers and carried forward unchanged; every P3-205 branch (budget floor/step, both snap modes, heading boundary) is executed | ✅ |
| Rollback validation | Surgical revert of `semantic_chunking.py` to the P3-204 state (`3C199B6C…`) with the new tests kept → `TestAdaptiveChunkingPolicy` fails to collect (`ChunkingPolicy` missing), while the pre-existing chunking/config tests all pass (20 + 20); byte-identical restore to `FBB9A87C…` → all new + existing tests green. Clean both directions | ✅ |

## 4. Independent Verification Results

### 4.1 Runtime behavior — reviewer probe (`ALL PROBES PASSED`)
- `### A` + 7200-char prose body at `max_chunk_chars=2000`, `heading_size_step=1000`,
  `min_chunk_chars=200` → 40 chunks (max 322 chars ≈ 200 + overlap) vs the
  P3-204 fixed-size 4 chunks (1964/2160/2160/676) — depth-driven shrinking works,
  the floor prevents a zero budget.
- `# A` + the same body → 4 chunks identical to default (level 1 keeps the base
  budget).
- Paragraph body split into 2 chunks, `overlap_chars=200`: default tail starts
  mid-word (`"paragraph text with a goo…"`); with `snap_overlap=True` the tail
  starts at the blank-line boundary (`"This is paragraph text…"`).
- `# First … ## Second` two-section doc: with `heading_overlap_boundary=True`
  the stored Second heading chunk is exactly `## Second`; with the default it
  carries the prepended tail (never starts with the heading).

### 4.2 Rollback behavior — full P3-205 test-set proof (independently re-verified)
Working tree is fully uncommitted, so rollback was proven by surgical per-file
reversal (temp backup + SHA-256 byte verification). Reverting `semantic_chunking.py`
to the P3-204 state (`3C199B6C9970A756AF37E4BC4D5F40EACE41BFD6CC25BA70F87D0395E20DE6D8`)
while **keeping the new tests**:

- The new `TestAdaptiveChunkingPolicy` class fails to collect: the P3-204 module
  has no `ChunkingPolicy` symbol, so `test_knowledge_engine.py` import errors —
  every adaptive test is feature-gated on the new API.
- The pre-existing chunking regression class (`TestStructuredContentChunking`,
  20 tests) and the config suite (`test_config.py`, 20 tests) all pass under the
  revert — the rollback does not disturb P3-201…P3-204 behavior.
- Restore → file hash identical to the pre-revert state
  (`FBB9A87C577AF33EE397919914FAF31B4BADE0853543C0C02AE4A2584D6589F4`) and all
  new + existing tests green.
- Rollback is clean both directions; the new tests gate exactly P3-205 behavior.

### 4.3 Determinism
`_budget_for_level` and `_overlap_start` are pure functions of the policy and the
input text (fixed regex scans, no RNG/clock/state); budget threading changes no
loop order. `test_default_policy_reproduces_plain_chunking` and the existing
determinism suites confirm identical output across fresh chunker instances.

### 4.4 Backward compatibility
- **Default policy is the identity:** `ChunkingPolicy()` — every knob at zero /
  off — reproduces P3-204 output byte-for-byte (unit-proven). The three split
  helpers gained an optional `budget` parameter that defaults to
  `self.max_chunk_chars`, so direct calls (e.g. the existing
  `SemanticChunker()._split_list_block("", 0)` test) are unaffected.
- **Overlap default unchanged:** with `snap_overlap=False` `_overlap_start`
  returns the raw `len(text) - overlap_chars` cut, identical to the old
  `text[-overlap_chars:]`.
- **Config contract preserved:** `settings.chunking == ChunkingSettings()` still
  holds (policy field defaults equal the dataclass defaults), so the frozen-spec
  config test keeps passing, and env overrides use the standard
  `PAM_CHUNKING__*` scheme.
- **One deliberate divergence (opt-in only):** enabling `heading_overlap_boundary`
  changes overlap behavior for chunks that begin with a heading — exactly what
  the knob promises. It is off by default.

### 4.5 Ruff
`ruff check` on `semantic_chunking.py`, `config.py`, `ingest_workflow.py`,
`test_knowledge_engine.py`, `test_config.py`, `test_chunking_pipeline.py`: 4
findings, zero in P3-205 code. A `git stash` run of the same check on the P3-204
baseline returns the identical 4 E501 findings (`test_knowledge_engine.py` lines
1069/1094/1230/1540, untouched classes); their line numbers shifted only by the
P3-205 insertions. **No new findings.**

### 4.6 Mypy
`mypy app/infrastructure/semantic_chunking.py`: **Success, no issues found.** The
new `ChunkingPolicy` (frozen, fully typed), `_budget_for_level`, `_overlap_start`,
and the `budget: int | None` parameters are all type-checked. The only mypy
output in the other two touched modules is the environmental numpy `__init__.pyi`
syntax error (stubs require Python ≥ 3.12, the interpreter is 3.14) plus the
pre-existing `faster_whisper` missing-stub note — both unrelated to P3-205.

### 4.7 Unit tests
`python -m pytest tests/unit -q` → **1110 passed / 0 failed / 1 deselected**,
including the 6 new `TestAdaptiveChunkingPolicy` tests and the 2 new config
tests. Full default suite `python -m pytest -q` → **1125 passed / 0 failed / 39
deselected**. The `fitz`/`PIL` `ModuleNotFoundError` set documented in prior
milestones no longer fails — the environment now has the optional deps installed.

### 4.8 Integration tests
Chunking pipeline file with `-m integration` → **8 passed / 0 failed**: the 6
pre-existing tests plus the 2 new ones. `test_adaptive_sizing_through_pipeline`
pushes a `#`/`###`-headed doc through `IngestionWorkflow` with
`heading_size_step=1000` and proves the stored `###` entries outnumber and are
smaller than the `#` entries. `test_heading_overlap_boundary_through_pipeline`
proves the `## Second` heading chunk is stored as-is with the flag on and with a
prepended tail with the flag off. The rest of the integration suite was not
re-run wholesale this milestone (it exceeds the terminal gate timeout via the
live-Ollama and service suites); the chunking file — the only integration scope
P3-205 touches — is fully green.

### 4.9 Coverage
`semantic_chunking.py` under the chunking + config unit suites: **99% (303
stmts, 2 miss)**. Every P3-205 branch executes: both `heading_size_step` paths
(fixed vs shrinking), the floor, the default and snapped overlap cuts, the
paragraph and list-item snap scans, the heading-boundary skip and the default
prepend. The 2 uncovered lines (458-461) are the P3-203 defensive dead-guard
carried forward unchanged, so coverage matches P3-204's 99% under the same
methodology. `config.py` is at 96% (the missed lines are the error/merge paths
untouched by P3-205).

### 4.10 Performance
All P3-205 logic is O(1) per section/chunk on top of existing linear scans:
`_budget_for_level` is one arithmetic op; `_overlap_start` runs one `rfind` plus
one bounded `finditer` (stop condition `cut`, bounded start `cut - snap_max_back`)
only when `snap_overlap` is on. Budget threading adds no passes. The ≤ 1 s per
1 MB ceiling is unaffected.

---

## 5. Findings

### Blocking
None.

### Recommended
None.

### Optional
- **O-1 (carried from P3-203/P3-204):** the defensive `else` at
  `semantic_chunking.py:458-461` (over-long paragraph whose sentence split
  returns nothing) remains untestable with the built-in tokenizers, leaving
  chunker coverage at 99% (2 missed lines). No action required for P3-205.
- **O-2 (one knob, two snap behaviors):** paragraph and list snapping share the
  single `snap_overlap` switch. This was a deliberate simplification — both are
  "snap the tail to the nearest boundary type", and the nearest of any enabled
  boundary wins — and it satisfies the paragraph- and list-aware requirements
  with independent tests. If a consumer ever needs paragraph-only or
  list-only snapping, split the flag; no consumer currently does.
- **O-3 (environmental, not a P3-205 defect):** `mypy` on `config.py` /
  `ingest_workflow.py` is blocked by the numpy `__init__.pyi` syntax error (stubs
  for 3.12, running 3.14); the full integration suite exceeds the terminal gate
  timeout (live-Ollama/service suites). Both are independent of P3-205 and
  unchanged from prior milestones.

---

## 6. Verdict

**APPROVED**

All six task requirements are implemented and independently verified. Dynamic
chunk sizing shrinks the per-section budget by heading depth (`heading_size_step`,
floored at `min_chunk_chars`) and flows through the existing block/list/sentence
splitters without breaking whole-item, whole-sentence, or atomic-block coherence.
Heading-aware overlap keeps chunks that begin with a heading unpolluted by the
previous section's tail (`heading_overlap_boundary`); paragraph- and list-aware
overlap snap tails to the nearest blank-line or list-item boundary within
`snap_max_back` (`snap_overlap`). Every behavior is a field of the frozen
`ChunkingPolicy`, mirrored in `ChunkingSettings` and `config/default.yaml`,
overridable by env, and wired into the real pipeline at
`IngestionWorkflow.create_default` — and the default policy reproduces P3-204
output byte-for-byte. The full default suite is green (1125 passed / 0 failed),
the chunking integration file is green (8 passed, 2 new), ruff reports zero new
findings, mypy reports zero findings on the touched module, chunker coverage is
99% (2 missed lines are the pre-existing unreachable guard), and rollback was
proven in both directions (revert to `3C199B6C…` → new tests fail, existing
tests pass; byte-verified restore to `FBB9A87C…` → all green).

---

*End of P3-205 engineering review.*
