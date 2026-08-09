# P2-203 Engineering Review — MIME Detection Service

**Task:** P2-203 (Milestone 2.2 — Metadata Extraction Framework)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` §P2-203 (lines 116–134) + §2 Normative Interfaces + §3 Normative Configuration
**ADR-001:** `docs/MASTER_ENGINEERING_DESIGN_DOCUMENT.md` lines 501–514
**Reviewer:** Principal Engineering Reviewer
**Date:** 2026-08-01
**Review scope:** P2-203 implementation only (`metadata/mime.py`, classifier MIME consult, config consumption, tests, report). No code modified.

---

## 1. Specification Compliance

| Frozen requirement (§P2-203) | Status | Evidence |
|---|---|---|
| `detect_mime(path: Path) -> str` interface | ✅ | `mime.py:29` — module-level function, returns `str` (never `None`; `application/octet-stream` on indeterminate) |
| Magic-number sniff, first **≤ 512 bytes** | ✅ | `_read_header` reads exactly 512 bytes (`mime.py:62`) |
| Optional `python-magic` used only if importable | ✅ | lazy `import magic` in `_magic_from_header` (`mime.py:70`), only when sniffing (unknown/extensionless) |
| `python-magic` absent → **one** warning (once) + stdlib fallback | ✅ | `_MAGIC_MISSING_WARNED` guard; `logger.warning` once per process (`mime.py:72-76`); warn-once test asserts exactly one record across two calls |
| `_magic_fallback(path)` stdlib sniff incl. Markdown `# ` / `---` / plain-text heuristic | ⚠️ | behavior ✅ (superset: PDF/ZIP/PNG/JPEG/GIF/WebP/WAV/Ogg/MPEG/XML/HTML/JSON/Markdown/plain-text); **name deviation** — frozen internal API `_magic_fallback(path)` does not exist; split into `_sniff_mime(header)` + `_read_header(path)` (O2) |
| `detect_mime` never overrides an explicit ingestor match for known extensions (ADR-001) | ✅ | `_extension_mime` resolves known extension first, **no file read**; `test_known_extension_takes_precedence_over_content` proves extension wins over PDF content |
| Classifier replaces `mimetypes.guess_type` with `detect_mime` when `mime_enabled: true`, stdlib path when disabled | ⚠️ | ✅ at API level (`classifier.py:108-112` + both paths tested); **config plumbing missing** — `mime_enabled` value is never read from settings (F1) |
| Consumes `intelligence.metadata.mime_enabled`; no new keys | ❌ | key exists (`config.py:276`, `default.yaml:140`) but **no code reads it**; `ingest_workflow.py:100` constructs `DocumentClassifier()` with default `True` — config has no effect (F1) |
| Testing strategy: extensionless Markdown → `text/markdown`; renamed `.pdf`; magic-absent warn-once; ADR-001 precedence | ✅ | first, third, fourth as distinct tests; "renamed .pdf" covered implicitly by the extensionless sniff matrix (same code path for `.bin`-renamed PDF) but not pinned as a named case (O3) |
| AC: extensionless Markdown classified via MIME | ✅ | `mime_type` → `text/markdown` (asserted); `kind` remains extension/source_type-driven per P2-203's scoped step 4 (limitation noted O4) |
| AC: `python-magic` absent logs one warning, system still works (AC 5) | ✅ | warn-once test + full fallback-table matrix pass with magic absent |
| DoD: fallback table tests; ADR-001 respected; warning-once tested | ✅ | all three met |

## 2. ADR-001 Compliance

- **Extension primary, MIME fallback** — ✅. `_extension_mime` short-circuits known extensions without reading content; content sniffing runs only for extensionless/unknown-extension files. Matches ADR-001 decision "Keep extension-based ingestion as primary with MIME-based as fallback" and the trade-off "try MIME first for extensionless files, fall back to extension for known-safe types".
- **`python-magic` optional; warning-only when absent** — ✅. Warning-only (no crash), fallback table carries the platform; satisfies "Consequence: Users on Windows without libmagic get extension-only detection" with a bonus stdlib content-sniff layer.
- **Extension wins over content for known extensions** — ✅, tested.
- **Latency respect** — ✅. No file I/O for known extensions; a single 512-byte read only for unknown/extensionless files (~50ms ADR-001 note is an upper bound; stdlib sniff is far cheaper).

## 3. MIME Detection Correctness

- **PDF/ZIP/PNG/JPEG/GIF/WebP/WAV/Ogg/MPEG signatures** — standard magic bytes, correct offsets (`RIFF`+`WEBP`/`WAVE` at 8..12, `PK\x03\x04/\x05\x06/\x07\x08`, `\xff\xd8\xff`, `%PDF-`). ✅
- **Markdown heuristic** — `# ` heading or `---` front-matter within the first 3 lines, NUL-byte guard before decode. ✅ matches frozen `# `/`---` spec.
- **libmagic precedence nuance** — generic `text/plain`/`application/octet-stream` from magic defers to the stdlib Markdown heuristic (libmagic does not identify Markdown); a concrete magic verdict (e.g. `audio/mpeg`) wins. Documented in module docstring; tested both directions. ✅
- **`.ipynb` supplemental map** — `application/x-ipynb+json` (stdlib `mimetypes` returns `None` on 3.14); `.md`/`.markdown`/`.eml` verified already mapped by stdlib on this Python (3.14). ✅
- **Extension match happens before any read** — `test_known_extension_does_not_read_file` proves a nonexistent `readme.md` resolves without `OSError`. ✅
- **Failure containment** — `_read_header` swallows `OSError` → `octet-stream`; a raising/broken libmagic is caught → stdlib fallback. ✅

## 4. Public Interfaces

- **`detect_mime(path: Path) -> str`** — signature exactly as frozen §2/§P2-203. ✅
- **Exported from `metadata/__init__.py`** and listed in `__all__` — resolves the P2-201 review line-63 deferral ("detect_mime deferred to P2-203"). ✅
- **No existing public signature changed.** `DocumentClassifier()` remains a valid no-arg construction; `classify()` returns the same `DocumentClassification` model. `mime_type` remains `str | None` at the domain level (`routing.py:16`, `documents.py:22`). ✅
- **Frozen internal API gap** — `_magic_fallback(path)` (listed in §2 Internal APIs) is absent; replaced by `_sniff_mime(header)`/`_read_header(path)`. Internal-only, functionally a superset; recorded as O2.

## 5. Backward Compatibility

- **`mime_enabled=False`** reproduces the pre-P2-203 behavior exactly: `mimetypes.guess_type(document.filename)` (same call, same inputs) — asserted by `test_mime_disabled_keeps_stdlib_behavior` (`None` for extensionless). ✅
- **`source_path=None`** (URL-sourced) falls back to the same `guess_type` path — no regression for URL documents. ✅
- **Default-on behavior** matches frozen §3 default `mime_enabled: true`. For known extensions, `detect_mime` returns the same value as the old `guess_type` except `.ipynb` (improvement: `None` → `application/x-ipynb+json`). No test asserted the old `None`. ✅
- **`_detect_kind` untouched** — all 24 existing `test_routing.py` classification tests pass unchanged. ✅
- **Rollback contract (R-4) partial** — the disable seam exists at the API level but is **not reachable from config** in the running system (F1); §3 "false ⇒ stdlib guess_type path, no magic sniff" is therefore not honored end-to-end.

## 6. Error Handling & Logging

- Unreadable/missing file → `application/octet-stream`, no exception escapes `classify()`. ✅
- Broken `python-magic` → caught (`except Exception`), stdlib fallback. ✅
- `KeyboardInterrupt`/`SystemExit` never swallowed (they are `BaseException`, not matched). ✅
- Missing-magic warning: `logger.warning` at module level, warn-once via module global — matches frozen "log one warning (once)". Minor: the global is not thread-safe (two concurrent first calls could double-warn) — O5.

## 7. Test Coverage

`tests/unit/test_mime_detection.py` (24 tests, all passing):

- Extension precedence (no file read, `.ipynb` supplement, extension-wins-over-PDF-content, `.pdf`). ✅
- Sniff matrix (12 parametrized: PDF/ZIP/PNG/JPEG/GIF/Markdown/JSON×2/XML/HTML/plain) + binary-garbage → `octet-stream` + missing-file → `octet-stream`. ✅
- Magic enhancement: concrete verdict wins, generic `text/plain` defers to Markdown, raising libmagic falls back. ✅
- Warn-once: two `detect_mime` calls → exactly one warning. ✅
- Classifier consult: `mime_enabled=True` extensionless Markdown → `text/markdown`; `mime_enabled=False` → stdlib `None`; `source_path=None` → filename fallback. ✅
- Real `python-magic` is not installed here; the optional path is exercised via `sys.modules["magic"]` monkeypatch (frozen strategy: "monkeypatched import"). ✅

Gaps (non-blocking): no named "renamed `.pdf`" test (O3); no test of MIME-sniff driving routing `kind` (out of P2-203 scope — O4).

## 8. Documentation

- Implementation report (`PHASE_2_MILESTONE_2_2_P2-203_IMPLEMENTATION_REPORT.md`) is accurate on Summary/Files/Tests/Results/Gates. ⚠️
- **Doc error:** "Next Recommended Task" labels **P2-204 as "Wire MIME detection into ingestion routing"** — frozen §P2-204 is **Language detection service (G16)**. There is **no** frozen 2.2 task that wires MIME into routing `kind`; the classifier MIME consult (step 4) is the last MIME touch-point in the milestone. The next task should be **P2-204 — Language detection (G16)** (or P2-205). This is a factual mislabel (O6).
- The report's claim that the integration failure is a pre-existing live-LLM smoke test is verified: `smoke_test.py` imports neither the classifier nor MIME code (direct `OllamaClient` → `ObsidianMarkdownGenerator`); the failure is llama3.1:8b omitting four optional quiz sections. Unrelated to P2-203. ✅

## 9. Regression Safety

| Gate | Result |
|---|---|
| `python -m pytest tests -m "not integration" -q` | **570 passed / 7 deselected** (baseline 546 + 24 new; 0 regressions) |
| `python -m pytest tests/integration -m integration -q` | 5 passed / 1 skipped (Tesseract absent) / 1 failed — live-LLM smoke, unrelated to P2-203 |
| `python -m ruff check app tests` | 64 errors — pre-existing baseline; **zero** in changed files |
| `python -m mypy app` | 4 pre-existing errors (fitz/pptx/whisper/numpy stubs); `mime.py`/`classifier.py` clean |
| Import cycles | none (clean import + full suite pass) |

Workflow-level regression is real: `test_complete_workflow.py` and `test_queue_worker_pipeline.py` exercise `IngestionWorkflow` → `DocumentClassifier()` → new `detect_mime` path and pass.

---

## Findings (remediation required)

**F1 — Config not consumed (binding, §P2-203 Configuration Changes + R-4 rollback).**
`intelligence.metadata.mime_enabled` exists in config (`config.py:276`, `default.yaml:140`) but nothing reads it. `ingest_workflow.py:100` constructs `DocumentClassifier()` with the hardcoded default `True`, so `mime_enabled: false` has **no effect** on the running system and the frozen rollback contract ("MIME … independently disableable", §3 "false ⇒ stdlib guess_type path, no magic sniff") is broken end-to-end. The fix is the P2-207-established pattern: plumb `settings.intelligence.metadata.mime_enabled` into the `DocumentClassifier(...)` construction at the single call site.

## Observations (non-blocking)

1. **O2 — Frozen internal API name absent:** `_magic_fallback(path)` (frozen §2/§P2-203 Interfaces) is renamed/split into `_sniff_mime(header)` + `_read_header(path)`. Functionally equivalent superset; internal-only. Either align the name or accept the deviation consciously.
2. **O3 — "renamed `.pdf` still detected" not a distinct test:** the sniff matrix covers PDF bytes on extensionless files (identical code path to a `.bin`-renamed PDF), but the frozen strategy's named case — including the extension-precedence edge (PDF bytes under a misleading known extension, e.g. `.txt`) — is not pinned as an explicit test.
3. **O4 — AC "classified `markdown` via MIME" is partial:** MIME populates `mime_type` only; `kind` remains extension/source_type-driven. For an extensionless file with an unknown `source_type`, `kind` stays `"unknown"` despite `mime_type == text/markdown`. This is consistent with P2-203's scoped step 4 (classifier `mime_type` field only) and the Purpose line ("feeds the classifier's `mime_type`"), but the AC wording is broader than delivered; routing-by-MIME is not a frozen 2.2 task.
4. **O5 — Minor robustness:** the warn-once module global is not thread-safe; UTF-8 non-ASCII (e.g. CJK) extensionless text scores below the ASCII printable-ratio 0.9 threshold → `application/octet-stream`; a UTF-8 BOM prefix defeats the `<!DOCTYPE`/`{` lstrip checks. None spec-blocking; the Markdown heuristic is byte-agnostic for `# ` and `---`.
5. **O6 — Report doc error:** "Next Recommended Task" mislabels P2-204 as MIME-into-routing wiring; frozen P2-204 is **Language detection (G16)**. Correct the report.

---

## Verdict

❌ **Needs Remediation**

P2-203's detection logic is correct, ADR-001-compliant, well-tested, and regression-safe (570 passed, ruff/mypy baselines unchanged), and the classifier consult is backward-compatible at the API level. However, a **binding frozen requirement is unmet**: §P2-203 Configuration Changes mandates consuming `intelligence.metadata.mime_enabled`, and the R-4 rollback contract requires MIME detection to be independently disableable via config. Today the config key is dead — `mime_enabled: false` has no effect in the running system because the value is never plumbed into `DocumentClassifier()` (`ingest_workflow.py:100`). The remediation is small and follows the P2-207 precedent: read `settings.intelligence.metadata.mime_enabled` and pass it at the classifier construction site, with a config-driven test (e.g., a workflow test asserting the stdlib `guess_type` path when disabled). The remaining items (O2–O6) are minor observations and documentation corrections, not blockers.
