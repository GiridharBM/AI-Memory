# Milestone 3.2 — P3-202 Engineering Review

**Task:** P3-202 — Semantic chunk boundaries: keep paragraphs intact, preserve
ordered/unordered/nested lists, avoid splitting inside list blocks, maintain
deterministic offsets; zero regression to P3-201/Phase 3.1
**Review date:** 2026-08-07
**Contract:** Task statement (M3.2, P3-202) — the chunker must keep paragraph and list
blocks whole, never split inside a list block or sentence-split list items, and keep
offsets deterministic. Deliverables: implementation, tests, engineering review (stop
after this document).
**Approved design decision:** list-aware block tokenization inside `SemanticChunker`
(native; reuses the `ingestion/utils.py:11` list-line convention), over the alternative
of pre-splitting lists in the structure detector.
**Verdict:** **APPROVED**

---

## 0. Review Method

Independent review — every claim re-derived from the live source and re-run gates:

- Task requirements re-read and mapped one-to-one to evidence (Section 1).
- Changed files read in full from source: `app/infrastructure/semantic_chunking.py`
  (293 lines, net +84 from P3-201's 209), new `TestListAwareChunking` class (13 tests)
  in `tests/unit/test_knowledge_engine.py`, new integration test in
  `tests/integration/test_chunking_pipeline.py`. `app/pipelines/ingest_workflow.py`
  is untouched by P3-202.
- Full default suite re-run; integration-marked suite re-run; ruff and mypy re-run on all
  touched files; coverage re-run on the chunker; reviewer-authored probe exercised the
  list behavior end-to-end (blank-line lists, nested ordered lists, sentence-fragment
  absence, paragraph+list blocks, determinism, empty text).
- Rollback re-verified by surgically reversing the P3-202 production edits (temp backup +
  SHA-256 byte verification, same method as P3-201) and running the full P3-202 test set
  under the revert, then restoring byte-identically and re-running.

---

## 1. Requirement Compliance

| Requirement | Independent verification | Result |
|-------------|--------------------------|--------|
| Keep paragraphs intact | `_split_blocks` (`semantic_chunking.py:17`) groups consecutive non-blank lines into `paragraph` blocks; paragraph blocks are packed whole by `_split_long_section` and only a single over-long paragraph reaches the existing `_split_by_sentences` path | ✅ |
| Preserve unordered lists | A block whose first line matches `_LIST_ITEM_RE` (`^(\s*)([-*+]|\d+[.)])\s+`, mirroring `ingestion/utils.py:11`) is a `list` block; short lists chunk verbatim, over-long lists split at whole-item boundaries | ✅ |
| Preserve ordered lists | Same `_LIST_ITEM_RE` covers `1.`/`1)`; verified by `test_short_ordered_list_stays_intact` and the runtime probe | ✅ |
| Preserve nested lists | Base-indent item lines delimit items; deeper-indented (`\s*` prefix) lines attach to their parent item, so nested children never split from the parent (`test_nested_items_never_split_from_parent`) | ✅ |
| Never split inside a list block | Over-long list blocks go to `_split_list_block` only — item-boundary splits, the sentence splitter never runs inside a list (`test_long_list_never_sentence_splits_items`, pipeline test) | ✅ |
| Deterministic offsets | Block/item tokenization is a pure function of the text (no RNG, no external state); chunk `start_char`/`end_char` derive from item lengths; two fresh chunkers produce identical `(text, start_char, end_char)` | ✅ |
| Zero regression to P3-201 / Phase 3.1 | All 15 `TestSemanticChunking` + 45 R-2 engine-path + 9 `TestHierarchicalChunking` + tokenizer tests pass unchanged; heading metadata flow untouched (P3-202 only changes `_split_long_section` block handling) | ✅ |

## 2. Acceptance Criteria (task deliverable set)

| Criterion | Independent verification | Result |
|-----------|--------------------------|--------|
| Implementation | `_LIST_ITEM_RE` + `_split_blocks` (paragraph/list block tokenizer) + rewritten `_split_long_section` + new `_split_list_block` in `SemanticChunker`; `_PARAGRAPH_SPLIT` (the blank-line paragraph splitter that sliced list blocks) deleted | ✅ |
| Tests | 13 unit tests (`TestListAwareChunking`: short unordered/ordered/nested, blank-line-in-list, item-boundary splitting, no-sentence-split, nested-parent fidelity, offsets, determinism, paragraph→list block break, fit-after-flush, empty input) + 1 pipeline integration test | ✅ |
| Engineering review | This document | ✅ |

## 3. Definition of Done

| DoD | Independent verification | Result |
|-----|--------------------------|--------|
| Unit | **1003 passed / 18 failed / 2 skipped / 34 deselected**; the 18 failures are ALL pre-existing `ModuleNotFoundError` (`fitz`/`PIL`) in 8 files P3-202 never touches (verified identical failure set with P3-202 reverted — Section 4.2); 1003 = 990 baseline + 13 new tests; 34 deselected = 33 + 1 new integration test | ✅ |
| Integration | **26 passed / 6 failed / 2 skipped**; the 6 failures are 5× pre-existing `fitz` env (email, image_pipeline ×3, ingestion_metadata) + 1× pre-existing live-Ollama smoke flake (O-3; the smoke test passed in one run and failed in another — flake, not P3-202); the 4 chunking-pipeline tests (3 existing + 1 new) all pass | ✅ |
| Ruff | On the 3 touched files: 4 findings, ALL pre-existing (E501×3 + F841 in `test_knowledge_engine.py` at lines 605/630/766/1076 — untouched classes; line numbers shifted +130 by the P3-202 insertions). **Zero new findings** | ✅ |
| Mypy | `mypy app/infrastructure/semantic_chunking.py`: **Success, no issues found**. **Zero findings** | ✅ |
| Coverage | `semantic_chunking.py` **100%** (157 stmts, 0 miss) under the chunking unit suites. One dead guard (`if not lines`) was removed during review — `"".split("\n")` returns `[""]`, never an empty list | ✅ |
| Rollback validation | Surgical revert to the P3-201 file (`9337F8F0…`) → exactly 6 unit + 1 integration P3-202 feature-gated tests fail; byte-identical restore (SHA-256 `1FB30A88…`) → all green. Clean both directions | ✅ |

## 4. Independent Verification Results

### 4.1 Runtime behavior — reviewer probe (`ALL PROBES PASSED`)
- Blank-line list (`- a\n\n- b`) chunks as one intact block `['- a\n\n- b']`.
- Nested ordered list (`1. x\n2. y\n   1. x2\n   2. y2\n3. z`) chunks as one block verbatim.
- Three multi-sentence items with `max_chunk_chars=40` produce one whole item per chunk —
  no `"two here."`-style sentence fragments, no mid-item splits.
- Paragraph + list + paragraph document chunks as a single intact block.
- Two fresh chunkers → identical `(text, start_char, end_char)`; empty input → `[]`.
- For every chunk in every probe: `end_char == start_char + len(text)` holds on
  blank-free lists (the invariant on which the offset test relies).

### 4.2 Rollback behavior — full P3-202 test-set proof (independently re-verified)
Working tree is fully uncommitted, so rollback was proven by surgical per-file reversal
(temp backup + SHA-256 byte verification). Reverting `semantic_chunking.py` to the P3-201
state (`9337F8F0…`) while **keeping the new tests** → exactly **6 unit + 1 integration
failures**:

- `test_long_list_splits_at_item_boundaries` (old code sentence-split the whole list
  into one chunk instead of two item-boundary chunks),
- `test_blank_line_inside_list_never_fragmented` (old code paragraph-split the blank-line
  list and sentence-fragmented each item),
- `test_long_list_never_sentence_splits_items` (old code produced fragment lines),
- `test_nested_items_never_split_from_parent` (old code returned a single unsplit chunk),
- `test_paragraph_followed_by_list_never_merged` (old code merged paragraph+list into one
  block),
- `test_split_list_block_empty_text` (the method does not exist on the P3-201 chunker),
- integration `test_list_block_through_pipeline` (old code stored sentence fragments like
  `"- Item 0 has several sentences … exceed the chunk budget."` without `Tail n.`).

The 7 remaining tests (short unordered/ordered/nested lists, short blank-line list,
offsets, determinism, fit-after-flush) hold in both states — correct, they are behavior
documentation / regression guards that must pass before and after. Restore → file hash
identical to the pre-revert state (`1FB30A88…`) and the full P3-202 test set green.
Rollback is clean both directions; the new tests gate exactly P3-202 behavior.

### 4.3 Determinism
`_split_blocks` and `_split_list_block` are pure functions of their input text (fixed
regex scans, no RNG/clock/state). `chunk_id`/`chunk_index`/`start_char`/`end_char` are
computed from the same math as before P3-202. Unit test + live probe confirm identical
output across fresh chunker instances, including nested and mixed-marker lists.

### 4.4 Backward compatibility
- **Chunk content contract unchanged for non-list text:** paragraph packing, sentence
  splitting for over-long paragraphs, heading-section splitting, metadata, and overlap
  all behave as in P3-201. `_PARAGRAPH_SPLIT` is deleted but its behavior (blank-line
  paragraph separation) is reproduced exactly by `_split_blocks` for text with no list
  lines — a blank-line-separated paragraph run produces the same paragraph blocks the old
  splitter produced.
- **Engine paths:** the list logic sits before any sentence split and is
  engine-independent; all 45 R-2 (heuristic/nltk/auto) tests pass unchanged.
- **One deliberate divergence:** when an over-long list whose items are separated by
  blank lines is split, the blank line at each item boundary is dropped from the chunk
  text (items are built from base-indent item lines; trailing blank lines fall at item
  ends and are stripped). Chunks remain contiguous in chunk space and offsets are
  deterministic; `end_char - start_char` equals the raw item span, so for blank-line
  lists `end_char - start_char == len(chunk.text) + 1`. For blank-free lists the exact
  `len` invariant holds. The milestone requires deterministic offsets, which this
  satisfies; exact source-slice identity is not required (and is already relaxed for
  stripped text). See O-1.

### 4.5 Ruff
`ruff check` on `semantic_chunking.py`, `test_knowledge_engine.py`,
`test_chunking_pipeline.py`: 4 findings, zero in P3-202 code. All are pre-existing
E501/F841 issues in `test_knowledge_engine.py` classes P3-202 never touches
(`TestEntityTypeLiteral`, `KnowledgeGraph`, `EmbeddingService`); their line numbers moved
(464/489/625/935 → 605/630/766/1076) purely because the P3-202 test class inserts ~130
lines above them. **No new findings.**

### 4.6 Mypy
`mypy app/infrastructure/semantic_chunking.py`: **Success, no issues found.** The new
`_split_blocks` and `_split_list_block` are fully typed; no environmental stub errors
surface in the touched module.

### 4.7 Unit tests
Full default suite: **1003 passed / 18 failed / 2 skipped / 34 deselected**. The 18
failures are the same `fitz`/`PIL` `ModuleNotFoundError` set as P3-201 (files P3-202 does
not touch). Chunking suite: `TestSemanticChunking` 15 + `TestSemanticChunkingAllEnginePaths`
45 + `TestHierarchicalChunking` 9 + `TestListAwareChunking` 13 = **82 passed, 0 failed**.
The two untracked PIL-requiring test files remain excluded as in previous milestones.

### 4.8 Integration tests
`-m integration`: **26 passed / 6 failed / 2 skipped**. Persistent failures: 5×
pre-existing `fitz` env (`test_email_attachment_ingestion.py`, `test_image_pipeline.py` ×3,
`test_ingestion_metadata.py`). The 6th is the documented live-Ollama smoke flake O-3
(`smoke_test::test_live_ollama_analysis_and_note_generation`) — it failed in one run and
passed in the next, both in the P3-202 state and in the reverted state, confirming it is a
pre-existing flake, not a P3-202 regression. The 4 chunking-pipeline tests all pass,
including the new `test_list_block_through_pipeline`, which pushes a 40-item blank-line
markdown list through `IngestionWorkflow` with `max_chunk_chars=60` and asserts every
stored entry is made of whole items (`line in items`), never a sentence fragment.

### 4.9 Coverage
`semantic_chunking.py` under the chunking unit suites: **100% (157 stmts, 0 miss)**. Every
branch of `_split_blocks` (list run, paragraph run, blank/`>`/`|` termination, list-start
termination of a paragraph) and `_split_list_block` (base-indent boundaries, item packing,
flush) is executed. During review one unreachable guard (`if not lines: return []` —
`"".split("\n")` can never return an empty list) was removed rather than left as dead
defensive code.

### 4.10 Performance
The list-aware tokenizer adds one linear pass over the section text (`_split_blocks`
splits into lines and scans each once; `_split_list_block` one more pass only for
over-long lists). Both are O(n) with no regex over the whole text (line-anchored
`_LIST_ITEM_RE.match` per line only). The ≤ 1 s per 1 MB ceiling is unaffected.

---

## 5. Findings

### Blocking
None.

### Recommended
None.

### Optional
- **O-1 (documented divergence):** blank lines between items of an over-long list are
  dropped at item boundaries (chunk text is the stripped item; the inter-item blank line
  is not part of any chunk). Chunk offsets are contiguous and deterministic in chunk
  space, but for such lists `end_char - start_char == len(text) + 1`. Blank-free lists
  keep the exact `end_char == start_char + len(text)` invariant, and non-list documents
  are byte-for-byte unchanged from P3-201. If downstream tooling ever requires verbatim
  document-slice reconstruction, the item builder should be revisited; no consumer
  currently does. No action required for P3-202.
- **O-2 (environmental, not a P3-202 defect):** the venv is missing optional deps
  (`fitz`, `PIL`, `pytesseract`, `docx`), so 18 default + 5 integration tests fail on
  `ModuleNotFoundError`/import skip; the live-Ollama smoke flake O-3 is unchanged from
  P3-201. All verified identical with P3-202 reverted (Section 4.2).

---

## 6. Verdict

**APPROVED**

All six task requirements are implemented and independently verified. The change is
purely additive and self-contained inside `SemanticChunker`: `_PARAGRAPH_SPLIT` (the
blank-line paragraph splitter that was slicing list blocks) is replaced by a deterministic
list-aware block tokenizer, over-long lists split at whole base-level item boundaries
(never mid-item, never via the sentence splitter), and ordered/unordered/nested lists plus
paragraphs stay intact. Offsets remain deterministic; the runtime probe passes every
scenario; chunker coverage is 100%; mypy reports zero findings; ruff introduces zero new
findings; the full default suite grows from 990 to exactly 1003 (13 new tests) with the
same 18 pre-existing environmental failures and the documented live-Ollama flake, all
confirmed identical with the change reverted. Rollback was proven in both directions
(revert → 7 feature-gated P3-202 tests fail; byte-verified restore → all green).

---

*End of P3-202 engineering review.*
