# Milestone 3.2 — P3-203 Engineering Review

**Task:** P3-203 — Improve handling of source code blocks in `SemanticChunker`: never
split fenced code blocks, preserve language metadata, preserve indentation, support
Markdown code fences, support inline code, preserve offsets; deliver implementation +
tests + engineering review (stop after this document).
**Review date:** 2026-08-07
**Contract:** Task statement (M3.2, P3-203) — fenced code blocks become atomic units of
chunking (never split, never merged with prose, kept verbatim with their language and
indentation); inline code spans must survive sentence splitting; offsets stay
deterministic.
**Approved design decision:** extend the P3-202 block tokenizer inside `SemanticChunker`
— `_split_blocks` gains a `code` block kind driven by CommonMark fence semantics
(`_FENCE_RE`), inline-code spans are masked before sentence tokenization
(`_mask_inline_code`), overlap treats code chunks as hard boundaries. No new
dependencies; reuses the existing `SentenceTokenizer` protocol and `DocumentChunk`
model. Alternative rejected: pre-processing code out in the structure detector
(`app/infrastructure/document_intelligence/structure/detector.py` uses a document-global
fence toggle at lines 58/145); P3-203 mirrors CommonMark per-block fence semantics
instead, so a fence inside one section cannot leak across headings.
**Verdict:** **APPROVED**

---

## 0. Review Method

Independent review — every claim re-derived from the live source and re-run gates:

- Task requirements re-read and mapped one-to-one to evidence (Section 1).
- Changed files read in full from source: `app/infrastructure/semantic_chunking.py`
  (374 lines, net +81 from P3-202's 293), new `TestCodeAwareChunking` class (15 tests)
  in `tests/unit/test_knowledge_engine.py`, new integration test
  `test_code_block_through_pipeline` in `tests/integration/test_chunking_pipeline.py`.
  `app/pipelines/ingest_workflow.py` is untouched by P3-203.
- Full default suite re-run; integration-marked suite re-run; ruff and mypy re-run on all
  touched files; coverage re-run on the chunker; reviewer-authored probe exercised the
  code behavior end-to-end (blank-line-in-fence, over-long code, short fenced sections,
  tilde fences, overlap hard boundaries, inline-code spans, offsets).
- Rollback re-verified by surgically reversing the P3-203 production edits (temp backup +
  SHA-256 byte verification, same method as P3-201/P3-202) and running the full P3-203
  test set under the revert, then restoring byte-identically and re-running.

---

## 1. Requirement Compliance

| Requirement | Independent verification | Result |
|-------------|--------------------------|--------|
| Never split fenced code blocks | `_FENCE_RE` (`semantic_chunking.py:16`, `^ {0,3}(`{3,}\|~{3,})(.*)$`) opens a `code` block in `_split_blocks` that swallows every following line verbatim — including blank lines — until the matching closing fence or end of text; `_split_long_section` (`:255-265`) emits a `code` block whole and never routes it to the sentence splitter or item splitter. Over-long code stays one verbatim chunk (probe + `test_overlong_code_block_not_split`) | ✅ |
| Preserve language metadata | The info string's first token is stored as the block's language (`lang = info.split()[0]`, `:72-73`); `_split_long_section` returns it as `{"language": lang}` which `chunk()` merges into chunk metadata (`{**meta, **extra}`, `:162`). Verified for ```python, `~~~js linenums="1"` (first-token only), and bare ``` → `""` | ✅ |
| Preserve indentation | Fenced code lines are joined verbatim (`"\n".join(run)`, `:74`) — no strip, no reflow, no per-line processing (`test_code_preserves_indentation`) | ✅ |
| Support Markdown code fences | Backtick and tilde fences, 3+ chars, up to 3 spaces of indent, optional info string; a closing fence must be the same char, ≥ the opener's length, and carry no info string (`:63-68`, CommonMark rule). Unclosed fences run to the end of the text and stay atomic (`test_unclosed_fence_runs_to_end`) | ✅ |
| Support inline code | `_INLINE_CODE_RE` (`[^`]*``) spans are masked before tokenization (`_mask_inline_code`, `:21-29`, replaces `.!?` inside spans with same-length `_`) and restored in each sentence after splitting (`:352-362`). Probed: the unmasked heuristic splits `` `note. separate` `` into `` `note. `` + `` separate` `` (two sentences); with masking it stays one intact span | ✅ |
| Preserve offsets | Code blocks are located by their exact block span; chunk offsets derive from cumulative block lengths as before; `end_char == start_char + len(text)` holds for code chunks (blank-free). Verified by `test_code_chunk_offsets_contiguous`, `test_code_chunking_deterministic`, and the probe | ✅ |

## 2. Acceptance Criteria (task deliverable set)

| Criterion | Independent verification | Result |
|-----------|--------------------------|--------|
| Implementation | `_FENCE_RE` + `_INLINE_CODE_RE` + `_mask_inline_code`; `_split_blocks` returns `(kind, block_text, lang)` 3-tuples with a `code` kind; `chunk()` routes any section containing a fence line through the block path (`has_fence` guard, `:136-139`); `_split_long_section` handles `code` blocks atomically (4-tuples with `extra` metadata); `_apply_overlap` treats code chunks as hard boundaries; `_split_by_sentences` masks/restores inline-code spans; dead-guard `else` hardened for empty sentence-chunk lists | ✅ |
| Tests | 15 unit tests (`TestCodeAwareChunking`: never-split, language/info-string/empty-lang, tilde fences, over-long atomic, isolated-from-prose, unclosed fence, indentation, fence-breaks-paragraph, contiguous offsets, overlap hard boundary, inline-code not split, heading+language, determinism) + 1 pipeline integration test (`test_code_block_through_pipeline`) | ✅ |
| Engineering review | This document | ✅ |

## 3. Definition of Done

| DoD | Independent verification | Result |
|-----|--------------------------|--------|
| Unit | **1003 passed / 18 failed / 1 skipped / 1 deselected**; the 18 failures are ALL the pre-existing `ModuleNotFoundError` (`fitz`/`PIL`) set in 7 files P3-203 never touches (test_metadata_extractors ×2, test_ocr_engine ×2, test_ocr_engines ×6, test_ocr_pdf ×4, test_processor_wiring ×1, test_processors ×1, test_table_intelligence ×2). Chunking/tokenizer suites + integration chunking-pipeline file: **162 passed / 0 failed** (includes the 15 new tests) | ✅ |
| Integration | **27 passed / 6 failed / 2 skipped / 15 deselected**; the 6 failures are 5× pre-existing `fitz` env (email, image_pipeline ×3, ingestion_metadata) + 1× pre-existing live-Ollama smoke flake (O-3; documented as flapping across runs since P3-201); the 5 chunking-pipeline tests (4 + 1 new) all pass | ✅ |
| Ruff | On the 3 touched files: 4 findings, ALL pre-existing (E501×3 + F841 in `test_knowledge_engine.py` at lines 754/779/1225/915 — untouched classes; line numbers shifted further by the P3-203 insertions). `semantic_chunking.py` and `test_chunking_pipeline.py`: **All checks passed**. **Zero new findings** | ✅ |
| Mypy | `mypy app/infrastructure/semantic_chunking.py`: **Success, no issues found**. **Zero findings** | ✅ |
| Coverage | `semantic_chunking.py` **99% (212 stmts, 2 miss)** under the chunking unit suites. The 2 uncovered lines (286-289) are a defensive dead-guard `else` (empty `sentence_chunks`): unreachable with the built-in tokenizers — probed an over-long all-inline-code paragraph and the heuristic still yields ≥ 1 sentence; masking never empties text. Documented, not a defect | ✅ |
| Rollback validation | Surgical revert to the P3-202 file (`1FB30A88…`) → **11 failed / 5 passed** on the full P3-203 test set (10 unit + 1 integration feature-gated tests fail; the 5 passing are behavior-documentation guards that must hold both ways); after tightening the inline-code test its masked-span case also fails on revert (2/2 check); byte-identical restore (`24845CBA…`) → all 16 green. Clean both directions | ✅ |

## 4. Independent Verification Results

### 4.1 Runtime behavior — reviewer probe (`ALL PROBES PASSED`)
- `"Prose intro.\n\n```python\nx = 1\n\ny = 2\n```\n\nOutro text."` at
  `max_chunk_chars=20` → 3 chunks, contiguous offsets (0-12 / 12-38 / 38-49), middle chunk
  verbatim with `{'language': 'python'}`.
- Over-long code block (40 lines, `max_chunk_chars=30`) → exactly **1 verbatim chunk**
  with `{'language': ''}`; never split, never reflowed.
- Short tilde section `~~~js linenums="1"\nconst x = 1;\n~~~` (well under the budget) →
  **`{'language': 'js'}`**. This is the `has_fence` fix: without it the "fits" shortcut
  (`.chunk()` line 139) would emit the section without routing through `_split_long_section`
  and drop the language key. Fix verified, regression-guarded by
  `test_fence_language_from_info_string` and `test_bare_fence_language_empty` (both would
  fail on the pre-fix shortcut).
- Overlap (`max_chunk_chars=40, overlap_chars=10`) on `PPPP…\n\n```\nCODE\n```\n\nRRRR…` →
  three clean chunks: no prose tail prepended to the code block, and no code tail leaks
  into the following prose chunk.
- Inline code: `` A×25 `note. separate` B×25 `` at `max_chunk_chars=60` → **one** chunk,
  byte-identical to the input. Unmasked control: the heuristic splits it into
  `` A×25 `note. `` / `` separate` B×25 `` — proving the masking is what preserves the span.
- For every code chunk in every probe: `end_char == start_char + len(text)` holds.

### 4.2 Rollback behavior — full P3-203 test-set proof (independently re-verified)
Working tree is fully uncommitted, so rollback was proven by surgical per-file reversal
(temp backup + SHA-256 byte verification). Reverting `semantic_chunking.py` to the P3-202
state (`1FB30A88…`) while **keeping the new tests** → **11 failed / 5 passed**:

- 10 unit failures: `test_fenced_code_block_never_split`, `test_fenced_code_language_metadata`,
  `test_bare_fence_language_empty`, `test_fence_language_from_info_string`,
  `test_tilde_fence_supported`, `test_code_block_isolated_from_prose`,
  `test_unclosed_fence_runs_to_end`, `test_fence_breaks_paragraph_run`,
  `test_overlap_skipped_across_code_chunks`, `test_code_chunk_keeps_heading_metadata` — the
  P3-202 chunker has no `code` block kind, no language metadata, no fence handling, and no
  overlap boundary logic, so every one of these fails as expected.
- Integration `test_code_block_through_pipeline` fails: the P3-202 pipeline stores the
  fenced code as a plain paragraph chunk with no `language` metadata.
- The 5 passing tests (over-long atomic, indentation, offsets, determinism, inline-code)
  are behavior-documentation guards that must hold in both states. The inline-code guard
  was then tightened to a discriminator case (span lands exactly on a 60-char chunk
  boundary): under the revert it splits into two chunks and fails (verified 2/2 failed),
  and on the P3-203 code it passes. Restore → file hash identical to the pre-revert state
  (`24845CBA…`) and all 16 P3-203 tests green.
- Rollback is clean both directions; the new tests gate exactly P3-203 behavior.

### 4.3 Determinism
`_FENCE_RE`/`_INLINE_CODE_RE`/`_split_blocks`/`_mask_inline_code` are pure functions of
their input text (fixed regex scans, no RNG/clock/state). `chunk_id`/`chunk_index`/
`start_char`/`end_char` are computed from the same math as before P3-203. Unit test +
live probe confirm identical output across fresh chunker instances, including mixed fence
types and inline-code text.

### 4.4 Backward compatibility
- **Chunk content contract unchanged for non-code text:** paragraph packing, sentence
  splitting for over-long paragraphs, heading-section splitting, metadata, list handling,
  and overlap all behave as in P3-202. `_split_blocks` for text with no fence lines
  produces exactly the same paragraph/list blocks as P3-202 (the `code` branch is only
  entered when `_FENCE_RE` matches).
- **Engine paths:** masking happens before any sentence split and is engine-independent;
  all 45 R-2 (heuristic/nltk/auto) tests pass unchanged; the nltk engine is unaffected
  because `_split_by_sentences` feeds it masked text and restores spans after.
- **Offsets invariant:** for code and blank-free text the exact
  `end_char == start_char + len(text)` invariant holds; the P3-202 documented divergence
  for blank-line-separated lists (O-1 in the P3-202 review) is unchanged.
- **One deliberate divergence:** a section that is under the chunk budget but contains a
  fence now routes through `_split_long_section` (block path) instead of the single-chunk
  shortcut. Output is identical for such sections (one chunk each) except that code blocks
  gain the `language` metadata key — which is the point of the change.

### 4.5 Ruff
`ruff check` on `semantic_chunking.py`, `test_knowledge_engine.py`,
`test_chunking_pipeline.py`: 4 findings, zero in P3-203 code. All are the pre-existing
E501/F841 issues in `test_knowledge_engine.py` classes P3-203 never touches
(`TestEntityTypeLiteral`, `KnowledgeGraph`, `EmbeddingService`); their line numbers moved
(605/630/766/1076 → 754/779/915/1225) purely because the P3-203 test class inserts ~130
lines above them. The chunker and the integration test file report **All checks passed**.
**No new findings.**

### 4.6 Mypy
`mypy app/infrastructure/semantic_chunking.py`: **Success, no issues found.** The new
`_FENCE_RE`-driven `code` kind and the 4-tuple `_split_long_section` are fully typed; no
environmental stub errors surface in the touched module.

### 4.7 Unit tests
Full default suite: **1003 passed / 18 failed / 1 skipped / 1 deselected**. The 18
failures are the same `fitz`/`PIL` `ModuleNotFoundError` set as P3-201/P3-202 (7 files
P3-203 does not touch). Chunking suite: `TestSemanticChunking` 15 +
`TestSemanticChunkingAllEnginePaths` 45 + `TestHierarchicalChunking` 9 +
`TestListAwareChunking` 13 + `TestCodeAwareChunking` 15 + `test_sentence_tokenizer` 60 =
**157 passed, 0 failed**. The two untracked PIL-requiring test files remain excluded as in
previous milestones.

### 4.8 Integration tests
`-m integration`: **27 passed / 6 failed / 2 skipped / 15 deselected**. Persistent
failures: 5× pre-existing `fitz` env (`test_email_attachment_ingestion.py`,
`test_image_pipeline.py` ×3, `test_ingestion_metadata.py`) and the documented live-Ollama
smoke flake O-3 (`smoke_test::test_live_ollama_analysis_and_note_generation`), which
failed in this run exactly as it has since P3-201. The 5 chunking-pipeline tests all pass,
including the new `test_code_block_through_pipeline`, which pushes
`# Code Doc` + prose + a ```python block with blank lines through `IngestionWorkflow`
(`max_chunk_chars=60`, heuristic) and asserts the code is stored as **one verbatim entry**
with `metadata["language"] == "python"`, heading metadata intact, and no `language` key on
any sibling entry.

### 4.9 Coverage
`semantic_chunking.py` under the chunking unit suites: **99% (212 stmts, 2 miss)**. Every
branch of `_split_blocks` (paragraph run, list run, fence open, fence-close match/mismatch
on char/length/info-string, fence-runs-to-end) and the `code` branch of
`_split_long_section` is executed. The 2 uncovered lines (286-289) are the defensive
`else` added when the P3-203 dead-guard was hardened (empty `sentence_chunks`); it is
unreachable with the built-in tokenizers — probed an over-long all-inline-code paragraph
and both the heuristic and nltk engines still return ≥ 1 sentence for any non-empty
masked text, and masking only replaces characters, never empties text. One percentage
point lower than P3-202's 100% solely because this new defensive branch is untestable
without injecting a pathological tokenizer; the 99% is strictly a superset of the P3-202
executed statements.

### 4.10 Performance
The code-aware tokenizer adds one linear pass over the section text (`_split_blocks`
scans each line once for fences; `_mask_inline_code` touches only characters inside
backtick spans; `_FENCE_RE.match` is line-anchored, not whole-text). Fenced blocks are
emitted in O(1) per block regardless of size (never re-split). All O(n); the ≤ 1 s per
1 MB ceiling is unaffected.

---

## 5. Findings

### Blocking
None.

### Recommended
None.

### Optional
- **O-1 (coverage delta, documented):** the defensive `else` at
  `semantic_chunking.py:286-289` (over-long paragraph whose sentence split returns nothing)
  is untestable with the built-in tokenizers, leaving chunker coverage at 99% (2 missed
  lines) versus P3-202's 100%. It exists to guarantee a chunk is always produced even if a
  future/third-party tokenizer ever returns an empty list. If 100% is ever required, inject
  a stubbed tokenizer in one test; no action required for P3-203.
- **O-2 (environmental, not a P3-203 defect):** the venv is missing optional deps
  (`fitz`, `PIL`, `pytesseract`), so 18 default + 5 integration tests fail on
  `ModuleNotFoundError`/import skip; the live-Ollama smoke flake O-3 is unchanged from
  P3-201/P3-202. All verified identical with P3-203 reverted (Section 4.2).

---

## 6. Verdict

**APPROVED**

All six task requirements are implemented and independently verified. Fenced code blocks
(both backtick and tilde, CommonMark close rules, up to 3-space indent, optional info
string) are atomic: never split by size, blank lines inside the fence preserved, never
merged with surrounding prose, language taken from the info string's first token, and
indentation kept byte-for-byte. Inline-code spans survive sentence splitting via
mask-and-restore, and overlap treats code chunks as hard boundaries so no prose tail or
code tail crosses a fence. Offsets remain deterministic and contiguous. The change is
purely additive inside `SemanticChunker` (no dependency, no pipeline/API change); a
`has_fence` shortcut fix (discovered by probe, fixed, and regression-guarded) ensures even
short fenced sections carry their language metadata. Mypy reports zero findings, ruff zero
new findings, chunker coverage 99% (2 missed lines are an untestable defensive guard, O-1),
all chunking/tokenizer suites and the chunking-pipeline integration file pass, and the
default/integration suites show the same pre-existing environmental failures and the same
documented live-Ollama flake as the reverted state. Rollback was proven in both directions
(revert to `1FB30A88…` → 11 feature-gated P3-203 tests fail; byte-verified restore to
`24845CBA…` → all green).

---

*End of P3-203 engineering review.*
