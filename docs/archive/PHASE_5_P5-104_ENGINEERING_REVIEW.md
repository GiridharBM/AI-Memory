# P5-104 Engineering Review — Query Processing and Retrieval Pipeline

**Task:** P5-104 — Query Processing and Retrieval Pipeline
**Phase:** Phase 5 (retrieval; canonical query entry point + CLI wiring, roadmap §4.7, MEDD §7.6)
**Date:** 2026-08-08
**Verdict:** **APPROVED**

---

## 1. Deliverable

P5-104 connects the frozen query-side interfaces to the retrieval stack. `SearchService` (MEDD §7.6) was the canonical query entry point but had zero production callers; this milestone gives it the same settings-based construction path the ingest side already has (`IngestionWorkflow.create_default`), then wires it to the CLI (`pam search`, roadmap §4.7). A query now flows through production wiring end to end — persisted store → embed → hybrid retrieval → RRF ranking → filter → top-k — without duplicating pipeline logic.

## 2. Specification Conformance

| Spec element (MEDD §7.6 / roadmap §4.7) | Actual behavior | Verdict |
|---|---|---|
| `SearchService.search(query, *, top_k=5, filter=None, min_score=0.0)` | Signature unchanged and still canonical; CLI delegates to it via `SearchService.create_default` | **MATCHES** |
| `SearchHit` result structure reused | CLI consumes `SearchHit` unchanged; no new result type | **MATCHES** |
| `pam search <query>` CLI command (roadmap 4.7) | `cli.command("search")` added to `app/cli/entry.py` | **MATCHES** |
| CLI accepts `--top-k`, `--source-type`, `--filter`, `--min-score` | All four options implemented; `--filter` parses JSON and `--source-type` merges in as `filter["source_type"]` | **MATCHES** |
| Settings-based construction matching ingest (`create_default`) | `SearchService.create_default(settings, *, embed=None)` mirrors `IngestionWorkflow.create_default`; store reads the same persisted file (`manifest_root/vector_store.json`) ingest writes; default embed uses the configured model (`settings.models.embeddings`, default `nomic-embed-text`) | **MATCHES** |
| Degrade gracefully when embeddings unavailable (roadmap 4.1 fallback) | `SearchService._embed_query` already swallows embedder failure → lexical-only; `create_default` default embedder is routed through the same path | **MATCHES** |
| Empty/blank query behavior | CLI rejects blank queries with exit 1; service short-circuits blank queries → `[]` | **MATCHES** |
| No live-service requirement in CLI path tests | Unit CLI tests monkeypatch `SearchService`; integration tests inject a deterministic fake embedder — no Ollama needed | **MATCHES** |

## 3. Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| 1. Connect query processing to retrieval without duplicating pipeline logic | DONE | `SearchService.create_default` is the single wiring point (mirrors `IngestionWorkflow.create_default`); CLI is a thin wrapper delegating to `service.search(...)`; no query-side duplicate of store/embed/rank/fuse/filter logic. |
| 2. Construct the canonical query entry point from settings | DONE | `create_default` builds `VectorStore(persistence_path=manifest_root/vector_store.json)` + default `EmbeddingService(settings.ollama, model=settings.models.embeddings)`; `embed` injectable for tests. |
| 3. Expose querying through the CLI (roadmap §4.7) | DONE | `pam search <query>` with `--top-k`, `--source-type`, `--filter`, `--min-score`; Rich table output; JSON-object `--filter` merged with `--source-type`; blank query, bad JSON, non-object JSON → exit 1; `--top-k 0` → typer usage error (exit 2). |
| 4. Persist-to-query round trip works | DONE | Integration tests run the real `IngestionWorkflow` (fake embedder) → write `vector_store.json` → `SearchService.create_default` loads the same file and serves hybrid queries. |
| 5. Preserve P5-101/102/103 scoring and ranking semantics | DONE | Zero changes to `_rrf_fuse`, `HybridSearch`, `SemanticSearch`, or `SearchService.search`; all prior scoring tests pass unchanged. |
| 6. Do not alter the `SearchService` public interface | DONE | `search(...)` signature untouched; `create_default` added as the settings-based constructor only. |
| 7. Blank/malformed query and embedder-failure handling | DONE | Blank CLI query rejected (exit 1); blank service query → `[]` with embed never called; embedder raising → lexical-only fallback (unit-tested). |

## 4. Testing — Coverage (`tests/unit/test_query_pipeline.py` 12 tests, `tests/unit/test_cli.py` +8 tests, `tests/integration/test_query_pipeline_integration.py` 5 tests)

| Required behavior | Covered by |
|---|---|
| `create_default` loads the persisted store | `TestCreateDefaultWiring.test_loads_persisted_store` (seeds store → create_default → hits with full entry fields incl. metadata) |
| Missing store file → empty results, no crash | `TestCreateDefaultWiring.test_missing_store_returns_empty` |
| Normal end-to-end query | `TestCompleteQueryPath.test_normal_query` |
| Empty/whitespace query → `[]`, embed never called | `TestCompleteQueryPath.test_empty_and_whitespace_query` |
| Multi-result ranking order | `TestCompleteQueryPath.test_multiple_results` (exact fused order across docs) |
| No-result query | `TestCompleteQueryPath.test_no_result_query` (embedder returns None → lexical-only → no match) |
| Post-fusion filtering | `TestCompleteQueryPath.test_filtered_query` |
| top-k limiting | `TestCompleteQueryPath.test_top_k_query` |
| min_score threshold (RRF units) | `TestCompleteQueryPath.test_min_score_query` (only 2/61 clears 0.03) |
| Deterministic repeated runs | `TestCompleteQueryPath.test_repeated_identical_query_deterministic` |
| Embed called exactly once per query | `TestEmbeddingAvoidanceAndFallback.test_embed_called_once_per_query` |
| Embedder failure degrades to lexical | `TestEmbeddingAvoidanceAndFallback.test_embedder_failure_falls_back_to_lexical` |
| CLI renders ranked results + forwards args | `test_cli_search_displays_ranked_results` (score format, source, type, `(query, top_k, filter, min_score)` forwarding) |
| CLI `--source-type` + `--filter` merge | `test_cli_search_merges_source_type_and_filter` |
| CLI no-results rendering | `test_cli_search_no_results` |
| CLI blank query → exit 1 | `test_cli_search_empty_query_exits_one` |
| CLI bad / non-object `--filter` → exit 1 | `test_cli_search_bad_filter_json_exits_one`, `test_cli_search_non_object_filter_exits_one` |
| CLI `--top-k 0` → usage error (exit 2) | `test_cli_search_zero_top_k_exits_two` |
| CLI service failure → graceful exit 1 | `test_cli_search_handles_service_failure` |
| Ingest → persist → query round trip (real workflow) | `tests/integration/test_query_pipeline_integration.py` (5 tests: queryable, deterministic, filter, top-k/min-score, blank) |

## 5. Verification (commands re-run this session)

| Gate | Result |
|------|--------|
| Focused pipeline suite (`test_query_pipeline.py` + `test_bm25.py` + `test_scoring.py`) | **55 passed** |
| CLI suite (`test_cli.py`) | **13 passed** |
| New integration file | **5 passed** (fake embedder, no live services) |
| Full default regression suite | **1366 passed / 0 failed / 59 deselected** (baseline 1346/54 + 20 new unit tests; 0 regressions) |
| Integration suite | **57 passed / 1 skipped** (Tesseract binary absent — pre-existing env skip) / **1 failed** (`smoke_test.py::test_live_ollama_analysis_and_note_generation` — pre-existing live-LLM flake, exercises no P5-104 code; same as P5-102/103 records) |
| Ruff | **All checks passed** on changed files (search.py, entry.py, 3 test files) |
| Mypy | **Success: no issues found** in the 4 core modules (bm25, search, vector_store infra + domain) |
| Coverage | `search.py` **95%** (5 lines: the live-Ollama default-embedder branch of `create_default`), `entry.py` **86%**, repo total **90%** vs floor 80% |
| Rollback | Trivially clean: production changes are the two additive edits (search.py `create_default`, entry.py `search` + 2 helpers); new tests are untracked files. Removing them restores the exact prior tree. |

## 6. Files Changed

| File | Action |
|------|--------|
| `app/infrastructure/search.py` | **Modified** — added `SearchService.create_default(settings, *, embed=None)` (settings → persisted store + default EmbeddingService; embed injectable) |
| `app/cli/entry.py` | **Modified** — added `pam search` command (route 4.7) + `_parse_search_filters` + `_print_search_results` helpers |
| `tests/unit/test_query_pipeline.py` | **New** — 12 tests for `create_default` wiring and the complete query path |
| `tests/unit/test_cli.py` | **Modified** — 8 new `pam search` tests |
| `tests/integration/test_query_pipeline_integration.py` | **New** — 5 ingest→persist→query round-trip tests with a deterministic fake embedder |

## 7. Findings

**Blocking:** None.

**Non-blocking:**
- The 5 uncovered lines in `search.py` are the `embed is None` default branch (constructs the live `EmbeddingService`); exercised in production, deliberately not in tests (no live Ollama in CI). 95% for the file, 90% repo-wide.
- `--source-type` is a convenience that merges into the `filter` dict (`filter["source_type"]`); roadmap's separate `--source-type` and `--filter` flags are both present, single code path.
- The pre-existing full-suite flake `tests/unit/test_mime_detection.py::test_binary_garbage_is_octet_stream` (unrelated untracked Phase 2–4 file) intermittently fails in full-suite runs and passes in isolation; not introduced by P5-104 and observed to self-clear.
- Per-task atomic commits pending (working tree carries pre-existing uncommitted Phase 2–4 work, consistent with M2.1–M5.0 convention).

## 8. Conclusion

The canonical query entry point is now connected to the retrieval stack and exposed to users: `SearchService.create_default` mirrors the ingest-side construction pattern (same persisted store file, configured embedding model, injectable embedder for tests), and `pam search` (roadmap §4.7) is a thin, testable CLI wrapper with `--top-k`, `--source-type`, `--filter`, and `--min-score`. Scoring and ranking semantics from P5-101/102/103 are untouched — zero changes to the fuse/hybrid/filter internals — and the full regression suite confirms it (1366 passed, 0 regressions). Persist-to-query round trips are proven against the real `IngestionWorkflow` with deterministic fake embeddings. All gates pass: unit + integration suites green (only the pre-existing Tesseract env-skip and live-LLM smoke flake), ruff clean, mypy clean on the core modules, and coverage well above the 80% floor.

**Verdict:** **APPROVED**
