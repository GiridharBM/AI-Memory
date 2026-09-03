# PAM V1 RELEASE COMMIT — 53

**Status:** RELEASE COMMITTED
**Commit:** `97197e2 release: PAM V1.0.0`
**Previous commit:** `10f74f1 feat: harden application layer and ingestion lifecycle`

---

## 1. Previous Commit

`10f74f1 feat: harden application layer and ingestion lifecycle`

## 2. New Release Commit

`97197e2 release: PAM V1.0.0`

## 3. Commit Message

`release: PAM V1.0.0`

## 4. Files Committed (8)

| File | Change |
|------|--------|
| `app/application/system_facts.py` | NEW — System Facts router + service (302 lines) |
| `app/application/qa_workflow.py` | +25 — System Facts dispatch in `ask()`, `origin` field |
| `app/cli/entry.py` | +12 — System Facts Panel |
| `app/application/__init__.py` | +3 — System Facts exports |
| `app/infrastructure/state/models.py` | +32 — 6H durable-ledger outcome fields |
| `tests/unit/test_system_facts.py` | NEW — router/service/workflow tests (284 lines) |
| `tests/unit/test_qa_workflow.py` | +395 — citations, QA contract, timeout, empty-answer tests |
| `tests/unit/test_queue_worker.py` | +106 — durable ledger + retry tests |

**Total:** 8 files changed, 1154 insertions(+), 5 deletions(-)

## 5. Test Results

- Full unit suite (excl. stale eval): **1587 passed, 1 deselected**
- Focused System Facts / QA / queue-worker: 105 passed
- Stale eval dataset (separate): 7 failed / 24 passed — KNOWN / PRE-EXISTING / NOT a V1 application failure (frozen v2.0 assertions vs v3.0 dataset)
- Ruff: 13 findings, all LOW/DOCUMENTATION (E501 / F401 / I001), style-only, no correctness issues

## 6. System Facts Verification

- "What QA model is PAM using?" → **System Facts** (origin=system): `qwen3:8b`, `ollama_num_ctx=8192`, no LLM, no retrieval, no network, no fabricated citations ✅
- All 5 categories intercept correctly (version, source count, chunk count, feature status, QA model)

## 7. Normal QA Verification

- "When was Utthunga founded?" → **normal retrieval + QA**: ANSWERED, valid citations `[SOURCE 1]` / `[SOURCE 4]`, deduplicated ✅
- Normal QA contract intact; System Facts does not hijack knowledge questions

## 8. Ollama 8192 Verification

- `ollama ps` → `qwen3:8b` **CONTEXT=8192** ✅
- `qa.timeout_seconds = 120` ✅
- No configuration changes made

## 9. Retrieval Freeze Verification

- Staged diff on `app/infrastructure/{embeddings,search,bm25,reranker,semantic_chunking}.py`: **EMPTY** ✅
- `reranker.enabled=false`, `hyde.enabled=false`, `answerability.enabled=false` ✅
- Production `min_cosine=0.25` (unchanged) ✅

## 10. Dataset/Corpus Protection

None of the following were staged or committed:
- `eval/dataset.json`
- `eval/run_eval.py`
- `eval/results/*`
- `vault/*` (corpus)
- `data/manifests/*` (runtime manifests)

All remain outside the release commit, as required.

## 11. Known Limitations

1. Retrieval FPR ≈ 0.857 (frozen by Phase 5G — not a V1 blocker)
2. Hit@5/MRR below historical guardrails
3. min_cosine production 0.25 vs evaluation 0.45 (INCONCLUSIVE / DOCUMENTED)
4. Ollama hardware-dependent latency (now at validated 8192 ctx)
5. `pam remove` exact-path limitation
6. Vector/KG separate-file non-atomic persistence
7. General evidence verification deferred
8. Stale eval test assertions
9. Ruff style-only findings (E501/F401/I001)

None prevent normal V1 use.

## 12. V1 Release Status

> **PAM V1.0.0**
> **STATUS: RELEASE COMMITTED**
> **RETRIEVAL: FROZEN**
> **APPLICATION: READY WITH DOCUMENTED LIMITATIONS**

Release commit `97197e2` contains only the approved application-layer + test changes. No push occurred. No tag created. Dataset, corpus, and retrieval remain frozen.

---

*This report (`53_PHASE_V1_RELEASE_COMMIT.md`) is intentionally NOT part of the release commit (`97197e2`).*
