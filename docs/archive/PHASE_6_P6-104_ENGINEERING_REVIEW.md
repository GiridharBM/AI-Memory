# P6-104 Engineering Review — Security, Configuration and Deployment Readiness

**Task:** P6-104 — Security, Configuration and Deployment Readiness
**Phase:** Phase 6 (production-hardening audit; no new features)
**Date:** 2026-08-09
**Verdict:** **APPROVED**

---

## 1. Deliverable

A production-readiness security and configuration audit of the live repository and its existing deployment conventions. No deployment platform was invented and no infrastructure was added — the audit evaluates the application as it actually runs (local-first, Ollama-backed CLI + background watcher). The 14 audit areas were checked against the live code, one repo-level data-exposure issue was remediated, one deployment-documentation inconsistency was fixed, and the production/development configuration separation is now locked by a test. No secrets exist in the system (the architecture requires none), and no production behavior was changed without evidence.

## 2. Audit Findings

### 2.1 Remediated

**R1 — Personal runtime data was tracked in git (security).** `data/processed/` (personal Markdown notes, WhatsApp images, JPEG/PNG), `data/failed/` (personal study PDFs and an MP3), and `data/manifests/processed_files.json` + `queue_state.json` (runtime state carrying original file paths and hashes) — 34 files — were committed. This contradicted the existing `.gitignore` intent: `data/cache/*`, `data/logs/*`, `data/staging/*` are ignored with `.gitkeep` whitelists, but `data/inbox/*`, `data/processed/*`, `data/failed/*`, `data/manifests/*` were not.

**Fix:** extended `.gitignore` to cover all five runtime dirs (keeping the `.gitkeep` whitelist) and ran `git rm --cached` so the 34 files are untracked **while remaining on disk** — no data deleted, no behavior change. The previously-untracked `data/manifests/knowledge_graph.json` and `vector_store.json` are now ignored too. Verified: only the five `.gitkeep` files remain tracked under `data/`.

**R2 — `requirements.txt` was missing required dependencies (deployment).** The README's documented install path (`pip install -r requirements.txt`) omitted `PyMuPDF` and `openpyxl`, both declared as required in `pyproject.toml`. `PyMuPDF` is an **eager import** in the OCR PDF path (`app/infrastructure/document_intelligence/ocr/pdf.py:37` — "legacy contract"), so the documented install produced a deployment that fails on scanned-PDF OCR with a raw `ImportError`; `openpyxl` is a lazy import but `.xlsx` ingestion silently loses table/spreadsheet extraction.

**Fix:** added `PyMuPDF>=1.24.0` and `openpyxl>=3.1.0` to `requirements.txt`, matching `pyproject.toml` required deps exactly.

**R3 — Production config separation was untested.** `config/production.yaml` (INFO, JSON logging, no colors) merged over `default.yaml`, but no test locked it.

**Fix:** added `test_production_environment_separates_logging_defaults` asserting `environment=production`, `logging.format="json"`, `logging.use_colors=False`, `logging.level="INFO"`.

### 2.2 Audit results by area

| # | Area | Result |
|---|------|--------|
| 1 | **Secret handling** | No secrets exist anywhere: the system talks only to a local Ollama host (`http://localhost:11434`), so no API keys/credentials are required. Repo-wide grep + full git-history scan: zero real secrets. Test fixtures contain only obviously-fake strings (`sk-test-12345`, `SECRET_KEY=super-secret`) | PASS |
| 2 | **Environment variables** | `PAM_` prefix + `__` nested delimiter; `PAM_ENVIRONMENT` selects environment; env overrides merge after YAML and are typed via `yaml.safe_load` + pydantic. Documented in README (config precedence: default.yaml → `<env>.yaml` → `PAM_*`) | PASS |
| 3 | **Configuration defaults** | Every setting has a safe default; pydantic `extra="forbid"` rejects typos; numeric bounds (`ge/le/gt`) on timeouts, sizes, retries; `test_invalid_config_fails_fast` locks fail-fast on bad config | PASS |
| 4 | **Unsafe hardcoded credentials** | None found in code, configs, or history | PASS |
| 5 | **Sensitive information in logs** | No keys/tokens logged. Whisper logs only path/language/duration; `tracebacks_show_locals`/`show_path` gated to debug mode; `httpx`/`httpcore` set to WARNING to suppress verbose HTTP transport; `JsonFormatter` uses a reserved-attr allowlist + `default=str` | PASS |
| 6 | **File/path handling** | Attachment filenames sanitized (`_safe_attachment_name`, path-traversal covered by `test_path_traversal_filename_sanitized`); vault writes atomic (`tmp` + `os.replace`); manifest/queue/vector-store same-dir temp + atomic replace | PASS |
| 7 | **Input validation** | Config fail-fast; extension allowlists (`PROCESSABLE_EXTENSIONS`, watcher `supported_extensions`); `max_file_size_mb`; CLI args validated (`exists=True`, `--top-k` min=1); empty search query rejected | PASS |
| 8 | **Dependency configuration** | `pip check` clean; `requirements.txt` now consistent with `pyproject.toml` (R2). Optional deps correctly scoped to `[intelligence]` extra | PASS after R2 |
| 9 | **Unsafe temporary-file behavior** | Email attachments use `tempfile.mkdtemp` (secure random dir) + sanitized names + workflow cleanup on both success and failure; no `TemporaryDirectory`/`mkstemp` misuse; no files written into predictable temp locations | PASS |
| 10 | **Permission assumptions** | Runtime dirs created on startup (`_ensure_runtime_directories`); `pam doctor` verifies directory writability and dependency presence before use; no elevated-permission or root assumptions | PASS |
| 11 | **Debug/development settings** | Debug-only traceback locals/paths; `development.yaml` = DEBUG + colors; `production.yaml` = INFO + JSON + no colors | PASS |
| 12 | **Production configuration separation** | `config/production.yaml` exists and merges correctly; now locked by R3 test | PASS after R3 |
| 13 | **Dependency/version consistency** | `pyproject.toml` ↔ `requirements.txt` reconciled; `pip check` clean; no version conflicts | PASS after R2 |
| 14 | **Deployment/startup instructions** | README documents install (venv + `requirements.txt`), `pam doctor`, `pam watch`, `pam ingest`, config precedence, env overrides, `PAM_ENVIRONMENT=production` — now accurate after R2 | PASS after R2 |

**Security-oriented code scan:** no `verify=False`, no `shell=True`, no unsafe `pickle.load` / `eval` / `exec` / `yaml.load`, no `subprocess` usage in `app/`.

## 3. Files Changed

| File | Action |
|------|--------|
| `.gitignore` | **Updated** — ignore `data/inbox/*`, `data/processed/*`, `data/failed/*`, `data/manifests/*` (`.gitkeep` whitelist preserved) |
| `data/…` (34 runtime files) | **Untracked** via `git rm --cached` — files remain on disk |
| `requirements.txt` | **Updated** — added `PyMuPDF>=1.24.0`, `openpyxl>=3.1.0` |
| `tests/unit/test_config.py` | **Updated** — +1 test (production config separation) |

## 4. Verification

| Check | Result |
|-------|--------|
| Repository secret scan (code + configs + git history) | **Clean** — no real secrets; only fake test-fixture strings |
| Tracked-file review (`git ls-files` for `.env`/`.pem`/`.key`/`.p12`/`id_rsa`/`credentials`/`netrc`/`token`) | **Clean** |
| Configuration tests (`test_config.py`) | **21 passed** (incl. new production-separation test) |
| Dependency consistency | `pip check`: **no broken requirements**; `requirements.txt` ≡ pyproject required deps |
| Startup/runtime path | `pam doctor` / `pam watch` / `pam ingest` verified against config; runtime dirs auto-created; queue state restored on restart |
| Deployment docs | README install/run/env-override instructions now accurate |
| Accidental files (`git status`/`git ls-files`) | Runtime data untracked; only `.gitkeep` under `data/`; no new stray files |

## 5. Gates (commands re-run this session)

| Gate | Result |
|------|--------|
| Full default regression suite | **1398 passed / 0 failed / 59 deselected** (P6-103 baseline 1397 +1 new; 0 regressions) |
| Integration suite | **56 passed / 1 skipped** (Tesseract binary absent — pre-existing env skip) / 29 deselected; 1 failure is the documented pre-existing live-Ollama content-miss flake (asserts LLM content; exercises none of this milestone's changes) |
| Ruff | **Clean on all changed files**; 11 findings remain on unchanged pre-existing lines (baseline debt, none in this milestone's files) |
| Mypy | No findings in changed code; whole-repo run remains blocked by the pre-existing numpy-stub/Python 3.14 + `faster_whisper`-untyped environment issues |
| Coverage | **TOTAL 90.03%** (floor 80%); `app/core/config.py` 96% |
| `pip check` | **Clean** |

## 6. Findings

**Blocking:** None.

**Non-blocking:**
- `structlog>=24.2.0` is declared in both dependency manifests but never imported anywhere in `app/`. Harmless but dead weight; recommend removal when convenient. Left in place to avoid an unnecessary manifest change.
- `vault/` (129 generated personal notes) remains tracked in git. This is the product's output directory (its `.gitkeep` is deliberately tracked, unlike `data/`), so it is not an accidental file — but it is personal content. Recommendation for the developer: decide whether the vault should be versioned; if not, apply the same `.gitkeep`-whitelist ignore pattern used for `data/`.
- 11 pre-existing ruff findings (10 × E501, 1 × F841) on untouched lines; working tree remains uncommitted per the per-milestone commit convention (the R1 untracking is staged and will land with the milestone commit).
- Whole-repo mypy remains blocked by the pre-existing numpy-stub/Python 3.14 and `faster_whisper`-untyped issues; the live-Ollama integration flake and Tesseract skip are pre-existing environment conditions.

## 7. Conclusion

The application's attack surface is genuinely small: local-only Ollama integration means there are no credentials to leak, and the security-oriented scan found no unsafe patterns (no shell/`eval`/unsafe-pickle/`verify=False`). The one real security exposure found was not in the code but in the repo itself — 34 personal runtime files tracked in git, contradicting the existing ignore intent; these are now untracked (preserved on disk) and the runtime-data dirs are ignored. The documented deployment path was also broken (`requirements.txt` missing a required eager-import dependency), now reconciled with `pyproject.toml`, and the production/development config separation is locked by a test. All gates pass: 1398 unit tests (0 regressions), coverage 90% (floor 80), hermetic integration green apart from the pre-existing live-Ollama flake, ruff clean on all changed files, `pip check` clean, and the repo secret scan is clean.

**Verdict:** **APPROVED**
