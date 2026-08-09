"""Integration tests for Milestone 2.5 image intelligence (P2-502, P2-506).

Frozen spec §13 integration row: a real photo fixture through
``IngestionWorkflow`` with a mocked vision engine, asserting the ``image_info``
payload lands on the document and the vision prompt reaches the engine; a
multi-image PDF asserting per-image page provenance in ``extra["images"]``.
Marked integration so Tesseract-free environments are unaffected.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.application import AIProcessingResult
from app.core.config import Settings
from app.domain.analysis import DocumentAnalysis
from app.domain.documents import SourceDocument
from app.infrastructure.document_intelligence.ocr.models import OcrResult, PageOcrResult
from app.infrastructure.ingestion import DocumentIngestionService
from app.infrastructure.vault import VaultWriter
from app.pipelines import IngestionWorkflow
from app.templates import ObsidianMarkdownGenerator

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "images"

EXPECTED_VISION_PROMPT = (
    "Analyze this image. If it contains handwritten text, transcribe "
    "all handwritten text accurately. If it contains printed text or "
    "digital content, extract all visible text. Return only the "
    "extracted text, nothing else."
)


class _RecordingProcessor:
    """Fake AI processor used to exercise the real pipeline without Ollama."""

    def __init__(self) -> None:
        self.documents: list[SourceDocument] = []

    def process(self, document: SourceDocument) -> AIProcessingResult:
        self.documents.append(document)
        return AIProcessingResult(
            document=document,
            analysis=_analysis(),
            attempts=1,
        )


def _workflow(settings: Settings, tmp_path: Path, *, ocr_service: object) -> IngestionWorkflow:
    return IngestionWorkflow(
        ingestion_service=DocumentIngestionService(settings=settings),
        processor=_RecordingProcessor(),
        ocr_service=ocr_service,
        note_generator=ObsidianMarkdownGenerator(),
        writer=VaultWriter(tmp_path / "vault"),
        settings=settings,
    )


@pytest.mark.integration
def test_photo_through_workflow_attaches_image_info_and_vision_prompt(
    tmp_settings: Settings, tmp_path: Path,
) -> None:
    service = MagicMock()
    service.extract.return_value = OcrResult(
        pages=[PageOcrResult(page_no=0, text="Extracted from mock vision")]
    )
    workflow = _workflow(tmp_settings, tmp_path, ocr_service=service)

    result = workflow.run(FIXTURES / "photo.png", expected_source_type="image")

    assert result.document.source_type == "image"
    info = result.document.metadata.extra["image_info"]
    assert info["format"] == "PNG"
    assert info["width"] == 200
    assert info["height"] == 120
    assert info["exif"]["decoded"]["Make"] == "PAM Test Camera"
    assert service.extract.call_count == 1
    args = service.extract.call_args
    assert args.args[0].source == str(FIXTURES / "photo.png")
    assert args.kwargs["prompt"] == EXPECTED_VISION_PROMPT


@pytest.mark.integration
def test_photo_without_vision_passthrough_keeps_image_info(
    tmp_settings: Settings, tmp_path: Path,
) -> None:
    tmp_settings.intelligence.ocr.enabled = False
    workflow = _workflow(tmp_settings, tmp_path, ocr_service=None)

    result = workflow.run(FIXTURES / "photo.png", expected_source_type="image")

    assert result.document.metadata.extra["image_info"]["format"] == "PNG"
    assert result.document.text == ""


@pytest.mark.integration
def test_pdf_with_embedded_image_attaches_page_provenance(
    tmp_settings: Settings, tmp_path: Path,
) -> None:
    import fitz

    pdf = tmp_path / "with_image.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(page.rect, filename=str(FIXTURES / "photo.png"))
    page.insert_text((72, 72), "a text-bearing pdf with an embedded image")
    doc.save(str(pdf))
    doc.close()

    workflow = _workflow(tmp_settings, tmp_path, ocr_service=None)
    result = workflow.run(pdf, expected_source_type="pdf")

    images = result.document.metadata.extra["images"]
    assert [img["page_no"] for img in images] == [1]
    assert [img["index"] for img in images] == [0]
    assert all(img["format"] == "PNG" for img in images)
    assert all(img["width"] > 0 for img in images)


@pytest.mark.integration
def test_text_only_pdf_has_no_images_key(tmp_settings: Settings, tmp_path: Path) -> None:
    import fitz

    pdf = tmp_path / "text.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "plain text pdf")
    doc.save(str(pdf))
    doc.close()

    workflow = _workflow(tmp_settings, tmp_path, ocr_service=None)
    result = workflow.run(pdf, expected_source_type="pdf")

    assert "images" not in result.document.metadata.extra


def _analysis() -> DocumentAnalysis:
    return DocumentAnalysis.model_validate(
        {
            "suggested_note_title": "Image Note",
            "summary": {"short": "s", "detailed": "d"},
            "key_concepts": [],
            "definitions": [],
            "important_entities": [],
            "tags": ["image"],
            "related_topics": [],
        }
    )
