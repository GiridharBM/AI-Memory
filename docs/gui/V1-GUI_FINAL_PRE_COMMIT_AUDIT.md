# PAM V1 GUI — Final Pre-Commit Audit

**Date:** 2026-09-30
**Branch:** `main` · **HEAD:** `ffcded1` · **Verified working tree:** the live repository, not reports.

---

## A. Overall Result

**READY FOR COMMIT.**

The PAM V1 GUI adapter (`app/interfaces/web/`) and SPA (`frontend/`) are complete,
non-destructive, faithful to real PAM data, and fully verified against the live
system. No V1 GUI blockers found. Remaining issues are cosmetic (mojibake
strings) or pre-existing and unrelated (ruff debt in tracked `eval/scripts/*`).

Per the brief: nothing was modified during this audit, and **nothing has been
committed or pushed** — the proposed staging list in §L requires explicit
approval.

---

## B. Repository state

| Item | State |
|---|---|
| HEAD | `ffcded1` "fix: repair EPUB ingestion (path-string parse, zip paths, dc metadata)" |
| Branch | `main` |
| Dirtied files | 7 tracked modified, 22 untracked entries |
| Commits | none since HEAD — all GUI work remains uncommitted |

---

## C. GUI files (new, belong to the commit)

| Path | Nature |
|---|---|
| `app/interfaces/web/` | 5 files: `__init__.py`, `server.py`, `deps.py`, `routes/{system,knowledge,interact}.py` |
| `tests/unit/test_web_routes.py` | 28 hermetic adapter tests |
| `frontend/` | React 19 + Vite 8 + TS 6 SPA: 7 page files, 9 components, 6 lib files, `index.css`, `vite.config.ts`, `package.json`/`package-lock.json`, `.oxlintrc.json`, tsconfigs, `index.html`, `README.md` ~ 40 files |
| `docs/gui/V1-GUI-IMPLEMENTATION-AUDIT.md` | pre-implementation audit + post-implementation status (matches reality) |
| `docs/gui/V1-GUI_FINAL_PRE_COMMIT_AUDIT.md` | this document |
| `pyproject.toml` | +9 lines: `gui` extra (`fastapi`, `uvicorn`, `python-multipart`) + `pam-gui` script |
| `uv.lock` | full re-resolution (see §H) |

---

## D. Unrelated dirty files (NOT part of this commit)

Tracked modifications:
- `eval/results/abstention_gate.json`, `eval/results/baseline_v1.json` (experiment outputs)
- `vault/index.md`, `vault/log.md`, `vault/overview.md` (vault, runtime-adjacent)
- `docs/01_Current_Implementation_Report.md` (research report work)

Untracked (prior research/paper work and Figure pipeline):
- `PAPER_PUBLICATION_AUDIT.md`, `PAPER_PUBLICATION_AUDIT_FINAL.md`
- `docs/PAM_V1_LEARNING_GUIDE.md`, `docs/RESEARCH_PAPER_EVIDENCE_AUDIT.md`
- `docs/pipeline.*`, `docs/pam_*_figure*.html`
- `research/`
- `app/application/qa_measurement_harness.py`, `app/infrastructure/banded_verifier.py`
- `tests/unit/test_{answerability_gate,banded_verifier,qa_measurement}.py`
- `vault/Notes/`

**None of these are staged in the proposed list (§L).**

---

## E. PAM core integrity

- `git status` shows **zero tracked modifications under `app/`**. The frozen
  research core (`app/core`, `app/domain`, `app/infrastructure`, `app/application`,
  `app/pipelines`, `app/cli`, `app/queue`, `app/watcher`) is untouched by this work.
- `app/interfaces/` is **additive only**: a new adapter package that imports
  existing services and projects them to JSON. No retrieval, chunking, embedding,
  BM25, RRF, QA, abstention, or config logic is duplicated or altered.
- `/sources` mirrors the proven CLI read projections
  (`_read_vector_store_sources` + `_annotate_source_ledger`, same `ManifestManager`
  construction as `pam sources`). `/system`, `/activity`, `/config` use the
  read-only ledger reader (entry.py:1216 — never creates dirs, never rewrites or
  quarantines the manifest).
- `pam-gui` console script points at `server.main()`; `--port 8000`, override via `PAM_GUI_PORT`.

---

## F. API audit (all real PAM data, none fabricated)

| Method & path | Real source | Verified live |
|---|---|---|
| `GET /api/system` | CLI projections + live Ollama probe + ledger | healthy, 31 sources / 526 chunks |
| `GET /api/health` | live Ollama probe | ok |
| `GET /api/retrieval` | resolved Settings + `OLLAMA_NUM_CTX=8192` + `RRF_K=60` | k=60 rendered |
| `GET /api/activity?limit=` | durable manifest ledger (read-only) | ok |
| `GET /api/config` | `settings.model_dump_json()` | ok |
| `GET /api/storage` | Settings paths + artifact sizes | ok |
| `GET /api/diagnostics` | env + settings + writability + probe | ok |
| `GET /api/evaluation` | `eval/results/*` inventory; metrics honest `Not available` | 18 artifacts, runtime_metrics=False |
| `GET /api/sources`, `/sources/{id}` | vector store + ledger; sha256-digest ids | ok |
| `POST /api/search` | `SearchService.search` (real RRF/cosine/BM25), timed latency | count=3, real scores, latency field |
| `POST /api/ask` | `QAWorkflow.ask` (citations/abstention/telemetry intact) | system-facts answered; honest 502 on >120s QA deadline |
| `POST /api/ingest` | `IngestionWorkflow.run` + ledger semantics (mirrors CLI) | covered by tests |
| `GET /api/ingest/capabilities` | live ingestor registry | 94 extensions, github+youtube URL inputs |

Sync routes run in Starlette's threadpool — correct fit for blocking `QAWorkflow`,
no async rewrite, no new httpx dependency.

---

## G. Security findings

- Binds `127.0.0.1` by default; CORS allows only the local Vite dev origin (`http://localhost:5173`). No auth for local V1 use (documented).
- SPA static serving is traversal-safe: `resolve()` + `is_relative_to` containment, still covered by `TestStaticSpa`.
- Uploads: size-capped 512 MB, basename-sanitised, staged under `staging_root/pam-gui-uploads` — **outside** the watched inbox (no double-ingest).
- **No destructive V1 operation is exposed**: `pam remove <source>` (entry.py:389, destructive) is excluded. No arbitrary file reads; source ids are opaque sha256 digests.
- No secrets in frontend or adapter. Frontend makes no third-party network calls (verified: vite config only proxies `/api` → 127.0.0.1:8000).
- `.gitignore` hygiene: root ignores `__pycache__/`; `frontend/.gitignore` ignores `node_modules`, `dist`, `*.local` → pyc and build artifacts cannot be staged.

---

## H. Frontend (11 screens, all rendered with real data)

Verified by fresh headless-Edge DOM dumps against the live server — all 11 routes
passed every marker check (`verify_dom.py`, 11/11 OK, 0 fails); dashboard DOM
contains the live values `31`, `526`, `318`, `189`, `17`.

| Route | Screen |
|---|---|
| `/#/dashboard` | live metrics, health, activity — `31` sources / `526` chunks |
| `/#/ask` | grounded QA, citations, retrieval transparency, honest error card |
| `/#/search` | retrieval only, all real per-leg scores + latency |
| `/#/memories` | indexed sources + chunk detail |
| `/#/ingest` | file upload / GitHub / YouTube (methods surfaced from live registry) |
| `/#/evaluation` | artifact inventory; metrics `Not available` |
| `/#/retrieval` | pipeline inspector from config; reranker/HyDE/answerability `Disabled` |
| `/#/activity` | ingestion ledger only (correctly scoped — ledger is ingest-only) |
| `/#/diagnostics` | env, models, storage, live probe |
| `/#/configuration` | resolved settings, read-only |
| `/#/storage` | vector store, artifacts, paths |

Design tokens match the approved palette exactly (bg `#0B0D10`, surface
`#12161C`, elevated `#181D24`, border `#262C35`, accent `#6D7CF5`, success
`#3FB950`, warning `#D29922`, danger `#F85149`, text `#F0F3F7`, muted `#9AA5B4`).

Dependency-free hash router; Ctrl+K focuses search. Runtime `document.title` is
set from the active section (verified: `<title>Dashboard — PAM</title>`), so the
static Vite `<title>frontend</title>` in `index.html` is overridden in use.

---

## I. Dependency audit

- `pyproject.toml`: `gui` extra = `fastapi`, `uvicorn`, `python-multipart` only.
  Base env and dev extra unchanged. `pam-gui` script added.
- `frontend/package.json`: deps = `react`, `react-dom`; dev = `@tailwindcss/vite`,
  `@types/node`, `@types/react(-dom)`, `@vitejs/plugin-react`, `oxlint`,
  `tailwindcss`, `typescript`, `vite`. Nothing else. `package-lock.json` present.
- **`uv.lock` scope finding (must be stated honestly):** the HEAD lock was already
  stale — it contained base + dev deps (46 packages) but was missing
  `faster-whisper>=1.0.0`, which is a **main dependency declared at HEAD**, and the
  entire `intelligence` extra. The working-tree lock is therefore a full
  re-resolution: ~45 new top-level packages = GUI additions (fastapi, starlette,
  uvicorn, python-multipart) **plus** the previously-unlocked faster-whisper stack
  (av, cffi, ctranslate2, onnxruntime, etc.) and intelligence extras (pymupdf,
  pdfplumber, pytesseract, nltk, huggingface-hub, tokenizers, odfpy, openpyxl,
  python-docx/pptx, xlsx/xlrd/xlwt, striprtf, etc.). The lock diff is broader
  than GUI scope but **matches declarations already present in pyproject at HEAD**
  — it is a repair of a stale lock, not a change to declared dependencies.
  Commercial-in-confidence imports (`av`, `onnxruntime`) live behind the
  `intelligence` extra, as they always did.
- No new dependency was added that a few lines of code could replace; no runtime
  deps beyond the four GUI transport packages.

---

## J. Verification results (run this session, on this checkout)

| Check | Result |
|---|---|
| `pytest -m 'not integration'` | **1742 passed, 57 deselected** (47.35 s; baseline 1714 + 28 adapter) |
| `ruff check .` | 33 errors — **all pre-existing** in tracked `eval/scripts/*.py` (backward_compat_check, ground_truth_audit, run_eval, sweep_3f, sweep_combined, sweep_thresholds, sweep_reranker); files unmodified at HEAD, not GUI |
| `ruff check app/interfaces tests/unit/test_web_routes.py` | **All checks passed** |
| `mypy app/interfaces/web` | **Success — no issues in 7 source files** (only pre-existing note: unused `odf.*` override entries) |
| `npm run lint` | 0 warnings, 0 errors (21 files, 116 rules) |
| `npm run build` (tsc -b && vite build) | clean; 33 modules; index.html 0.45 kB; CSS 23.61 kB (gzip 5.58); JS 277.22 kB (gzip 81.35 kB) |
| Fresh server boot | `http://127.0.0.1:8000/api/system` → healthy, 31 sources / 526 chunks |
| Live API smoke | search returns real RRF/cosine/BM25 scores + `latency_seconds`; capabilities = 94 extensions, github+youtube; evaluation = 18 artifacts, runtime_metrics=False; system-facts answered LLM-free |
| Headless Edge DOM | all 11 routes rendered with live data; 11/11 marker OK |
| Server hygiene | server stopped after audit → 0 python processes |

---

## K. Performance

- **Search:** ~10.8 s wall-clock live (embedding-bound; every request embeds the
  query). Real `latency_seconds` returned to the UI.
- **Ask:** system-facts questions answer in <1 s (`origin=system`, no citations,
  LLM-free). Grounded QA on this machine can exceed PAM's own 120 s
  `qa.timeout_seconds` while `qwen3:8b` cold-loads at 8192 context → the route
  returns the honest 502 with the real cause (`test_qa_failure_becomes_502_not_an_answer`).
  The GUI waits server-side and never imposes its own premature timeout.
- **Ingestion:** synchronous, indeterminate progress indicator — no fabricated percentage.

---

## L. Proposed staging list (requires approval; nothing committed)

```
git add app/interfaces/
git add frontend/
git add docs/gui/
git add tests/unit/test_web_routes.py
git add pyproject.toml uv.lock
```

Everything in §D is explicitly excluded. Note: `frontend/src/assets/hero.png` and
`frontend/src/assets/vite.svg` are Vite scaffold leftovers inside `frontend/` and
would be committed with `git add frontend/` unless removed or excluded first
(see §M.4).

---

## M. Remaining issues (none block the commit)

1. **Mojibake strings (cosmetic, user-visible):** `server.py:52`
   `title="PAM â€" Personal AI Memory"` and the SPA fallback message
   "The GUI bundle is not built yet â€"" contain literal U+00E2 U+20AC + quote
   bytes instead of an em dash (bytes verified). Same corruption in the
   `test_web_routes.py` module docstring and one sample answer string. Not fixed
   during the audit (per brief, do not modify) — a 4-line fix if you want it
   before commit.
2. **Stale-lock scope:** `uv.lock` re-resolution includes pre-existing
   faster-whisper/intelligence packages beyond GUI scope (see §I) — expected and
   correct, but the diff is larger than the GUI alone.
3. **Pre-existing ruff debt:** 33 errors in tracked `eval/scripts/*.py` — not
   touched, not GUI, present at HEAD.
4. **Vite scaffold leftovers:** `frontend/index.html` static `<title>frontend</title>`
   (overridden at runtime), unreferenced `frontend/src/assets/{hero.png,vite.svg}`
   and `frontend/public/icons.svg`. Decide: delete the two asset files, or accept
   them in the commit.
5. **No web UI pixel pass:** model cannot view images — final pixel review of
   `pam_shots\*.png` is left to you.

---

## N. Declaration

This audit was performed on the actual working tree (not prior reports). All
values above were re-verified this session: pytest, ruff, mypy, build, lint,
fresh server boot, live API smoke, and headless-Edge DOM renders of all 11 routes.
The GUI reports real PAM state, fabricates nothing, exposes no destructive
operation, and leaves the frozen research core untouched.