# Phase 5D — Real-Corpus Evaluation Dataset Freeze

**Status:** FROZEN — `eval/dataset.json` is now the canonical real-corpus evaluation dataset (v3.0, 199 queries). No production changes; no commits.
**Date:** 2026-08-27
**Approval:** Phase 5D action (merge + freeze), evaluation-only baseline run authorized.

---

## 1. Dataset before merge

`eval/dataset.json` held **dataset v2.0 — 160 queries** (created 2026-08-19, expanded Phase 3D from v1.0's 50):

- 123 positive / 37 negative
- Ground truth for only 10 legacy documents (the 94-chunk original corpus)
- **0 queries covered any of the 14 documents ingested in Phase 4/5** — the Phase 5A finding that left the interference invisible to the suite
- 3 orphan queries (q092–q094) referencing content of the intentionally removed `pam_smoke_test` document

Backup taken before modification: `eval/results_backup_20260827/dataset_pre_5d.json` — verified byte-identical (SHA-256 match) to the pre-merge `dataset.json` and containing exactly 160 queries / version "2.0".

## 2. Obsolete queries removed

| ID | Reason removed |
|---|---|
| q092 | References `pam_smoke_test` content no longer in the corpus — permanently unanswerable |
| q093 | Same |
| q094 | Same |

These were the ONLY historical queries removed (programmatically confirmed: `set(backup_ids) - set(merged_ids) == {q092, q093, q094}`).

## 3. New queries added

All 42 Phase 5B proposal queries appended unchanged: **q161–q202** (37 positive / 5 negative; 14/14 new-document coverage). Deep-compared against `eval/dataset_v3_proposed.json` — every field (query text, expected_sources, expected_evidence, evidence_fragments, category, difficulty, ground_truth_reliable, answerability, rationale) is content-equivalent.

## 4. Final dataset composition

`eval/dataset.json` metadata now version **"3.0"**, phase **"5D"**, frozen = PHASE_5D.

| Component | Count |
|---|---|
| q001–q091 (surviving historical) | 91 |
| q092–q094 (removed) | 0 |
| q095–q160 (surviving historical) | 66 |
| q161–q202 (new real-corpus, from Phase 5B proposal) | 42 |
| **Total queries** | **199** |
| Positive (have ground truth) | 157 |
| Negative (abstention) | 42 |

Positive/negative counts were read from the actual merged dataset, not assumed (157 / 42 — the originally drafted description said 162/37 and was corrected).

## 5. Validation results (all programmatic)

| Check | Result |
|---|---|
| Exactly 199 queries | PASS |
| No duplicate IDs | PASS |
| q001–q091 present | PASS |
| q092–q094 absent | PASS |
| q095–q160 present | PASS |
| q161–q202 present | PASS |
| Positive/negative counts (actual): 157 / 42 | PASS |
| Every expected source resolves to a file in the current 24-source corpus (run_eval fragment match) | PASS |
| Every positive query has `expected_evidence` | PASS |
| All 37 new positives' `evidence_fragments` grounded verbatim in expected-source chunks | PASS |
| Negatives: empty `expected_sources`, category "negative", no evidence fragments | PASS |
| Schema: required keys (id, query, expected_sources, expected_evidence, category, difficulty, ground_truth_reliable) present on every query | PASS |
| Historical queries carry no Phase 5B-only fields (answerability / evidence_fragments are new-query-only) | PASS |
| Metadata version == "3.0" | PASS |

**VALIDATION: ALL PASS.**

## 6. Ground-truth integrity

- **New queries:** byte-for-byte content-identical to the approved, audited, and vet-full proposal (q161–q202 verified via deep JSON comparison).
- **Surviving historical:** every one of the 157 surviving q001–q160 records is identical to the pre-merge backup (deep comparison) — no historical text, evidence, or expected source was altered.
- **Only intended change set:** remove exactly q092–q094, add exactly q161–q202. Confirmed programmatically.

## 7. Dataset coverage

| Coverage dimension | Before (v2.0) | After (v3.0) |
|---|---|---|
| Queries | 160 | 199 |
| Positive / negative | 123 / 37 | 157 / 42 |
| Legacy documents covered | 10 | 10 |
| New documents covered | **0** | **14** |
| Total corpus coverage | 10 of 24 | **24 of 24** |

All 24 sources in the current corpus are now measurable. The three surviving sources with no positive ground truth are the legacy reachability artifacts that were removed (pam_smoke_test) — all current sources have query coverage.

## 8. Frozen corpus state

| Item | Value |
|---|---|
| Sources | 24 |
| Chunks | 195 |
| Embedding model | nomic-embed-text, 768-dim |
| Vector store | `data/manifests/vector_store.json` (unchanged) |
| Historical pre-ingestion backup | `data/manifests/backups/20260824_225735/` (101 chunks) |

## 9. Frozen configuration

| Parameter | Value |
|---|---|
| top_k | 5 |
| min_cosine | 0.45 |
| reranker | disabled (`false`) |
| hyde | disabled (`false`) |
| answerability | disabled (`false`) |
| BM25 | k1=1.5, b=0.75 |
| RRF | k=60 |
| Source-key map | frozen 12 legacy keys + 14 Phase 5B keys |

No retrieval or production code was modified in Phase 5D.

## 10. Baseline evaluation (frozen 199-query dataset)

Run with the production `SearchService` + `AbstentionGate(0.45)` unchanged, current corpus, all optional gates off. Results:

| Metric | Value |
|---|---|
| Hit@1 | **0.8408** (132/157) |
| Hit@3 | 0.9108 |
| Hit@5 | **0.9236** (145/157) |
| Hit@10 | 0.9236 |
| MRR | **0.8773** |
| FPR | **0.8571** (36/42 negatives accepted) |
| FNR | **0.0000** |
| Abstention rate | 0.0302 (6/199) |
| Positive acceptance | 1.0000 |
| Negative rejection | 0.1429 (6/42) |
| Latency avg | 77.1 ms |
| Latency p50 | 37.4 ms |
| Latency p95 | 47.1 ms |

Saved to `eval/results/phase_5d_frozen_baseline.json` (Phase 5C artifacts untouched).

## 11. Comparison with Phase 5C

This baseline is exactly the Phase 5C **Experiment C** scenario re-run against the frozen dataset (the 199 queries are the same 157 + 42; the corpus and config are identical).

| Metric | 5C Exp C | 5D baseline | Δ |
|---|---|---|---|
| Hit@1 | 0.8408 | 0.8408 | 0.0000 |
| Hit@5 | 0.9236 | 0.9236 | 0.0000 |
| MRR | 0.8773 | 0.8773 | 0.0000 |
| FPR | 0.8571 | 0.8571 | 0.0000 |
| FNR | 0.0000 | 0.0000 | 0.0000 |
| Abstention rate | 0.0302 | 0.0302 | 0.0000 |
| Pos acceptance | 1.0000 | 1.0000 | 0.0000 |
| Neg rejection | 0.1429 | 0.1429 | 0.0000 |
| Latency avg | 42.0 ms | 77.1 ms | +35.1 |
| Latency p50 | 50.9 ms | 37.4 ms | −13.5 |
| Latency p95 | 60.1 ms | 47.1 ms | −13.0 |

Per-query comparison: **199/199 identical** (same expected rank, same abstention decision, same correctness).

**Difference explained:** retrieval is fully deterministic, so all correctness metrics (Hit/MRR/FPR/FNR/abstention) match to the 4th decimal. Latency differs purely from run-to-run environment variance — the Phase 5D run includes a single 7.3 s cold-start outlier (first embedding call after a cold Ollama cache), which inflates the mean while the p50/p95 are actually lower (37.4 / 47.1 vs 50.9 / 60.1 ms). No tuning was performed; no system changed.

## 12. Known limitations

- FPR 0.857 is the dominant open weakness — the 0.45 cosine gate accepts 36/42 true negatives, including all 5 hard near-miss negatives (q196–q200). Deliberately NOT addressed in this phase.
- Certificate queries (7) are thin and serve as source-discrimination probes; two AWS certs rank 2 and one Python cert (q193) ranks outside top-5 due to sibling-document boilerplate overlap.
- Legacy negatives are easier than new negatives, so aggregate FPR mixes two difficulty regimes.
- Baseline latency includes one cold-start outlier; p95 (47 ms) is the more representative ceiling.

## 13. Final dataset status

**`eval/dataset.json` is now the frozen real-corpus evaluation dataset.**

- Version **3.0**, 199 queries (157 positive / 42 negative), covering **24/24 sources**.
- Contains exactly the surviving historical queries plus the audited Phase 5B real-corpus queries.
- Immutable from this point; any future change requires explicit approval and a new freeze cycle with a fresh pre-change backup (pattern established here).
- Composition: 157 historical valid (q001–q091, q095–q160) + 42 new real-corpus (q161–q202). q092–q094 removed (pam_smoke_test obsolete).

## 14. Recommended next phase (NOT started)

The next phase (e.g., Phase 5E) should target the single dominant failure: **abstention / FPR** (currently 0.857). Options, in expected-leverage order, remain pending approval:

1. **Semantic answerability or grounded-evidence gating** — the 0.45 cosine-only gate provably fails on near-miss negatives (all 5 accepted at 0.55–0.63 top cosine). Evidence from Phase 3G-B indicates answerability gating is the established next candidate.
2. **Retrieval-ranking improvement** (Phase 3C reranker scoping) to address the 18 legacy regressions where PAM/GPU docs legitimately out-rank legacy sources.
3. Re-run the frozen 199-query baseline after any approved change and require: Hit@5 ≥ 0.93, MRR ≥ 0.88 on the full suite, FPR below 0.811.

Until then: no FPR optimization, no production code changes, no re-ingestion, no config changes.

---

**Artifacts produced by Phase 5D:** `eval/results_backup_20260827/dataset_pre_5d.json` (backup), `eval/dataset.json` (frozen v3.0, 199 queries), `eval/results/phase_5d_frozen_baseline.json` (baseline), `30_PHASE_5D_REAL_CORPUS_DATASET_FREEZE.md` (this report). No commits.