# P5-101 Engineering Review — Retrieval Foundation

**Task:** P5-101 — Retrieval Foundation
**Phase:** Phase 5 (retrieval foundation; no BM25 / RRF / re-ranking / hybrid yet)
**Date:** 2026-08-08
**Verdict:** **APPROVED**

---

## 1. Deliverable

A deterministic, provenance-preserving retrieval foundation per MEDD §7.6, built as strictly additive changes over the existing `VectorStore` / `SemanticSearch` / `HybridSearch`:

| Artifact | Purpose | Reuses |
|----------|---------|--------|
| `VectorEntry.start_char` / `end_char` | Half-open char offsets into the source document, preserved per chunk | `DocumentChunk.start_char` / `end_char` |
| `VectorStore.search(filters=...)` | Deterministic ranking (score desc, `entry.id` asc tie-break) + exact-match filtering on entry fields / metadata keys | Existing cosine `search()` |
| `SearchHit` provenance fields | `source_type`, `chunk_index`, `start_char`, `end_char`, `metadata`, `parent_section` on every hit | Existing `text` / `source` / `score` / `entry_id` |
| `SearchService` | Spec-facing facade `search(query, *, top_k, filter, min_score)`; embeds the query text via an injected callable and returns `SearchHit[]` | MEDD §7.6 interface |
| `_run_knowledge_engine` offsets | Pipeline stores chunk offsets into every `VectorEntry` | `DocumentChunk` |

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| 1. Identify the canonical searchable unit | DONE | `DocumentChunk` (id, text, source, source_type, chunk_index, offsets, metadata) is the searchable unit; its `VectorEntry` projection is what the store persists. |
| 2. Identify existing metadata | DONE | `VectorEntry` carries `source`, `source_type`, `chunk_index`, `metadata` (heading keys: `heading`, `heading_level`, `heading_path`, `parent_heading`); chunk offsets existed on `DocumentChunk` but were dropped at the store boundary — now carried through. |
| 3. Smallest retrieval abstraction required by the specification | DONE | `SearchService.search(query, *, top_k=5, filter=None, min_score=0.0) -> list[SearchHit]` matches the MEDD §7.6 interface verbatim; dense-only, one ranking pass, no speculative architecture. |
| 4. Deterministic retrieval results | DONE | `VectorStore.search` sorts by `(-score, entry.id)` — a total order, so equal scores always resolve identically regardless of insertion order (tests prove across construction orders and repeated searches). |
| 5. Preserve document identity, chunk identity, source metadata, offsets where available, existing metadata filters | DONE | Every `SearchHit` carries `entry_id` (chunk id), `source` (document), `source_type`, `chunk_index`, `start_char`/`end_char`, and a copy of `metadata`. `filters=` applies exact-match on entry fields then metadata keys; structured `$in` syntax is roadmap 4.5 (unchanged). |
| 6. Stable result structure with retrieved chunk/document, score, source metadata | DONE | `SearchHit` (slots dataclass) is the single result shape returned by `SearchService`, `SemanticSearch`, and `HybridSearch` via the shared `_to_hit`. |
| 7. Handle empty index, empty query, missing docs, invalid ids, duplicate candidates | DONE | Empty index → `[]`; blank query → `[]`; unknown entry ids → `None`/absent (existing `get`/`remove`); duplicate chunk ids → deduped at insertion (`dict` keyed by id), so a duplicate candidate can never surface twice; embedder failure → `[]`. |
| 8. Do not implement advanced ranking or hybrid search yet | DONE | No BM25 (4.1), no RRF (4.2), no cross-encoder (4.3), no query rewriting (4.4), no `$in` filter syntax (4.5), no parent-child context (4.6), no CLI (4.7). `HybridSearch` is untouched behaviorally. |
| 9. Do not break Phase 1–4 behavior | DONE | `SemanticSearch`/`HybridSearch` signatures and `VectorStore` public API unchanged (only additive params/fields). Full default suite: **1289 passed / 0 regressions**. |
| 10. Feature-disabled backward compatible | DONE | `SearchService` returns `[]` when the embedder raises or returns `None` (no Ollama / service disabled); the pipeline still short-circuits when `_chunker`/`_embedding_service`/`_vector_store` is `None`; old persisted stores load fine (offsets default to `None` via `.get`). |

## 3. Backward Compatibility

- `VectorEntry` gains two optional fields with `None` defaults — every existing constructor call site is unaffected.
- Persisted `vector_store.json` files written before this milestone load unchanged (`start_char`/`end_char` fall back to `None`); new saves add the two keys.
- `SemanticSearch`, `HybridSearch`, and `VectorStore.search` keep their existing signatures; `SearchService` is a new class with no consumers to migrate.
- `_run_knowledge_engine` behavior is identical except entries now carry offsets (tested: `test_knowledge_engine_skips_when_no_components` unchanged).
- No config schema, no CLI/API change, no MEDD version bump (milestone released as a whole, per Phase 4 convention).

## 4. Testing

**17 new tests** in `tests/unit/test_knowledge_engine.py` (`TestSearchService` ×11; `TestVectorStore` +4; `TestSemanticSearch` +1; `TestHybridSearch` +1):

- Empty index, blank/empty query, embedder raising, embedder returning `None` (feature-disabled) → `[]`.
- Single-document multi-chunk retrieval; multi-document retrieval; `top_k`; `min_score` threshold.
- Full hit provenance (entry id, source, source_type, chunk_index, offsets, metadata copy, `parent_section is None`).
- Filter on an entry field (`source_type`) and on a metadata key (`heading`); non-matching filter → `[]`.
- Determinism: equal-score entries resolve in `entry.id` order across repeated searches and for both `VectorStore.search` and `HybridSearch`.
- Duplicate chunk ids deduped (single result, last-write-wins text).
- Offsets round-trip through `save()` / `_load()`.

## 5. Verification (commands re-run this session)

| Gate | Result |
|------|--------|
| Focused suite (`test_knowledge_engine.py`) | **212 passed** |
| Full default regression suite | **1289 passed / 0 failed / 54 deselected** (baseline +17 new; 0 regressions) |
| Integration suite | **52 passed / 1 skipped** (Tesseract binary absent — pre-existing env skip) / **1 failed** (`smoke_test.py::test_live_ollama_analysis_and_note_generation` — pre-existing live-LLM flake, nondeterministic model-output truncation, exercises no P5-101 code; same flake documented in P4-104/105) |
| Ruff (changed app files) | **All checks passed** (0 findings on `domain/vector_store.py`, `infrastructure/vector_store.py`, `infrastructure/search.py`, `pipelines/ingest_workflow.py`; the 4 findings on unchanged test-file lines are pre-existing baseline debt) |
| Mypy (`--ignore-missing-imports`) | **Success: no issues found** in the 3 core modules (env-wide mypy blocked by the pre-existing numpy-stub issue under Python 3.14) |
| Coverage | `domain/vector_store.py` **100%**, `infrastructure/search.py` **100%**, `infrastructure/vector_store.py` **95%** (4 pre-existing guard/warning lines: `save()` with no path, `_load()` with missing path, corrupt-file warning; all new code 100% covered). Repo floor 80%. |

## 6. Files Changed

| File | Action |
|------|--------|
| `app/domain/vector_store.py` | **Updated** — `VectorEntry.start_char` / `end_char` (optional) |
| `app/infrastructure/vector_store.py` | **Updated** — deterministic tie-break, exact-match `filters=`, offset persistence |
| `app/infrastructure/search.py` | **Updated** — `SearchHit` provenance fields, shared `_to_hit`, new `SearchService`, deterministic `HybridSearch` order |
| `app/pipelines/ingest_workflow.py` | **Updated** — store chunk offsets in `VectorEntry` |
| `tests/unit/test_knowledge_engine.py` | **Updated** — 17 new tests |

## 7. Findings

**Blocking:** None.

**Non-blocking:**
- `SearchHit.parent_section` is always `None` today; it maps from `metadata["parent_section_id"]` when that key exists, and roadmap 4.6 (parent-child retrieval) will populate the section text. `parent_heading`/`heading_path` are already preserved in `metadata`.
- `filters=` is exact-match only; structured `$in` / range syntax is roadmap 4.5.
- Vector store remains an in-memory JSON-persisted store; FAISS (roadmap 4.x dependency) is unchanged.
- Per-task atomic commits pending (working tree uncommitted, consistent with M2.1–M4.0 convention).

## 8. Conclusion

P5-101 delivers the retrieval foundation as strictly additive changes: the `DocumentChunk` provenance (offsets included) now flows all the way through the vector store, ranking is fully deterministic, exact-match metadata filtering is available, and the MEDD §7.6 `SearchService` facade is implemented dense-only with safe `[]` behavior when embedding is unavailable. Existing `SemanticSearch`/`HybridSearch`/`VectorStore` APIs are unchanged, persisted stores remain compatible, and no advanced ranking or hybrid machinery was added. All gates pass (1289 unit tests, 0 regressions; 52 integration tests pass; ruff clean on changed files; mypy clean on core modules; new code 100% covered; the sole failing test is a pre-existing live-LLM flake independent of this milestone).

**Verdict:** **APPROVED**
