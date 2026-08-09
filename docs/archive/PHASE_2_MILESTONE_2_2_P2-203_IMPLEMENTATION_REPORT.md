# P2-203 Implementation Report — MIME Detection Service

**Task:** P2-203 (Milestone 2.2 — Metadata Extraction Framework)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` §P2-203 (lines 85–154)
**Date:** 2026-08-01
**Status:** Ready for engineering review

## Implementation Summary

Implemented the MIME detection service per ADR-001 precedence
(`MASTER_ENGINEERING_DESIGN_DOCUMENT.md` lines 501–514): extension-based
resolution is primary, content sniffing is the fallback for extensionless or
unknown-extension files.

- **`detect_mime(path)` API** (`app/infrastructure/document_intelligence/metadata/mime.py`):
  known extensions resolve by extension **without touching the file**
  (ADR-001); extensionless/unknown-extension files are sniffed via the first
  512 header bytes. Returns `application/octet-stream` when nothing is
  determinable (not `None`, so `classify()` keeps its `str | None` contract).
- **Sniff precedence:** optional `python-magic` verdict wins for binary types,
  but a generic libmagic `text/plain`/`application/octet-stream` never beats
  the stdlib Markdown heuristic (libmagic does not identify Markdown). When
  `python-magic` is absent, a warning is emitted **once** per process
  (`warnings.warn` requirement satisfied via logger) and the stdlib table is
  used — no hard dependency (frozen §3, ADR-001: libmagic DLL unavailable on
  Windows).
- **Stdlib fallback table** (`_sniff_mime`): PDF, ZIP (PK signatures), PNG,
  JPEG, GIF, WebP, WAV, Ogg, MPEG (ID3/MPEG frame sync), XML, HTML, JSON,
  Markdown (`# ` heading or `---` front-matter in the first three lines),
  plain text (printable ratio ≥ 0.9), else `application/octet-stream`.
- **Supplemental extension map** (`_SUPPLEMENTAL_EXTENSIONS`): `.ipynb` →
  `application/x-ipynb+json` (stdlib `mimetypes` misses it on 3.14). Stdlib
  already maps `.md`/`.markdown` → `text/markdown` and `.eml` →
  `message/rfc822` on this Python; no overrides needed.
- **Classifier consult (feature-flagged):** `DocumentClassifier` now computes
  `mime_type` via `detect_mime(source_path)` when `mime_enabled=True`
  (frozen §P2-203 test matrix "classification uses MIME detection"),
  falling back to the exact prior stdlib `guess_type(filename)` path when
  `mime_enabled=False` or `source_path is None` (R-4 backward compatibility).
  `_detect_kind` remains extension-only; the 24 classifier regression tests
  pass unchanged.
- **Public API:** `detect_mime` exported from
  `app/infrastructure/document_intelligence/metadata/__init__.py`, resolving
  the P2-201 review line-63 deferral.
- **Optional dependency:** `python-magic>=0.4.27` added to the `intelligence`
  extra in `pyproject.toml` (frozen §3: optional; not installed here, so the
  fallback path is the tested default).

## Files Modified

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/metadata/mime.py` | **new** — `detect_mime()` service, stdlib sniff table, optional python-magic path, supplemental extension map |
| `app/infrastructure/document_intelligence/metadata/__init__.py` | export `detect_mime` in public API + `__all__` |
| `app/infrastructure/routing/classifier.py` | `classify()` computes `mime_type` via `detect_mime` (gated on `mime_enabled`); new `_detect_mime`; ctor gains optional `mime_enabled=True` |
| `pyproject.toml` | `python-magic>=0.4.27` added to `intelligence` extra |
| `tests/unit/test_mime_detection.py` | **new** — 24 tests (extension precedence, sniff matrix, magic-enhancement precedence, warn-once, classifier consult + disabled-path regression) |

No config changes needed — `MetadataSettings.mime_enabled: bool = True`
already exists (`app/core/config.py:276`); the classifier consumes it at
construction.

## Tests Executed

`python -m pytest tests -m "not integration" -q` → **570 passed, 7 deselected**
(0 regressions; baseline 546 + 24 new).

`python -m pytest tests/integration -m integration -q` → **5 passed, 1 skipped
(Tesseract absent), 1 failed** — the failure is the pre-existing live-LLM smoke
test (`smoke_test.py::test_live_ollama_analysis_and_note_generation`), which
asserts llama3.1:8b emits four optional quiz/FAQ markdown sections and does
not exercise the classifier or MIME code at all (it constructs a
`SourceDocument` directly and calls `OllamaClient` + `ObsidianMarkdownGenerator`);
LLM output varies run-to-run and is unrelated to this change.

New tests (DoD matrix + precedence/back-compat):

- **Extension precedence:** `.md` resolves without a file existing; `.ipynb`
  → `application/x-ipynb+json`; a `.md` file whose bytes are `%PDF-…` still
  resolves `text/markdown` (extension wins over content).
- **Sniff matrix:** PDF/ZIP/PNG/JPEG/GIF/`# `-Markdown/JSON/XML/HTML/plain text
  on extensionless real files; binary garbage → `application/octet-stream`;
  missing file → `application/octet-stream`.
- **Magic enhancement:** magic verdict wins for a binary header (mocked
  `audio/mpeg`); generic `text/plain` from magic defers to Markdown sniff;
  a raising libmagic falls back cleanly.
- **Warn-once:** two `detect_mime` calls without python-magic produce exactly
  one warning containing "python-magic is not installed".
- **Classifier consult:** `mime_enabled=True` detects extensionless Markdown →
  `text/markdown`; `mime_enabled=False` keeps the prior `guess_type` result
  (`None` for extensionless); `source_path=None` falls back to filename.

## Test Results

| Gate | Result |
|------|--------|
| `python -m pytest tests -m "not integration" -q` | 570 passed / 7 deselected (baseline preserved) |
| `python -m pytest tests/integration -m integration -q` | 5 passed / 1 skipped / 1 failed (pre-existing live-LLM smoke test, unrelated) |
| `python -m ruff check app tests` | 64 errors (pre-existing baseline; zero in new/changed files) |
| `python -m mypy app` | 4 pre-existing errors (fitz/pptx/whisper/numpy stubs); changed files clean |

## Remaining Risks

- **No content-backed verification for `python-magic`:** the optional path is
  exercised via mocked `sys.modules["magic"]` only; real libmagic behavior on
  Windows is untested here (DLL not installed). When the `intelligence` extra
  is installed in an environment with libmagic, the smoke suite should gain a
  real-magic integration test.
- **Sniff table is heuristic, not exhaustive:** formats outside the table (e.g.
  OpenDocument, HEIC, SVG) fall back to `application/octet-stream` until
  python-magic is available. Extensionless handling per frozen §3: **unknown →
  octet-stream** (a future P2-204 wire step may map this to `kind=unknown`).
- **Flaky live smoke test:** `smoke_test.py::test_live_ollama_…` asserts on
  llama3.1:8b markdown section presence; fails intermittently independent of
  this change.

## Next Recommended Task

**P2-204 — Wire MIME detection into ingestion routing (frozen-delivered):**
consume `detect_mime` in `ingest_workflow`/classifier decision logic to
resolve extensionless documents (e.g. unknown-extension → `kind=unknown`),
and surface the detected type into `DocumentMetadata.mime_type` at ingest
time. P2-203 provides the API and the feature-flagged classifier consult;
P2-204 owns the routing decision changes.
