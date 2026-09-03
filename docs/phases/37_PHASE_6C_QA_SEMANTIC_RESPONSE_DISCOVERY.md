# 37_PHASE_6C_QA_SEMANTIC_RESPONSE_DISCOVERY.md

Phase 6C — QA Semantic Response Handling (DISCOVERY ONLY)
Status: COMPLETE — no production code modified, no commits
Baseline commit: `9f282b4` (Phase 3F retrieval checkpoint; 6A/6B uncommitted working tree intact)

---

## 1. Objective — VALIDATED

Investigate the QA application-layer limitations left by Phase 6B and decide,
on evidence, whether they require implementation. Focus: model soft-abstention,
citation semantics (validity vs groundedness), the three-state output contract,
no-citation handling, CLI snippet quality, deterministic validation options,
failure-path ambiguity, and test coverage. **This phase made zero code changes.**

## 2. Frozen constraints — VALIDATED

- HEAD `9f282b4`; no commits/pushes/staging.
- `embedding = nomic-embed-text`, `min_cosine = 0.45`, `reranker.enabled=false`,
  `hyde.enabled=false`, `answerability.enabled=false` (confirmed in
  `config/default.yaml`).
- Retrieval, `eval/dataset.json`, real corpus, vault — untouched.
- Phase 6A/6B working-tree changes left exactly as they were.

## 3. Current QA flow — VALIDATED

Confirmed by inspection of `app/application/qa_workflow.py`, `app/prompts/qa.py`,
`app/cli/entry.py`, `app/infrastructure/search.py`, `app/core/logging.py`:

`ask()` → `SearchService.search` → (reranker off) → `hits[:top_k]` →
`AbstentionGate.evaluate` (`no_results` / `no_evidence` /
`cosine_below_threshold`) → (answerability off) → `build_context` (max 8 chunks,
12 000 chars, `[SOURCE N]` numbering, per-hit raw scores) →
`build_qa_user_prompt` → `OllamaClient.generate_text` (QA timeout 120 s) →
`resolve_citations` → `QAAnswer` (verdict in `outcome`).

- `AbstentionGate.evaluate`: empty hits → abstain; reranker-inactive path uses
  top-1 `cosine_score` vs `min_cosine` (0.25 in `create_default`; 0.45 in the
  frozen retrieval config; hardcoded per call site), BM25 never overrides.
- `SearchHit` carries `text/source/source_type/entry_id/chunk_index/start_char/end_char/
  metadata{heading, parent_heading}/cosine_score/bm25_score/rerank_score`.
- `resolve_citations` returns `(citations, invalid_numbers, duplicate_count)`,
  answer text never mutated.
- CLI `_print_qa_answer`: green "Answer" panel for answered; yellow
  "Insufficient evidence" for abstained; red "Ask failed" + exit 1 for FAILED;
  cited-sources table (`# / Document / Section / Type / Score / Snippet`) when
  citations exist, full retrieved list otherwise; yellow warnings for invalid /
  duplicate citations. Log/traceback output is on stderr (6B).

## 4. Soft-abstention behavior — INCONCLUSIVE (measured by inspection, not live data)

Observed classification: model prose such as *"I don't have enough
information…"*, *"The provided context does not contain…"*, *"I cannot
determine this from the sources…"* is stored **verbatim** in
`QAAnswer.answer` with **`outcome="answered"`**:

- **Becomes ANSWERED — yes.** There is no detection path before/after
  generation.
- **Citations attached — no** (the model typically emits none), so
  `citations == []`, `invalid_citations == []`, `duplicate_citations == 0`.
- **Full source list shown — yes.** With no citations the CLI falls back to
- rendering the entire retrieved hit list (`result.sources`, Score/Source/Snippet).
- **Is it harmful?** Moderately. The behavior is *transparent* (all retrieved
  context is displayed, so a reader can judge for themselves) but the
  *labeled state is wrong*: a green "Answer:" panel implies answerability, and
  programmatically a truthful self-abstention is indistinguishable from an
  answered/no-citation response. This weakens the 6B "explicit contract" goal.
- **Deterministic detection reliability — INCONCLUSIVE / not yet validated.**
  There is **no local corpus of real LLM answers**: `eval/results/*.json`
  contain retrieval verdicts only (e.g. `answerability_eval.json` holds
  `answerability_insufficient_evidence` gate reasons, no generation text).
  English phrasing is distinctive but open-ended (negation, mixed answers such
  as "I can't find X, but Y is …", hedging), so a keyword/pattern detector has
  unknown false positive/negative rates until measured on live qwen3:8b output.
  **Decision: do not implement keyword matching now** — first collect N real
  answers and measure. (Measurement was not performed in this discovery phase;
  that requires a live Ollama run, which is outside discovery's frozen budget.)

## 5. Citation behavior — VALIDATED

| case | application-visible behavior |
|------|------------------------------|
| A valid citations | resolved to real hits via `resolve_citations`; cited-sources table shown |
| B no citations | accepted; `citations=[]`; full retrieved list shown |
| C invalid citations | listed in `invalid_citations`, never remapped; text verbatim; CLI warning panel |
| D mixed valid+invalid | valid resolved, invalid reported, both surfaced together |
| E duplicate citations | deduplicated in the table, counted in `duplicate_citations` |
| F resolves-but-unsupported | **not verifiable locally** — existence ≠ support |

What the application can verify **locally today**: citation *syntax*, *range*
(1..len(hits)), *presence*, and *duplication* — all deterministic.

What it **cannot** verify locally: whether a cited chunk actually *supports* the
claim (factor of paraphrasing, ellipsis, multi-hop, and the answer draw from up
to 12 000 context chars). Existing components that touch this (the answerability
gate and the banded verifier) both require an LLM call and are disabled.

**Validity ≠ Groundedness.** Citation existence proves only that the model
referenced a supplied source; it does not prove factual correctness. This report
does not claim otherwise.

## 6. No-citation behavior — VALIDATED (with a noted labeling gap)

A generated answer with zero citations is currently **accepted as ANSWERED**.
The prompt (`QA_SYSTEM_PROMPT`) instructs the model to cite every source it
uses, so a no-citation answer can mean: (a) a truthful soft abstention,
(b) a prompt violation (used context, cited nothing), or (c) a legitimate
content answer that needs no citation and faithfully falls back to
documenting insufficiency. The application cannot currently distinguish these.

## 7. Invalid-citation behavior — VALIDATED

Implemented in 6B and confirmed: out-of-range numbers (including 0) are
collected (deduplicated, order-preserving), surfaced in `invalid_citations`,
rendered as a yellow warning panel ("No fabricated source was created and no
citation was renumbered"), never silently remapped, never mutated in the answer.
Malformed tokens (`[SOURCE x]`, unbracketed `SOURCE 1`) are treated as plain
text and not flagged. This is a deliberate, documented, safe posture.

## 8. Answer/source relationship — INCONCLUSIVE

The CLI "Snippet" column shows a 200-character whitespace-collapsed prefix of
`hit.text`. Residual risks, verified by inspection:

- The context given to the model is *truncated* at `MAX_CONTEXT_CHARS = 12 000`
  (per `build_context`); the snippet is taken from the **full** stored chunk, so
  a displayed snippet can differ from the exact text the model saw.
- The snippet is the whole chunk preview, not the specific span the model cited.
- There is no local mechanism (no `difflib`/overlap util; grep found none) to
  tie an answer sentence to a cited span.

None of this mislabels which source a `[SOURCE N]` maps to (that is exact), but
"Snippet" is *approximate evidence*, not a quote-verified extract.

## 9. Three-state contract evaluation — VALIDATED (sufficient)

`ANSWERED / ABSTAINED / FAILED` covers every current flow unambiguously:

- answered → `outcome="answered"`, valid citations optionally present;
- abstained → gate rejected, fixed message, reason preserved, LLM not invoked;
- failed → `QAError`/`QATimeoutError` raised, never a `QAAnswer`.

The no-citation-answered case is *not* a new outcome — it is a flag *inside*
answered (`citations == []`) that the CLI already renders differently. Adding a
fourth state (`NO_CITATIONS`, `PARTIAL`, …) would be theoretical completeness
without a user-visible or programmatic need. **Recommendation: keep the
three-state contract; add at most an explicit "answered without citations"
surface label (not a new state).**

## 10. Failure-path evaluation — VALIDATED (one residual ambiguity)

| failure | current handling | ambiguity? |
|---------|------------------|------------|
| Ollama unavailable | `QAError` → FAILED, red panel, exit 1, traceback on stderr | none |
| timeout | `QATimeoutError` (distinct 6A) → FAILED, same | none |
| malformed response | not schema-checked (free text); any text is accepted | **yes** |
| invalid citations | warning panel, exit 0 (deliberate) | none |
| **empty answer** | `answer==""` → outcome `answered`, empty green panel, **exit 0** | **yes** |
| model exception (non-wrapped) | propagates to CLI catch-all → FAILED | none (minor: workflow should wrap) |

**Residual ambiguity:** an empty/whitespace answer is currently treated as a
successful ANSWERED. It is a degenerate generation output (a technical failure,
not an abstention — the gate already conveyed "no evidence" if that was the
case). This should be FAILED. This is the one clearly-correct deterministic fix
identified.

## 11. Deterministic validation options — VALIDATED (compare only, not implemented)

| option | expected benefit | false-positive risk | false-negative risk | latency | complexity | deterministic? |
|--------|------------------|--------------------|--------------------|---------|------------|----------------|
| A citation syntax validation | low-mid; catches formatting drift | low | medium (malformed unrecognized) | 0 | low | YES (implemented in 6B) |
| B citation range validation | high; kills fabricated `[SOURCE 9]` | none | none | 0 | low | YES (implemented in 6B) |
| C citation presence requirement | high for verifiability promise | **high** — blocks truthful citation-less answers; model formatting variance (bold, lists) | none | 0 | low | YES but fragile to model formatting |
| D semantic soft-abstention detection | mid; honest labeling | **medium** — negation/mixed answers | **high** — phrasing variance | 0 (local) | low-mid | NO (heuristic) |
| E answer-to-source textual overlap | mid; coarse groundedness signal | high (paraphrase, idioms, very short answers) | high (templates) | 0 | medium | YES (algorithmic, semantically weak) |
| F LLM-as-judge | high; matches the disabled answerability/banded gates | low-ish but nondeterministic | depends on judge model | +1 LLM call (seconds) | medium | NO |
| G no additional validation | zero | — | — | 0 | 0 | — |

## 12. Risk analysis — VALIDATED / DEFERRED

- Implementation of **C or D or E without data** risks either blocking truthful
  answers (C), mislabeling through phrasing/negation (D), or a meaningless
  "groundedness" number (E). None is justified today.
- **F** already exists in prototype form (`answerability.py`, `banded_verifier.py`,
  both disabled); enabling it is an operational/calibration decision, not a
  discovery answer — deferred, and explicitly out of the frozen scope.
- The only low-risk, correct-by-construction change is the **empty-answer guard**
  plus an **honest citation-less label** in the CLI. Both are deterministic,
  zero-latency, and cannot block a truthful answer.
- Real-corpus measurement (collect N answers via `pam ask` on the eval dataset)
  is the prerequisite for any of C/D/E/F and was **not** run in this phase.

## 13. Test-gap analysis — VALIDATED

Coverage today: `test_qa_workflow.py` (44: gate 19, citation validation 10,
answer contract 7, + misc), `test_cli.py` (24, incl. 6B outcome rendering),
`test_qa_timeout.py` (4), `test_answerability_gate.py` (17),
`test_reranker.py` (35). Full suite 1549 passed / 7 failed / 57 deselected.

Remaining gaps (all are *absence* tests, matching the unimplemented behaviors):

- no test for soft-abstention text (any phrasing) — none exists (grep confirms),
- no test for an empty/whitespace answer at workflow or CLI level,
- no CLI test for the no-citation label (only the workflow-level
  `test_answer_without_citations_keeps_full_sources_for_display`),
- no test for a model response containing a mix of answer + abstention prose,
- no `abstention message collision` test (model output that happens to equal
  `ABSTENTION_MESSAGE`).

No existing test conflicts with the 6B contract (all pass; new fields carry
defaults). The **7 stale `test_eval_dataset.py` failures are unrelated** to QA:
they assert the V2.0 reference contract against the V3.0 working-tree
`eval/dataset.json` and fail identically with or without QA changes.

## 14. Recommendation — C. SMALL TARGETED FIX ONLY (with measurement prerequisite)

Outcome: **C — small targeted fix**, not a full semantic-implementation phase,
not "accept as-is."

Justified now (deterministic, zero-risk, closes real ambiguities):

1. **Empty/whitespace answer → FAILED** (`QAError`/`QATimeoutError`-family):
   a degenerate successful-looking empty panel today.
2. **Honest citation-less labeling (CLI + contract field):** tag an ANSWERED
   result with `citations == []` as "answered without cited sources" (surface
   label only — no new top-level state). Keeps the contract truthful without
   blocking any answer.
3. **Wrap unexpected model exceptions** into `QAError` inside `ask()` so the
   workflow's stated contract (QAError/QATimeoutError only) matches reality.

Not justified until measured (deferred; requires a live sample run of ~3×30
queries over the frozen eval dataset, counting soft-abstention phrasing,
no-citation rate, and invalid/repeated citation rates):

4. Semantic soft-abstention detection (option D) — only after rate + false
   positives are known.
5. Citation presence requirement (option C) — only if the no-citation rate is
   meaningfully non-zero, and never hard-blocking.
6. Overlap-based groundedness (E) or enabling the LLM verifier (F) — no.

## 15. Proposed Phase 6C implementation, if justified — PROPOSED (not executed)

Pending user approval, a minimal Phase 6C implementation would be exactly the
three items in §14(1–3) plus a measurement harness (script that runs `pam ask`
over the eval dataset, offline-safe, writes a `qa_answers.jsonl` sample and a
summary of citation/no-citation/soft-abstention rates). No retrieval, dataset,
or corpus change; no new state; no keyword classifier until data justifies it.

## 16. Acceptance criteria — PROPOSED

- empty/whitespace model output is FAILED (exit 1, "Ask failed", no empty green
  panel); covered by workflow + CLI tests;
- ANSWERED-without-citations renders an explicit label and still shows the full
  retrieved list (existing tests continue to pass);
- all QA tests from 6A/6B remain green; full suite still 1549p/7f(identical)/57d;
- measurement run produces `qa_answers.jsonl` + a one-page rate summary;
- retrieval, dataset, corpus, HEAD `9f282b4` untouched; no commits.

## 17. Rollback plan — PROPOSED

All three fixes are additive guards in `qa_workflow.py` + one CLI render branch.
Rollback = revert those hunks (or the working tree to the 6B state); the
three-state contract and citation logic are untouched, so 6B behavior is
restored exactly. No data migrations, no config changes, no schema changes.

## 18. Deferred items — DEFERRED

- Keyword/pattern soft-abstention classification — until sample measurement.
- Citation-presence enforcement / retry-on-no-citation — until no-citation rate
  measured; retry only if rate justifies cost and determinism is preserved.
- Answer-to-source overlap groundedness signal.
- Enabling the answerability gate or banded verifier (operational calibration).
- Snippet improvement: show the exact chunk slice the model received and/or the
  cited span; basename-collision disambiguation.
- User-facing abstention-reason prose.

---

### Git safety result — VALIDATED

Discovery session performed **read-only inspection** (no production file was
modified). Verified before finishing:

```
git status --short    → no new/changed entries beyond the pre-existing working
                        tree + report 37 (the only sanctioned new file)
git diff --stat       → unchanged from the 6B stop point
```

Confirmed: no retrieval changes, no dataset changes, no corpus changes, no
commits, no pushes, no staging, no temporary scripts left in the repository
(6B/6C helper scripts live outside the repo in the Temp opencode directory).