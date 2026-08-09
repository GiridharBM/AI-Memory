# MEDD Documentation Synchronization Report

**Author:** Principal Software Architect
**Date:** 2026-08-04
**Scope:** Synchronize `docs/MASTER_ENGINEERING_DESIGN_DOCUMENT.md` with the shipped implementation through Milestone 2.5. Documentation-only; **no implementation code modified.**
**Driving artifacts:** `docs/PHASE_2_MILESTONE_2_1_FINAL_REVIEW.md`, `docs/PHASE_2_MILESTONE_2_5_REMEDIATION_REPORT.md`, `docs/PHASE_2_MILESTONE_2_5_IMPLEMENTATION_REPORT.md`.

**Verification basis (live source of truth):**
- `app/infrastructure/document_intelligence/ocr/base.py` — `OcrEngine` protocol, `DocumentOcrService`, `OCRSelectionError`
- `app/infrastructure/document_intelligence/ocr/models.py` — `OcrResult`, `PageOcrResult`
- `app/infrastructure/document_intelligence/ocr/__init__.py` — `get_default_ocr_service`
- `app/infrastructure/document_intelligence/ocr/pdf.py` — `render_pdf_pages`
- `app/infrastructure/document_intelligence/ocr/engines.py` — `VisionOcrEngine`, `TesseractOcrEngine`
- `app/infrastructure/document_intelligence/images/metadata.py` — `ImageAnalyzer`, `analyze_image`
- `app/infrastructure/document_intelligence/images/diagram.py` — `drawio_to_mermaid`, `DiagramParser`
- `app/infrastructure/document_intelligence/images/multi.py` — `MultiImageExtractor`
- `app/infrastructure/document_intelligence/imaging/preprocess.py` — shared preprocessing
- `app/core/config.py` — `OcrSettings`, `ImageSettings`, `Settings`
- `config/default.yaml` — `intelligence.ocr.*`, `intelligence.images.*`

---

## 1. Updated Sections

| # | Section | Location | Change |
|---|---------|----------|--------|
| 1 | §7.2 OCR Module — "Current Implementation" protocol bullet | MEDD line ~1851 | Corrected `OcrEngine` protocol description to the implemented `run()` API; removed `extract()` + `ExtractionContext` |
| 2 | §7.2 OCR Module — "Interfaces" block | MEDD lines ~1872-1968 | Rewritten end-to-end to match the implementation (see §2) |
| 3 | §7.2 OCR Module — "Data Flow" | MEDD line ~1865 | Verified `DocumentOcrService.extract()` — **unchanged**, this method exists in the implementation (`base.py:67`) |

No other MEDD sections reference the obsolete API. A repo-wide grep for `ExtractionContext`, `mean_confidence`, `select(document`, `OcrSettings, *`, `vision_client=None` in `docs/` now returns zero hits.

---

## 2. Old API → New API (Interfaces block)

### 2.1 `OcrEngine` protocol

| Item | Old (MEDD) | New (implementation) |
|------|-----------|----------------------|
| Protocol attribute | `supported_kinds: set[str]` | `name: str` **and** `supported_kinds: set[str]` (`base.py:23-24`) |
| Method | `def extract(self, document: ProcessedDocument, ctx: ExtractionContext) -> OcrResult` | `def run(self, source: Path, *, prompt: str, preprocess: bool = False) -> OcrResult` (`base.py:26`) |
| `@runtime_checkable` | not shown | shown (matches `base.py:19`) |
| Parameter type | `ProcessedDocument` | `Path` (`source`) |
| Context type | `ExtractionContext` | **removed — type does not exist in the codebase** |
| Engine list | not shown | `name = "vision"` / `"tesseract"`, `supported_kinds = {"scanned_pdf","image","handwritten"}` (`engines.py:31-32, 142`) |

**Reason for change:** The protocol was documented as an aspirational `extract()` design that was never implemented; the shipped contract is `run(source, *, prompt, preprocess)`.

### 2.2 `DocumentOcrService`

| Item | Old (MEDD) | New (implementation) |
|------|-----------|----------------------|
| `__init__` | not shown | `def __init__(self, engines: list[OcrEngine] | None = None) -> None` (`base.py:34`) |
| `register` | `def register(self, engine: OcrEngine) -> None` | unchanged (`base.py:37`) |
| `engines` property | not shown | `@property engines -> list[OcrEngine]` (registration-order snapshot) (`base.py:41-44`) |
| `select` | `def select(self, document: ProcessedDocument) -> OcrEngine  # raises OCRSelectionError if none` | `def select(self, kind: str, *, engine: str = "auto") -> OcrEngine` — kind-based; explicit `engine=` requires name+kind match; raises `OCRSelectionError` (`base.py:46-65`) |
| `extract` | `def extract(self, document: ProcessedDocument) -> OcrResult` | `def extract(self, document: SourceDocument, *, prompt: str, engine: str = "auto", preprocess: bool = False) -> OcrResult` (`base.py:67-87`) |

**Reason for change:** `select()` is keyed on the document **kind** string with an `engine` selector, not on the document object; `extract()` carries required `prompt` and optional `engine`/`preprocess` keyword arguments and accepts a `SourceDocument`.

### 2.3 `OcrResult` / `PageOcrResult` models

| Item | Old (MEDD) | New (implementation) |
|------|-----------|----------------------|
| Base | `@dataclass` | pydantic `BaseModel` (`models.py:14, 22`) |
| `PageOcrResult` | not shown | `page_no: int`, `text: str`, `confidence: float \| None = None` (`models.py:14-19`) |
| `OcrResult.text` | plain field `text: str` | `@property text` — concatenated non-empty page text (`models.py:30-33`) |
| Confidence field | `mean_confidence: float \| None` | `confidence: float \| None` (mean of per-page confidences) (`models.py:26`) |
| Flag fields | not shown | `empty_pages: list[int]`, `low_confidence_pages: list[int]` (`models.py:27-28`) |
| `from_pages` | `def from_pages(pages) -> "OcrResult"` | `@classmethod from_pages(cls, pages, *, confidence_threshold: float = 50.0) -> "OcrResult"` (`models.py:35-67`) |

**Reason for change:** The models were documented as a dataclass with a `mean_confidence` field and a stored `text` field; the shipped models are pydantic `BaseModel`s with `confidence`, empty/low-confidence flag lists, and a computed `text` property.

### 2.4 `get_default_ocr_service` factory

| Item | Old (MEDD) | New (implementation) |
|------|-----------|----------------------|
| Signature | `def get_default_ocr_service(settings: OcrSettings, *, vision_client=None) -> DocumentOcrService` | `def get_default_ocr_service(settings: Settings) -> DocumentOcrService` (`__init__.py:26`) |
| Parameters | `OcrSettings` + optional `vision_client` | full `Settings`; **no** `vision_client` kwarg |

**Reason for change:** The factory consumes the complete `Settings` object to build both engines (`settings.intelligence.ocr`, `settings.ollama`, `settings.models.vision`); the documented `vision_client=` injection point does not exist in the signature (`__init__.py:51-89`).

---

## 3. Obsolete API references removed from the MEDD

| Obsolete symbol | Occurrences | Disposition |
|-----------------|-------------|-------------|
| `ExtractionContext` | 2 (protocol bullet, Interfaces block) | Removed — type does not exist in code |
| `OcrEngine.extract(...)` | 2 | Replaced with `OcrEngine.run(...)` |
| `DocumentOcrService.select(document)` | 1 | Replaced with `select(kind, *, engine="auto")` |
| `DocumentOcrService.extract(document)` (bare) | 1 | Replaced with full kwarg signature on `SourceDocument` |
| `OcrResult.mean_confidence` | 1 | Replaced with `confidence` |
| `OcrResult` as `@dataclass` with stored `text` | 1 | Replaced with pydantic `BaseModel` + `text` property |
| `get_default_ocr_service(OcrSettings, *, vision_client=None)` | 1 | Replaced with `get_default_ocr_service(Settings)` |

---

## 4. Verification

- **No code modified:** `git status` shows only `docs/MASTER_ENGINEERING_DESIGN_DOCUMENT.md` changed by this task (implementation files untouched).
- **Repo-wide doc sweep:** `ExtractionContext`, `mean_confidence`, `select(document`, `OcrSettings, *`, `vision_client=None` → **0 hits** under `docs/`.
- **Every new signature verified against source:** `base.py`, `models.py`, `__init__.py` read directly; the MEDD Interfaces block now mirrors them field-for-field (including `name`, `engines` property, `from_pages` classmethod, `confidence_threshold=50.0`, and the `@runtime_checkable` decorator).
- **Unchanged sections confirmed accurate:** `DocumentOcrService.extract()` in the Data Flow diagram, Configuration block, Dependencies, Extension Points, and Future Work all already matched the implementation.

---

## 5. Residual Note

The §7.2 Interfaces block in the MEDD is now a faithful representation of the implementation but intentionally omits the module-level imports (`BaseModel`, `Field`, `OcrSettings`, `Settings`, `OllamaVisionClient`) for brevity. This is consistent with the MEDD's role as a design contract rather than a copy of source; the canonical imports remain in `models.py`, `base.py`, and `__init__.py`.
