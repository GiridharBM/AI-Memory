# Milestone 3.1 — P3-103 Engineering Review

**Task:** P3-103 — NLTK `punkt_tab` sentence-tokenizer engine (optional)
**Verdict:** **APPROVED**
**Date:** 2026-08-06
**Reviewer stance:** independent re-verification. The implementation report (`docs/PHASE_3_MILESTONE_3_1_P3-103_IMPLEMENTATION_REPORT.md`) was **not** trusted; every claim below was re-run live against the code and the environment.

---

## 1. Verdict Summary

| Gate | Verdict |
|------|---------|
| Approved spec / roadmap conformance | ✅ Pass — P3-103 block, D1/D4/D5/D9, Wave-0 preflight all honored; deviation recorded and user-approved |
| Acceptance Criteria (AC1, AC2) | ✅ Pass — verified live, not only via tests |
| Definition of Done | ✅ Pass — optional-dep path proven both ways; wheel preflight recorded; governing-fixture conformance verified |
| Runtime behavior | ✅ Pass — D5 reconstruction, determinism, selection stability, edge cases |
| Rollback | ✅ Pass — P3-101/P3-102 state intact with engine absent |
| Ruff | ✅ Pass |
| Mypy | ✅ Pass |
| Unit tests | ✅ 51/51 |
| Integration tests | ✅ 29 passed / 1 skipped / 1 failed (pre-existing environmental Ollama smoke test, identical at the P3-102 baseline) |
| Documentation | ✅ Pass — report matches reality; docstring and roadmap annotation present |

**Blocking findings:** none.
**Recommended findings:** none.
**Optional findings:** 3 (see §5). None block the phase.

---

## 2. Deviation Verification (Wave-0 preflight — independently re-run)

The implementation deviates from D1's premise ("data ships bundled in the wheel — no model download, fully offline"). The deviation is user-approved and documented. Independent re-verification confirms every claim in the deviation:

1. **Wheels carry no data.** Inspected the preflight artifacts (`C:\Users\girid\AppData\Local\Temp\opencode\wheelpreflight\`): nltk **3.8.1** and **3.9.0** wheels (`py3-none-any`) contain only `nltk/tokenize/punkt.py` — zero tokenizer data files. Confirmed again on the **installed 3.10.2**: a recursive scan of the package directory finds no `punkt_tab`, `.pickle`, or `.tab` files. "Bundled data" is factually false for every nltk release. The report's claim is accurate.
2. **Bare `PunktSentenceTokenizer()` fails AC1.** Live: `len(t._params.abbrev_types) == 0` and `"Dr. Smith went to Washington. He arrived at 9:00 a.m."` splits into **3** sentences (`['Dr.', 'Smith went to Washington.', 'He arrived at 9:00 a.m.']`). The engine correctly requires the pretrained model.
3. **`PunktTokenizer` + `load_lang` exist in the pinned range.** Grepped the nltk **3.9.0** wheel source: `class PunktTokenizer` and `def load_lang` both present, and present in installed 3.10.2. The `nltk>=3.9` pin is valid.
4. **D9 behavioral preflight passed.** `PunktTokenizer("english")` on `"AAAA. BBBB. CCCC. DDDD."` → `['AAAA.', 'BBBB.', 'CCCC.', 'DDDD.']`, identical to the regex engine — the `"AAAA.BBBB."` overlap regression contract is preserved. D9 contingency correctly **not** triggered.

The deviation (use pretrained `PunktTokenizer("english")` with a documented one-time `nltk.download("punkt_tab")` for the optional `intelligence` extra) is the correct response to a false premise, faithfully recorded in the report (§1), the roadmap annotation, and the module docstring. Runtime stays offline after setup.

---

## 3. Acceptance Criteria — live verification

**AC1 — with nltk installed, the AC1 fixture → exactly 2 sentences.**
Live probe: `get_sentence_tokenizer("nltk").split("Dr. Smith went to Washington. He arrived at 9:00 a.m.")` → exactly the two expected spans. Also covered by `TestNltkTokenizer::test_ac1_fixture_is_exactly_two_sentences` (runs on nltk 3.10.2 + `punkt_tab`).

**AC2 — with nltk absent, `"auto"` logs one warning and returns the heuristic engine.**
Two independent live subprocess probes (fresh interpreters, no test fixtures):
- **Data absent** (`nltk.data.path` forced to an empty dir): registry = `['heuristic']`, `_nltk_available() == False`, `auto → _HeuristicSentenceTokenizer`, one warning logged, empty/whitespace → `[]`, no crash, exit 0.
- **NLTK absent** (`find_spec` meta-path hook raising `ImportError` for `nltk.*`): identical result — registry = `['heuristic']`, `auto → heuristic` + one warning, explicit `"nltk"` → `SentenceTokenizerSelectionError`, no crash.

Both directions of the optional-dep DoD clause behave exactly as specified. (The `TestNltkAbsentFallback` unit test is env-independent via `monkeypatch`, so this gate also holds on CI machines without nltk.)

---

## 4. Runtime, Determinism, and D5 — live verification

An independent probe (18 cases + randomized inputs + a 50-sentence document) exercised the real nltk engine:

- **D5 reconstruction** held on all 18 cases — AC1, governing fixture, CJK `"甲。乙。"` and `"甲。 乙。"`, decimals, `U.S.A.`, `etc.` mid-sentence, multi/leading/trailing whitespace, trailing fragment, no-terminator, quoted `!`/`?`, ellipsis, empty/whitespace-only, mixed punctuation. Every split partitions the input with whitespace-only gaps; no content loss.
- **Determinism:** 3 runs × 5 random 200-char inputs → identical output; `auto` selection stable across calls.
- **Long-document:** 51 spans from a 50-sentence doc, D5 holds, no dropped content.
- **Edge-case observations** recorded as O-1/O-2 below; both satisfy D5 (no content loss) and neither is in the AC list.

Coverage: **97%** on the module (missing lines 205, 208–209 = the guard's absent branches — `_PunktTokenizer is None` / `except LookupError` — unexecutable in an nltk+data environment; both paths were exercised manually via the subprocess probes above).

---

## 5. Findings

### Blocking
None.

### Recommended
None.

### Optional

- **O-1 — multi-space boundary merge.** `"A.   B.  C."` → `['A.', 'B.  C.']`: nltk treats single-letter `B.` as an abbreviation and, absent a newline, does not break after it. D5 holds (no content loss); deterministic; not in the AC list; same class of inherent Punkt behavior as P3-102 O-1. No action needed — flag for the P3-104/P3-106 regression to confirm real-doc impact (docs rarely carry multi-space separators).
- **O-2 — leading whitespace joins the first span.** `"  A. B."` → `['  A.', 'B.']`. D5 permits this (the gap before span 1 is empty; whitespace is span content), but P3-104's single-space re-join will carry it. Confirm at P3-106 that no double-space leaks into chunker output from leading/trailing whitespace in source text.
- **O-3 — stale premise wording in the roadmap Objective.** The P3-103 Objective field still reads "data ships bundled in the wheel — no download, offline," which the deviation is known to have falsified. The deviation+closure annotation immediately below it corrects the record, so this is the correct historical artifact — leave it as-is (do not rewrite the false premise out; it documents what was caught).

---

## 6. Regression / Integration Verification

| Gate | Result (re-run) |
|------|------------------|
| Tokenizer unit suite | **51 passed** (P3-102 baseline 34; +17 net) |
| Full default suite | **998 passed / 31 deselected** (+17 net, 0 regressions) |
| Integration suite | 29 passed / 1 skipped (Tesseract not installed) / **1 failed** — `smoke_test.py::test_live_ollama_analysis_and_note_generation`; pre-existing environmental failure requiring a live Ollama server, identical at the P3-102 baseline, exercising `OllamaClient`/`ObsidianMarkdownGenerator` (untouched by P3-103) |
| Rollback (engine absent) | tokenizer suite **35 passed / 16 skipped** — the 34 P3-101/P3-102 tests + the env-independent absent-fallback test pass; nltk tests skip cleanly; `auto` degrades to heuristic + one warning |
| Ruff | clean on both modified files |
| Mypy | clean on the module |
| Public API | `SentenceTokenizer`, `get_sentence_tokenizer`, `register_sentence_tokenizer`, `SentenceTokenizerSelectionError` unchanged; nothing wired into ingestion |

The P3-101 O-1 test-hygiene fix (direct module-attribute assignment → `monkeypatch.setattr` in `test_selection_is_stable_per_call`) was re-checked: the old direct assignment leaked `_nltk_available = False` into later tests in the file; the fix is behavior-neutral and correctly confined.

---

## 6b. Deviation ratification note

The P3-103 deviation (one-time `nltk.download("punkt_tab")` vs. D1's "bundled" premise) should be ratified at the Phase 3 engineering spec review, as the implementation report recommends (§8). It does not change the approved ACs, DoD, or public interfaces of P3-103.

---

## 7. Conclusion

P3-103 is implemented to the approved spec within the recorded (user-approved) deviation. All acceptance criteria pass live; DoD is met; rollback is safe; the optional-dep path is proven in both directions (nltk+data present and absent); no regressions. The implementation is a minimal, correctly-guarded addition consistent with the milestone's backward-compatibility rules.

**Verdict: APPROVED.** Proceed to P3-104 in milestone order.

---

*End of P3-103 engineering review.*
