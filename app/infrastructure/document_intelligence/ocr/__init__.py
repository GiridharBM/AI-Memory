"""OCR engine package — public API surface."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from app.core.config import Settings
from app.core.logging import get_logger
from app.infrastructure.document_intelligence.ocr.base import (
    DocumentOcrService,
    OcrEngine,
    OCRSelectionError,
)
from app.infrastructure.document_intelligence.ocr.models import OcrResult, PageOcrResult

__all__ = [
    "DocumentOcrService",
    "OCRSelectionError",
    "OcrEngine",
    "OcrResult",
    "PageOcrResult",
    "get_default_ocr_service",
]

logger = get_logger(__name__)


def _shared_preprocessor(settings: Settings) -> Callable[[bytes], bytes] | None:
    """Bridge the shared path-based ``Preprocessor`` to the engines' bytes contract.

    Both preprocess toggles (``ocr.preprocess`` and ``images.preprocess``) run
    through this one shared ``imaging/preprocess.py`` implementation (R-a): the
    engine applies it per call based on the ``preprocess`` flag it receives.
    Dimension/size guards come from ``intelligence.images.*`` (P2-503 single
    source of truth, frozen §4.5).  Returns ``None`` when neither toggle is
    enabled — engines then receive no preprocessor and the bridge is never
    invoked regardless of the per-call ``preprocess`` flag.  Degrades to
    bytes-unchanged when Pillow/numpy are absent, the image is oversized, or
    the transform fails.
    """
    images = settings.intelligence.images
    cfg = settings.intelligence.ocr
    if not (cfg.preprocess or images.preprocess):
        return None

    from app.infrastructure.document_intelligence.imaging import Preprocessor

    pre = Preprocessor(
        enabled=True,
        max_dimensions=images.max_dimensions,
        max_bytes=images.max_bytes,
    )

    def run(data: bytes) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        out = pre.process(tmp_path)
        try:
            if out == tmp_path:
                return data
            return out.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)
            if out != tmp_path:
                out.unlink(missing_ok=True)

    return run


def get_default_ocr_service(settings: Settings) -> DocumentOcrService:
    """Build the OCR service from ``intelligence.ocr`` config (P2-108).

    ``enabled: false`` returns an empty registry (no OCR). ``engine="auto"``
    registers the vision engine first, then Tesseract, so ``select`` picks
    vision as primary and falls back to Tesseract for printed text. Explicit
    ``engine="vision"`` / ``"tesseract"`` register only that engine. The
    configured ``page_limit`` (0 = all) and ``max_pages`` cap flow through to
    both engines.
    """
    cfg = settings.intelligence.ocr
    if not cfg.enabled:
        return DocumentOcrService()

    preprocessor = _shared_preprocessor(settings)
    page_limit = cfg.page_limit or None  # 0 means "no limit"
    engines: list[OcrEngine] = []
    if cfg.engine in ("auto", "vision"):
        vision_engine = _build_vision_engine(
            settings, page_limit=page_limit, preprocessor=preprocessor
        )
        if vision_engine is not None:
            engines.append(vision_engine)
    if cfg.engine in ("auto", "tesseract"):
        engines.append(
            _build_tesseract_engine(settings, page_limit=page_limit, preprocessor=preprocessor)
        )
    return DocumentOcrService(engines=engines)


def _build_vision_engine(
    settings: Settings, *, page_limit: int | None, preprocessor: Callable[[bytes], bytes] | None,
) -> OcrEngine | None:
    from app.infrastructure.document_intelligence.ocr.engines import VisionOcrEngine
    from app.infrastructure.llm.vision_client import OllamaVisionClient

    cfg = settings.intelligence.ocr
    try:
        vision_client = OllamaVisionClient(
            settings.ollama, vision_model=settings.models.vision,
        )
    except Exception:
        logger.warning(
            "Vision client unavailable; OCR will fall back to Tesseract "
            "(or fail for vision-required kinds)."
        )
        return None
    return VisionOcrEngine(
        vision_client,
        zoom=cfg.zoom,
        page_limit=page_limit,
        max_pages=cfg.max_pages,
        preprocessor=preprocessor,
    )


def _build_tesseract_engine(
    settings: Settings, *, page_limit: int | None, preprocessor: Callable[[bytes], bytes] | None,
) -> OcrEngine:
    from app.infrastructure.document_intelligence.ocr.engines import TesseractOcrEngine

    cfg = settings.intelligence.ocr
    return TesseractOcrEngine(
        tesseract_cmd=cfg.tesseract_cmd,
        lang=cfg.tesseract_lang,
        zoom=cfg.zoom,
        page_limit=page_limit,
        max_pages=cfg.max_pages,
        confidence_threshold=cfg.confidence_threshold,
        preprocessor=preprocessor,
    )
