# P4-104 Engineering Review — Knowledge Graph Construction

**Task:** P4-104 — Knowledge Graph Construction
**Phase:** Phase 4 (document-level graph construction; no graph storage/retrieval)
**Date:** 2026-08-08
**Verdict:** **APPROVED**

---

## 1. Deliverable

New document-level graph-construction capability in `app/infrastructure/document_intelligence/graph/`, wired into the ingestion enrichment stage:

| Artifact | Purpose |
|----------|---------|
| `builder.py` | Deterministic `DocumentGraphBuilder.build(entities, relationships, source) → KnowledgeGraph`; `find_relationships()` lookup; `graph_to_dict()` serialization; `get_default_document_graph_builder()` (composition root) and `build_document_graph()` (public API) |
| `__init__.py` | Package exports |
| `config/default.yaml` + `app/core/config.py` | `intelligence.graph.enabled` toggle mirroring the `entities`/`relationships` blocks (rollback R-4) |
| `app/pipelines/ingest_workflow.py` | Enrichment stage now attaches `metadata.extra["knowledge_graph"]` beside `extra["entities"]`/`extra["relationships"]` |

The builder reuses the P4-101 `Entity`/`Relationship` models as input and the existing M4 in-memory `KnowledgeGraph`/`KnowledgeNode`/`KnowledgeEdge` (`app/domain/knowledge_graph.py`) as the graph abstraction — requirement 2/10: no new graph store, no persistent graph-database infrastructure.

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| 1. Reuse the P4-101 entity/relationship models | DONE | `build()` consumes `Sequence[Entity]` and `Sequence[Relationship]` directly (the same objects the workflow extracts for `extra["entities"]`/`extra["relationships"]`); the graph is a derived view, never a re-parse. |
| 2. Smallest graph abstraction required | DONE | Reuses the existing in-memory `KnowledgeGraph` (nodes dict + edges list, `add_node`/`add_edge`/`neighbors`/`subgraph`). No new graph class, no database. Only added capability missing from `KnowledgeGraph` is relationship lookup — a 9-line `find_relationships()` filter. |
| 3. nodes/entities, edges/relationships, deterministic traversal, entity-id lookup, relationship lookup | DONE | `Entity` → `KnowledgeNode` (`node_type="entity"`), `Relationship` → `KnowledgeEdge` (`edge_type`/`weight` carried directly). Traversal = `KnowledgeGraph.neighbors` (single-hop, deterministic over the sorted edge list). Entity-id lookup = `graph.nodes[id]`. Relationship lookup = `find_relationships(graph, *, source_id, target_id, edge_type)` (wildcard filters, deterministic order). |
| 4. Preserve document/source metadata | DONE | `KnowledgeNode.source = source` on every node; edge `metadata["source"]` and the relationship `id` preserved on every edge; `entity_type`/`importance` preserved in node metadata. |
| 5. Prevent duplicate nodes and duplicate edges | DONE | Nodes dedup by `Entity.id` (`add_node` dict semantics); edges dedup by `(source_id, target_id, edge_type)` after a deterministic sort (first wins). Proven by `test_duplicate_entities_collapse_to_one_node` / `test_duplicate_relationships_collapse_to_one_edge`. |
| 6. Handle disconnected nodes | DONE | Entities with no shared section produce isolated nodes with zero edges — a valid graph. Proven by `test_disconnected_entities_yield_isolated_nodes` and the pipeline-level section test. |
| 7. Handle cycles safely | DONE | Traversal is single-hop `neighbors` (no recursion); `KnowledgeGraph.subgraph` uses a visited set. A 3-cycle builds, traverses, and subgraphs without hanging (`test_cycle_traversal_is_safe`). |
| 8. Handle missing/invalid relationships without crashing | DONE | Edges whose endpoints are not in the entity set are skipped with a logged warning; empty/`[]` inputs yield an empty graph. Proven by `test_missing_targets_are_skipped_without_crash` and `test_empty_input_yields_empty_graph`. At the workflow boundary the builder is wrapped in the M2.2 lesson-L4 containment (`test_builder_failure_contained_and_ingestion_continues`). |
| 9. Keep graph construction deterministic | DONE | Nodes and edges are sorted by id, so the built graph is a pure function of the inputs regardless of input list order. Proven byte-stable via `graph_to_dict` equality across reversed input and across instances (`test_deterministic_across_input_order`, `test_same_input_identical_across_instances`). |
| 10. No persistent graph-database infrastructure | DONE | Output is the in-memory `KnowledgeGraph`. The only serialization is `graph_to_dict()` mirroring `KnowledgeGraph.save`'s shape for the `metadata.extra` artifact; the M4 `save`/`load`/`merge` persistence is untouched and not required by this milestone. |

## 3. Design Notes

- **Mapping.** `Entity` → `KnowledgeNode(id=entity.id, label, node_type="entity", source, metadata={"entity_type", "importance"})`. `Relationship` → `KnowledgeEdge(source_id, target_id, edge_type, weight, metadata={"id": relationship.id, "source"})`. The relationship id survives on the edge (KnowledgeEdge has no id field; `metadata["id"]` carries it) so `extra["knowledge_graph"]` round-trips with `KnowledgeGraph.load` and links back to `extra["relationships"]`.
- **Dedup keys.** Nodes keyed by `Entity.id`; edges keyed by `(source_id, target_id, edge_type)` — the same canonicalization P4-103 already applies to pairs, so a second `related_to` edge between the same endpoints can never form.
- **Determinism.** Inputs are sorted (`entities` by id, `relationships` by id) before dedup/insert, and edges are sorted by `(source_id, target_id, edge_type)` for output — order-independent construction with deterministic traversal and lookup.
- **Single-pass consistency.** `_enrich_relationships` now returns `Relationship` objects (mirroring the P4-103 `_enrich_entities` refactor); the caller serializes `extra["relationships"]` and feeds the same objects to `_enrich_graph`, so extraction, detection, and construction can never disagree. When `relationships.enabled` is false, the graph is built from entities alone (disconnected nodes) — the graph toggle is independent.
- **Rollback surface.** `graph.enabled: false` omits the `knowledge_graph` key entirely; the feature is additive-only.

## 4. Testing

**27 focused tests** across `tests/unit/test_document_graph_builder.py` (17) and `tests/integration/test_graph_pipeline.py` (10), covering every mandated category:

- Empty graph; single node; multiple nodes (with `entity_type`/`importance` metadata); single edge (type/weight/id/source metadata); multiple edges.
- Disconnected components: isolated nodes with no edges, `neighbors` on an isolated node returns `[]`.
- Cycles: 3-cycle builds, single-hop `neighbors` never loops, `subgraph(depth=2)` visits all nodes exactly once.
- Duplicate entities → one node; duplicate relationships → one edge.
- Missing relationship targets skipped without crashing; `[]` input → empty graph.
- Deterministic construction: `graph_to_dict` byte-stable across reversed input order and across builder instances; sorted node/edge output.
- Entity-id lookup (`graph.nodes.get`); relationship lookup via `find_relationships` (source/target/type wildcards, conjunctive filters, deterministic order).
- Serialization: `graph_to_dict` round-trips through `KnowledgeGraph.load` (unit and pipeline-level).
- Public API: `DocumentGraphBuilder`, `get_default_document_graph_builder`, `build_document_graph`.
- **Pipeline wiring (integration):** real `StructureAnalyzer` → `EntityExtractor` → `RelationshipDetector` → `DocumentGraphBuilder` — nodes cover the extracted entities with `source` preserved, edges reflect section connectivity, cross-section entities stay disconnected.
- **Workflow wiring (integration):** `IngestionWorkflow.create_default` attaches `extra["knowledge_graph"]` for markdown (node ids, `node_type`, edge metadata asserted); `relationships.enabled: false` yields a nodes-only graph; `graph.enabled: false` and non-text kinds omit the key; a raising builder is contained and ingestion completes; the builder is wired by `create_default` even when disabled.

## 5. Verification (commands re-run this session)

| Gate | Result |
|------|--------|
| Focused tests | **27 passed** (17 unit + 3 chained + 7 workflow integration) |
| Full regression suite | **1242 passed / 0 failed / 52 deselected** (baseline 1222 + 20 new non-integration; 0 regressions) |
| Integration suite | **50 passed / 1 skipped** (Tesseract binary absent — pre-existing env skip) / 1242 deselected. `smoke_test.py::test_live_ollama_analysis_and_note_generation` (live `llama3.1:8b` call, independent of P4-104) failed on model-output variance: different note sections missing on each re-run, i.e. nondeterministic LLM truncation, not a code regression. |
| Ruff | **All checks passed** (changed files: graph package, config, workflow, both test files) |
| Mypy | **graph package: 0 issues.** The single new workflow line (`builder.build`) follows the pre-existing `object`-typed DI pattern (identical to siblings at 682/720/728/928); full-repo mypy remains blocked by the environment numpy-stub issue under the Python 3.14 interpreter. |
| Coverage (`graph` package) | **100%** (41 stmts, 0 miss; repo floor 80%) |
| Rollback | Additive-only: remove the `graph/` package, the config toggle, the enrichment call, and its tests; `enabled: false` alone suffices for behavior rollback (R-4). Worktree uncommitted (per-task atomic commits pending), consistent with the M2.1–M4 convention. |

## 6. Files Changed

| File | Action |
|------|--------|
| `app/infrastructure/document_intelligence/graph/builder.py` | **Created** — `DocumentGraphBuilder`, `find_relationships`, `graph_to_dict`, composition roots |
| `app/infrastructure/document_intelligence/graph/__init__.py` | **Created** — package exports |
| `app/infrastructure/document_intelligence/__init__.py` | **Modified** — export graph functions |
| `app/core/config.py` | **Modified** — `GraphSettings` model; `IntelligenceSettings.graph` field |
| `config/default.yaml` | **Modified** — `intelligence.graph.enabled: true` |
| `app/pipelines/ingest_workflow.py` | **Modified** — DI param, `_graph()` accessor, `_enrich_graph()` + `extra["knowledge_graph"]`; `_enrich_relationships` refactored to return `Relationship` objects |
| `tests/unit/test_document_graph_builder.py` | **Created** — 17 focused tests |
| `tests/integration/test_graph_pipeline.py` | **Created** — 3 chained + 7 workflow-integration tests |

## 7. Findings

**Blocking:** None.

**Non-blocking:**
- `smoke_test.py::test_live_ollama_analysis_and_note_generation` is a live-model smoke test (requires a running Ollama `llama3.1:8b`); it exercises `OllamaClient` → `ObsidianMarkdownGenerator` and no P4-104 code. It is nondeterministic by nature — different note sections were missing on consecutive runs — and is not a regression introduced by this milestone.
- `KnowledgeEdge` carries no id field (M4 design); the relationship id is preserved in edge `metadata["id"]`. A future graph-retrieval milestone may promote id to a first-class field (TD-14 precedent).
- Per-task atomic commits pending (worktree uncommitted; consistent with M2.1–M3.2 convention).
- Phase 4 milestones ship additive-only; no MEDD version bump until Phase 4 is released as a whole.

## 8. Conclusion

P4-104 delivers deterministic, dependency-free document-level graph construction that reuses the P4-101 models and the existing in-memory `KnowledgeGraph` abstraction: entities map to nodes (with source/type/importance metadata), relationships map to deduplicated edges (with id/source metadata), disconnected entities and cycles are handled safely, missing relationship targets are skipped, and construction is a pure function of the pipeline's entity/relationship output — wired into the workflow as `extra["knowledge_graph"]` behind `graph.enabled`. All gates pass (1242 passed, 0 regressions; ruff clean; graph package mypy-clean; 100% package coverage; 50 integration tests pass; the sole failing test is a pre-existing live-LLM flake independent of this milestone).

**Verdict:** **APPROVED**
