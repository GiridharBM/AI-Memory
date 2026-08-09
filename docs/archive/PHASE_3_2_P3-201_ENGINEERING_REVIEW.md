# Milestone 3.2 — P3-201 Engineering Review

**Task:** P3-201 — Hierarchical semantic chunking (heading hierarchy, parent-child
relationships, heading metadata on every chunk; deterministic; rollback-compatible;
zero regression to Phase 3.1)
**Review date:** 2026-08-07
**Contract:** Task statement (M3.2, P3-201) — detect Markdown heading hierarchy
(`#`…`######`), preserve parent-child section relationships, keep heading metadata
attached to every chunk, deterministic output, rollback compatibility, no Phase 3.1
regression. Deliverables: implementation, tests, engineering review.
**Approved design decision:** native in-chunker heading detection (user-selected over the
MEDD §7.4 `metadata.extra["structure"]` consumption seam; see O-1)
**Verdict:** **APPROVED**

---

## 0. Review Method

Independent review — every claim re-derived from the live source and re-run gates:

- Task requirements re-read and mapped one-to-one to evidence (Section 1).
- Changed files read in full from source: `app/infrastructure/semantic_chunking.py`
  (209 lines), `app/pipelines/ingest_workflow.py` (VectorEntry wiring), new
  `TestHierarchicalChunking` class in `tests/unit/test_knowledge_engine.py`, new
  integration test in `tests/integration/test_chunking_pipeline.py`.
- Full default suite re-run; integration-marked suite re-run; ruff and mypy re-run on all
  touched files; coverage re-run on the chunker; reviewer-authored probe exercised the
  hierarchy end-to-end (paths, parents, level-skip, preamble, determinism, empty-metadata
  rollback contract).
- Rollback re-verified by surgically reversing the P3-201 production edits (temp backup +
  SHA-256 byte verification) and running the **entire** suite under the revert, then
  restoring and re-running.

---

## 1. Requirement Compliance

| Requirement | Independent verification | Result |
|-------------|--------------------------|--------|
| Detect Markdown heading hierarchy (`#`…`######`) | `_split_by_headings` parses each ATX heading match into `level` (1-6 from `#`-run length) with the existing frozen pattern `^#{1,6}\s+.+` (`semantic_chunking.py:14`) | ✅ |
| Preserve parent-child section relationships | Parent = nearest preceding heading with a strictly lower level (level-skip handled: `# A` → `### C` parents C to A); `parent_heading` carries the immediate parent title | ✅ |
| Heading metadata attached to every chunk | `chunk()` attaches `dict(heading_meta)` to both single-section and `_split_long_section` sub-chunks; `_apply_overlap` preserves `metadata`; keys: `heading`, `heading_level`, `heading_path`, `parent_heading` | ✅ |
| Deterministic output | Metadata derived purely from the text scan (no state, no RNG); two fresh chunkers produce identical `[c.metadata for c in chunks]` (unit test + live probe) | ✅ |
| Rollback compatibility | Preamble and heading-less text keep Phase 3.1 `metadata == {}` (byte-identical behavior); chunk `text`/`start_char`/`end_char`/`chunk_id`/`chunk_index` math untouched — verified by surgical revert run (Section 4.2) | ✅ |
| No regression to Phase 3.1 | All 15 `TestSemanticChunking` + 45 R-2 engine-path tests pass unchanged; full-suite rollback proof both directions | ✅ |

## 2. Acceptance Criteria (task deliverable set)

| Criterion | Independent verification | Result |
|-----------|--------------------------|--------|
| Implementation | `SemanticChunker` hierarchy + metadata; `VectorEntry` metadata wired (`ingest_workflow.py` `metadata=chunk.metadata`) so hierarchy is persisted/retrievable | ✅ |
| Tests | 9 unit tests (`TestHierarchicalChunking`: root, nesting, siblings, level-skip, preamble, sub-chunk inheritance, overlap, determinism, empty-metadata) + 1 pipeline integration test | ✅ |
| Engineering review | This document | ✅ |

## 3. Definition of Done

| DoD | Independent verification | Result |
|-----|--------------------------|--------|
| Unit | **990 passed / 18 failed / 2 skipped / 33 deselected**; the 18 failures are ALL pre-existing `ModuleNotFoundError` (`fitz`/`PIL`) in 8 files P3-201 never touches (verified identical failure set with P3-201 reverted — Section 4.2); chunking suite fully green | ✅ |
| Integration | **26 passed / 5 failed / 4 skipped**; the 5 failures = 4× pre-existing `fitz` env + 1× pre-existing live-Ollama smoke flake (O-3, documented in the P3-106 review); the 3 chunking-pipeline tests (2 existing + 1 new) all pass | ✅ |
| Ruff | On all 4 touched files: 5 findings, ALL pre-existing (B007 `semantic_chunking.py:178`; E501×3 + F841 in `test_knowledge_engine.py` at lines 464/489/625/935 — outside P3-201 code). **Zero new findings** | ✅ |
| Mypy | `mypy` on the two changed app modules: 7 errors, ALL pre-existing environmental (missing stubs/modules for `faster_whisper`/`pytesseract`/`PIL`/`fitz`, numpy 3.12 syntax). **Zero new findings** | ✅ |
| Coverage | `semantic_chunking.py` **98%** (105 stmts, 2 miss = pre-existing `_split_long_section` lines 182/185); the P3-201 hierarchy code is 100% covered | ✅ |
| Rollback validation | Surgical revert → 25 failed (18 env + 7 feature-gated P3-201 tests); byte-identical restore (SHA-256 `9337F8F0…`) → 18 env failures only. Clean both directions | ✅ |

## 4. Independent Verification Results

### 4.1 Runtime behavior — reviewer probe (`ALL PROBES PASSED`)
Nested document (`# Top` / `## Middle` / `### Leaf` / `## Sibling`, with preamble):
paths `["Top", "Top/Middle", "Top/Middle/Leaf", "Top/Sibling"]`; parents
`["", "Top", "Middle", "Top"]`; levels `["1", "2", "3", "2"]`. Level-skip
`# A` → `### C` → path `A/C`, parent `A`. Preamble chunk keeps `{}`. Heading-less text
keeps `{}`. Two fresh chunkers → identical metadata. `start_char`/`end_char`/text
content unchanged from Phase 3.1 shape.

### 4.2 Rollback behavior — full-suite proof (independently re-verified)
Working tree is fully uncommitted, so rollback was proven by surgical per-file reversal
(temp backup + SHA-256 byte verification, not `git stash`). Reverting the P3-201
production footprint (`semantic_chunking.py` hierarchy + `ingest_workflow.py` metadata
line) while **keeping the new tests** → **25 failed**: the 18 pre-existing `fitz`/`PIL`
env failures plus exactly **7 P3-201 feature-gated tests**
(`test_single_heading_root`, `test_nested_heading_path_and_parent`,
`test_sibling_headings_reset_parent`, `test_level_skip_parents_to_nearest_lower`,
`test_preamble_chunk_has_no_heading_metadata`, `test_sub_chunks_inherit_heading_metadata`,
`test_overlap_preserves_heading_metadata`). Two P3-201 tests
(`test_no_headings_leaves_metadata_empty`, `test_heading_metadata_deterministic`) hold in
both states — correct, they are regression guards on Phase 3.1 empty-metadata behavior
and determinism, and must pass before and after. Restore → file hashes identical to the
pre-revert state (semantic_chunking.py `9337F8F0…`) and suite back to **18 failed /
990 passed** (the 7 gated tests green, env failures unchanged). Rollback is clean both
directions; the P3-201 tests gate exactly P3-201 behavior.

### 4.3 Determinism
Metadata is a pure function of the text scan (`_split_by_headings` stack over the same
regex matches the frozen `_HEADING_PATTERN`); no RNG, no clock, no external state.
Unit test + live probe confirm identical metadata across instances. Overlapped chunks
preserve their section metadata through `_apply_overlap` (the `metadata` field was
already carried there).

### 4.4 Backward compatibility
- **Chunk content contract unchanged:** `text`, `chunk_id`, `chunk_index`,
  `start_char`, `end_char`, and `source`/`source_type` are produced by the same
  `_split_by_headings` → `_split_long_section` → `_apply_overlap` pipeline; the only
  change is populating the previously-always-empty `metadata` field on heading-led
  chunks. Preamble and heading-less chunks keep `{}`.
- **Engine paths:** hierarchy is computed before any sentence split and is
  engine-independent; all 45 R-2 (heuristic/nltk/auto) tests pass unchanged.
- **No Phase 3.1 regression:** the 18 default-suite failures are byte-identical before
  and after P3-201 (all `fitz`/`PIL` `ModuleNotFoundError` in files P3-201 does not
  touch); the 983 pre-P3-201 passes grow to exactly 990 = 983 + 7 gated tests.

### 4.5 Ruff
`ruff check` on `semantic_chunking.py`, `ingest_workflow.py`, `test_knowledge_engine.py`,
`test_chunking_pipeline.py`: 5 findings, zero in P3-201 code. The B007
(`semantic_chunking.py:178`, `_split_long_section` — pre-existing, documented since
P3-106) and the four `test_knowledge_engine.py` findings (E501 at 464/489/935, F841 at
625) all predate P3-201 and sit outside the `TestHierarchicalChunking` class (lines
273-361). **No new findings.**

### 4.6 Mypy
`mypy app/infrastructure/semantic_chunking.py app/pipelines/ingest_workflow.py`:
7 errors, all pre-existing environmental (missing library stubs / uninstalled optional
deps: `faster_whisper`, `pytesseract`, `PIL`, `fitz`; numpy 3.12 `Type` syntax). None in
P3-201 code. **No new findings.**

### 4.7 Unit tests
Full default suite: **990 passed / 18 failed / 2 skipped / 33 deselected**. The 18
failures are `fitz`/`PIL` `ModuleNotFoundError` in `test_metadata_extractors.py` (2),
`test_ocr_engine.py` (2), `test_ocr_engines.py` (6), `test_ocr_pdf.py` (4),
`test_processor_wiring.py` (1), `test_processors.py` (1), `test_table_intelligence.py`
(2). Chunking suite: `TestSemanticChunking` 15 + `TestSemanticChunkingAllEnginePaths`
45 + `TestHierarchicalChunking` 9 = **69 passed, 0 failed**. Two extra untracked test
files (`test_image_intelligence.py`, `test_preprocess.py`) require PIL and are excluded
from the run (they are not in git, not part of any milestone baseline).

### 4.8 Integration tests
`-m integration`: **26 passed / 5 failed / 4 skipped**. Failures: 4× pre-existing
`fitz` env (`test_email_attachment_ingestion.py`, `test_image_pipeline.py` ×2,
`test_ingestion_metadata.py`) + 1× pre-existing live-Ollama smoke flake
(`smoke_test::test_live_ollama_analysis_and_note_generation` — the documented O-3,
live-model section nondeterminism). The 3 chunking-pipeline tests all pass, including the
new `test_hierarchical_heading_metadata_through_pipeline`, which asserts the stored
`VectorEntry.metadata` carries `heading_path` `["Top", "Top/Sub"]`, `parent_heading`
`["", "Top"]`, `heading_level` `["1", "2"]` through `IngestionWorkflow` with the fake
embedding service.

### 4.9 Coverage
`semantic_chunking.py` under the chunking unit suites: **98.10%** (105 stmts, 2 miss).
The 2 missed lines (182, 185) are the pre-existing paragraph-pack tail of
`_split_long_section`; every P3-201 line (`_split_by_headings` hierarchy stack,
metadata construction, chunk wiring) is executed. DoD coverage gate exceeded.

### 4.10 Performance
The hot path scan count is unchanged: `_split_by_headings` performed one
`_HEADING_PATTERN.finditer` before and after P3-201 (the old `positions` list became the
`matches` list). Per-heading work is O(1) amortized (stack push/pop), so the ≤ 1 s per
1 MB ceiling is unaffected; no benchmark regression possible by construction.

---

## 5. Findings

### Blocking
None.

### Recommended
None.

### Optional
- **O-1 (design-seam divergence, by decision):** the user explicitly selected native
  in-chunker heading detection over the MEDD §7.4 / roadmap G14 pinned seam
  ("Phase 3 reads `metadata.extra["structure"]` → `DocumentStructure` → maps
  `DocumentSection.id` → chunk `parent_id`"). P3-201 instead derives hierarchy from the
  chunker's own heading scan and attaches `heading`/`heading_level`/`heading_path`/
  `parent_heading` metadata directly to every chunk (and, via the one-line wiring, to
  persisted `VectorEntry.metadata`). This is self-contained and deterministic, but the
  structure-consumption seam is now a *potential future* consumer of the metadata rather
  than the mechanism — Phase 4 parent-child retrieval work should reconcile this before
  depending on either channel. No action required for P3-201.
- **O-2 (environmental, not a P3-201 defect):** the current venv is missing optional
  deps present at the M3.1 approval run (`fitz`, `PIL`, `pytesseract`), so 18 default +
  5 integration tests fail on `ModuleNotFoundError`. The failure set is byte-identical
  with P3-201 reverted (Section 4.2), proving none are attributable to this change.
- **O-3 (documented, pre-existing):** the `test_live_ollama_analysis_and_note_generation`
  smoke flake (live-model section nondeterminism) continues to fail intermittently;
  unchanged from P3-104/105/106 reviews.

---

## 6. Verdict

**APPROVED**

All six task requirements are implemented and independently verified. The change is
purely additive: heading hierarchy is derived natively and deterministically from the
existing heading scan, every chunk (including sentence-split sub-chunks and overlapped
chunks) carries `heading`/`heading_level`/`heading_path`/`parent_heading` metadata,
preamble and heading-less text preserve the exact Phase 3.1 empty-metadata behavior, and
the one-line `VectorEntry` wiring makes the hierarchy retrievable downstream. Full-suite
rollback was proven in both directions (revert → 7 feature-gated tests fail; byte-verified
restore → all green), the chunking suite is 69/69 across all three engine paths, ruff and
mypy introduce zero new findings, and chunker coverage is 98% with the hierarchy code
fully exercised. The only failures are pre-existing environmental (`fitz`/`PIL`) and the
documented live-Ollama smoke flake, all confirmed identical with the change reverted.

---

*End of P3-201 engineering review.*
