"""OCR result models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_CONFIDENCE_THRESHOLD = 50.0  # tesseract conf scale is 0-100


class PageOcrResult(BaseModel):
    """OCR result for a single page."""

    page_no: int
    text: str
    confidence: float | None = None


class OcrResult(BaseModel):
    """Aggregated OCR result for a document."""

    pages: list[PageOcrResult] = Field(default_factory=list)
    confidence: float | None = None
    empty_pages: list[int] = Field(default_factory=list)
    low_confidence_pages: list[int] = Field(default_factory=list)

    @property
    def text(self) -> str:
        """Concatenated non-empty page text, mirroring the legacy joined output."""
        return "\n\n".join(page.text for page in self.pages if page.text)

    @classmethod
    def from_pages(
        cls,
        pages: list[PageOcrResult],
        *,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> OcrResult:
        """Aggregate per-page results and flag empty/low-confidence pages.

        Pages below ``confidence_threshold`` or with no text are flagged with a
        warning so silent OCR quality loss is observable (P2-106).
        """
        confidences = [page.confidence for page in pages if page.confidence is not None]
        empty_pages = [page.page_no for page in pages if not page.text.strip()]
        low_confidence_pages = [
            page.page_no
            for page in pages
            if page.confidence is not None and page.confidence < confidence_threshold
        ]
        for page in pages:
            if not page.text.strip():
                logger.warning("OCR page empty.", extra={"page_no": page.page_no + 1})
            elif page.confidence is not None and page.confidence < confidence_threshold:
                logger.warning(
                    "OCR page low confidence.",
                    extra={"page_no": page.page_no + 1, "confidence": page.confidence},
                )
        return cls(
            pages=pages,
            confidence=sum(confidences) / len(confidences) if confidences else None,
            empty_pages=empty_pages,
            low_confidence_pages=low_confidence_pages,
        )
