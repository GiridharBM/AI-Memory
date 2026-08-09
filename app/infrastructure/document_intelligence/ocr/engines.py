"""OCR engine implementations."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.infrastructure.document_intelligence.ocr.models import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    OcrResult,
    PageOcrResult,
)
from app.infrastructure.document_intelligence.ocr.pdf import render_pdf_pages
from app.infrastructure.llm.vision_client import OllamaVisionClient

logger = get_logger(__name__)


class VisionOcrEngine:
    """OCR engine backed by a vision model, mirroring the Phase-1 path.

    Sequential per-page loop over ``render_pdf_pages`` with an early stop on
    the first empty page and a bounded retry (1 retry) per page on transient
    vision errors — a failed page yields ``""`` plus a warning and never
    aborts the pass.
    """

    name = "vision"
    supported_kinds = {"scanned_pdf", "image", "handwritten"}

    def __init__(
        self,
        vision_client: OllamaVisionClient,
        *,
        zoom: float = 2.0,
        page_limit: int | None = 5,
        max_pages: int = 200,
        preprocessor: Callable[[bytes], bytes] | None = None,
    ) -> None:
        self._vision = vision_client
        self._zoom = zoom
        self._page_limit = page_limit
        self._max_pages = max_pages
        self._preprocessor = preprocessor

    def run(self, source: Path, *, prompt: str, preprocess: bool = False) -> OcrResult:
        """Extract text from a scanned PDF or image via the vision model."""
        if preprocess and self._preprocessor is None:
            logger.warning(
                "Preprocessing requested but no preprocessor registered "
                "(P2-104 not wired); running un-preprocessed."
            )
            preprocess = False
        if source.suffix.lower() == ".pdf":
            return self._run_pdf(source, prompt=prompt, preprocess=preprocess)
        return self._run_image(source, prompt=prompt, preprocess=preprocess)

    def _describe(self, png_bytes: bytes, *, prompt: str) -> str:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(png_bytes)
            tmp_path = Path(tmp.name)
        try:
            return self._vision.describe_image(tmp_path, prompt=prompt)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _run_pdf(self, source: Path, *, prompt: str, preprocess: bool) -> OcrResult:
        pages: list[PageOcrResult] = []
        for page in render_pdf_pages(
            source,
            zoom=self._zoom,
            page_limit=self._page_limit,
            max_pages=self._max_pages,
        ):
            png = page.png_bytes
            if preprocess and self._preprocessor is not None:
                png = self._preprocessor(png)
            text = self._with_retry(
                lambda png=png: self._describe(png, prompt=prompt), page_no=page.page_no
            )
            pages.append(PageOcrResult(page_no=page.page_no, text=text, confidence=None))
            if not text.strip():
                logger.warning(
                    "Empty vision OCR result; stopping page loop.",
                    extra={"page_no": page.page_no + 1},
                )
                break
        return OcrResult.from_pages(pages)

    def _run_image(self, source: Path, *, prompt: str, preprocess: bool) -> OcrResult:
        def describe() -> str:
            if preprocess and self._preprocessor is not None:
                return self._describe(self._preprocessor(source.read_bytes()), prompt=prompt)
            return self._vision.describe_image(source, prompt=prompt)

        text = self._with_retry(describe, page_no=0)
        return OcrResult.from_pages([PageOcrResult(page_no=0, text=text, confidence=None)])

    def _with_retry(self, fn: Callable[[], str], *, page_no: int) -> str:
        for attempt in range(2):  # initial + 1 bounded retry
            try:
                return fn()
            except Exception:
                logger.warning(
                    "Vision OCR failed on page, attempt %s of 2.",
                    attempt + 1,
                    extra={"page_no": page_no + 1},
                    exc_info=True,
                )
        return ""


class TesseractOcrError(RuntimeError):
    """Raised when the Tesseract binary is unavailable."""


_TESSERACT_BINARY_MESSAGE = (
    "Tesseract OCR binary not found on PATH. Install Tesseract OCR and ensure "
    "'tesseract' is reachable, or set intelligence.ocr.tesseract_cmd. "
    "Run 'pam doctor' for OCR engine availability."
)


class TesseractOcrEngine:
    """Offline OCR engine backed by the Tesseract binary via pytesseract.

    ``run`` lazily imports pytesseract and raises a clear ``ImportError`` when
    the package is absent (G06). PDF pages are rendered through
    ``render_pdf_pages`` and OCR'd independently; a page that fails yields
    ``""`` with a warning and never aborts the document. The ``prompt``
    parameter is accepted for ``OcrEngine`` conformance and ignored — offline
    OCR has no prompt.
    """

    name = "tesseract"
    supported_kinds = {"scanned_pdf", "image"}

    def __init__(
        self,
        *,
        tesseract_cmd: str = "",
        lang: str = "eng",
        zoom: float = 2.0,
        page_limit: int | None = None,
        max_pages: int = 200,
        preprocessor: Callable[[bytes], bytes] | None = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        self._tesseract_cmd = tesseract_cmd
        self._lang = lang
        self._zoom = zoom
        self._page_limit = page_limit
        self._max_pages = max_pages
        self._preprocessor = preprocessor
        self._confidence_threshold = confidence_threshold

    def run(self, source: Path, *, prompt: str, preprocess: bool = False) -> OcrResult:
        """Extract text from a scanned PDF or image via Tesseract."""
        pytesseract = self._import_tesseract()
        if preprocess and self._preprocessor is None:
            logger.warning(
                "Preprocessing requested but no preprocessor registered; running un-preprocessed."
            )
            preprocess = False
        if source.suffix.lower() == ".pdf":
            return self._run_pdf(pytesseract, source, preprocess=preprocess)
        return self._run_image(pytesseract, source, preprocess=preprocess)

    def _import_tesseract(self) -> Any:
        try:
            import pytesseract  # type: ignore[import-untyped]  # noqa: E402
        except ImportError as exc:
            raise ImportError(
                "Tesseract OCR requires the 'pytesseract' package. "
                "Install with: pip install pytesseract"
            ) from exc
        if self._tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd
        return pytesseract

    def _run_image(self, pytesseract: Any, source: Path, *, preprocess: bool) -> OcrResult:
        if preprocess and self._preprocessor is not None:
            text, confidence = self._ocr_png_bytes(
                pytesseract, self._preprocessor(source.read_bytes())
            )
        else:
            text, confidence = self._ocr_path(pytesseract, source)
        return OcrResult.from_pages(
            [PageOcrResult(page_no=0, text=text, confidence=confidence)],
            confidence_threshold=self._confidence_threshold,
        )

    def _run_pdf(self, pytesseract: Any, source: Path, *, preprocess: bool) -> OcrResult:
        pages: list[PageOcrResult] = []
        for page in render_pdf_pages(
            source,
            zoom=self._zoom,
            page_limit=self._page_limit,
            max_pages=self._max_pages,
        ):
            png = page.png_bytes
            if preprocess and self._preprocessor is not None:
                png = self._preprocessor(png)
            try:
                text, confidence = self._ocr_png_bytes(pytesseract, png)
            except TesseractOcrError:
                raise  # binary missing — fatal, not a page-level degradation
            except Exception:
                logger.warning(
                    "Tesseract OCR failed on page; page left empty.",
                    extra={"page_no": page.page_no + 1},
                    exc_info=True,
                )
                text, confidence = "", None
            pages.append(PageOcrResult(page_no=page.page_no, text=text, confidence=confidence))
        return OcrResult.from_pages(pages, confidence_threshold=self._confidence_threshold)

    def _ocr_path(self, pytesseract: Any, path: Path) -> tuple[str, float | None]:
        try:
            text = pytesseract.image_to_string(str(path), lang=self._lang)
            data = pytesseract.image_to_data(
                str(path), lang=self._lang, output_type=pytesseract.Output.DICT
            )
        except pytesseract.TesseractNotFoundError as exc:
            logger.warning("Tesseract binary not found.", extra={"path": str(path)})
            raise TesseractOcrError(_TESSERACT_BINARY_MESSAGE) from exc
        return text.strip(), _mean_confidence(data)

    def _ocr_png_bytes(self, pytesseract: Any, png_bytes: bytes) -> tuple[str, float | None]:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(png_bytes)
            tmp_path = Path(tmp.name)
        try:
            return self._ocr_path(pytesseract, tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)


def _mean_confidence(data: Any) -> float | None:
    """Mean word confidence from pytesseract ``image_to_data`` output."""
    confidences: list[float] = []
    for raw in data.get("conf", []):
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            confidences.append(value)
    if not confidences:
        return None
    return sum(confidences) / len(confidences)
