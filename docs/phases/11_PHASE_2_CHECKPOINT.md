# Phase 2 Checkpoint — Correctness & Dependency Fixes (Partial)

**Date:** 2026-08-19
**Status:** Initial changes applied. Six format parsers NOT implemented.
**Test suite:** 1377 passed, 57 deselected, 0 failed

---

## What Changed

### 1. `app/infrastructure/ingestion/docx_ingestor.py`

**Changed:** `supported_suffixes` from `(".docx", ".odt", ".rtf")` to `(".docx",)`

**Why:** `python-docx` can only parse OOXML `.docx` files. It cannot parse `.odt` (ODF) or `.rtf` (Rich Text Format). The `.odt` path would always raise `IngestionError("Unable to read DOCX file")`. The `.rtf` path was dead code — `TextIngestor` is registered before `DocxIngestor` in the service, so `.rtf` files were already caught by `TextIngestor` and read as raw text (producing RTF markup garbage).

**Behavior change:** `.odt` and `.rtf` files now fall through to the next ingestor in the chain. `.odt` has no parser and returns `UnsupportedSourceError`. `.rtf` is caught by `TextIngestor` and read as plain text (RTF markup — same garbage as before, but now the dead code in DocxIngestor is gone).

**Safety:** The removed suffixes never worked correctly in this ingestor. No working path was removed.

**Test evidence:** `test_supported_extensions_includes_new_types` updated to assert `.odt not in extensions` and `.rtf not in extensions`. All 1377 tests pass.

---

### 2. `app/infrastructure/ingestion/spreadsheet_ingestor.py`

**Changed:** `supported_suffixes` from `(".xls", ".xlsx", ".ods")` to `(".xlsx",)`

**Why:** `openpyxl` can only parse OOXML `.xlsx` files. It cannot parse legacy `.xls` (BIFF format) or `.ods` (ODF). Both would always raise `IngestionError("Unable to read spreadsheet file")`.

**Behavior change:** `.xls` and `.ods` files now return `UnsupportedSourceError` instead of a confusing "Unable to read spreadsheet file" error.

**Safety:** The removed suffixes never worked. No working path was removed.

**Test evidence:** `test_supported_extensions_includes_new_types` updated to assert `.xls not in extensions` and `.ods not in extensions`. All 1377 tests pass.

---

### 3. `app/infrastructure/ingestion/pptx_ingestor.py`

**Changed:** `supported_suffixes` from `(".pptx", ".ppt", ".odp")` to `(".pptx",)`

**Why:** `python-pptx` can only parse OOXML `.pptx` files. It cannot parse legacy `.ppt` (OLE binary) or `.odp` (ODF). Both would always raise `IngestionError("Unable to read PPTX file")`.

**Behavior change:** `.ppt` and `.odp` files now return `UnsupportedSourceError` instead of a confusing error.

**Safety:** The removed suffixes never worked. No working path was removed.

**Test evidence:** `test_supported_extensions_includes_new_types` updated to assert `.ppt not in extensions` and `.odp not in extensions`. All 1377 tests pass.

---

### 4. `app/infrastructure/ingestion/txt_ingestor.py`

**Changed:** `supported_suffixes` removed `.rtf` from the tuple.

**Why:** `TextIngestor` reads files via `pathlib.read_text(encoding="utf-8")`. For `.rtf` files this produces raw RTF markup (`{\rtf1\ansi...}`) — not rendered text. The content is garbage for RAG purposes. The correct behavior is to return `UnsupportedSourceError` so the user knows the format is not supported, rather than silently ingesting unusable content.

**Behavior change:** `.rtf` files now return `UnsupportedSourceError` instead of silently producing garbage content.

**Safety:** The previous behavior was worse — it silently produced unusable data. Failing cleanly is safer.

**Test evidence:** `test_supported_extensions_includes_new_types` updated to assert `.rtf not in extensions`. All 1377 tests pass.

---

### 5. `pyproject.toml`

**Changed:**
- Removed `structlog>=24.2.0` from `[project.dependencies]`
- Added `python-docx>=1.1.0` to `[project.dependencies]`
- Added `python-pptx>=0.6.23` to `[project.dependencies]`
- Added `faster-whisper>=1.0.0` to `[project.dependencies]`

**Why:**
- `structlog`: Zero imports found in `app/`. Verified via grep. Dead dependency.
- `python-docx`: Imported in `docx_ingestor.py:42`. Runtime required for DOCX ingestion. Was undeclared.
- `python-pptx`: Imported in `pptx_ingestor.py:42`. Runtime required for PPTX ingestion. Was undeclared.
- `faster-whisper`: Imported in `audio_ingestor.py`. Runtime required for audio transcription. Was undeclared.

**Behavior change:** `pip install` now correctly installs the three required libraries and no longer installs structlog.

**Safety:** Declaring dependencies that are actually imported is strictly correct. Removing an unused dependency has no runtime effect.

**Test evidence:** All 1377 tests pass. No import errors.

---

### 6. `requirements.txt`

**Changed:** Mirrored the pyproject.toml changes exactly — removed `structlog`, added `python-docx`, `python-pptx`, `faster-whisper`.

**Why:** `requirements.txt` must stay in sync with `pyproject.toml`.

**Safety:** Same rationale as pyproject.toml.

**Test evidence:** All 1377 tests pass.

---

### 7. `tests/unit/test_ingestion.py`

**Changed:** In `test_supported_extensions_includes_new_types`:
- `assert ".odt" in extensions` → `assert ".odt" not in extensions`
- `assert ".rtf" in extensions` → `assert ".rtf" not in extensions`
- Added: `assert ".xls" not in extensions`
- Added: `assert ".ods" not in extensions`
- Added: `assert ".ppt" not in extensions`
- Added: `assert ".odp" not in extensions`

**Why:** The test previously asserted that broken formats were listed as supported. The test now correctly asserts they are not.

**Safety:** Test now matches actual behavior.

**Test evidence:** All 1377 tests pass including this updated test.

---

## Verification

| Check | Result |
|---|---|
| Tests pass | 1377 passed, 57 deselected |
| Retrieval code unchanged | Confirmed — zero diff on search.py, vector_store.py, bm25.py, embeddings.py |
| Config unchanged | Confirmed — zero diff on config/ |
| README unchanged | Confirmed |
| .gitignore unchanged | Confirmed |
| No commits made | Confirmed |

---

## The Six Removed Formats

**The six formats have NOT been implemented. Their previously incorrect adapter registrations were removed.**

| Format | Current Status | Root Cause of Previous Failure | Correct Parser Needed | Dependency Needed | V1.1 Priority |
|---|---|---|---|---|---|
| **RTF** | Unsupported — returns `UnsupportedSourceError` | TextIngestor read it as plain text (garbage); DocxIngestor claimed support but was unreachable | `pyth` (pure Python RTF parser) or `unrtf` (CLI) or `striprtf` | `striprtf` (~50 LOC wrapper) | Low — RTF is rare in modern workflows |
| **ODT** | Unsupported — returns `UnsupportedSourceError` | `python-docx` cannot parse ODF ZIP structure | `odfpy` (`odf.text`) or `python-docx` with ODF plugin | `odfpy` | Medium — common in LibreOffice workflows |
| **XLS** | Unsupported — returns `UnsupportedSourceError` | `openpyxl` cannot parse BIFF (legacy Excel) format | `xlrd` for reading + `openpyxl` for writing | `xlrd` (already commonly paired with openpyxl) | Medium — legacy Excel files still exist |
| **ODS** | Unsupported — returns `UnsupportedSourceError` | `openpyxl` cannot parse ODF spreadsheet format | `odfpy` (`odf.table`) or `pyexcel-ods` | `odfpy` (same as ODT) | Low — niche format |
| **PPT** | Unsupported — returns `UnsupportedSourceError` | `python-pptx` cannot parse legacy OLE PPT format | `olefile` + custom binary extraction or `libreoffice --convert` | `olefile` + custom code, or external tool | Low — legacy PowerPoint is rare |
| **ODP** | Unsupported — returns `UnsupportedSourceError` | `python-pptx` cannot parse ODF presentation format | `odfpy` (`odf.presentation`) or `libreoffice --convert` | `odfpy` (same as ODT) | Low — niche format |

### Parser Selection Notes

- **`odfpy`** covers ODT + ODS + ODP (all three ODF formats) with a single dependency. If any ODF format is prioritized, all three become available.
- **`xlrd`** is the standard solution for `.xls`. It pairs naturally with `openpyxl` (which handles `.xlsx`).
- **`striprtf`** is the simplest pure-Python RTF-to-text converter. ~50 lines of wrapper code.
- **Legacy PPT** is the hardest — no clean Python library exists. `olefile` can parse the OLE container but extracting text requires custom slide parsing. `libreoffice --convert` is the reliable path but adds an external runtime dependency.

---

> Checkpoint created. No further Phase 2 implementation performed.
> Awaiting instructions for Phase 2 completion or next phase.
