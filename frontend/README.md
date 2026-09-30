# PAM V1 GUI — Frontend

The PAM graphical interface: a React + TypeScript + Vite SPA, styled with
Tailwind CSS v4, served by the local PAM FastAPI adapter.

PAM itself is authoritative. This frontend is a **presentation layer only** — it
calls the local API, renders the real state it receives, and never fabricates a
value. Every number on screen comes from the running PAM system.

## Stack

| Concern | Choice |
|---|---|
| UI | React 19 |
| Language | TypeScript 6 (strict) |
| Build | Vite 8 |
| Styling | Tailwind CSS v4 (design tokens in `src/index.css`) |
| Lint | Oxlint (`npm run lint`) |
| Routing | Dependency-free hash router (`src/lib/router.ts`) — no deep links, SSR or SEO needed for a local tool |
| HTTP | `fetch` through `src/lib/api.ts`; no state library |

The UI never contacts any third-party host. In development Vite proxies `/api`
to the local FastAPI process; in production FastAPI serves this built bundle
same-origin (no CORS in production).

## Architecture

```
PAM core (app/application, app/infrastructure, app/pipelines)
   │  in-process calls, cached singletons (deps.py)
   ▼
FastAPI adapter (app/interfaces/web/)
   │  HTTP/JSON on 127.0.0.1:8000
   ▼
This SPA (React → src/pages/*, src/components/*)
```

## Development

Prerequisites:

- Ollama running on `http://localhost:11434` with the configured LLM
  (`qwen3:8b` by default) and embeddings (`nomic-embed-text`).
- PAM dependencies installed: `uv sync --extra gui --extra intelligence`.

Two processes while developing:

```powershell
# Terminal 1 — FastAPI backend (serves the API; also mounts dist/ if built)
uvicorn app.interfaces.web.server:app --port 8000

# Terminal 2 — Vite dev server with HMR (proxies /api to 127.0.0.1:8000)
cd frontend
npm run dev
```

Frontend: `http://localhost:5173/` · Backend API docs: `http://127.0.0.1:8000/docs`

## Production (single process)

```powershell
uv sync --extra gui --extra intelligence   # install once
npm run build                               # tsc -b && vite build → frontend/dist
pam-gui                                     # serves the bundle + API on 127.0.0.1:8000
```

`pam-gui` is `app.interfaces.web.server:main` — it serves `frontend/dist` and the
API from one process. Port override: `PAM_GUI_PORT`.

## Pages

| Route | Page | Source |
|---|---|---|
| `/#/dashboard` | Dashboard — live metrics, health, activity | `pages/Dashboard.tsx` |
| `/#/ask` | Ask PAM — grounded QA with citations and retrieval transparency | `pages/Ask.tsx` |
| `/#/search` | Search — retrieval only, real per-leg scores | `pages/Search.tsx` |
| `/#/memories` | Memories — indexed sources + chunk detail | `pages/Memories.tsx` |
| `/#/ingest` | Add Knowledge — file upload / GitHub / YouTube | `pages/Ingest.tsx` |
| `/#/evaluation` | Evaluation — experiment artifact inventory | `pages/Intelligence.tsx` |
| `/#/retrieval` | Retrieval — pipeline inspector from config | `pages/Intelligence.tsx` |
| `/#/activity` | Activity — ingestion ledger | `pages/Intelligence.tsx` |
| `/#/diagnostics` | Diagnostics — env, models, storage | `pages/System.tsx` |
| `/#/configuration` | Configuration — resolved settings (read-only) | `pages/Intelligence.tsx` |
| `/#/storage` | Storage — vector store, artifacts, paths | `pages/System.tsx` |

## API contract

`frontend/src/lib/types.ts` mirrors the adapter's response shapes exactly; every
field PAM may fail to determine is `number | null` or `string | null` and the UI
renders those as **Not available** — there is no fake-data fallback anywhere.

## Testing & checks

```powershell
# Backend adapter tests
pytest tests/unit/test_web_routes.py

# Full backend suite (baseline: 1742 passed, 57 deselected)
pytest -m 'not integration'

# Frontend
npm run lint                                   # oxlint
npm run build                                  # typecheck (tsc -b) + production build
```

## Known limitations

- **Cold local QA is slow.** A grounded (retrieval-generated) answer on this
  machine can exceed PAM's own 120 s QA deadline while the local `qwen3:8b`
  cold-loads at 8192 context; the route then returns an honest 502 with the
  real cause and the UI shows an error card. System-facts questions ("How many
  sources are indexed?") answer instantly with `origin=system`, no citations.
- Ingestion is synchronous in PAM and reports no progress, so the Ingest page
  shows an indeterminate indicator — never a fabricated percentage.
- Activity is scoped to the durable ingestion ledger; searches, queries and
  config changes are not persisted and do not appear.
- Evaluation shows the real `eval/results` artifact inventory; headline metrics
  are reported as **Not available** because there is no runtime evaluation service.
- Reranker, HyDE and the answerability gate default to **Disabled** and are
  rendered as such — the pipeline diagram never implies otherwise.

## Security

- Server binds to `127.0.0.1` by default; CORS allows only the local Vite dev
  origin. No auth is introduced for local V1 use.
- Static SPA serving is traversal-safe (`resolve()` + `is_relative_to`
  containment, covered by `TestStaticSpa`).
- Uploads are size-capped (512 MB), filename-sanitised to the basename, and
  staged under `staging_root/pam-gui-uploads` — outside a watched inbox.
- V1 exposes no destructive operation (no `pam remove`, no cleanup actions).