# Phase 6 — PAM V1 Application-Layer Discovery

**Status:** ANALYSIS / DISCOVERY ONLY — inventory and design of the application layer on top of the frozen retrieval V1. No production code, config, corpus, dataset, retrieval artifact, or embedding modified; no commits; no pushes. STOP point: this report is the deliverable; Phase 6A implementation awaits explicit approval.
**Date:** 2026-08-28
**Head input gates:** Phases 1–5G (architecture, retrieval, real-corpus evaluation, freeze), frozen 5D baseline, reports 01–33.

---

## 1. Objective

Define what the PAM V1 *application layer* must look like on top of the frozen retrieval V1: inventory the actual code that exists today, inventory the ten user flows, define the V1 user journey, identify the answering layer, design the source/citation, abstention, and ingestion experiences, choose exactly ONE interface, analyze privacy/observability, draw the V1 feature boundary, set V1 application acceptance criteria, and propose the implementation roadmap (6A–6H).

**Constraint honored (frozen retrieval):** nothing below modifies, tunes, or re-opens retrieval. Cosine threshold, embeddings, chunking, BM25/RRF, reranker/HyDE/answerability enablement, `VectorStore`/`SearchService` behavior, `eval/dataset.json`, and all frozen artifacts are **out of scope** and treated as given. Future retrieval work is V1.1+.

**Evidence basis:** code inspection of `app/`, `config/default.yaml`, `pyproject.toml`, `README.md` (this phase); frozen baseline `phase_5d_frozen_baseline.json`; reports 27–33.

## 2. Frozen retrieval state (given, verbatim — NOT re-opened)

| Item | Value |
|---|---|
| Dataset | `eval/dataset.json` v3.0 — 199 queries (157 pos / 42 neg, q001–q202) |
| Corpus | 24 sources / 195 chunks, nomic-embed-text 768-dim |
| Config | top_k=5, min_cosine=0.45, BM25 k1=1.5/b=0.75, RRF k=60; reranker/hyde/answerability all `false` |
| Baseline | Hit@1 0.841, Hit@5 0.924, MRR 0.877, FPR 0.857, FNR 0.000, abstention 0.030, p95 47.1 ms |
| Guardrails | FNR ≤ 0.033; Hit@5 ≥ 0.93; MRR ≥ 0.88; FPR materially < 0.811 (target ≤ 0.5); p95 < 500 ms — NOT relaxed; the green-flag subset is the V1.1 reopening gate |
| Decision artifact | report 33 — Decision C: freeze retrieval V1, move to the application layer |

**Application-relevant fact from 5E/5F:** 31/36 FPs are *content-sufficiency* misses — retrieval is on-topic, the fact is absent from memory. The retrieval layer cannot distinguish these; the **application layer** must (a) present evidence transparently so the user can judge, and (b) abstain honestly when there is genuinely nothing. 12/36 hard-core FPs (cos ≥ 0.62) are score-indistinguishable from TPs — no application-side score rule can catch them; honest evidence presentation is the only honest V1 tool.

## 3. Current architecture (inspected this phase)

```
pam (typer CLI, entry: app.cli.entry:main)
├── ingest group          pdf | markdown | txt | github <url> | youtube <url>
├── status / doctor / config / config-show / watch
├── search <q> [--top-k --source-type --min-score --filter]
└── ask <q>   [--top-k --min-score --filter]
        │
        ├── pipelines.IngestionWorkflow ─ DocumentIngestionService (22 ingestors, auto-detect)
        │     ├── DocumentClassifier + ProcessorRouter (per-kind model routing)
        │     ├── RoutedDocumentProcessor (OCR / vision / handwriting / audio transcriber)
        │     ├── DocumentAIProcessor (Ollama JSON, validation_retries=2)
        │     ├── ObsidianMarkdownGenerator → VaultWriter → vault/Notes/*.md
        │     └── Knowledge engine: SemanticChunker → EmbeddingService → VectorStore
        │           (data/manifests/vector_store.json) + KnowledgeGraph (knowledge_graph.json)
        │
        ├── SearchService (hybrid dense+BM25+RRF, k=60; embed=EmbeddingService, nomic-embed-text)
        │     └── VectorStore (same persisted file ingest writes)
        │
        └── QAWorkflow
              ├── SearchService.search (top_k=5)
              ├── AbstentionGate (top-1 cosine ≥ 0.25; reranker inactive in V1)
              ├── build_context (8 chunks / 12,000 chars)
              └── OllamaClient.generate_text (system=QA_SYSTEM_PROMPT, model=ollama.model)
```

**Observability/watch path:** `watch` → `WatchService` (watchdog observer on `data/inbox`, recursive, 1 s) → `QueueManager` (FIFO, dedup, max 1000) → `QueueWorker` (1 thread) → SHA-256 → manifest dedup → `IngestionWorkflow` → move to `data/processed/` → record in manifest. `QueueStateStore` persists pending+in-flight items for crash recovery.

**Key numbers (inspected):** Ollama `localhost:11434`, model `qwen3:8b` (analysis + QA), programming `qwen2.5-coder:7b`, vision/OCR `qwen2.5vl:latest`, audio `faster-whisper`, embeddings `nomic-embed-text`; ollama timeout **3600 s** (config), retries 3, backoff 1.0; logs INFO + file `application.log` 10 MB × 5; manifest `data/manifests/processed_files.json`; queue state `data/manifests/queue_state.json`; max file 50 MB; watcher interval 1 s.

## 4. Current user flows (inventory of the ten flows, Step 2)

| # | Flow | Command / interface | Inputs | Outputs | Dependencies | Failure behavior | Observed limits |
|---|---|---|---|---|---|---|---|
| 1 | Ingest a file | `pam ingest pdf\|markdown\|txt <path>` | local path | "Ingestion Complete" table (source type, note title, note path, created/updated, AI attempts) | Ollama + vision/OCR + model routing | red panel, exit 1 | **No manifest dedup on the direct path** — re-ingesting the same file re-processes; only VaultWriter created/updated tells you |
| 2 | Watch inbox + auto-process | `pam watch` (Ctrl+C drains) | files dropped in `data/inbox` | rich progress bar; file moved to `data/processed/`; manifest entry; queue persisted | watchdog, queue, Ollama | unsupported → `data/failed/`; unexpected → failed; crash → queue restored on restart | **workers=1**: one slow doc (video/audio/OCR) blocks the inbox |
| 3 | Search | `pam search <q> [--top-k --min-score --source-type --filter]` | query text | ranked table: Score / Source / Type / 200-char snippet; "No results found." when empty | Ollama embed + BM25 + RRF | red panel, exit 1 | filter is exact-match only ($in/range debit 4.5) |
| 4 | Ask / RAG | `pam ask <q> [--top-k --min-score --filter]` | question text | answer panel + Sources table (Score / Source / 200-char snippet) | Ollama embed + generate; abstention gate | QAError → red panel, exit 1 | sources table omits **section**, char-offset, and metadata; answer has no per-claim source tags user can verify against |
| 5 | Retrieve sources | `pam ask` / `pam search` result tables | — | source name = document path or URL | — | — | no jump-to-location; no page/section display; no link to the vault note |
| 6 | Abstain | gate abstains → fixed message; LLM insufficient → model's own "not enough" prose | — | `"I don't have enough relevant information in the knowledge base to answer this question."` with `sources=[]` → CLI prints "No sources retrieved." | abstention gate (cosine ≥ 0.25) | — | **Hides the evidence that triggered abstention** — worst UX for the FPR-0.857 world: user can't see the on-topic-but-fact-absent chunks |
| 7 | Status / health | `pam status`, `pam doctor` | — | status table; doctor check list (deps, dirs, Ollama, model, OCR, tesseract) | — | doctor exit 1 on failures | status shows hardcoded "0" rows for processed/skipped/failed (runtime counters reset on restart) — **misleading** |
| 8 | Errors / diagnostics | red panels + exit codes; `data/logs/application.log` | — | structured logs enrich with source, question, sha, latency | — | per-command red panel | errors are clear but not machine-readable; no correlation id linking a queue item → note → chunks |
| 9 | Re-ingest / duplicate | redrop file in inbox (hash dedup → skip); edit file → re-process (updated note) | — | skip logged as duplicate; re-process → `created=False/updated=True` | manifest SHA-256 | — | **direct `pam ingest` bypasses dedup**; re-processing an updated doc **appends new chunks but never removes the stale chunks** of the old version (VectorStore has no delete-by-source) |
| 10 | View stored info | `pam status` (note count, manifest entries) + open `vault/Notes/` in Obsidian | — | manifest = durable processed-file ledger (hash, original path/name, processed_at, extension, generated note) | — | manifest corruption quarantined + rebuilt | manifest records **successes only** — failures, duplicates, and queue history are not durable |

## 5. Current capabilities (labeled)

| Capability | Status | Evidence |
|---|---|---|
| CLI command surface (ingest/status/doctor/config/watch/search/ask) | **VALIDATED / EXISTS** | `app/cli/entry.py` — full typer surface, rich tables/panels, exit codes |
| Direct ingestion (pdf/md/txt) + network (github/youtube) | **VALIDATED / EXISTS** | 22-ingestor `DocumentIngestionService`, auto-detect by path/URL |
| Watcher + queue automation with crash recovery | **VALIDATED / EXISTS** | `WatchService`, `QueueManager` (dedup, FIFO), `QueueWorker`, `QueueStateStore` |
| Deduplication (SHA-256 manifest) | **VALIDATED / EXISTS** | worker path + manifest |
| RAG answer generation | **VALIDATED / EXISTS** | `QAWorkflow.ask`, grounded `QA_SYSTEM_PROMPT`, bounded context (8/12 000) |
| Abstention gate (no/low-evidence) | **VALIDATED / EXISTS** | `AbstentionGate` (cosine ≥ 0.25) + fixed message |
| Source/citation rendering | **PARTIAL** | prompt instructs `[SOURCE N]`; CLI shows score+source+snippet only — no section, no offset, no note link |
| Root-cause diagnostics | **PARTIAL** | `doctor` covers config/deps/dirs/Ollama/OCR; post-watcher failure triage requires grep in logs + `data/failed/` |
| Durable runtime metrics | **PARTIAL** | structured logs yes; persisted counters no (`RuntimeStats` in-memory only; status hardcodes 0) |
| Durable failure/duplicate ledger | **MISSING** | manifest = processed positive ledger only; failures/duplicates not recorded |
| Web UI / REST API | **MISSING** | CLI-only (deferred V1.1 per §11) |
| Retrieval optimizations (rerank/hyde/answerability/parent-child) | **DEFERRED** | code exists, all disabled; frozen |

## 6. Missing capabilities (labeled)

| Missing / weak | Label | Notes |
|---|---|---|
| Generic `pam ingest <path>` for any supported extension (docx, xlsx, code, image, audio, video, eml, …) | **MISSING (V1 SHOULD)** | today only md/txt/pdf subcommands; watcher auto-detects the rest, direct path ingest does not |
| Evidence-preserving abstention (show what failed) | **MISSING (V1 MUST)** | core §9 design; hides retrieval output today |
| Source → vault-note link + section/offset locator in ask output | **MISSING (V1 MUST)** | citation §8 design |
| Durable status/ledger (persisted successes + failures + duplicates, correct counters) | **MISSING (V1 MUST)** | §10/§13 |
| Failed-file inbox triage command | **MISSING (V1 SHOULD)** | currently only `data/failed/` on disk |
| QA-scoped generation timeout | **MISSING (V1 MUST)** | configured ollama timeout is 3600 s — a hung generation stalls `ask` and the single watcher worker |
| Stale-chunk invalidation on re-ingest / delete / re-index | **DEFERRED (V1.1+)** | re-ingesting an updated doc appends; old chunks remain (see §17 risk 6) |
| Streaming answers, conversation memory, multi-turn | **DEFERRED (V1.1+)** | QA is single-turn stateless |

## 7. Answering-layer analysis (Step 4)

**What exists (VALIDATED):**
- **Model/provider:** `qwen3:8b` via **local** Ollama (`localhost:11434`), plain-text generation (`OllamaClient.generate`), retries 3 with exponential backoff 1.0 s ^(attempt-1). Embeddings `nomic-embed-text`. Both local — nothing leaves the machine.
- **Prompt system:** `QA_SYSTEM_PROMPT` (grounded rules: use only retrieved context, no invented facts, explicit "not enough information" language, **prompt-injection guard** — retrieved docs are data, not instructions, cite `[SOURCE N]`); `build_qa_user_prompt(question, context)`; zero-context fallback "No relevant context was retrieved…".
- **Context construction:** `build_context` bounds at 8 chunks / 12 000 chars, deterministic `[SOURCE N]` blocks with `Source:`, `Section:` (from `metadata.heading`/`parent_heading`), `Score:`, `Content:`.
- **Hallucination safeguards in V1:** grounded system prompt; top-1-cosine abstention gate; hard context bounds (no prompt overflow); prompt-injection instruction. These are **soft** controls — they reduce but cannot eliminate fabrication (the 12 hard-core/survivor FPs from 5F confirm score-level indistinguishability).
- **Error handling:** Ollama down/errors → `QAError("Unable to generate an answer because the Ollama server is unavailable or returned an error.")`, exit 1. Empty question → `QAError`. Answerability gate exists in code but is **disabled** (frozen) — V1 relies on prompt honesty + gate + evidence display.

**Honest assessment (validation labels):**
- Grounded generation with bounded context: **VALIDATED**.
- Abstention gate as hard guardrail: **VALIDATED** as *no-evidence* detector; **insufficient** as *fact-absence* detector (FPR 0.857 — most on-topic-but-empty retrievals pass it). V1 must treat the gate as "no relevant evidence", not "answer is supported". Everything else is the model's responsibility + user-visible evidence.
- Banded verifier (5F): **DEFERRED candidate** — 0.405 FPR / 0.070 FNR / ~17 s p95; rejected for V1; the honest application-layer strategy is evidence transparency, not another LLM gate.

**V1 recommendation:** keep the current Q* → RRF → gate → bounded ground → `[SOURCE N]` generation pipeline unchanged. Application-layer work targets the *presentation and guard* of that pipeline: QA-scoped timeout (see §10/§17), sources that are verifiable, and abstention that shows its reasoning instead of hiding it.

## 8. Citation / source experience design (Step 5)

**What metadata actually exists on a retrieved hit (inspected — do not invent more):** `SearchHit` carries `text`, `source` (document path or URL), `score` (RRF), `entry_id`, `cosine_score`, `bm25_score`, `rerank_score` (0 in V1), `parent_section` (None in V1), `source_type`, `chunk_index`, `start_char`, `end_char`, and `metadata` (`heading`, `parent_heading`, heading-path keys). No page numbers exist at chunk level — char offsets do. GitHub/Youtube documents carry repo/video metadata in document metadata, not per chunk.

**V1 citation contract (PROPOSED — all fields already exist):**
1. In-answer citations stay `[SOURCE N]` matching the `[SOURCE N]` context order (prompt already enforces this). 
2. Sources table for `ask` becomes: `[N]` | Document (basename of path / full GitHub `owner/repo` / `YouTube Transcript - {video_id}`) | Section (from `metadata.heading` else `parent_heading` else `—`) | Score | 200-char snippet. 
3. Add a `--location` affordance (V1 SHOULD): print `start_char–end_char` so a future "open at offset" can jump; do **not** fabricate page numbers.
4. On abstention, the same sources table renders with a "retrieved but insufficient" label (§9).
5. Traceability: every source's document has a vault note (manifest `generated_note`) — print `Note: …` once a mapping is trivially available; full note-linking is V1.1.

**Design decisions:** no new metadata fields, no retrieval change. This is purely presentational over frozen per-hit data.

## 9. Abstention UX (Step 6)

**Context:** FPR 0.857 (measured, frozen). Two distinct, often-confused conditions:
- **A. No relevant evidence** — gate abstains (no results / both leg scores 0 / top-1 cosine < 0.25). Rare (abstention 0.030).
- **B. On-topic but fact absent** (the 31/36 content-sufficiency FPs) — retrieval passes, no answer exists. The model, following QA_SYSTEM_PROMPT, should say it doesn't know. Today this is a soft, opaque prose answer.

**PROPOSED V1 abstention UX (no answerability implementation):**

1. **Same honest, plain message for A and B**, phrased to educate: *"I couldn't find enough relevant information in your memory to answer this question."*
2. **Always show the evidence.** For B, render the retrieved sources with scores plus this label: *"I found these documents on the topic but not the specific information you asked for."* This is the single most important fix — it makes the retrieval-vs-knowledge distinction visible to the user and exposes what to add.
3. **Distinguish from failure:** generation/connection errors get a *separate* message ("Ollama server unavailable…") — an error is not an abstention.
4. **Next action:** append *"If this information exists, add it to your memory (drop the file in `data/inbox` or run `pam ingest …`)."* — ties the abstention loop back to the ingestion UX.
5. **No score shenanigans:** no retuned thresholds, no second LLM gate — the 12 hard-core FPs prove that trained, score-level separation is impossible and an LLM gate was measured (5F) to add 17 s and still fail FNR. V1 ships honesty + transparency.

**Labels:** honest abstention with evidence = **MUST (PROPOSED)**; error/abstention separation = **MUST (PROPOSED)**; anything answerability-like = **DEFERRED (V1.1+, on the 5F mechanism, scoped/fail-open)**.

## 10. Ingestion UX (Step 7)

**Current (VALIDATED):** inbox watch → stable-file wait → queue → SHA-256 dedup → routed processor → AI analysis → note write → move to `data/processed/`; failures to `data/failed/`; queue persisted for restart recovery; email attachments re-ingested with cleanup. Duplicates skipped with a log + counter. Every watcher outcome is either processed, dedup-skipped, recorded failed+relocated, or still queued — **no silent loss** on the watcher path.

**Gaps to close in V1 (PROPOSED):**
1. **One generic path command** — `pam ingest <any-supported-path>` (extension auto-detect through `DocumentIngestionService`), keeping the typed subcommands as aliases. Closes the direct-path coverage gap and routes direct ingest **through the manifest** so duplicates are skipped there too.
2. **Durable processing ledger** — persist per-file outcomes: `success | duplicate | failed | queued`, plus note path, SHA-256, source type, timestamp, error reason. Substrate for `status` (no more hardcoded 0s), failed-inbox triage, and re-ingestion.
3. **Clear failure feedback** — `pam status` lists pending, failed (with reason), last-N processed; failed files remain in `data/failed/` and are never deleted.
4. **Re-ingestion semantics** — keep hash-based skip; edited file → re-process → note updated (`created=False`); V1 prints "already in memory" for duplicates instead of silently re-running.
5. **Status reporting** — success table already good (note path, created/updated, attempts); extend with "duplicate → skipped".

**Labels:** generic path + ledger + failed triage = **MUST (PROPOSED)**; delete/re-index of stale chunks = **DEFERRED (V1.1+, see §6/§17)**.

## 11. Interface comparison and decision (Step 8)

| Option | Scope today | Pros | Cons | Verdict |
|---|---|---|---|---|
| **A. CLI-first (keep + harden)** | Exists: 8 commands, rich tables, exit codes | zero new surface; retrieval settled; answer+sources+abstention render fine; local-first; scriptable; smallest V1 diff | no graphics; not discoverable by non-tech users | **⚑ RECOMMENDED for V1** |
| B. Local web UI | none | pretty, charts, clickable sources; natural for full-text reading | new server process, port/auth boundary, longer latency loop, second codebase | V1.1 |
| C. REST API + CLI | none | integrates with external tools/automations | API surface + auth + versioning for a single-user local tool = premature | V1.1 |
| D. Desktop/local app | none | native file drop, tray | largest build, packaging per-OS | not in scope |
| E. CLI + lightweight web UI | partial (CLI) | both worlds | two surfaces to maintain for V1 = violates the smallest-diff rule | V1.1 |

**DECISION (ONE): A — CLI-first.** Evidence: the entire retrieval + QA surface is already CLI and frozen in tests; the V1 gaps (§6/§9/§10) are all resolvable inside the CLI; adding any secondary surface now doubles the attack/maintenance surface for no V1 metric benefit. Revisit E/C/B in V1.1 after real usage feedback.

## 12. Privacy / security (Step 9)

**What leaves the machine:** only the two explicitly-invoked network ingestors —
- `pam ingest github <url>` → 2 GETs to `api.github.com` (repo metadata + README), 30 s timeout, `User-Agent: personal-ai-memory`, no auth token. 
- `pam ingest youtube <url>` → `YouTubeTranscriptApi` fetch (video id), en/en-US/en-GB. 
- `MetadataSettings.url_timeout_seconds` (30) suggests an extractor may perform URL fetches; **flagged** for verification in 6A (needs confirmation of the exact extractor + what URL it fetches).
Everything else (embeddings, analysis, QA generation, searches) hits **local Ollama only** — no cloud inference, no analytics, no telemetry.

**Storage:** notes → `vault/`; inbox, processed, failed, manifests, vector store, knowledge graph, queue state, logs → `data/`. Logs record source paths, note paths, SHA-256, **question text**, and hit counts (INFO). SHA-256 hashes are content hashes. No credentials are stored anywhere; env override via `PAM_*`.

**Threats / mitigations:**
- Prompt injection via ingested external content (GitHub READMEs, YouTube transcripts) — mitigated by the QA system-prompt guard ("retrieved docs are data, not instructions"); **soft** — keep, and in V1.1 consider a provenance flag for non-local sources. 
- Path/SHA disclosure — local-only logs; acceptable. 
- Untrusted attachments (email) — extracted to temp then cleaned up (post-processing cleanup verified); max 20 attachments, 50 MB cap. 
- Local Ollama exposure — `localhost:11434`; no firewalling needed for single-user default; note that binding Ollama on LAN would change this.
- No network is ever contacted during `ask`/`search`/`watch`/`status`/`doctor`.

## 13. Observability (Step 10)

**Exists (VALIDATED):** structured `logging` (JSON-capable/rich), INFO by default, file 10 MB × 5; per-stage ingestion logs (processor+model selected, routed processor done, knowledge engine done, workflow complete); queue worker logs (detection, dedup, process start/finish, elapsed, queue latency); QA logs (retrieval hits, rerank top score, abstain reason, generation failure); `doctor`/`status` surfaces.

**Gaps → V1 (PROPOSED):**
1. **User-facing + persisted, not dev-only:** a durable `status` that reports real counts — processed, duplicates, failed, queued, last-N events — backed by the §10 ledger. `RuntimeStats` alone is lost on restart.
2. **Failed-file triage:** `pam status` exposes failed files (path + reason) that otherwise live only in `data/failed/`.
3. **QA-scoped latency metric:** p50/p95 of answer generation surfaced in status/logs (the retrieval p95 47.1 ms is frozen; generation latency is application-layer and currently unmeasured end-to-end).
4. **Separate user vs debug tiers:** keep rich CLI panels as the user face; structured log file as the debug sink (already separate; formalize the split).
5. **Lightweight event ledger schema:** `{ts, kind: processed|duplicate|failed|queued, source, source_type, sha256, note_path, error?, latency_ms?, queue_latency_ms?}` — one JSONL file; enough for diagnostics and the V1.1 web UI.

## 14. V1 feature boundary (Step 11)

**MUST HAVE (V1):**
1. `pam ask` grounded answer + verifiable sources (document, section, score, snippet, `[SOURCE N]` contract) — §8.
2. Honest abstention that shows its evidence + separates abstention from error — §9.
3. `pam ingest` for any supported file + watcher paths, with clear success/duplicate/failure feedback; no silent loss — §10.
4. Durable status (real counters, failed triage) replacing hardcoded 0s — §13.
5. Clear, actionable errors for Ollama absent, model missing, unsupported source, bad config, empty question — with consistent exit codes.
6. QA generation scoped to a sane timeout (guard against the 3600 s config value) — §17.
7. Local-only guarantee preserved and documented; github/youtube remain explicit opt-in commands.

**SHOULD HAVE (V1 if cheap):**
1. Generic `pam ingest <path>` with dedup wired in.
2. `--location` char-offset output; "Note:" line linking each source to its vault note.

**V1.1+ (explicitly deferred):** web UI / REST (decision A), reranker/hyde/answerability enablement, parent-child retrieval (`parent_section`), stale-chunk invalidation / delete / re-index, streaming, conversation/multi-turn, page-level citations, knowledge-graph-grounded answers, provenance flags for non-local sources.

## 15. V1 application acceptance criteria (Step 13 — ADDED on top of retrieval)

Retrieval acceptance is **unchanged** (5D freeze: Hit@1 0.841, Hit@5 0.924, MRR 0.877, FPR 0.857, FNR 0.000, p95 47.1 ms — not redefined, not re-argued). Application acceptance (new):

1. **A1 – Grounded answer contract:** every generated answer produced by `pam ask` from a non-abstained retrieval renders ≥ 1 source row and follows the `[SOURCE N]` citation instruction; no invented metadata (no page numbers) is displayed.
2. **A2 – Abstention honesty:** when retrieval finds nothing OR the model reports insufficient info, output is the standard "couldn't find enough relevant information" message **with** the retrieved evidence labeled "on-topic but insufficient"; a separate, explicit error is shown for generation/connection failures.
3. **A3 – No silent loss:** each inbox file reaches exactly one durable outcome — processed (note + manifest), duplicate (skipped + recorded), failed (relocated to `data/failed/` + recorded with reason), or queued (recoverable across restart). Verified by a scripted watch/crash-recovery smoke test.
4. **A4 – Truthful status:** `pam status` counts match the persisted ledger (processed/duplicates/failed/pending) — not runtime-reset 0s.
5. **A5 – Failure clarity:** Ollama down, model missing, unsupported source, bad config, and empty questions each produce a distinct, actionable message and non-zero exit code.
6. **A6 – Privacy invariant:** e2e watch→ask exercise makes zero network calls besides the two opt-in ingest commands.
7. **A7 – QA latency guard:** a generated answer completes within the new QA-scoped timeout without hanging `ask` or the worker; timeout/error is surfaced, not swallowed.
8. **A8 – Regression:** full unit suite green (1377 passing, coverage ≥ 89.7%), ruff/mypy clean, and the frozen retrieval eval (199 queries) reproduces the 5D baseline exactly.

## 16. Proposed implementation roadmap (Step 14)

| Phase | Scope (application layer only; retrieval untouched) | Exit objective |
|---|---|---|
| **6A** | Application architecture + interface (decision A): durable processing ledger, status/doctor rewrite on the ledger, failed triage, generic `pam ingest <path>` with dedup, QA-scoped timeout guard, confirm exact URL-fetching metadata extractor (§12 flag) | A3 A4 A5 A7 substrate in place; A6 verified |
| **6B** | Answer generation polish: QA output contract (sources with document/section/score/snippet), `[SOURCE N]` rendered, note-link line, `--location` offsets | A1 |
| **6C** | Citation/source completion + abstraction: evidence-preserving abstention rendering, error-vs-abstention separation, retrieval-but-insufficient labeling | A2 |
| **6D** | CLI/API/UI finalization per decision A: consistent panels, exit codes, help text, scriptability; (web UI stays V1.1) | A5 |
| **6E** | Error handling hardening: per-condition message map, watch-path failure ergonomics | A5 A3 |
| **6F** | Integration testing: scripted e2e flows (ingest→ask→citations→abstention→duplicate→crash recovery), watcher tests, dedup tests | A1–A5 test coverage |
| **6G** | E2E validation: run the full journey, re-run unit suite + frozen retrieval eval, verify A1–A8 | all acceptance green |
| **6H** | V1 application freeze: same freeze protocol as 5G — decision artifact, measured numbers, V1.1 backlog (web UI, rerank/answers/verification, parent-child, delete/re-index) | frozen V1 application layer; report written |

Ordering rationale: 6A first because the ledger/status/interface substrate unblocks B–E; B–E then parallel-friendly; F/H validate and close.

## 17. Risks

| # | Risk | Evidence / driver | V1 mitigation |
|---|---|---|---|
| 1 | Misleading answers on fact-absent queries (FPR 0.857; 12 hard-core FPs score-indistinguishable) | 5E §6, 5F survivors | Evidence transparency (§8/§9); honest abstention; no score-derived false confidence |
| 2 | 3600 s Ollama timeout → hung `ask`/worker (retries ×3 ⇒ worst-case multi-hour) | config `timeout_seconds: 3600` | QA-scoped timeout (6A); surfaced as error A7 |
| 3 | Re-ingest of a changed doc appends new chunks; **stale chunks stay** and pollute retrieval | `VectorStore.add_batch` append-only, no delete-by-source | V1: show note "updated" + last-indexed-at in status; full invalidation → V1.1 (documented in report 33 + §14) |
| 4 | Single worker (le=1) blocks inbox behind slow media/OCR | `QueueSettings.workers` le=1 | surface queue depth + per-item latency; document; parallel workers → V1.1 |
| 5 | Direct-paths (ingest/search/ask) bypass manifest dedup ⇒ duplicate notes/chunks | inspection §4 row 9 | route direct ingest through manifest (6A) |
| 6 | Soft prompt-injection guard for external content (GitHub/YouTube) | QA system prompt only | keep guard; provenance flags + hard content boundary → V1.1 |
| 7 | Status "0" rows mislead users into thinking watcher is idle-broken | `RuntimeStats` in-memory; hardcoded rows | persisted ledger + truthful counters (A4) |
| 8 | Unresolved URL-fetching metadata extractor could leak a document URL | `MetadataSettings.url_timeout_seconds` | confirm exact extractor in 6A; if it fetches document URLs, surface it in `doctor` and privacy note (A6) |

## 18. Recommended next implementation phase

**ONE recommended phase: Phase 6A — Application Architecture & Interface (CLI-first) Substrate.**

Rationale: it is the prerequisite for every other roadmap item. It converts the three highest-value V1 MUSTs into substrate — the durable processing ledger (truthful `status`, failed triage, dedup everywhere), the QA generation guard (timeout, latency measurement), and the interface decision (A: CLI-first, no new surface) — while confirming the last privacy open question (§12 flag). It is also the narrowest phase that eliminates the two user-hostile behaviors measured this phase: misleading status (A4) and silent/noisy re-ingestion (A3/A5). 6B–6H then layer on presentation and validation without re-architecture.

---

*End of Phase 6 discovery. STOP: awaiting explicit approval before Phase 6A implementation.*