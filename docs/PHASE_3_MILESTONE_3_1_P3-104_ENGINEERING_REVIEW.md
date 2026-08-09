# Milestone 3.1 — P3-104 Engineering Review

**Task:** P3-104 — `SemanticChunker` integration (wire the sentence tokenizer in)
**Verdict:** **APPROVED**
**Date:** 2026-08-06
**Reviewer stance:** independent re-verification. The implementation report (`docs/PHASE_3_MILESTONE_3_1_P3-104_IMPLEMENTATION_REPORT.md`) was **not** trusted; every gate was re-run live against the code and environment.

---

## 1. Verdict Summary

| Gate | Verdict |
|------|---------|
| Approved spec / roadmap conformance | ✅ Pass — diff matches the P3-104 block exactly; D5/D5a/D8 honored |
| Acceptance Criteria | ✅ Pass — verified live, not only via tests |
| Definition of Done | ✅ Pass |
| Runtime behavior | ✅ Pass — incl. edge cases the report's tests don't cover |
| Rollback guarantees | ✅ Pass — independently re-verified |
| Deterministic behavior | ✅ Pass |
| Backward compatibility | ✅ Pass |
| Ruff | ✅ Zero new findings (5 pre-existing, unrelated) |
| Mypy | ✅ Clean |
| Unit tests | ✅ 138 (tokenizer+KE) / full suite 1001 passed |
| Integration tests | ✅ 29 passed / 1 skipped / 1 environmental fail (live Ollama; flaky, not P3-104) |
| Documentation | ✅ Pass — report and roadmap annotation accurate vs. reality |

**Blocking findings:** none.
**Recommended findings:** none.
**Optional findings:** 3 (see §5). None block the phase.

---

## 2. Approved Specification / Roadmap Conformance

Re-read the frozen P3-104 block and decisions verbatim. The diff (`git diff HEAD -- app/infrastructure/semantic_chunking.py`, +24/−4) delivers exactly the spec:

- `sentence_tokenizer: str = "auto"` dataclass field (public interface per spec — additive with default; `SemanticChunker()` still constructs).
- Engine resolved **once per instance** in `__post_init__` (D8) via `get_sentence_tokenizer` — the P3-101 resolution helper, consumed as the roadmap's "resolution helper consumed here" describes. `sentence_tokenizer.py` needed no change.
- `_split_by_sentences` delegates to `self._tokenizer.split(text)` in place of `_SENTENCE_END.split(text)`. Heading/paragraph/overlap logic, the single-space re-join, and the `start_char`/`end_char` math are byte-for-byte untouched (D5/D5a).
- `_SENTENCE_END` regex removed (sole consumer was `_split_by_sentences`; verified no other runtime reference remains).

The test diff shows **only additions** after `test_chunk_overlap_zero`; all 12 existing `TestSemanticChunking` cases are unchanged. The 3 new tests match the roadmap's "Tests to create" list.

---

## 3. Acceptance Criteria — live verification

**AC1 — chunk boundaries align with true sentence boundaries.** The over-long AC1 paragraph splits into exactly **2** chunks (`"Dr. Smith went to Washington."` / `"He arrived at 9:00 a.m."`). This is a genuine delegation gate: the old `_SENTENCE_END` regex split after `"Dr."` (followed by capital `S`), producing **3** — so the test fails against pre-P3-104 code (confirmed in the rollback run, §6).

**AC2 — governing byte-exact contract `"AAAA.BBBB."`.** Reproduced exactly under all three engine paths:
- `auto` (→ nltk): `['AAAA.', 'AAAA.BBBB.', 'BBBB.CCCC.', 'CCCC.DDDD.']`
- `heuristic`: identical
- `nltk`: identical
Also independently probed with a **multi-space** variant (`"AAAA.   BBBB. CCCC. DDDD."`): contract still holds — P3-103's O-1 concern (single-letter-abbrev merge) does not affect the all-caps governing fixture.

**AC3 — offsets preserved.** `test_chunk_overlap_offsets_preserved` passes unchanged. The D5a offset math is untouched (contiguity invariant verified live, §4).

**AC4 — existing `TestSemanticChunking` cases pass unchanged with default `"auto"`.** All 12 unchanged tests pass under the resolved nltk engine. No input in the existing suite triggers an engine divergence (all use single-space `"Sentence N."` / governing patterns, on which both engines are span-identical).

---

## 4. Runtime, Determinism, and Backward Compatibility — live verification

An independent probe exercised scenarios **not** covered by the report's tests:

- **Two over-long paragraphs in one section:** 7 chunks, offsets contiguous across the paragraph boundary (…79→95→130), no content loss, no crash.
- **Trailing whitespace in an over-long paragraph:** normalized at the boundary (D5) — `"One sentence here. Another one.   "` → 2 clean chunks, offsets ok.
- **Single sentence longer than `max_chunk_chars`:** preserved whole, not split or corrupted.
- **Empty / whitespace-only text:** `[]` (short-circuits before the tokenizer).
- **Heading path (non-sentence-split byte-compat):** `# Title\n\nFirst section.\n\n## Subtitle\n\nSecond section.` → 2 chunks with the pre-existing overlap concatenation (`First section.## Subtitle`), byte-identical in character to pre-P3-104 behavior.
- **Offsets contiguity on 6 randomized 400-char inputs:** all `ok` (chunk[i].end == chunk[i+1].start; end == start + len(text)).
- **Determinism:** identical output across two separately-constructed instances and repeated calls.
- **Backward compatibility:** positional ctor `SemanticChunker(2000, 200)` works; equality correct (same config equal, different `sentence_tokenizer` unequal, `_tokenizer` excluded via `compare=False`); repr clean (`repr=False`); bare ctor + `chunk()` works; fail-fast on unknown engine (`SentenceTokenizerSelectionError` at construction); D8 log fires at DEBUG on construction; explicit `heuristic`/`nltk` select correctly.
- **Nltk-absent path** (import-blocked subprocess): `SemanticChunker()` constructs, `auto`→heuristic with one warning, governing contract + AC1 both hold, no crash.

**Findings-relevant observation:** offsets remain D5a "concatenation positions" — e.g., in the two-paragraph probe, chunk 5's `start_char=95` while the raw text has `"Prof."` at 97 (the `\n\n` separator is not counted). This is the spec-frozen math (D5a), pre-existing and intentionally unchanged; recorded as O-1.

---

## 5. Findings

### Blocking
None.

### Recommended
None.

### Optional

- **O-1 — offsets are D5a concatenation positions, not raw-text positions.** `start_char`/`end_char` don't index the source document whenever separators aren't a single space or cross paragraph boundaries (verified: two-paragraph probe). Pre-existing, spec-frozen, and P3-104 correctly must NOT change it; P3-104's new offset test correctly locks the D5a contiguity invariant. Flagging for future work: consumers that use chunk offsets to slice the source text will be off wherever this applies.
- **O-2 — D4 degradation warning now fires at `SemanticChunker()` construction.** In an nltk-absent environment, every `SemanticChunker()` (including the startup construction at `ingest_workflow.py:247`) logs one warning. This is the intended D8-at-construction design + D4 semantics, and the report documents it — but it is a new log-emission point relative to pre-P3-104. Consider at P3-105 whether startup-time construction should be deferred or the warning downgraded when the degradation is already known.
- **O-3 — live-Ollama integration smoke test is environment-flaky.** `smoke_test.py::test_live_ollama_analysis_and_note_generation` passed on the implementation run and failed on this review run (it requires a live Ollama server; identical flakiness observed at the P3-102 and P3-103 baselines). Unrelated to P3-104; treat as environmental, not a regression.

---

## 6. Rollback / Regression Verification (independently re-run)

- **Rollback:** with `semantic_chunking.py` reverted to `HEAD` (pre-P3-104), `TestSemanticChunking` runs **13 passed / 2 failed** — the only failures are the two tests that require the new field/delegation (`test_sentence_aligned_chunks_ac1_fixture`, `test_heuristic_engine_deterministic`); the 12 existing cases and the offsets test pass under the old code. The new tests therefore gate exactly the P3-104 behavior, and rollback to the P3-103 chunker is clean.
- **Full default suite:** **1001 passed / 31 deselected** (P3-103 baseline 998; +3 net new, 0 regressions).
- **Tokenizer + knowledge-engine unit files:** **138 passed** (51 + 87, incl. the 3 new).
- **Integration:** 29 passed / 1 skipped (Tesseract not installed) / 1 environmental failure (O-3). `test_knowledge_engine_persistence.py` (constructs `IngestionWorkflow` with the chunker, asserts `_chunker is not None`): **2 passed**.
- **Mypy:** clean on `semantic_chunking.py` and `sentence_tokenizer.py`.
- **Ruff:** the 5 findings on the changed files are all **pre-existing** — `B007` at the committed `for _, end, txt` loop (`semantic_chunking.py:147`, untouched by the diff) and `E501`/`F841` in `test_knowledge_engine.py` at lines from prior working-tree work (renumbered by +6 from the test insertions; none in the P3-104 additions). Zero new findings.

---

## 7. Documentation Accuracy

The implementation report's claims were checked against re-run results: 15/15 `TestSemanticChunking`, 138 unit, 1001/31 full, mypy clean, ruff zero new, rollback (2 new tests fail on revert), D8-at-construction, fail-fast — all confirmed. The report's one non-reproducible figure, "integration 30 passed / 1 skipped", reflects its run; the review run hit the environmental Ollama flake (O-3) — a server-state difference, not a documentation error. The roadmap closure annotation and the module/class docstrings match the code.

---

## 8. Conclusion

P3-104 implements the frozen spec exactly: the tokenizer is wired into the chunker via an additive, backward-compatible field; resolution happens once per instance (D8) with the D5a re-join/offset math preserved; the change surface is minimal (+24/−4 in the module, +3 tests) and the only removed code (`_SENTENCE_END`) was dead after the delegation. All acceptance criteria and DoD items pass live; rollback is clean; deterministic; no regressions. P3-103's deferred boundary observations (O-1/O-2 of that review) were re-checked at the chunker level and behave correctly.

**Verdict: APPROVED.** Proceed to P3-105 in milestone order.

---

*End of P3-104 engineering review.*
