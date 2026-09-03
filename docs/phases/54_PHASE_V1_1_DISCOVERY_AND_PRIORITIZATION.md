# PAM V1.1 — DISCOVERY & PRIORITIZATION AUDIT (READ-ONLY)

**Report:** `54_PHASE_V1_1_DISCOVERY_AND_PRIORITIZATION.md`
**Type:** Discovery / prioritization ONLY — no implementation
**Published V1.0.0:** `v1.0.0` → `a4e5b2a` (`release: finalize v1.0.0`)
**Current local HEAD:** `97197e2` (`release: PAM V1.0.0`, System Facts cleanup)
**Remote origin/main:** `198823d` (`docs: finalize V1 README`)

---

## 1. Executive Summary

PAM published **V1.0.0** at tag `v1.0.0 → a4e5b2a`. The local `main` has since advanced 6 commits past `origin/main` (experimental retrieval, eval infrastructure, application hardening, System Facts, and a "release" commit) contained in `97197e2`. This audit is **read-only**: it records the git/architecture state, classifies the delta, reviews documented limitations against the Phase 5 evidence, and proposes a **focused, smallest-coherent V1.1** — leaving retrieval optimization, evidence verification, and Agentic AI as separate future/research tracks. Nothing was modified, staged, committed, pushed, tagged, or rebased.

**Recommended V1.1 focus: reliability + source management + ingestion/CLI usability** — NOT retrieval.

---

## 2. Git / Release Baseline

| Item | Value | Label |
|------|-------|-------|
| Published V1.0.0 | tag `v1.0.0` → `a4e5b2a` | VERIFIED |
| Tag type | annotated, message "Release v1.0.0" | VERIFIED |
| Remote | `origin` → `https://github.com/GiridharBM/AI-Memory.git` | VERIFIED |
| Remote main | `origin/main` → `198823d` | VERIFIED |
| Current local branch | `main` at `97197e2` | VERIFIED |
| Local vs remote | `[origin/main: ahead 6]` | VERIFIED |
| Pre-existing tags | `v1.0.0` (a4e5b2a), `v2.0.0` (4f97684, separate older release) | VERIFIED |
| Working tree | contains pre-existing modified/untracked files — UNTOUCHED | VERIFIED |

**DELTA `v1.0.0..HEAD`:** 19 commits, 82 files changed, ~33,980 insertions / ~984 deletions.

---

## 3. Published V1.0.0 State

`v1.0.0` (commit `a4e5b2a`) "release: finalize v1.0.0" contains the **finalized, published V1 baseline**:
- **Finalized app:** `app/application/qa_workflow.py` (added), `app/prompts/qa.py` (added), CLI (`app/cli/entry.py`), `app/application/__init__.py`
- **Documentation:** PROJECT_STATUS, FINAL_PROJECT_REPORT, RELEASE_NOTES, TESTING_AND_VERIFICATION finalized
- **Corpus cleaned:** removed ~7,470 lines of placeholder/experimental vault notes (the real 24-source corpus base established)
- **Version:** `pyproject.toml = 1.0.0`

This is the authoritative published release. It is an **ancestor** of both `origin/main` (`198823d`) and the local work (`97197e2`).

---

## 4. Current Local Development State

`97197e2` ("release: PAM V1.0.0") is **6 commits ahead of `origin/main`, 0 behind** — a clean fast-forward candidate, BUT the intermediate commits were intentionally kept off `origin/main`:

| Commit | Classification |
|--------|----------------|
| `6a603d8` add experimental cross-encoder reranking | B — Retrieval experiment |
| `e287226` expand evaluation infrastructure | C — Eval infrastructure |
| `8524caf` fix BM25 abstention override + experimental hyde | B — Retrieval experiment |
| `9f282b4` evaluate cross-encoder abstention gate | B/C — Retrieval experiment |
| `10f74f1` harden application layer and ingestion lifecycle | A — Required application improvement |
| `97197e2` release: PAM V1.0.0 (System Facts) | A — Required application improvement |

**`97197e2` is NOT the original V1.0.0 release.** It is a local application-layer enhancement (System Facts from 6I-B/6I-C) layered over experimental retrieval commits. The published `v1.0.0` tag is distinct and must not be moved.

---

## 5. V1.0 → V1.1 Delta

19 commits classified (see §4 + below):
- **A. Required application improvement:** `0879957` (ruff fix), `bcc3ae0` (mypy fix), `10f74f1` (application hardening), `97197e2` (System Facts)
- **B. Retrieval experiment:** `6a603d8`, `8524caf`, `9f282b4`
- **C. Evaluation infrastructure:** `e287226`, (`9f282b4` mixed)
- **D. Documentation:** `10b8536`, `c749465`, `198823d`
- **E. Other (CI/license/merge/test-infra):** `203998c`, `705b824`, `600333e`, `d7a8edb`, `a15890e`, `27418f8`, `c4380a4`, `7020bec`
- **F. Unclear:** none

---

## 6. Current Architecture

| Layer | Components | State |
|-------|-----------|-------|
| **Ingestion** | `app/infrastructure/ingestion/` — ~28 ingestors (pdf/docx/pptx/md/txt/epub/csv/xlsx/notebook/db/code/image/audio/video/diagram/github/youtube/email/archive...), routing classifier, secret guard | VERIFIED |
| **Storage** | `vector_store.json` (in-memory dict + atomic temp+`os.replace`), `knowledge_graph.json`, manifest ledger | VERIFIED |
| **Knowledge graph** | `app/infrastructure/knowledge_graph.py`, `app/domain/knowledge_graph.py` | VERIFIED |
| **Vector store** | 768-dim nomic-embed-text, cosine search, `min_cosine=0.25` production | VERIFIED |
| **Search pipeline** | `search.py` — dense + BM25 + RRF (early fusion), reranker/hyde off | FROZEN |
| **QA workflow** | `qa_workflow.py` — ANSWERED/ABSTAINED/FAILED, citation validation, wall-clock timeout (120s), System Facts dispatch | VERIFIED |
| **CLI** | `app/cli/entry.py` — ingest/status/doctor/ask/search/config/watch/remove; System Facts Panel | VERIFIED |
| **System Facts** | `system_facts.py` — 5 categories, deterministic, no LLM/retrieval | VERIFIED |
| **Queue/watcher** | `app/queue/`, `app/watcher/` — background ingestion, durable ledger, retry | VERIFIED |
| **Status/doctor** | truthful runtime state + dependency/Ollama checks | VERIFIED |
| **Config** | `config/default.yaml` — app/paths/ollama/logging/watcher/queue/manifest/processing/models/intelligence/reranker/hyde/answerability/qa/chunking | VERIFIED |
| **Tests** | `tests/unit`, `tests/integration` — 1587 unit pass (excl. stale eval), hermetic temp stores | VERIFIED |

---

## 7. Confirmed Limitations

| # | Limitation | Classification → V1.1 bucket |
|---|-----------|------------------------------|
| 1 | Retrieval FPR ≈ 0.857 (answering-layer defect, not retrieval) | B — V1.1 research (evidence verification) |
| 2 | Hit@5 0.924 / MRR 0.877 below guardrails (narrow ranking gap) | D — retrieval; frozen; research-only |
| 3 | min_cosine production 0.25 vs eval 0.45 (INCONCLUSIVE/DOCUMENTED) | C — Documentation only (do not reopen) |
| 4 | Ollama hardware-dependent latency (now 8192 ctx validated) | C — Documentation / ops |
| 5 | `pam remove` requires exact source form (path/URL) — no fuzzy/content/source-browse | A — V1.1 source management |
| 6 | Vector/KG separate-file, not single-transaction atomic (temp+`os.replace` per file) | A — V1.1 reliability (low priority) |
| 7 | Evidence verification deferred | B — V1.1 research track |
| 8 | Stale eval tests (7/24 v2.0-vs-v3.0) | C — Documentation (frozen by 5D) |
| 9 | No source browsing / listing UX | A — V1.1 usability |
| 10 | Ingestion errors partially non-actionable | A — V1.1 ingestion UX |

---

## 8. Candidate Improvements

Evaluated candidates (STEP 7) with user value / complexity / risk / retrieval dependency / success criteria / V1.1-ness:

1. **`pam remove` path handling** — usability/robustness. Low-medium value, low complexity, low risk, no retrieval dep. Success: remove by exact path/URL works reliably; no data loss on re-ingest failure. **V1.1.**
2. **Persistence atomicity** — reliability. Medium value for crash safety, low-medium complexity, low risk, no retrieval dep. Success: vector+KG+manifest update as a recoverable unit; no partial corruption. **V1.1 (low priority).**
3. **Source management** — list/browse/inspect sources. High user value, medium complexity, low risk, no retrieval dep. Success: `pam sources` lists/describes the 24 sources + counts. **V1.1 (core).**
4. **Ingestion UX** — clearer per-source errors/retry. High value, medium complexity, low risk. Success: errors actionable; no silent failure. **V1.1.**
5. **CLI UX** — consistent meaning, better help, predictable exit codes. Medium value, low-medium complexity, low risk. Success: every command's exit code documents a state. **V1.1 (partial).**
6. **Web/API interface** — a server/API. High value, high complexity, medium risk, new surface. Success: read-only API returns status/sources/ask. **DEFER (V1.2).**
7. **Evidence verification** — answering-layer verifier. High value for FPR, high complexity, high risk (FNR/latency), no retrieval change but answering-layer signature. Success: FPR materially below 0.857 at FNR ≤ 0.033 and acceptable latency on a scoped, fail-open design. **RESEARCH track (not core V1.1).**
8. **Retrieval FPR research** — per §6, mis-aimed; answering-layer defect. **DEFER (research).**
9. **Factual correctness evaluation** — measurement harness for answer faithfulness. Medium-high value, medium complexity, low risk. Success: faithfulness/groundedness metric reported. **V1.1 research/observability (optional).**
10. **Agentic AI** — DEFER (§11).
11. **Better status/observability** — richer status, per-source health. Medium value, low-medium complexity, low risk. Success: status reflects source/chunk/KG health accurately. **V1.1 (with source mgmt).**
12. **Configuration UX** — better config ergonomics. Low-medium value, low complexity, low risk. **V1.1 optional.**
13. **Backup/recovery** — export/restore of store+KG+manifest. Medium value, medium complexity, low risk. Success: one command back/restores cleanly. **V1.1 optional / defer.**
14. **Source browsing** — see §8.3. **V1.1 (core).**
15. **Other evidence-backed** — secret guard hardening already present; no new critical item measured. **N/A.**

---

## 9. Retrieval Freeze Review

**Verdict: RETRIEVAL V1 REMAINS FROZEN. No change recommended.**

Evidence (from Phase 5G decision and 5E audit):
- FPR 0.857 is **37 of 157 matches: an answering-layer defect** (31/36 FPs are content-sufficiency misses — on-topic chunks, fact absent). No retrieval score/threshold/model/reranker detects them.
- Every retrieval lever measured-exhausted: thresholds (3B/5E), embeddings (3G-A), reranker (3C), HyDE (3E), metadata (5E), doc removal (5E). All REJECTED with recorded outcomes.
- Hit@5/MRR fail two guardrails independent of abstention; a **narrow, named ranking gap**, not systemic.
- Strict rule yields **zero** justified retrieval experiments. 5G chose freeze → application layer.
- The candidate that deletes the FP class (evidence verification) is an **answering/application-layer** mechanism; its FNR/latency cost is correctable there, not by touching retrieval.

---

## 10. 3G-A / 3G-B Assessment

- **3G-A (embedding experiment, mxbai-embed-large):** REJECTED. Degraded Hit@1/5/MRR; FPR reduction only from dropping negatives, at positive-cost. No threshold meets acceptance. **NOT reopened.**
- **3G-B (query scope / answerability gate):** REJECTED as root fix; achieves ~-70% FPR but violates FNR; classifier accuracy unmodeled. Prototype only, default-off. **NOT reopened.**

---

## 11. 5E / 5F Assessment

- **5E (FPR root-cause + signal analysis):** COMPLETE. Only cosine separates; all 12 other signals overlap TPs/FPs; 12/36 FPs hard-core (≥0.62). Conclusion: FPR = answering-layer (C+E), ranking gap = secondary (B). **Completed; feeds evidence-verification research.**
- **5F (banded answerability verifier):** REJECTED for V1 (FNR 0.070 > 0.033 at latency 17s p95; no threshold satisfies all guardrails). **CANDIDATE mechanism** for the answering layer — retain as research, default-off. **NOT reopened as retrieval.**

---

## 12. 5G Decision Preservation

**5G decision (retrieval V1 FREEZE → application layer) is PRESERVED.** Verified intact this audit:
- dataset v3.0 frozen (199q), corpus (24src/195chunk) intact, config (`reranker/hyde/answerability=false`, `min_cosine=0.25` production) unchanged, `phase_5d_frozen_baseline.json` present.
- No retrieval, dataset, corpus, or config modification occurred.

---

## 13. V1.1 Prioritization Matrix

| Candidate | User Value | Complexity | Risk | Retrieval Change? | Priority | Recommendation |
|-----------|-----------|-----------|------|-------------------|----------|----------------|
| Source management (browse/list) | High | Med | Low | No | **P1** | V1.1 core |
| Ingestion UX (actionable errors/retry) | High | Med | Low | No | **P1** | V1.1 core |
| Reliability (re-ingest safety, atomicity) | Med-High | Med | Low | No | **P1** | V1.1 core |
| `pam remove` path handling | Med | Low | Low | No | **P2** | V1.1 |
| Better status/observability | Med | Low-Med | Low | No | **P2** | V1.1 |
| CLI UX (predictable exits/help) | Med | Low-Med | Low | No | **P2** | V1.1 (partial) |
| Configuration UX | Low-Med | Low | Low | No | **P2** | V1.1 optional |
| Backup/recovery | Med | Med | Low | No | **P2** | V1.1 optional / defer |
| Evidence verification | High | High | Med-High | No (answering layer) | **RESEARCH** | Defer to research track |
| Factual-correctness eval | Med-High | Med | Low | No | **RESEARCH** | Observability research |
| Web/API interface | High | High | Med | No | **P3** | Defer (V1.2) |
| Agentic AI | High | Very High | High | No | **DEFER** | Post V1.1 |
| Retrieval FPR research | — | — | — | Yes | **DEFER** | Mis-aimed (answering-layer) |

**P0 (critical): none** — no unhandled critical bug is measured. All 20 V1 acceptance criteria passed.
**Scope:** P1 (source mgmt, ingestion UX, reliability) + selected P2 (remove handling, status, CLI) = focused V1.1.

---

## 14. Recommended V1.1 Scope

**Smallest coherent V1.1 — "Reliability + Source Management + Usability"**

**In scope (engineering):**
1. **Source management** — `pam sources` list/browse/inspect; per-source health (chunks, KG, last ingest, status).
2. **Ingestion UX** — actionable, categorized errors; transparent retry; clearer per-source outcome.
3. **Reliability** — re-ingestion never destroys prior valid data on failure; strengthen atomicity guarantees; source removal robustness.
4. **`pam remove` path handling** — robust multi-form removal + confirm/feedback.
5. **Status/observability + CLI UX** — truthful enriched status; documented, predictable exit codes and help.

**Out of V1.1 (separate tracks):** retrieval optimization (frozen), evidence verification (research), Agentic AI (later), web/API (V1.2).

---

## 15. Deferred Research

- **Evidence verification** (answering-layer FPR fix) — reuse 5F verifier concept with scoped/fail-open engineering. Separate gate.
- **Factual correctness / faithfulness evaluation** harness.
- **Retrieval-side Hit@5/MRR ranking gap** — only with a new, specific hypothesis and new corpus/model; not now.
- **Agentic AI** — see §11 / §16.

---

## 16. Agentic AI Assessment

**Recommendation: DEFER. PAM is NOT yet ready for an Agentic AI layer.**

Rationale:
- An agent that plans multi-step retrieval, decides when more retrieval is needed, combines memories, verifies information, and performs actions requires a **solid, verifiable retrieval + answering foundation first**. V1 retrieval is frozen and FPR (answering-layer) is unsolved.
- The evidence-verification gap (FPR) is the prerequisite an agent would depend on for trustworthy multi-hop answers. Building agents on an unverified answering layer amplifies hallucination risk.
- V1.1 should build the **foundation** (reliable source management, observability, and — via research — evidence verification). An agentic layer is a separate post-V1.1 program, not a label to apply now.

---

## 17. Success Criteria (for proposed V1.1)

Concrete, measurable:
1. `pam sources` lists all 24 sources with per-source chunk + KG + status counts; accurate vs `status`.
2. Re-ingestion failure never corrupts/destroys previously valid vector/KG/manifest data (test = pre-existing data intact after simulated failure).
3. `pam remove <source>` removes exactly that source across vector+KG+ledger; no data loss for other sources (tested).
4. Ingestion errors are categorized + actionable; no silent failures; no secrets leak.
5. `status` truthfully reflects state (sources, chunks, KG, failures, retries).
6. CLI exit codes documented and predictable per command.
7. **No regression:** full unit suite ≥ 1587 passed; stale eval tests remain the known 7, unmodified.
8. **Retrieval remains byte-identical** to frozen baseline unless a separate, explicitly-approved research gate approves a change.
9. No secret leakage on any path.
10. No new critical bug introduced.

---

## 18. Release Strategy

**Rules (unchanged):**
- Published `v1.0.0 → a4e5b2a` must NOT move/delete/rewrite.
- Do NOT push `main` blindly — `97197e2` contains 4 experimental retrieval commits (`6a603d8`, `e287226`, `8524caf`, `9f282b4`) deliberately kept off `origin/main`.

**Proposed path:**
1. Keep `97197e2` as the local application-layer state, OR (preferred) **track V1.1 work on `974...`-independent clean history** — but do NOT fast-forward-push the experimental commit stack to `origin/main`.
2. For a real release, **squash/rebuild** `main` so it carries only the vetted application-layer changes (10f74f1 hardening + 97197e2 System Facts) *without* the experimental retrieval commits — or branch V1.1 off `198823d`/`10f74f1`, keeping `main` clean.
3. Eventually publish V1.1 as a **new commit + new annotated tag `v1.1.0`** pointing at the vetted release commit (never reuse/move `v1.0.0`).
4. `origin/main` should be advanced only with the cleaned, releasable history — not the experimental stack.

No git operation performed in this audit.

---

## 19. Risks

- **History complexity:** 6 un-pushed commits mixing experiments + app work → risk of accidentally publishing experiments. Mitigate by branch/squash discipline (§18).
- **Evidence verification research** could reintroduce FNR/latency risk; keep default-off, scoped.
- **Source management** must not mutate corpus during browse; read-only + explicit actions only.
- **Atomicity** work touches store/KG save paths — must preserve byte-identical retrieval and existing data.
- No critical live risk measured at V1 (all V1 acceptance criteria passed).

---

## 20. Final Recommendation

**Proceed to a focused V1.1 (Reliability + Source Management + Usability), with retrieval frozen and evidence verification/Agentic AI as separate deferred tracks.** Before any V1.1 implementation: clean the git history (§18) so `main`/`origin/main` stay free of the experimental commit stack; do not touch `v1.0.0`. Then implement the P1 scope against the §17 success criteria with the robot-atomized, non-destructive test discipline used throughout.

---

*Labels used: CONFIRMED, VERIFIED, RECOMMENDED, DEFERRED, REJECTED, RESEARCH, INCONCLUSIVE.*
