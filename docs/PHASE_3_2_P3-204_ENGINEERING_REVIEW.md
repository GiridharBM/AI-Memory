# Milestone 3.2 — P3-204 Engineering Review

**Task:** P3-204 — Handle structured content intelligently: preserve Markdown tables,
HTML tables, blockquotes, callouts, and definition lists; never corrupt structured
formatting; deliver implementation + tests + engineering review (stop after this
document).
**Review date:** 2026-08-07
**Contract:** Task statement (M3.2, P3-204) — structured blocks must survive chunking
atomically and byte-for-byte, never split by size or sentence, never merged with
surrounding prose, and structured formatting must never be corrupted.
**Approved design decision:** extend the P3-202/P3-203 block tokenizer inside
`SemanticChunker` — `_split_blocks` gains structured block kinds (`table`,
`html_table`, `blockquote`, `callout`, `definition`), each atomic with `structure_type`
(and `callout_type`) metadata; overlap treats all structured blocks as hard boundaries.
Conventions mirror the existing structure detector / `ingestion.utils`: the markdown
table verdict uses the shared `_TABLE_SEPARATOR_RE` (a `|`-leading pipe run is a table
only when it contains a separator row, exactly like `detector.py:82` and
`utils.py:13`), and `>`-leading lines group as blockquotes. No new dependencies.
**Verdict:** **APPROVED**

---

## 0. Review Method

Independent review — every claim re-derived from the live source and re-run gates:

- Task requirements re-read and mapped one-to-one to evidence (Section 1).
- Changed files read in full from source: `app/infrastructure/semantic_chunking.py`
  (468 lines, net +94 from P3-203's 374), new `TestStructuredContentChunking` class
  (21 tests) in `tests/unit/test_knowledge_engine.py`, new integration test
  `test_structured_content_through_pipeline` in `tests/integration/test_chunking_pipeline.py`.
  `app/pipelines/ingest_workflow.py` is untouched by P3-204.
- Full default suite re-run; integration-marked suite re-run; ruff and mypy re-run on all
  touched files; coverage re-run on the chunker; reviewer-authored probe exercised the
  structured behavior end-to-end (markdown/HTML tables, no-separator pipe runs,
  blockquotes with `>`-only blank markers, callouts of multiple types, definition lists
  with indented continuations, single-line/unclosed HTML tables, overlap hard
  boundaries, heading-metadata merge).
- Rollback re-verified by surgically reversing the P3-204 production edits (temp backup +
  SHA-256 byte verification, same method as P3-201/P3-202/P3-203) and running the full
  P3-204 test set under the revert, then restoring byte-identically and re-running.

---

## 1. Requirement Compliance

| Requirement | Independent verification | Result |
|-------------|--------------------------|--------|
| Preserve Markdown tables | A `|`-leading pipe run whose lines include a GFM separator row (`_TABLE_SEPARATOR_RE`, mirroring `utils.py:13`/`detector.py:82`) is a `table` block; `_split_long_section` emits it whole (in `_ATOMIC_KINDS`), so it is never sentence-split even when cells contain `. ` terminators and the block exceeds the budget (`test_table_never_sentence_split`). Verbatim, one chunk, `structure_type: table` | ✅ |
| Preserve HTML tables | A line containing `<table` (case-insensitive) opens an `html_table` block that swallows every line verbatim through `</table>` (or end of text when unclosed); single-line `<table>…</table>` and multi-line forms both stay one atomic chunk (`test_html_table_preserved_verbatim`, `_single_line_atomic`, `_unclosed_runs_to_end`) | ✅ |
| Preserve blockquotes | `>`-leading lines group verbatim into a `blockquote` block, including `>`-only blank markers between quote lines; never merged with surrounding prose (`test_blockquote_preserved_verbatim`, `test_blockquote_not_merged_with_prose`) | ✅ |
| Preserve callouts | A `>` block whose first content is `[!TAG]` (GitHub/Obsidian callout) becomes a `callout` block with `callout_type` (tag lowercased: note/tip/warning/caution/important); content preserved verbatim (`test_callout_detected_with_type`, `test_callout_type_variants`); plain blockquotes carry no `callout_type` | ✅ |
| Preserve definition lists | Pandoc-style `Term` / `: definition` lists (with indented continuation lines) group into a `definition` block; over-long lists stay atomic (`test_definition_list_preserved`, `test_definition_list_over_long_atomic`); a paragraph ending on a term line is not merged into the list (`test_paragraph_term_preceding_definition_not_merged`) | ✅ |
| Never corrupt structured formatting | Structured blocks are byte-for-byte verbatim, atomic (never size- or sentence-split), hard overlap boundaries (no prose tail prepended into a structure, no structure tail leaked out — `test_overlap_skipped_across_structured_blocks`), and never merged with prose; a pipe run WITHOUT a separator row stays a `paragraph` (mirrors the detector, avoiding false positives) | ✅ |

## 2. Acceptance Criteria (task deliverable set)

| Criterion | Independent verification | Result |
|-----------|--------------------------|--------|
| Implementation | `_TABLE_SEPARATOR_RE`, `_OPEN/_CLOSE_TABLE_RE`, `_CALLOUT_RE`, `_DD_RE`, `_ATOMIC_KINDS`, `_is_structured_line`; `_split_blocks` returns `(kind, text, extra_metadata)` with five new structured kinds; `chunk()` shortcut trigger generalized from `has_fence` to `has_structured` so under-budget structured sections still get metadata; `_split_long_section` routes all six atomic kinds through one path carrying `extra`; `_apply_overlap` treats `language`-or-`structure_type` chunks as hard boundaries | ✅ |
| Tests | 21 unit tests (`TestStructuredContentChunking`: verbatim markdown/HTML tables, no-separator pipe-run stays paragraph, single-line + unclosed HTML tables, blockquote with blank markers, not-merged-with-prose, callout detection/type variants/no-type, definition lists atomic + ends-before-prose + paragraph-term not merged, never sentence-split, overlap hard boundary, contiguous offsets, heading metadata, short-section metadata, determinism) + 1 pipeline integration test | ✅ |
| Engineering review | This document | ✅ |

## 3. Definition of Done

| DoD | Independent verification | Result |
|-----|--------------------------|--------|
| Unit | **1024 passed / 18 failed / 1 skipped / 1 deselected**; the 18 failures are ALL the pre-existing `ModuleNotFoundError` (`fitz`/`PIL`) set in 7 files P3-204 never touches (test_metadata_extractors ×2, test_ocr_engine ×2, test_ocr_engines ×6, test_ocr_pdf ×4, test_processor_wiring ×1, test_processors ×1, test_table_intelligence ×2). Chunking/tokenizer suites + integration chunking-pipeline file: **184 passed / 0 failed** (includes the 21 new tests) | ✅ |
| Integration | **28 passed / 6 failed / 2 skipped / 15 deselected**; the 6 failures are 5× pre-existing `fitz` env (email, image_pipeline ×3, ingestion_metadata) + 1× pre-existing live-Ollama smoke flake (O-3); the 6 chunking-pipeline tests (5 + 1 new) all pass | ✅ |
| Ruff | On the 3 touched files: 4 findings, ALL pre-existing (E501×3 + F841 in `test_knowledge_engine.py` at lines 962/987/1123/1433 — untouched classes; line numbers shifted further by the P3-204 insertions). `semantic_chunking.py` and `test_chunking_pipeline.py`: **All checks passed**. **Zero new findings** (one new E501 in a P3-204 test was caught and fixed during the gate run) | ✅ |
| Mypy | `mypy app/infrastructure/semantic_chunking.py`: **Success, no issues found**. **Zero findings** | ✅ |
| Coverage | `semantic_chunking.py` **99% (266 stmts, 2 miss)** under the chunking unit suites. The 2 uncovered lines (380-383) are the P3-203 documented defensive dead-guard `else` (empty `sentence_chunks`), unreachable with the built-in tokenizers and carried forward unchanged; all P3-204 branches are executed | ✅ |
| Rollback validation | Surgical revert to the P3-203 file (`24845CBA…`) → **20 failed / 2 passed** on the full P3-204 test set (19 unit + 1 integration feature-gated tests fail; the 2 passing are behavior-documentation guards that must hold both ways); byte-identical restore (`3C199B6C…`) → all 22 green. Clean both directions | ✅ |

## 4. Independent Verification Results

### 4.1 Runtime behavior — reviewer probe (`ALL PROBES PASSED`)
- `"Intro prose here.\n\n| Name | Value |\n|---|---|\n| alpha | 1 |\n| beta | 2 |\n\nOutro prose here."` at
  `max_chunk_chars=20` → 3 chunks, contiguous offsets (0-17 / 17-70 / 70-87), the table a
  verbatim single chunk with `{'structure_type': 'table'}` and
  `end_char == start_char + len(text)`.
- Multi-line `<table>…</table>` → one verbatim chunk with `{'structure_type': 'html_table'}`;
  single-line `<table><tr><td>x</td></tr></table>` → one chunk.
- Blockquote with `>`-only blank marker (`> a\n>\n> b`) → one verbatim chunk with
  `{'structure_type': 'blockquote'}`, isolated from leading/trailing prose.
- `> [!WARNING] Check this carefully.\n> Second callout line.` → one verbatim chunk with
  `{'structure_type': 'callout', 'callout_type': 'warning'}`.
- `Pythonsaurus\n: A large reptile.\n: It lives in swamps.\n    Continuation here.` → one
  verbatim chunk with `{'structure_type': 'definition_list'}`, indented continuation kept.
- `| a | b |\n| c | d |` (no separator row) → a `paragraph` chunk with no `structure_type`
  — matches the detector convention.
- Overlap (`max_chunk_chars=40, overlap_chars=10`) on `PPPP…\n\n<table>\n\nRRRR…` → three
  clean chunks: no prose tail prepended into the table, no table tail leaked into the
  following prose chunk.
- `# Title` + `> quote` + a table → every chunk carries the heading metadata merged with
  its structure metadata (`{'heading': 'Title', …, 'structure_type': …}`).

### 4.2 Rollback behavior — full P3-204 test-set proof (independently re-verified)
Working tree is fully uncommitted, so rollback was proven by surgical per-file reversal
(temp backup + SHA-256 byte verification). Reverting `semantic_chunking.py` to the P3-203
state (`24845CBA…`) while **keeping the new tests** → **20 failed / 2 passed**:

- 19 unit failures — every structured-kind test fails as expected: the P3-203 chunker has
  no `table`/`html_table`/`blockquote`/`callout`/`definition` block kinds, no
  `structure_type`/`callout_type` metadata, no structured overlap boundaries, and its
  `has_fence` shortcut drops structure metadata for under-budget sections.
- Integration `test_structured_content_through_pipeline` fails: the P3-203 pipeline stores
  the table/callout/definition list as plain prose entries with no structure metadata.
- The 2 passing tests are behavior-documentation guards that must hold in both states:
  `test_pipe_run_without_separator_is_paragraph` (the detector-mirroring pipe-run verdict
  is a convention both chunkers share) and `test_structured_chunking_deterministic`
  (determinism holds with and without the feature).
- Restore → file hash identical to the pre-revert state (`3C199B6C…`) and all 22 P3-204
  tests green.
- Rollback is clean both directions; the new tests gate exactly P3-204 behavior.

### 4.3 Determinism
`_split_blocks`, `_TABLE_SEPARATOR_RE`/`_CALLOUT_RE`/`_DD_RE` verdicts, and
`_is_structured_line` are pure functions of their input text (fixed regex scans, no
RNG/clock/state). `chunk_id`/`chunk_index`/`start_char`/`end_char` are computed from the
same math as before P3-204. Unit test + live probe confirm identical output across fresh
chunker instances, including a document mixing every structured kind.

### 4.4 Backward compatibility
- **Chunk content contract unchanged for unstructured text:** paragraph packing, sentence
  splitting for over-long paragraphs, heading-section splitting, lists, and overlap all
  behave as in P3-203. `_split_blocks` for text with no structured lines produces exactly
  the same paragraph/list/code blocks as P3-203 — the new branches are only entered when
  their trigger line is seen, and the code-fence branch is byte-identical in behavior
  (its `{"language": lang}` metadata now flows through the `extra` dict instead of being
  re-instantiated in `_split_long_section`).
- **Engine paths:** masking and structured handling happen before any sentence split and
  are engine-independent; all 45 R-2 (heuristic/nltk/auto) tests pass unchanged.
- **Offsets invariant:** `end_char == start_char + len(text)` holds for every structured
  chunk (probed and unit-tested); the P3-202 documented blank-line-list divergence is
  unchanged.
- **One deliberate divergence:** a section that is under the chunk budget but contains any
  structured line now routes through the block path instead of the single-chunk shortcut
  (the P3-203 `has_fence` trigger generalized to `has_structured`). Such sections still
  produce the same chunk texts and offsets, but structured blocks are emitted as separate
  chunks carrying `structure_type` metadata — which is what makes overlap hard-boundary
  behavior and downstream structure filtering possible. Plain-prose sections are
  unaffected (identical single-chunk output, no metadata).

### 4.5 Ruff
`ruff check` on `semantic_chunking.py`, `test_knowledge_engine.py`,
`test_chunking_pipeline.py`: 4 findings, zero in P3-204 code. All are the pre-existing
E501/F841 issues in `test_knowledge_engine.py` classes P3-204 never touches
(`TestEntityTypeLiteral`, `KnowledgeGraph`, `EmbeddingService`); their line numbers moved
(754/779/915/1225 → 962/987/1123/1433) purely because the P3-204 test class inserts ~130
lines above them. One new E501 introduced in a P3-204 test was caught by this gate run and
fixed (line wrapped). The chunker and the integration test file report
**All checks passed**. **No new findings.**

### 4.6 Mypy
`mypy app/infrastructure/semantic_chunking.py`: **Success, no issues found.** The new
`_split_blocks` `(kind, text, dict[str, str])` return type and `_is_structured_line` are
fully typed; no environmental stub errors surface in the touched module.

### 4.7 Unit tests
Full default suite: **1024 passed / 18 failed / 1 skipped / 1 deselected**. The 18
failures are the same `fitz`/`PIL` `ModuleNotFoundError` set as P3-201/P3-202/P3-203 (7
files P3-204 does not touch). Chunking suite: `TestSemanticChunking` 15 +
`TestSemanticChunkingAllEnginePaths` 45 + `TestHierarchicalChunking` 9 +
`TestListAwareChunking` 13 + `TestCodeAwareChunking` 15 + `TestStructuredContentChunking`
21 + `test_sentence_tokenizer` 60 = **178 passed, 0 failed**, plus the 6 chunking-pipeline
integration tests. The two untracked PIL-requiring test files remain excluded as in
previous milestones.

### 4.8 Integration tests
`-m integration`: **28 passed / 6 failed / 2 skipped / 15 deselected**. Persistent
failures: 5× pre-existing `fitz` env (`test_email_attachment_ingestion.py`,
`test_image_pipeline.py` ×3, `test_ingestion_metadata.py`) and the documented live-Ollama
smoke flake O-3 (`smoke_test::test_live_ollama_analysis_and_note_generation`), which
failed in this run exactly as it has since P3-201. The 6 chunking-pipeline tests all pass,
including the new `test_structured_content_through_pipeline`, which pushes a heading +
prose + markdown table + callout blockquote + definition list through `IngestionWorkflow`
(`max_chunk_chars=200`, heuristic) and asserts each structure is stored as exactly one
verbatim entry with its `structure_type`/`callout_type` metadata and heading metadata
intact, and that no sibling entry carries structure metadata.

### 4.9 Coverage
`semantic_chunking.py` under the chunking unit suites: **99% (266 stmts, 2 miss)**. Every
new branch is executed: all five structured block kinds (including the no-separator
pipe-run paragraph verdict, the single-line/unclosed HTML-table close detection, the
callout-vs-blockquote first-line verdict, the definition-list continuation and
end-before-prose break, and the paragraph-ending-on-a-term break), the `has_structured`
shortcut, and the `_ATOMIC_KINDS` path in `_split_long_section`. The 2 uncovered lines
(380-383) are the P3-203 documented defensive dead-guard carried forward unchanged, so
coverage matches P3-203's 99% under the same methodology.

### 4.10 Performance
The structured tokenizer adds one linear pass over the section text (`_split_blocks`
scans each line once; `_is_structured_line` is a line-anchored `any()` over the section).
Structured blocks are emitted in O(1) per block regardless of size (never re-split or
re-scanned). All O(n); the ≤ 1 s per 1 MB ceiling is unaffected.

---

## 5. Findings

### Blocking
None.

### Recommended
None.

### Optional
- **O-1 (carried from P3-203, coverage delta):** the defensive `else` at
  `semantic_chunking.py:380-383` (over-long paragraph whose sentence split returns
  nothing) remains untestable with the built-in tokenizers, leaving chunker coverage at
  99% (2 missed lines). Unchanged from P3-203; no action required for P3-204.
- **O-2 (scope of definition-list support):** definition lists are detected in the
  Pandoc/`Term\n: definition` form (the common markdown dialect). A dd line whose
  continuation is a bare indented paragraph is preserved while the continuation lines are
  indented; after `clean_text` normalization the leading indentation is collapsed, so the
  integration pipeline groups the dd markers but a dedented continuation may become a
  separate paragraph. Content is never lost or corrupted — only grouped. If downstream
  ever requires exact definition-grouping across dedented continuations, the `clean_text`
  normalization would need revisiting; no consumer currently does.
- **O-3 (environmental, not a P3-204 defect):** the venv is missing optional deps
  (`fitz`, `PIL`, `pytesseract`), so 18 default + 5 integration tests fail on
  `ModuleNotFoundError`/import skip; the live-Ollama smoke flake O-3 is unchanged from
  P3-201/P3-202/P3-203. All verified identical with P3-204 reverted (Section 4.2).

---

## 6. Verdict

**APPROVED**

All six task requirements are implemented and independently verified. Markdown tables
(pipe-run + GFM separator verdict mirroring `utils.py`/the detector), HTML tables
(`<table>` through `</table>` or end of text), blockquotes (verbatim, `>`-only blank
markers included), callouts (`[!TAG]` first line, lowercased `callout_type`), and
Pandoc-style definition lists are each atomic block kinds — never split by size or
sentence, never merged with prose, never reflowed — and every structured chunk carries
stable `structure_type` (and `callout_type`) metadata merged with heading metadata.
Overlap treats structured blocks as hard boundaries so formatting stays byte-for-byte
under overlap, and the `has_structured` shortcut trigger gives short structured sections
the same metadata and boundary behavior as long ones. The change is purely additive
inside `SemanticChunker` (no dependency, no pipeline/API change); the pipe-run verdict
reuses the shared `_TABLE_SEPARATOR_RE` so a pipe run without a separator stays a
paragraph, exactly like the structure detector. Mypy reports zero findings, ruff zero new
findings, chunker coverage 99% (2 missed lines are the P3-203 unreachable guard, O-1), all
chunking/tokenizer suites and the chunking-pipeline integration file pass, and the
default/integration suites show the same pre-existing environmental failures and the same
documented live-Ollama flake as the reverted state. Rollback was proven in both directions
(revert to `24845CBA…` → 20 feature-gated P3-204 tests fail; byte-verified restore to
`3C199B6C…` → all green).

---

*End of P3-204 engineering review.*
