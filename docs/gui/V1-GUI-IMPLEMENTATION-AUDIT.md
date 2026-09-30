# PAM V1 GUI — Implementation Audit

**Date:** 2026-09-30
**Branch:** `main` · **HEAD:** `ffcded1` "fix: repair EPUB ingestion (path-string parse, zip paths, dc metadata)"
**Baseline test result:** `1714 passed, 57 deselected` (pytest, `-m 'not integration'`)

**Scope of this document:** repository audit performed before any GUI code was
written, per the V1 brief. No application code was modified to produce it.

---

## 1. Existing architecture

PAM is a clean layered Python application, Python ≥ 3.11, packaged with
setuptools, exposed as a single console script (`pam = app.cli.entry:main`).

| Layer | Package | Responsibility |
|---|---|---|
| Domain | `app/domain/` | Pure data shapes — `VectorEntry`, `SearchResult`, `SourceDocument`, `KnowledgeGraph`, chunking/routing/notes contracts. No I/O. |
| Infrastructure | `app/infrastructure/` | All adapters: `VectorStore`, `BM25Index`, `SearchService`/`HybridSearch`, `EmbeddingService`, `OllamaClient`, ingestion (**21 ingestors**), `ManifestManager`, vault writer, reranker, HyDE, answerability gate, model routing. |
| Application | `app/application/` | Use cases: `QAWorkflow`, `SystemFactsService`/`SystemFactsRouter`, `AIProcessor`, `qa_measurement_harness`. |
| Pipeline | `app/pipelines/` | `IngestionWorkflow` — the end-to-end ingest orchestrator. |
| Interface | `app/cli/entry.py` | **Typer CLI — the only existing interface.** |
| Runtime | `app/watcher/`, `app/queue/` | Inbox watcher + single-worker durable queue. |
| Persistence | `data/manifests/` | `vector_store.json`, `processed_files.json`, `knowledge_graph.json`, `queue_state.json`, plus timestamped backups. |
| Knowledge output | `vault/Notes/` | 290 generated Obsidian notes. |
| Evaluation | `eval/` | 8 analysis scripts + 18 result artifacts (`eval/results/*.json`, `*.jsonl`). |

Layer discipline is strict and already tested: infrastructure never imports the
CLI, and the CLI never reimplements retrieval. **The GUI must preserve this.**

### Verified call surfaces (exact signatures)

```python
# app/infrastructure/search.py:314
SearchService.create_default(settings: Settings, *, embed=None) -> SearchService
SearchService.search(query: str, *, top_k: int = 5,
                     filter: dict[str, object] | None = None,
                     min_score: float = 0.0) -> list[SearchHit]

# app/infrastructure/search.py:21 — per-hit scores ARE exposed
@dataclass(slots=True)
class SearchHit:
    text: str; source: str; score: float; entry_id: str
    cosine_score: float = 0.0     # raw dense leg
    bm25_score: float = 0.0       # raw lexical leg
    rerank_score: float = 0.0     # 0.0 ⇒ reranker disabled or failed
    parent_section: str | None = None
    source_type: str = ""; chunk_index: int = 0
    start_char: int | None; end_char: int | None
    metadata: dict[str, str]

# app/application/qa_workflow.py:406 / :458
QAWorkflow.create_default(settings, *, model=None) -> QAWorkflow
QAWorkflow.ask(question: str, *, top_k: int = 5, min_score: float = 0.0,
               filter: dict | None = None) -> QAAnswer

# app/application/qa_workflow.py:182 — the full answer contract
@dataclass(slots=True)
class QAAnswer:
    answer: str
    sources: list[SearchHit]
    model: str
    outcome: str                    # "answered" | "abstained"
    abstention_reason: str | None
    citations: list[SourceCitation] # validated [SOURCE N] -> SearchHit
    invalid_citations: list[int]
    duplicate_citations: int
    latency_seconds: float | None
    telemetry: ObservationTelemetry | None
    origin: str                      # "retrieval" | "system"

# app/core/config.py:537
load_settings(*, environment=None, config_dir=None) -> Settings
settings.model_dump_json()           # already used by `pam config --json`

# app/pipelines/ingest_workflow.py:249 / :318
IngestionWorkflow.create_default(settings, *, vision_client=None, transcriber=None)
IngestionWorkflow.run(source: str | Path, *, expected_source_type: str | None = None)
    -> IngestionWorkflowResult      # SYNCHRONOUS; returns on completion only
```

---

## 2. Frontend status

**None. Zero frontend code exists.**

Verified by: `git ls-files` filtered for `package.json|*.tsx|*.jsx|*.vue|*.svelte|
vite.config|next.config|tailwind.config` → no matches. Recursive disk scan for
`package.json`, `*.config.*`, `index.html` outside `.venv`/`.git` → no matches.
No `static/`, no Jinja templates (`app/templates/obsidian_note.py` is a note
*renderer*, not an HTML template).

**The project documents this as a known, intentional gap** — not an oversight:

- `docs/MASTER_ENGINEERING_DESIGN_DOCUMENT.md:210` — *"**No web UI.** Terminal-only
  CLI. No REST API, no web interface, no Obsidian plugin integration."*
- Same doc, gap **G27**: *"Web UI | Terminal only | HTML/JS search + upload |
  Non-technical users excluded | Medium | Medium"* — remediation scope
  *"Basic web UI (React or plain HTML/JS)"*, sized **4 weeks**, belonging to the
  Docker/REST/auth/monitoring milestone.
- `docs/01_Current_Implementation_Report.md:1108` — *"**Web UI** | **Not
  Implemented** | No frontend code, no HTTP server, no API routes"*.

Consequence: there is **no existing frontend convention to follow**. The brief's
fallback applies — choose the simplest maintainable stack compatible with PAM.

---

## 3. Backend / API status

**No HTTP or API layer exists.** Grep across all `*.py` for
`fastapi|flask|django|starlette|uvicorn|gradio|streamlit|http.server|aiohttp|
litestar|sqlalchemy|jinja` → **zero matches**. `pyproject.toml` declares no web
dependency.

PAM is CLI-only. Every capability a GUI needs is already reachable in-process
through the application/infrastructure services listed in §1 — what is missing
is purely a *transport* to reach them.

---

## 4. Integration opportunities — what the GUI can show with **real** data

Every row below is an **existing** authoritative source. None require new
endpoints to be invented; they require a thin read adapter.

| UI surface | Authoritative source (real, today) | Verified value on this checkout |
|---|---|---|
| Sources count | `VectorStore.entries()` grouped by `source`; CLI `entry.py:306` | **31** distinct sources |
| Memory chunks | `len(vector_store.json["entries"])`; CLI `entry.py:1299` | **526** chunks |
| Knowledge Sources breakdown | `entry["source_type"]` in the store | `pdf 318, markdown 189, scanned_pdf 17, audio 1, image 1` |
| Retrieval top-K | `QAWorkflow.ask(top_k=)` default, config-derived | `top_k=5` |
| System: LLM | `settings.ollama.model` | `qwen3:8b` |
| System: embeddings | `settings.models.embeddings` | `nomic-embed-text` |
| System: RRF k | `_rrf_fuse(..., k=60)` in `search.py:65` | `k = 60` |
| System: reranker | `settings.reranker.enabled` | `false` → must render **Disabled** |
| System: HyDE | `settings.hyde.enabled` | `false` → must render **Disabled** |
| System: answerability | `settings.answerability.enabled` | `false` → must render **Disabled** |
| System: Ollama live | `OllamaClient.is_available()` / `.model_exists()` (used at `entry.py:603`) | live probe, real OK/WARN/FAIL |
| Memories list + per-source status | CLI `_read_vector_store_sources` `entry.py:306` + `_annotate_source_ledger` `entry.py:346` | source, type, chunks, status, last_ingested |
| Memory detail (chunks) | `VectorStore.get(id)` / `.entries()`, chunk `metadata`, `start_char`/`end_char` | real chunk text |
| **Activity timeline** | `ManifestEntry` (`state/models.py:10`) — `processed_at`, `status`, `chunks_stored`, `error_reason`, `embedding_succeeded`, `indexing_succeeded` | **50 ledger events**: 42 processed, 4 failed, 4 skipped |
| Ledger counts | manifest `status` tallies (`entry.py:163-167`) | real |
| Search results + scores | `SearchHit.cosine_score` / `.bm25_score` / `.score` / `.rerank_score` | **all four real** — no fake scores needed |
| Ask answer + citations | `QAAnswer.answer/citations/outcome/abstention_reason/latency` | real, incl. abstention |
| System-facts answers | `SystemFactsService.resolve()` (`system_facts.py:198`) — version, counts, feature flags, capabilities | real, LLM-free |
| Supported ingest types | `SUPPORTED_INGESTION_TYPES` (`system_facts.py:29`) + `service.supported_extensions()` (`service.py:178`) | 21 ingestors, real list |
| Ingestion result | `IngestionWorkflowResult` — `chunks_stored`, `embedding_succeeded`, `indexing_succeeded`, `engine_error` | real |
| Configuration (all 6 categories) | `settings.model_dump()` — `pam config --json` already does exactly this | real, backend-authoritative |
| Storage | `settings.paths.*`, file sizes of `vector_store.json` (6.0 MB) / `knowledge_graph.json` (0.65 MB) | real |
| Evaluation | `eval/results/*.json` — 18 artifacts, static on disk | inventory real; metrics schema-dependent (see §5) |
| Vault notes | `vault/Notes/*.md` | 290 |

**Nothing in the Dashboard design needs to be invented.** The design's example
figures (24 sources / 195 chunks) do **not** match this installation (31 / 526) —
confirming they were placeholders and must be rendered from live data.

---

## 5. Limitations & gaps (documented, not "fixed")

These are real gaps between the GUI spec and current PAM capability. Per the
brief, they are **documented rather than papered over with fake data**.

1. **No HTTP transport (the one blocking gap).** Everything else is reachable
   in-process; only the transport is missing. → §6.
2. **Activity is ingestion-only.** The manifest ledger records *ingest* events.
   Searches, QA queries, config changes and diagnostics runs are **not** recorded
   anywhere. The Activity page must therefore be titled/scoped to ingestion
   activity. Inventing search/QA events is forbidden and is not done.
3. **No ingestion progress reporting.** `IngestionWorkflow.run()` is synchronous
   and returns only on completion; there is no progress callback or phase
   reporting. → indeterminate progress indicator (§17 explicitly allows this).
4. **Evaluation data is static, not runtime-computed.** `eval/results/*.json`
   are frozen experiment artifacts produced offline by `eval/scripts/*`. The
   Evaluation page can list them and parse headline metrics only where the
   schema is unambiguous; otherwise `Not available`.
5. **System-facts vs. knowledge questions.** `SystemFactsRouter` intercepts
   tool-intent questions ("how many sources", "is reranker enabled") and returns
   them with `origin="system"`, `sources=[]`. The UI must render those
   distinctly from grounded answers — they have **no citations by design**.
6. **Non-deterministic availability.** Ollama/embedding health is only knowable
   by live probe. When the server is down, Ask/Search must degrade to
   `Not available from the current PAM runtime`, never to a fabricated result.
7. **`remove` is destructive** (`entry.py:389`) — deletes vectors, KG nodes and
   ledger entries. Excluded from V1 GUI.
8. **`OLLAMA_NUM_CTX = 8192`** is a hardcoded constant (`system_facts.py:38`),
   a runtime setting not present in `config/default.yaml`. It cannot be shown as
   a configurable value without touching core.
9. **BM25 index cost.** `HybridSearch` rebuilds the full BM25 index whenever
   `VectorStore.version` changes (`search.py:164`). A GUI process must cache the
   `VectorStore`/`SearchService` singletons or every request pays a full-corpus
   rebuild over 526 chunks.
10. **Vector store is a single 6 MB JSON document**, fully materialised in
    memory on load. Fine at this scale; the GUI must not assume it scales.

---

## 6. Proposed implementation approach

### Backend: one new **additive** adapter package, zero core edits

```
app/interfaces/web/            # NEW package — the only backend addition
├── __init__.py
├── server.py                  # FastAPI app factory, CORS, static mount
├── deps.py                    # cached settings / SearchService / QAWorkflow singletons
└── routes/                    # thin read-only projections of existing services
    ├── system.py  sources.py  search.py  ask.py  ingest.py  config.py
```

Rules that make this non-invasive:

- **No existing file is modified.** The adapter *imports* `load_settings`,
  `SearchService`, `QAWorkflow`, `ManifestManager`, `VectorStore`,
  `IngestionWorkflow` and *projects* their results to JSON. No retrieval,
  chunking, embedding, BM25, RRF, QA, abstention or config logic is duplicated
  or altered.
- Reuses the CLI's already-proven read projections
  (`_read_vector_store_sources`, `_annotate_source_ledger`) — the **logic** is
  honoured as-is; only the Rich rendering is replaced by JSON.
- Routes declared with **sync `def`**, so Starlette runs them in a threadpool.
  This is the correct fit: `QAWorkflow` is fully blocking (measured 31–55 s per
  question) and already enforces its own wall-clock deadline
  (`_generate_with_deadline`, `qa_workflow.py:611`). Async would add an
  `httpx` dependency and rewrite the Ollama call path for no benefit.
- New dependency added as an **optional extra** (`[project.optional-dependencies]
  gui = ["fastapi", "uvicorn"]`) so `pip install -e .` and the frozen research
  environment are **completely unchanged**.

### Frontend: React + Vite + TypeScript + Tailwind, in `frontend/`

The brief permits this when no frontend exists, and the MEDD G27 row names
React. Plain CSS instead of Tailwind would also satisfy "no unnecessary
dependencies"; **Tailwind is the one discretionary choice here** and is
recommended because the visual direction is a dense, token-driven dark UI where
utility classes are markedly shorter than a hand-written stylesheet.

No Next.js (no SSR/SEO need for a local-first desktop tool; it adds a server
runtime). No state-management library — `fetch` + a small typed client is enough
for ~10 read-only endpoints.

### Data-integrity rules encoded in the UI

- Every figure is either a real backend value or the literal string
  `Not available` / `Unavailable`. No placeholder numbers anywhere.
- Feature-flag rows render `Disabled` when `enabled=false` (reranker, HyDE,
  answerability are all `false` by default) — never "Ready".
- The retrieval-pipeline visualisation shows **only** stages that are actually
  enabled for the running configuration.
- Top bar shows `● LOCAL · HEALTHY` only when config load succeeds **and** the
  Ollama probe passes; otherwise `● STATUS UNKNOWN` / degraded.

---

## 7. Files that will be created

```
docs/gui/V1-GUI-IMPLEMENTATION-AUDIT.md      this document
app/interfaces/__init__.py                    new empty package
app/interfaces/web/__init__.py
app/interfaces/web/server.py
app/interfaces/web/deps.py
app/interfaces/web/routes/__init__.py
app/interfaces/web/routes/{system,sources,search,ask,ingest,config}.py
tests/unit/test_web_routes.py                 new tests for the adapter only
frontend/**                                   new Vite + React + TS app
pyproject.toml                                MODIFIED — add `gui` extra only
```

## 8. Files that must remain untouched

Everything else, explicitly:

```
app/core/**            app/domain/**          app/infrastructure/**
app/application/**     app/pipelines/**        app/queue/**
app/watcher/**         app/prompts/**          app/templates/**
app/cli/**             eval/**                 vault/**      data/**
config/**              tests/**  (existing)    docs/**  (existing)
```

In particular `app/application/qa_workflow.py`, `app/infrastructure/search.py`,
`app/infrastructure/bm25.py`, `app/infrastructure/vector_store.py`,
`app/infrastructure/state/**`, `app/core/config.py` and the CLI are the frozen
research core and the GUI is a consumer of them, never an editor of them.

---

## 9. Stop-condition flag

The brief's §33 requires stopping before a *significant architectural change*.
This audit's conclusion:

- **Not required:** any change to retrieval, ingestion, storage, QA, abstention,
  configuration semantics, CLI behaviour, existing tests or existing docs.
- **Required:** a new transport (`app/interfaces/web/`) and a new optional
  dependency, both purely additive.

The additive transport is unavoidable — a browser cannot call a Python object —
and the project's own design doc already scopes it as planned future work
(G27 / Phase 7). It is nonetheless a decision with a dependency footprint, so it
is raised for approval before implementation rather than assumed.

---

## 10. Post-implementation status (final)

**Date:** 2026-09-30 · **HEAD still `ffcded1`** — all GUI work remains uncommitted.

### Implemented

- `app/interfaces/web/` — FastAPI adapter: `server.py` (app factory, CORS,
  traversal-safe SPA mount), `deps.py` (cached settings / SearchService /
  QAWorkflow / VectorStore singletons, 10 s Ollama health TTL, read-only ledger
  reader, post-ingest cache invalidation), `routes/{system,knowledge,interact}.py`.
- `frontend/` — React 19 + TypeScript + Vite + Tailwind SPA, 11 screens, hash
  router, typed API client, unified loading/empty/error/success handling.
- `pyproject.toml` — optional `gui` extra (`fastapi`, `uvicorn`,
  `python-multipart`) + `pam-gui` console script. No core PAM file modified.
- `tests/unit/test_web_routes.py` — 28 adapter tests (hermetic: tmp settings,
  stubbed Ollama, no network, no durable state).

### API surface (all mapped to real PAM services)

| Method & path | Real source |
|---|---|
| `GET /api/system` | CLI read projections + live Ollama probe + ledger |
| `GET /api/health` | live Ollama probe |
| `GET /api/retrieval` | resolved `Settings` + `OLLAMA_NUM_CTX`, `RRF_K=60` |
| `GET /api/activity?limit=` | durable manifest ledger (read-only reader) |
| `GET /api/config` | `settings.model_dump_json()` (read-only) |
| `GET /api/storage` | `Settings.paths` + artifact sizes + ledger/store counts |
| `GET /api/diagnostics` | environment + settings + writability + live probe |
| `GET /api/evaluation` | `eval/results/*` file inventory (no invented metrics) |
| `GET /api/sources`, `/api/sources/{id}` | vector store + ledger annotation; digest ids |
| `POST /api/search` | `SearchService.search` (real RRF/cosine/BM25; latency timed) |
| `POST /api/ask` | `QAWorkflow.ask` (citations, abstention, telemetry intact) |
| `POST /api/ingest` | `IngestionWorkflow.run` + ledger semantics (mirrors CLI) |
| `GET /api/ingest/capabilities` | live ingestor registry (`supported_extensions`) |

### Verification (actually run on this checkout)

| Check | Result |
|---|---|
| `pytest -m 'not integration'` | **1742 passed, 57 deselected** (baseline 1714 + 28 adapter) |
| `ruff check app/interfaces tests/unit/test_web_routes.py` | All checks passed |
| `mypy app/interfaces/web` | Success, no issues (7 files) |
| `npm run lint` (oxlint) | 0 warnings, 0 errors (21 files, 116 rules) |
| `npm run build` (tsc -b && vite build) | typecheck clean; 33 modules; dist 277 KB (gzip 81 KB) |
| Live boot check | dist served, SPA fallback, `/api/system` healthy |
| Live API smoke | search real scores + latency; system-facts ask answered; 31 sources / 526 chunks; source detail; 94 extensions |
| Headless-browser render | Edge headless DOM of all 11 routes rendered with real data; real screenshots in `pam_shots\` |

### Virtual-Phalanx acceptance notes

- [x] No fabricated statistics/sources/chunks/backend capabilities.
- [x] No destructive V1 operation exposed (`pam remove` excluded).
- [x] Static path traversal protection kept and re-tested (`TestStaticSpa`).
- [x] Reranker / HyDE / answerability render **Disabled** (all default off).
- [x] Evaluation shows artifact inventory only; metrics = Not available.
- [x] Activity explicitly scoped to ingestion (ledger is ingest-only).
- [x] Configuration page is read-only; setting semantics untouched.
- [x] `Not available` shown wherever a real value cannot be determined.
- [x] All changes left in the working tree; nothing committed or pushed.

### Known limitations (unchanged by the GUI, documented, not worked around)

- Cold grounded QA on this machine can exceed PAM's own 120 s
  `qa.timeout_seconds` while `qwen3:8b` cold-loads at 8192 context. Observed
  live: a retrieval-generated answer timed out at the QA deadline and the route
  returned the honest 502 (`test_qa_failure_becomes_502_not_an_answer` covers
  this mapping). System-facts questions answer instantly (`origin=system`).
  The GUI waits server-side and never imposes its own premature timeout.
- Ingestion is synchronous; no progress surface exists → indeterminate spinner.
- Dev-only `pyproject.toml` note: mypy reports unused `odf.*` override entries
  (pre-existing, unrelated to the GUI).
