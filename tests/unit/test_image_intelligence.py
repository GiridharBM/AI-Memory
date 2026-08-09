"""Unit tests for image intelligence (Milestone 2.5): P2-501..P2-506.

EXIF fixture, preprocess toggles, drawio→Mermaid, prompt templating, and
multi-image provenance (frozen spec §8).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from PIL import Image
from pydantic import ValidationError

from app.core.config import Settings
from app.domain.document_intelligence import ImageExif, ImageInfo
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.document_intelligence.images import (
    DiagramParser,
    MultiImageExtractor,
    Preprocessor,
    analyze_image,
    drawio_to_mermaid,
    get_default_multi_image_extractor,
    preprocess_image,
)
from app.infrastructure.document_intelligence.images.metadata import ImageAnalyzer
from app.infrastructure.ingestion import DocumentIngestionService
from app.infrastructure.routing.processor_impls import (
    DiagramProcessor,
    HandwritingProcessor,
    OCRProcessor,
    VisionProcessor,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "images"

DRAWIO_XML = (
    "<mxfile><diagram name=\"Architecture\">\n"
    "<mxGraphModel><root>\n"
    '<mxCell id="1" value="Web Server" style="rounded=1" vertex="1"/>\n'
    '<mxCell id="2" value="Database" style="shape=cylinder" vertex="1"/>\n'
    '<mxCell id="3" value="" style="edgeStyle=orthogonal" edge="1" source="1" target="2"/>\n'
    "</root></mxGraphModel></diagram></mxfile>"
)


def _document(
    *,
    source: str = "doc",
    source_type: str = "pdf",
    source_path: Path | None = None,
    text: str = "",
    filename: str = "doc",
) -> SourceDocument:
    return SourceDocument(
        source=source,
        source_path=source_path,
        source_type=source_type,
        filename=filename,
        text=text,
        metadata=DocumentMetadata(title="Doc"),
    )


def _workflow(settings: Settings | None = None):
    from app.pipelines.ingest_workflow import IngestionWorkflow

    return IngestionWorkflow(
        ingestion_service=MagicMock(),
        ollama_client=MagicMock(),
        note_generator=MagicMock(),
        writer=MagicMock(),
        settings=settings,
    )


class TestImageInfoModel:
    def test_round_trips_through_json(self) -> None:
        info = ImageInfo(
            path="a.png",
            format="PNG",
            width=200,
            height=120,
            size_bytes=506,
            mode="RGB",
            page_no=1,
            index=0,
            exif=ImageExif(raw={271: "PAM"}, decoded={"Make": "PAM"}),
        )
        restored = ImageInfo.model_validate(info.model_dump(mode="json"))
        assert restored == info

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ImageInfo.model_validate(
                {"path": "a.png", "format": "PNG", "confidence": 0.9}
            )

    def test_defaults(self) -> None:
        info = ImageInfo(path="a.png", format="PNG", width=0, height=0, size_bytes=0)
        assert info.mode == ""
        assert info.page_no is None
        assert info.index == 0
        assert info.exif.raw == {}


class TestImageAnalyzer:
    def test_dimensions_format_and_size(self) -> None:
        info = analyze_image(FIXTURES / "plain.png")
        assert info.format == "PNG"
        assert info.width == 80
        assert info.height == 60
        assert info.mode == "RGB"
        assert info.size_bytes > 0
        assert info.path == str((FIXTURES / "plain.png").resolve())

    def test_exif_tags_decoded(self) -> None:
        info = analyze_image(FIXTURES / "photo.png")
        assert info.exif.decoded["Make"] == "PAM Test Camera"
        assert info.exif.decoded["Model"] == "Fixture Model"
        assert 271 in info.exif.raw

    def test_include_exif_false_skips_read(self) -> None:
        info = analyze_image(FIXTURES / "photo.png", include_exif=False)
        assert info.exif.raw == {}
        assert info.width == 200

    def test_corrupt_image_degrades_to_file_level_info(self, tmp_path: Path) -> None:
        corrupt = tmp_path / "corrupt.png"
        corrupt.write_bytes(b"not an image")
        info = analyze_image(corrupt)
        assert info.format == "PNG"
        assert info.width == 0
        assert info.height == 0
        assert info.size_bytes == len(b"not an image")
        assert info.exif.raw == {}

    def test_svg_gets_no_exif(self, tmp_path: Path) -> None:
        svg = tmp_path / "diagram.svg"
        svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
        info = analyze_image(svg)
        assert info.format == "SVG"
        assert info.exif.raw == {}

    def test_missing_file_reports_zero_size(self, tmp_path: Path) -> None:
        info = analyze_image(tmp_path / "missing.png")
        assert info.size_bytes == 0

    def test_injected_analyzer_is_used(self) -> None:
        fake = MagicMock(spec=ImageAnalyzer)
        fake.analyze.return_value = ImageInfo(
            path="x", format="PNG", width=1, height=1, size_bytes=1
        )
        analyze_image(FIXTURES / "plain.png", analyzer=fake)
        fake.analyze.assert_called_once()


class TestImageIngestor:
    def test_attaches_image_info(self) -> None:
        result = DocumentIngestionService().ingest(FIXTURES / "photo.png")
        assert result.succeeded and result.document is not None
        info = result.document.metadata.extra["image_info"]
        assert info["format"] == "PNG"
        assert info["width"] == 200
        assert info["height"] == 120

    def test_disabled_leaves_document_phase1_identical(
        self, tmp_settings: Settings,
    ) -> None:
        tmp_settings.intelligence.images.exif_enabled = False
        service = DocumentIngestionService(settings=tmp_settings)
        result = service.ingest(FIXTURES / "photo.png")
        assert result.succeeded and result.document is not None
        assert "image_info" not in result.document.metadata.extra

    def test_unsupported_extension_still_matches_mime(self, tmp_path: Path) -> None:
        unknown = tmp_path / "data.avif"
        unknown.write_bytes(b"unknown")
        result = DocumentIngestionService().ingest(unknown)
        assert not result.succeeded


class TestMultiImageExtractor:
    def test_per_image_page_provenance(self) -> None:
        images = MultiImageExtractor().extract(FIXTURES / "multi_image.pdf")
        assert [img.page_no for img in images] == [1, 2]
        assert [img.index for img in images] == [0, 1]
        assert all(img.format == "PNG" for img in images)
        assert all(img.width > 0 and img.height > 0 for img in images)
        assert all(img.size_bytes > 0 for img in images)

    def test_corrupt_pdf_returns_empty_and_releases_handle(self, tmp_path: Path) -> None:
        corrupt = tmp_path / "corrupt.pdf"
        corrupt.write_bytes(b"%PDF fake")
        assert MultiImageExtractor().extract(corrupt) == []
        shutil.move(str(corrupt), str(tmp_path / "moved.pdf"))

    def test_text_only_pdf_returns_empty(self, tmp_path: Path) -> None:
        import fitz

        pdf = tmp_path / "text.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "no images here")
        doc.save(str(pdf))
        doc.close()
        assert MultiImageExtractor().extract(pdf) == []

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert MultiImageExtractor().extract(tmp_path / "nope.pdf") == []

    def test_default_factory(self) -> None:
        assert isinstance(get_default_multi_image_extractor(), MultiImageExtractor)


class TestPreprocessGuards:
    def test_max_dimensions_override_skips(self, tmp_path: Path) -> None:
        src = tmp_path / "big.png"
        Image.new("L", (64, 64), 128).save(src)
        assert preprocess_image(src, max_dimensions=32) == src

    def test_max_bytes_override_skips(self, tmp_path: Path) -> None:
        src = tmp_path / "big.png"
        Image.new("L", (64, 64), 128).save(src)
        assert preprocess_image(src, max_bytes=1) == src

    def test_preprocessor_passes_config_guards(self, tmp_path: Path) -> None:
        src = tmp_path / "big.png"
        Image.new("L", (64, 64), 128).save(src)
        pre = Preprocessor(enabled=True, max_dimensions=32)
        assert pre.process(src) == src

    def test_undersize_still_preprocesses(self, tmp_path: Path) -> None:
        src = tmp_path / "small.png"
        Image.new("L", (16, 16), 128).save(src)
        pre = Preprocessor(enabled=True, max_dimensions=8000)
        result = pre.process(src)
        try:
            assert result != src
            assert result.exists()
        finally:
            result.unlink(missing_ok=True)


class TestDiagramParser:
    def test_drawio_converts_to_mermaid(self) -> None:
        mermaid = drawio_to_mermaid(DRAWIO_XML)
        assert mermaid.startswith("flowchart LR")
        assert 'n_1["Web Server"]' in mermaid
        assert 'n_2["Database"]' in mermaid
        assert "n_1 --> n_2" in mermaid

    def test_edge_label_annotated(self) -> None:
        xml = (
            "<mxfile><mxGraphModel><root>"
            '<mxCell id="a1" value="A" vertex="1"/>'
            '<mxCell id="b1" value="B" vertex="1"/>'
            '<mxCell id="e1" value="calls" edge="1" source="a1" target="b1"/>'
            "</root></mxGraphModel></mxfile>"
        )
        mermaid = drawio_to_mermaid(xml)
        assert 'a1["A"]' in mermaid
        assert 'b1["B"]' in mermaid
        assert 'a1 -->|"calls"| b1' in mermaid

    def test_unparseable_returns_empty(self) -> None:
        assert drawio_to_mermaid("<not xml") == ""

    def test_no_labels_returns_empty(self) -> None:
        xml = (
            "<mxfile><mxGraphModel><root>"
            '<mxCell id="1" style="rounded=1" vertex="1"/>'
            "</root></mxGraphModel></mxfile>"
        )
        assert drawio_to_mermaid(xml) == ""

    def test_unsupported_suffix_returns_empty(self, tmp_path: Path) -> None:
        vsdx = tmp_path / "plan.vsdx"
        vsdx.write_text("{}", encoding="utf-8")
        assert DiagramParser().parse(vsdx) == ""

    def test_parse_reads_drawio_file(self, tmp_path: Path) -> None:
        path = tmp_path / "arch.drawio"
        path.write_text(DRAWIO_XML, encoding="utf-8")
        mermaid = DiagramParser().parse(path)
        assert mermaid.startswith("flowchart LR")


class TestDiagramProcessor:
    def test_enabled_produces_mermaid_note(self, tmp_path: Path) -> None:
        path = tmp_path / "arch.drawio"
        path.write_text(DRAWIO_XML, encoding="utf-8")
        doc = _document(
            source=str(path),
            source_type="diagram",
            source_path=path,
            text="raw labels",
            filename="arch.drawio",
        )
        result = DiagramProcessor().process(doc)
        assert result.extracted_text.startswith("flowchart LR")
        assert result.metadata["mermaid"] is True
        assert "```mermaid" in result.markdown

    def test_disabled_passthrough(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.infrastructure.routing.processor_impls as impls

        monkeypatch.setattr(impls, "_diagram_enabled", lambda: False)
        doc = _document(source_type="diagram", text="raw labels")
        result = DiagramProcessor().process(doc)
        assert result.extracted_text == "raw labels"
        assert "mermaid" not in result.metadata

    def test_unparseable_file_falls_back_to_raw(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.drawio"
        path.write_text("not xml", encoding="utf-8")
        doc = _document(
            source=str(path), source_type="diagram", source_path=path,
            text="raw", filename="broken.drawio",
        )
        result = DiagramProcessor().process(doc)
        assert result.extracted_text == "raw"


class TestProcessorLanguageWiring:
    def _mock_service(self):
        from app.infrastructure.document_intelligence.ocr.models import OcrResult

        service = MagicMock()
        service.extract.return_value = OcrResult(pages=[])
        return service

    def _doc(self, source_type: str, suffix: str, tmp_path: Path) -> SourceDocument:
        path = tmp_path / f"file{suffix}"
        path.write_bytes(b"fake")
        return _document(
            source=str(path), source_type=source_type, source_path=path,
            filename=f"file{suffix}", text="",
        )

    def test_vision_substitutes_language_into_prompt(self, tmp_path: Path) -> None:
        service = self._mock_service()
        doc = self._doc("image", ".png", tmp_path)
        proc = VisionProcessor(
            ocr_service=service, prompt="Extract. Respond in {language}.", language="fr"
        )
        proc.process(doc)
        service.extract.assert_called_once_with(
            doc, prompt="Extract. Respond in fr.", preprocess=False
        )

    def test_ocr_substitutes_language_into_prompt(self, tmp_path: Path) -> None:
        service = self._mock_service()
        doc = self._doc("scanned_pdf", ".pdf", tmp_path)
        proc = OCRProcessor(
            ocr_service=service, prompt="Extract. Respond in {language}.", language="de"
        )
        proc.process(doc)
        service.extract.assert_called_once_with(
            doc, prompt="Extract. Respond in de.", preprocess=False
        )

    def test_handwriting_substitutes_language_into_prompt(self, tmp_path: Path) -> None:
        service = self._mock_service()
        doc = self._doc("handwritten", ".png", tmp_path)
        proc = HandwritingProcessor(
            ocr_service=service, prompt="Extract. Respond in {language}.", language="ja"
        )
        proc.process(doc)
        service.extract.assert_called_once_with(
            doc, prompt="Extract. Respond in ja.", preprocess=False
        )

    def test_workflow_passes_language_into_constructors(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import app.infrastructure.routing.processor_impls as impls
        from app.domain.processed_document import ProcessedDocument

        captured: dict[str, object] = {}

        class _SpyVision:
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)

            def process(self, document: SourceDocument) -> ProcessedDocument:
                return ProcessedDocument(title="t", content="c", markdown="m")

        monkeypatch.setattr(impls, "VisionProcessor", _SpyVision)
        wf = _workflow()
        wf._run_routed_processor("VisionProcessor", _document(), language="fr")
        assert captured["language"] == "fr"


class TestWorkflowEnrichImages:
    def test_pdf_with_images_attaches_page_provenance(self) -> None:
        doc = _document(
            source=str(FIXTURES / "multi_image.pdf"),
            source_path=FIXTURES / "multi_image.pdf",
            source_type="pdf",
            text="",
            filename="multi_image.pdf",
        )
        images = _workflow()._enrich_images(doc, "pdf")
        assert images is not None
        assert [img["page_no"] for img in images] == [1, 2]
        assert images[0]["format"] == "PNG"
        assert images[0]["index"] == 0

    def test_non_pdf_kind_returns_none(self) -> None:
        doc = _document(source_type="csv", text="a,b\n")
        assert _workflow()._enrich_images(doc, "csv") is None

    def test_missing_source_path_returns_none(self) -> None:
        doc = _document(source_type="pdf", source_path=None)
        assert _workflow()._enrich_images(doc, "pdf") is None

    def test_text_pdf_returns_none(self, tmp_path: Path) -> None:
        import fitz

        pdf = tmp_path / "text.pdf"
        doc_ = fitz.open()
        page = doc_.new_page()
        page.insert_text((72, 72), "no images")
        doc_.save(str(pdf))
        doc_.close()
        doc = _document(
            source=str(pdf), source_path=pdf, source_type="pdf", filename="text.pdf",
        )
        assert _workflow()._enrich_images(doc, "pdf") is None

    def test_extractor_failure_contained(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.infrastructure.document_intelligence.images as images

        def _boom(_: Path) -> list[Any]:
            raise RuntimeError("boom")

        monkeypatch.setattr(
            images, "get_default_multi_image_extractor",
            lambda: type("Boom", (), {"extract": _boom})(),
        )
        doc = _document(
            source=str(FIXTURES / "multi_image.pdf"),
            source_path=FIXTURES / "multi_image.pdf",
            source_type="pdf",
            filename="multi_image.pdf",
        )
        assert _workflow()._enrich_images(doc, "pdf") is None

