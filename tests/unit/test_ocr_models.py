"""Tests for OCR result aggregation and diagnostics (P2-106)."""

from __future__ import annotations

import logging

import pytest

from app.domain.processed_document import ProcessedDocument
from app.infrastructure.document_intelligence.ocr.models import OcrResult, PageOcrResult


def _pages(*specs: tuple[int, str, float | None]) -> list[PageOcrResult]:
    return [
        PageOcrResult(page_no=page_no, text=text, confidence=confidence)
        for page_no, text, confidence in specs
    ]


class TestAggregation:
    def test_mean_confidence(self) -> None:
        result = OcrResult.from_pages(_pages((0, "a", 90.0), (1, "b", 70.0), (2, "c", None)))
        assert result.confidence == pytest.approx(80.0)
        assert result.empty_pages == []
        assert result.low_confidence_pages == []

    def test_flags_empty_and_low_confidence_pages(self) -> None:
        result = OcrResult.from_pages(
            _pages((0, "ok", 95.0), (1, "shaky", 30.0), (2, "", None)),
            confidence_threshold=50.0,
        )
        assert result.confidence == pytest.approx(62.5)
        assert result.empty_pages == [2]
        assert result.low_confidence_pages == [1]

    def test_threshold_boundary_is_not_flagged(self) -> None:
        result = OcrResult.from_pages(
            _pages((0, "borderline", 50.0)), confidence_threshold=50.0
        )
        assert result.low_confidence_pages == []

    def test_all_none_confidence_yields_none(self) -> None:
        result = OcrResult.from_pages(_pages((0, "x", None)))
        assert result.confidence is None
        assert result.low_confidence_pages == []

    def test_text_joins_non_empty_pages(self) -> None:
        result = OcrResult.from_pages(_pages((0, "first", 90.0), (1, "", None), (2, "third", 80.0)))
        assert result.text == "first\n\nthird"


class TestDiagnostics:
    def test_logs_warning_per_empty_page(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            OcrResult.from_pages(_pages((2, "", None)))
        assert "OCR page empty." in caplog.text

    def test_logs_warning_per_low_confidence_page(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            OcrResult.from_pages(_pages((1, "x", 20.0)), confidence_threshold=50.0)
        assert "OCR page low confidence." in caplog.text

    def test_no_warning_when_quality_good(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            OcrResult.from_pages(_pages((0, "good", 90.0)), confidence_threshold=50.0)
        assert "OCR page empty." not in caplog.text
        assert "OCR page low confidence." not in caplog.text


class TestProcessedDocumentOcrField:
    def test_defaults_to_none(self) -> None:
        doc = ProcessedDocument(title="t", content="c", markdown="m")
        assert doc.ocr is None

    def test_accepts_ocr_result(self) -> None:
        ocr = OcrResult.from_pages(
            [PageOcrResult(page_no=0, text="hello", confidence=80.0)]
        )
        doc = ProcessedDocument(title="t", content="c", markdown="m", ocr=ocr)
        assert doc.ocr is not None
        assert doc.ocr.text == "hello"
        assert doc.ocr.confidence == pytest.approx(80.0)
