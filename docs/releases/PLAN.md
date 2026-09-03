# Phase 3B Implementation Plan — Retrieval Abstention Gate

## Context
Phase 3A found that RRF scores are compressed into a 17% band (0.028–0.033) and cannot distinguish positive from negative queries. The negative-query FPR is 1.000. The raw cosine and BM25 scores are computed but discarded at the `_rrf_fuse` boundary — only IDs cross. To build an evidence-based gate, we must plumb raw scores through and use them as the primary signal.

## Files to Modify

| File | Change |
|------|--------|
| `app/infrastructure/search.py` | Add `cosine_score`/`bm25_score` to SearchHit; plumb through _rrf_fuse and HybridSearch.search() |
| `app/application/qa_workflow.py` | Add AbstentionGate class; gate check in QAWorkflow.ask() |
| `eval/run_eval.py` | Add abstention metric computation (FPR, FNR, abstention rate) |
| `tests/unit/test_qa_workflow.py` | Add 7 new tests for gate behavior |

## Files NOT Modified
- `app/infrastructure/bm25.py` — no changes
- `app/infrastructure/vector_store.py` — no changes
- `app/infrastructure/embeddings.py` — no changes
- `app/domain/vector_store.py` — no changes
- `app/prompts/qa.py` — no changes
- `app/core/config.py` — no changes

---

## Step 1: Add raw score fields to SearchHit

In `app/infrastructure/search.py`, add two fields to the `SearchHit` dataclass:

```python
@dataclass(slots=True)
class SearchHit:
    text: str
    source: str
    score: float          # RRF fusion score (existing)
    entry_id: str
    cosine_score: float = 0.0   # NEW: raw cosine similarity from vector leg
    bm25_score: float = 0.0     # NEW: raw BM25 score from lexical leg
    parent_section: str | None = None
    source_type: str = ""
    chunk_index: int = 0
    start_char: int | None = None
    end_char: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)
```

Both new fields default to 0.0 → backward-compatible. Existing `_to_hit()` and all callers continue to work without changes.

---

## Step 2: Plumb raw scores through _rrf_fuse

Modify `_rrf_fuse` to accept optional score dictionaries:

```python
def _rrf_fuse(
    *ranked_lists: list[str],
    k: int = 60,
    score_maps: tuple[dict[str, float], ...] | None = None,
) -> list[tuple[str, float, float, float]]:
    """RRF fusion. Returns (entry_id, rrf_score, leg0_score, leg1_score)."""
    scores: dict[str, float] = {}
    leg_scores: dict[str, tuple[float, float]] = {}
    for list_idx, ranked in enumerate(ranked_lists):
        for rank, entry_id in enumerate(ranked, start=1):
            scores[entry_id] = scores.get(entry_id, 0.0) + 1.0 / (k + rank)
            if score_maps and list_idx < len(score_maps):
                raw = score_maps[list_idx].get(entry_id, 0.0)
                prev = leg_scores.get(entry_id, (0.0, 0.0))
                if list_idx == 0:
                    leg_scores[entry_id] = (raw, prev[1])
                else:
                    leg_scores[entry_id] = (prev[0], raw)
    result = []
    for entry_id, rrf_score in sorted(scores.items(), key=lambda item: (-item[1], item[0])):
        leg0, leg1 = leg_scores.get(entry_id, (0.0, 0.0))
        result.append((entry_id, rrf_score, leg0, leg1))
    return result
```

**Key decisions:**
- `score_maps` is optional → old callers (tests) still work with just IDs
- Return type changes from `list[tuple[str, float]]` to `list[tuple[str, float, float, float]]` — only internal callers affected
- The leg order is always [vector_scores, bm25_scores]

---

## Step 3: Update HybridSearch.search()

In `HybridSearch.search()`, build score maps from the raw results and pass to `_rrf_fuse`:

```python
# Build score maps from raw results
vector_score_map = {r.entry.id: r.score for r in dense}
bm25_score_map = {ids[i]: score for i, (doc_idx, score) in enumerate(lexical) if doc_idx < len(ids)}

fused = _rrf_fuse(
    [r.entry.id for r in dense],
    fused_ids,
    k=self._rrf_k,
    score_maps=(vector_score_map, bm25_score_map),
)

hits: list[SearchHit] = []
for entry_id, score, cosine_score, bm25_score in fused:
    entry = self._store.get(entry_id)
    assert entry is not None
    hit = _to_hit(SearchResult(entry=entry, score=score))
    hit.cosine_score = cosine_score
    hit.bm25_score = bm25_score
    if hit.score >= min_score:
        hits.append(hit)
return hits[:top_k]
```

---

## Step 4: AbstentionGate class in qa_workflow.py

```python
@dataclass(slots=True)
class AbstentionResult:
    abstain: bool
    reason: str | None = None

class AbstentionGate:
    def __init__(self, min_cosine: float = 0.25) -> None:
        self._min_cosine = min_cosine

    def evaluate(self, hits: list[SearchHit]) -> AbstentionResult:
        if not hits:
            return AbstentionResult(True, "no_results")
        if hits[0].cosine_score == 0.0 and hits[0].bm25_score == 0.0:
            return AbstentionResult(True, "embedding_failed")
        if hits[0].cosine_score < self._min_cosine:
            return AbstentionResult(True, f"cosine_below_threshold ({hits[0].cosine_score:.4f} < {self._min_cosine})")
        return AbstentionResult(False)
```

**Signal priority:**
1. Empty hits → abstain (no evidence at all)
2. Both scores zero → abstain (embedding failed, BM25 returned nothing meaningful)
3. Top-1 cosine below threshold → abstain (semantic similarity too low)

**Why cosine is the primary signal (from Phase 3A):**
- Cosine is bounded [0,1], interpretable, query-dependent
- BM25 scores are unbounded, corpus-dependent, harder to threshold
- RRF scores are compressed (Phase 3A finding)
- The gate uses cosine as the rejection signal, BM25 as a fallback

---

## Step 5: Integrate gate in QAWorkflow.ask()

```python
def __init__(self, search_service, ollama_client, *, model=None, min_cosine: float = 0.25):
    self._search_service = search_service
    self._ollama_client = ollama_client
    self._model = model
    self._abstention_gate = AbstentionGate(min_cosine=min_cosine)

def ask(self, question, *, top_k=5, min_score=0.0, filter=None):
    # ... existing validation ...
    hits = self._search_service.search(...)
    
    # Abstention gate
    abstention = self._abstention_gate.evaluate(hits)
    if abstention.abstain:
        logger.info("Abstaining.", extra={"reason": abstention.reason, "question": question})
        return QAAnswer(
            answer="I don't have enough relevant information in the knowledge base to answer this question.",
            sources=[],
            model="",
        )
    
    # ... existing context build + LLM generation (unchanged) ...
```

**QAAnswer for abstained queries:**
- `answer`: Clear abstention message
- `sources`: Empty list (no citations — nothing was accepted)
- `model`: Empty string (LLM was not invoked)
- LLM is NOT called → zero latency cost for rejected queries

---

## Step 6: Extend eval/run_eval.py

Add abstention metrics computation after the existing `compute_metrics()`:

```python
# After computing standard metrics:
positive_queries = [r for r in results if r["expected_sources"]]
negative_queries = [r for r in results if not r["expected_sources"]]

# Abstention tracking (requires gate integration or post-hoc analysis)
fp = sum(1 for r in negative_queries if not r.get("abstained", False))
fn = sum(1 for r in positive_queries if r.get("abstained", False))
abstained_count = sum(1 for r in results if r.get("abstained", False))

metrics["abstention"] = {
    "false_positive_rate": fp / len(negative_queries) if negative_queries else 0,
    "false_negative_rate": fn / len(positive_queries) if positive_queries else 0,
    "abstention_rate": abstained_count / len(results) if results else 0,
    "positive_acceptance_rate": 1 - (fn / len(positive_queries)) if positive_queries else 1,
    "negative_rejection_rate": 1 - (fp / len(negative_queries)) if negative_queries else 0,
}
```

**To make this work**, the eval script needs to either:
- (a) Call `qa_workflow.ask()` instead of `search_service.search()` directly, OR
- (b) Instantiate `AbstentionGate` and call `gate.evaluate(hits)` per query

Option (b) is better — it keeps the eval at the retrieval level without requiring Ollama.

---

## Step 7: Tests (7 new tests)

1. **Strong relevant retrieval → accepted**: High cosine_score hits → gate passes
2. **Weak retrieval → rejected**: Low cosine_score hits → gate rejects
3. **Negative query → rejected**: Empty hits or zero scores → gate rejects
4. **Borderline score → deterministic**: Score exactly at threshold → gate passes (>= is accept)
5. **Accepted query → QA context built normally**: Gate passes → build_context called → LLM invoked
6. **Rejected query → LLM not invoked**: Gate rejects → QAAnswer returned → generate_text NOT called
7. **Existing behavior unchanged**: All existing tests pass without modification

---

## Step 8: Threshold Selection (data-driven)

**Process:**
1. Run eval BEFORE gate (collect raw cosine scores for all 50 queries)
2. Analyze cosine score distribution: positive vs negative
3. Find the natural separation point
4. Set threshold at the point that maximizes FPR reduction while keeping Hit Rate@5 ≥ baseline - 0.02

**Expected outcome (from Phase 3A analysis):**
- Negative queries with completely out-of-domain content (q032, q035) likely have lower cosine scores
- Negative queries that partially match PAM content (q033, q036) may have higher cosine scores
- The gate will catch the former, not the latter — this is expected and documented

**If no useful threshold exists:**
Report that finding per the spec: "If the gate cannot achieve a useful tradeoff on this dataset, DO NOT force it."

---

## Step 9: Evaluation Runs

1. **Before**: Run `eval/run_eval.py` unmodified → record metrics
2. **Threshold calibration**: Analyze raw cosine scores from step 1
3. **After**: Run `eval/run_eval.py` with gate active → record metrics
4. **Compare**: Report before/after in `14_PHASE_3B_ABSTENTION_RESULTS.md`

---

## Step 10: Report

Create `D:\Projects\Personal AI Memory\14_PHASE_3B_ABSTENTION_RESULTS.md` with all 12 sections as specified.

---

## What is NOT changed
- `_rrf_fuse` signature is extended (not replaced) — old callers work
- SearchHit gains fields with defaults — old callers work
- QAWorkflow gains optional param — old callers work
- No BM25 changes (tokenization, k1, b)
- No RRF k changes
- No embedding changes
- No chunking changes
- No ingestion changes
- QA system prompt unchanged
- Existing [SOURCE N] citation behavior preserved

## Risk Assessment
- **Low risk**: SearchHit field additions (backward-compatible defaults)
- **Low risk**: _rrf_fuse extension (optional param, old callers unaffected)
- **Medium risk**: Threshold calibration (depends on actual cosine scores from real data)
- **Mitigation**: If no useful threshold exists, report finding and don't force it

## Estimated Lines Changed
- search.py: ~25 lines (SearchHit fields + _rrf_fuse extension + plumbing)
- qa_workflow.py: ~30 lines (AbstentionGate class + gate check in ask())
- run_eval.py: ~25 lines (abstention metrics)
- test_qa_workflow.py: ~80 lines (7 new tests)
- Total: ~160 lines
