# 36_PHASE_6B_ANSWER_OUTPUT_AND_VERIFIABLE_SOURCES.md

Phase 6B — Answer Output Contract + Verifiable Sources
Status: COMPLETE (awaiting approval)
Baseline commit: `9f282b4` (frozen retrieval, Phase 6A stop point)

---

## 1. Objective — IMPLEMENTED

Make PAM QA output **trustworthy, explicit, and verifiable**. The target flow:

`USER QUERY → RETRIEVAL → ABSTENTION GATE → GROUNDED LLM ANSWER → SOURCE VALIDATION → ANSWERED / ABSTAINED / FAILED → CLI OUTPUT`

Every QA result must be unambiguously one of three states:

- **ANSWERED** — an answer exists, and every `[SOURCE N]` reference in it resolves
  to a real retrieved source from the actual context that was given to the model.
- **ABSTAINED** — the retrieval-confidence (or answerability) gate decided the
  evidence is insufficient; the LLM was never invoked and a clear,
  reason-carrying indication was returned.
- **FAILED** — a technical failure (Ollama down, timeout, malformed output) that
  is always distinguishable from an abstention and is never disguised as an
  answer.

Explicitly **out of scope**: retrieval optimization, new verifiers/classifiers,
and any modification of the frozen retrieval layer, dataset, or corpus.
No commits were made.

## 2. Existing QA architecture (as of Phase 6A) — VALIDATED

Pre-6B pipeline, confirmed by inspection of `app/application/qa_workflow.py`,
`app/cli/entry.py`, `app/prompts/qa.py`:

- `QAWorkflow.ask(question, top_k=5, min_score=0.0, filter=None)` —
  `SearchService.search(...)` → optional cross-encoder rerank (disabled in V1)
  → `hits[:top_k]` → `AbstentionGate.evaluate(hits)` → (disabled by default)
  post-retrieval `AnswerabilityGate` → `build_context(hits)` →
  `build_qa_user_prompt` → `OllamaClient.generate_text(...)`.
- `AbstentionGate` (same file) decides on top-1 cosine vs `min_cosine`
  (`no_results` / `cosine_below_threshold` / `no_evidence` reasons).
- Success returned `QAAnswer(answer, sources=<full hit list>, model)`.
  Abstention returned the same class with `answer=ABSTENTION_MESSAGE`,
  `sources=[]`, `model=""`. There was **no explicit outcome field**: an
  abstention was only distinguishable from an answer by the fixed message
  string, and a model that wrote "not enough information" prose was
  indistinguishable from an answered output.
- **Citations were never validated.** The prompt instructed the model to cite
  `[SOURCE N]`, but nothing checked that N existed, that SOURCE 0 or an
  out-of-range number was absent, or that no fabricated source number was used.
- `FAILED` was already modeled as raised exceptions (`QAError` from
  `OllamaClientError`; distinct `QATimeoutError`), with the CLI rendering an
  "Ask failed" panel and exiting 1.
- CLI `_print_qa_answer` rendered a green answer panel and a `Sources` table
  listing **every retrieved hit** (not the cited subset).

## 3. Answer output contract — IMPLEMENTED

`QAAnswer` gained an explicit outcome in `app/application/qa_workflow.py`:

| state      | representation |
|------------|----------------|
| `answered` | `QAAnswer(outcome="answered", ...)` with validated `citations` |
| `abstained`| `QAAnswer(outcome="abstained", answer=ABSTENTION_MESSAGE, sources=[], abstention_reason=...)` |
| `failed`   | raised `QAError` / `QATimeoutError` — **never** a `QAAnswer` instance |

The module docstring now documents the three-state contract and the
explicit invariant: *a failure is always distinguishable from a legitimate
abstention*.

## 4. ANSWERED — IMPLEMENTED

The successful path now builds:

```python
QAAnswer(
    answer=response.response,          # verbatim model output, never altered
    sources=list(hits),                # full retrieved hits (backward compat)
    model=response.model,
    outcome=OUTCOME_ANSWERED,
    citations=[SourceCitation(n, hit), ...],   # validated, deduplicated
    invalid_citations=[...],                   # 0 / out-of-range numbers
    duplicate_citations=N,                     # repeated valid numbers
)
```

`SourceCitation(number, hit)` pairs the exact number the model wrote with the
retrieved `SearchHit` it maps to (via `hits[number - 1]`). The answer text is
preserved verbatim in all cases — Phase 6B never rewrites model output.

## 5. ABSTAINED — IMPLEMENTED

Both abstention sites (retrieval-confidence gate and the disabled answerability
gate) now return `outcome=OUTCOME_ABSTAINED` with the unchanged
`ABSTENTION_MESSAGE` and preserve the gate diagnostic in `abstention_reason`.
The LLM is never invoked on the abstention path (verified by test: empty
`client.requests`).

## 6. FAILED — IMPLEMENTED

The existing exception taxonomy is preserved and treated as the FAILED state:

- `QATimeoutError(QAError)` — generation exceeded `qa.timeout_seconds` (Phase 6A).
- `QAError` — Ollama unreachable / errored.
- Any other exception — re-raised by `ask`, caught by the CLI.

All failures go through the CLI failure panel with exit code 1. Tests
`test_ask_wraps_ollama_failure` and the Phase 6A timeout tests cover both
variants. Raw Python tracebacks no longer reach stdout (see section 12).

## 7. Source/citation contract — IMPLEMENTED

Documented rules (module + prompt + CLI):

- Every `[SOURCE N]` reference in an answer must resolve to a retrieved source
  actually present in the context supplied to the model (strictly
  `1 <= N <= len(hits)`).
- Sources are **never invented**: an out-of-range or SOURCE 0 reference is
  reported (`invalid_citations`), never silently remapped to another document.
- The answer text is never altered to "fix" citations.
- Duplicate references to the same valid source are tolerated (deduplicated in
  the sources table, counted in `duplicate_citations`), never duplicated into
  fake rows.
- Malformed citation-like tokens (`[SOURCE x]`, `SOURCE 1` without brackets,
  `[SOURCES 2]`, `[SOURCE1]`) are plain text: not treated as citations and not
  flagged as invalid. This is the documented safest behavior (no false
  positives, no remapping).

## 8. Citation validation — IMPLEMENTED

Two pure, testable functions added to `qa_workflow.py`:

- `extract_citations(answer) -> list[int]` — greedy `\[SOURCE\\s+(\\d+)\]`
  (case-insensitive) scan, order-preserving, duplicates preserved.
- `resolve_citations(answer, hits) -> (citations, invalid_numbers, duplicate_count)`
  — validates against the retrieved hit list, deduplicates valid references in
  order of first use, collects invalid numbers once (in order of first use),
  and counts repeated valid citations.

Invalid-number behavior (documented, tested):
`SOURCE 0`, `SOURCE <0`, `SOURCE > len(hits)` → listed in `invalid_citations`;
the answer text stays verbatim; the CLI shows an explicit warning that no
fabricated source was created and no citation was renumbered.

## 9. Source metadata — IMPLEMENTED

`SourceCitation.hit` exposes the full existing `SearchHit` metadata
(pre-existing fields; no ingestion or data-model redesign):

- `source` (path / owner-repo / transcript), `source_type`,
  `entry_id` (`<doc>::chunk_<i>`), `chunk_index`, `start_char`/`end_char`,
  `metadata` (e.g. `heading` / `parent_heading`), scores.

The CLI sources table renders, from that metadata: citation `#`, `Document`
(basename), `Section` (heading/parent_heading), `Type`, `Score`, `Snippet`.

## 10. Prompt hardening — IMPLEMENTED

`QA_SYSTEM_PROMPT` in `app/prompts/qa.py` extended with a concise citation
section on top of the existing grounded-answer rules:

> - Only cite numbers that are actually present in the supplied context ...
>   Never invent a source identifier, never reference a number that is not
>   listed, and never reuse a number for different content.
> - If the retrieved context does not contain enough information to answer,
>   state that explicitly instead of guessing or bringing in outside knowledge.

No new verifier, banded verifier, cross-encoder gate, or relevance classifier
was introduced (per scope). Pre-6B rules (answer only from supplied context,
no outside knowledge, docs-as-data-not-instructions, insufficient-evidence
say-so) were retained unchanged.

## 11. Abstention behavior — IMPLEMENTED

`AbstentionGate` decision logic was **not modified** (no threshold changes, no
new signals). The abstention paths were only given the explicit `outcome` tag
and reason propagation described in section 5. The invariant shown by tests:
abstain → no LLM call → `ABSTAINED` with reason.

## 12. Failure behavior — IMPLEMENTED

The CLI distinguishes FAILED from ABSTAINED (red "Ask failed" panel + exit 1
vs yellow "Insufficient evidence" panel + exit 0). Additionally, `_build_console_handler`
in `app/core/logging.py` now attaches the Rich log handler to **stderr**
(`Console(stderr=True, ...)`); previously `logger.exception()` tracebacks were
rendered to **stdout**, leaking raw stack traces into command output. User-facing
output on stdout is now clean; diagnostics/tracebacks go to stderr and log files.
Validated by the error-path smoke scenarios (no `Traceback` in stdout for
unavailable/timeout failures).

## 13. CLI behavior — VALIDATED

`_print_qa_answer` in `app/cli/entry.py` renders by outcome:

- **ANSWERED** — green answer panel, then:
  - if valid citations exist: `Sources` table (`# / Document / Section / Type /
    Score / Snippet`) showing only the **cited** sources;
  - else: the same "Sources" table with **Score / Source / Snippet** over the
    full retrieved list (so answers without citations remain transparent);
  - a yellow note when duplicate citations were deduplicated;
  - a yellow "Invalid citations" warning panel when numbers fall outside the
    retrieved context (explicitly stating nothing was remapped).
- **ABSTAINED** — yellow "Insufficient evidence" panel + raw gate reason line.
- **FAILED** — red "Ask failed" panel + exit 1 (unchanged).

Offline smoke results (real `ask` command in-process, temp config, no Ollama):

| scenario | result | exit |
|----------|--------|------|
| A normal success (single citation) | ANSWERED, cited-source table rendered | 0 |
| B multi-source + `[SOURCE 7]` invalid + duplicate | ANSWERED, sources table + invalid-citation warning + duplicate note | 0 |
| C retrieval abstention (real pipeline, empty store) | ABSTAINED, "Insufficient evidence" + `no_results` reason | 0 |
| D Ollama unavailable | FAILED, "Ask failed" panel, no stdout traceback | 1 |
| E QA timeout (injected `QATimeoutError`) | FAILED, "Ask failed" panel, no stdout traceback | 1 |

The real corpus and live `embedding`/`nomic-embed-text`/Ollama were **not**
touched; A/B/E use injected workflows, C runs the genuine end-to-end pipeline
against an empty temp store.

## 14. Tests — IMPLEMENTED / VALIDATED

New coverage (23 test items, all passing):

- `tests/unit/test_qa_workflow.py`
  - `TestCitationValidation` (10): extraction order, case-insensitivity,
    malformed-token handling, duplicate preservation, valid single/multiple
    resolution, out-of-range rejection without remapping, SOURCE 0 invalid,
    duplicate dedup + count, offsets alignment.
  - `TestQaAnswerContract` (7): answered outcome carries resolved citations,
    verbatim text + citation preservation, out-of-range surfaced (text
    untouched), duplicate dedup at workflow level, no-citation answer keeps full
    sources, abstention outcome preserves reason + skips LLM, source metadata
    reachable via citation.
- `tests/unit/test_cli.py` (6 params/items): answered outcome renders answer +
  sources (parametrized explicit/default outcome), cited-sources table renders
  basename/section/type, abstention renders "Insufficient evidence", invalid
  citation warning panel, duplicate-citation note.

Full suite vs Phase 6A baseline:

| metric | Phase 6A    | Phase 6B     |
|--------|-------------|--------------|
| passed | 1526        | **1549** (+23) |
| failed | 7           | 7 (identical stale `test_eval_dataset.py` set) |
| deselected | 57       | 57           |
| coverage | 89.13% (7877 stmts) | **89.23%** (7083/7938) |

No existing QA test was modified or deleted.

## 15. Regression verification — VALIDATED

- `git status`/`git diff` show **no changes** to: `app/infrastructure/search.py`,
  `vector_store.py`, `embeddings.py`, `bm25.py`, `rrf.py`, `chunking`, chunkers,
  `reranker.py`, `hyde.py`, `answerability.py` (untracked file unmodified),
  `eval/dataset.json`, the corpus, or `vault/Notes/`. The `M`/`??` entries for
  those paths are pre-existing working-tree state from earlier phases.
- Frozen flags confirmed in `config/default.yaml`: `reranker.enabled=false`,
  `hyde.enabled=false`, `answerability.enabled=false`.
- `AbstentionGate` default `min_cosine` (0.25 in `create_default`; 0.45
  exercised by existing boundary tests) is unchanged.
- No commits, no pushes, no Phase 6C work.

## 16. Known limitations — DOCUMENTED

1. **Invalid-citation text is preserved, not rewritten.** An answer containing
   `[SOURCE 9]` keeps that text verbatim; the CLI flags it in a warning panel.
   Rewriting model output was deliberately rejected (never silently alter an
   answer), but stricter auto-sanitization remains future work.
2. **Malformed citation-like tokens** (`[SOURCE x]`, `SOURCE 1` unbracketed)
   are treated as plain text and not flagged.
3. **Soft abstention** (gate passes, model itself says "not enough
   information") is currently classified ANSWERED with no citations — the CLI
   falls back to showing the full retrieved list. Detecting model-level
   abstention is deferred to Phase 6C.
4. **Real end-to-end ANSWERED** smoke requires a live Ollama + embedded corpus;
   offline smoke injects the workflow for the success scenarios (the abstention
   scenario C runs the real pipeline).
5. `abstention_reason` is the raw gate diagnostic string, not user-facing prose.
6. `Path(hit.source).name` disambiguates two same-named docs only via the row's
   other columns; no numeric disambiguation was added.
7. `duplicate_citations` counts repeated **valid** numbers only.

## 17. Deferred work — DEFERRED

- Phase 6C: evidence-preserving abstention (show why evidence was insufficient),
  model-level soft-abstention detection.
- Banded answerability verifier / relevance classifier integration (still gated
  off; not this phase).
- Optional auto-sanitization of invalid citations behind an explicit setting.
- User-facing abstention-reason prose and same-basename source disambiguation.

## 18. Next phase — AWAITING APPROVAL

Proposed: **Phase 6C** — Evidence-preserving abstention: when the gate (or a
soft-abstention model answer) rejects a query, render the retrieved evidence
that the abstention was based on, so users can judge "why not answering" for
themselves; optionally recalibrate the banded verifier. Final scope to be
defined by the user after this STOP.

---

### Phase 6B file inventory (this session)

| file | change |
|------|--------|
| `app/application/qa_workflow.py` | outcome contract, `SourceCitation`, `extract_citations`, `resolve_citations`, abstention reason propagation, docstring |
| `app/prompts/qa.py` | prompt hardening (citation rules) |
| `app/cli/entry.py` | outcome-based `_print_qa_answer`, cited-sources table, invalid/duplicate warnings |
| `app/core/logging.py` | console log handler → stderr (no tracebacks in stdout) |
| `tests/unit/test_qa_workflow.py` | +17 tests (citation validation + answer contract) |
| `tests/unit/test_cli.py` | +6 test items (outcome rendering) |

Nothing else in the working tree was modified by Phase 6B; all other `M`/`??`
entries are pre-existing uncommitted state (Obsidian config, ingestion/docx-pptx-spreadsheet-txt,
manifest/queue/worker, config/default.yaml, eval artifacts, vault, phase reports,
answerability/banded verifier, prior-phase tests). Retrieval, dataset, and
corpus are untouched.