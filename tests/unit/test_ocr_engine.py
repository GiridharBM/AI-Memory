"""Tests for the OCR engine protocol and registry (P2-101)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings, load_settings
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.document_intelligence.ocr import (
    DocumentOcrService,
    OCRSelectionError,
    PageOcrResult,
    get_default_ocr_service,
)
from app.infrastructure.document_intelligence.ocr.models import OcrResult


class _FakeEngine:
    """Minimal OcrEngine implementation for smoke-testing the protocol."""

    name = "fake"
    supported_kinds = {"scanned_pdf"}

    def __init__(self) -> None:
        self.calls: list[tuple[Path, str, bool]] = []

    def run(self, source: Path, *, prompt: str, preprocess: bool = False) -> OcrResult:
        self.calls.append((source, prompt, preprocess))
        return OcrResult(pages=[PageOcrResult(page_no=0, text=f"fake:{prompt}")])


class _ImageEngine(_FakeEngine):
    name = "image_only"
    supported_kinds = {"image"}


def _doc(*, source_type: str = "scanned_pdf", path: Path | None = None) -> SourceDocument:
    return SourceDocument(
        source=str(path or Path("scan.pdf")),
        source_path=path,
        source_type=source_type,
        filename=path.name if path else "scan.pdf",
        text="",
        metadata=DocumentMetadata(title="Scan"),
    )


class TestRegistry:
    def test_register_and_engines_snapshot(self) -> None:
        service = DocumentOcrService()
        service.register(_FakeEngine())
        service.register(_ImageEngine())
        assert [e.name for e in service.engines] == ["fake", "image_only"]

    def test_initial_engines_from_constructor(self) -> None:
        service = DocumentOcrService(engines=[_FakeEngine()])
        assert len(service.engines) == 1

    def test_empty_registry_is_deterministic(self) -> None:
        service = DocumentOcrService()
        with pytest.raises(OCRSelectionError, match="No OCR engine available"):
            service.select("scanned_pdf")


class TestSelection:
    def test_auto_selects_first_matching(self) -> None:
        service = DocumentOcrService(engines=[_FakeEngine(), _ImageEngine()])
        assert service.select("scanned_pdf").name == "fake"

    def test_auto_skips_non_matching(self) -> None:
        service = DocumentOcrService(engines=[_ImageEngine()])
        with pytest.raises(OCRSelectionError, match="scanned_pdf"):
            service.select("scanned_pdf")

    def test_explicit_engine_name(self) -> None:
        service = DocumentOcrService(engines=[_FakeEngine(), _ImageEngine()])
        assert service.select("image", engine="image_only").name == "image_only"

    def test_explicit_engine_missing_raises(self) -> None:
        service = DocumentOcrService(engines=[_FakeEngine()])
        with pytest.raises(OCRSelectionError, match="engine 'image_only'"):
            service.select("image", engine="image_only")


class TestExtract:
    def test_delegates_to_selected_engine(self, tmp_path: Path) -> None:
        path = tmp_path / "scan.pdf"
        path.write_bytes(b"%PDF-1.4")
        engine = _FakeEngine()
        service = DocumentOcrService(engines=[engine])
        result = service.extract(_doc(path=path), prompt="extract it")
        assert result.text == "fake:extract it"
        assert engine.calls == [(path, "extract it", False)]

    def test_missing_source_path_raises(self) -> None:
        service = DocumentOcrService(engines=[_FakeEngine()])
        with pytest.raises(ValueError, match="source path is missing"):
            service.extract(_doc(path=None), prompt="x")

    def test_empty_registry_extract_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "scan.pdf"
        path.write_bytes(b"%PDF-1.4")
        service = DocumentOcrService()
        with pytest.raises(OCRSelectionError):
            service.extract(_doc(path=path), prompt="x")


class TestFactory:
    def test_default_factory_registers_auto_engines(self) -> None:
        service = get_default_ocr_service(load_settings())
        assert isinstance(service, DocumentOcrService)
        assert [e.name for e in service.engines] == ["vision", "tesseract"]

    def test_disabled_returns_empty_registry(self) -> None:
        settings = load_settings()
        settings.intelligence.ocr.enabled = False
        service = get_default_ocr_service(settings)
        assert service.engines == []

    def test_engines_receive_the_shared_preprocessor(self, monkeypatch) -> None:
        """Config-gated bridge: the factory wires the bridge only when at least
        one preprocess toggle is enabled.

        When both ``ocr.preprocess`` and ``images.preprocess`` are ``False``
        (default config), engines receive ``preprocessor=None``.
        """
        import app.infrastructure.document_intelligence.ocr as ocr_pkg

        def sentinel(_: bytes) -> bytes:
            return _

        monkeypatch.setattr(ocr_pkg, "_shared_preprocessor", lambda settings: sentinel)

        # With default config (both toggles off), bridge should NOT be registered.
        settings_off = load_settings()
        assert settings_off.intelligence.ocr.preprocess is False
        assert settings_off.intelligence.images.preprocess is False
        monkeypatch.setattr(ocr_pkg, "_shared_preprocessor", lambda settings: None)
        service_off = get_default_ocr_service(settings_off)
        for engine in service_off.engines:
            assert engine._preprocessor is None

        # With at least one toggle on, bridge IS registered.
        monkeypatch.setattr(ocr_pkg, "_shared_preprocessor", lambda settings: sentinel)
        settings_on = load_settings()
        settings_on.intelligence.ocr.preprocess = True
        service_on = get_default_ocr_service(settings_on)
        assert [e.name for e in service_on.engines] == ["vision", "tesseract"]
        for engine in service_on.engines:
            assert engine._preprocessor is sentinel

    def test_vision_engine_routes_bytes_through_shared_bridge(self, tmp_path: Path) -> None:
        """AC2: preprocess=True sends engine input through the real shared bridge.

        Uses the real ``_shared_preprocessor`` with a 1-byte max_bytes cap; the
        engine must still produce a result (shared module degrades to a no-op
        on missing Pillow / oversized input) and reach the vision client.
        """
        import app.infrastructure.document_intelligence.ocr as ocr_pkg
        from app.infrastructure.document_intelligence.ocr.engines import VisionOcrEngine

        settings = _settings_with_ocr(engine="vision", preprocess=True)
        settings.intelligence.images.max_bytes = 1
        preprocessor = ocr_pkg._shared_preprocessor(settings)
        assert preprocessor is not None  # ocr.preprocess=True → bridge built

        source = tmp_path / "page.png"
        source.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 8)

        client = MagicMock()
        client.describe_image.return_value = "x"
        engine = VisionOcrEngine(client, preprocessor=preprocessor)

        result = engine.run(source, prompt="p", preprocess=True)
        assert result.pages[0].text == "x"
        assert client.describe_image.call_count == 1

def _settings_with_ocr(**overrides: object) -> Settings:
    settings = load_settings()
    for key, value in overrides.items():
        setattr(settings.intelligence.ocr, key, value)
    return settings


class TestFactorySelection:
    def test_auto_registers_vision_first_then_tesseract(self) -> None:
        service = get_default_ocr_service(_settings_with_ocr(engine="auto"))
        assert [e.name for e in service.engines] == ["vision", "tesseract"]

    def test_explicit_vision_registers_only_vision(self) -> None:
        service = get_default_ocr_service(_settings_with_ocr(engine="vision"))
        assert [e.name for e in service.engines] == ["vision"]

    def test_explicit_tesseract_registers_only_tesseract(self) -> None:
        service = get_default_ocr_service(_settings_with_ocr(engine="tesseract"))
        assert [e.name for e in service.engines] == ["tesseract"]

    def test_auto_selects_vision_for_printed_and_handwritten_kinds(self) -> None:
        service = get_default_ocr_service(_settings_with_ocr(engine="auto"))
        assert service.select("scanned_pdf").name == "vision"
        assert service.select("image").name == "vision"
        assert service.select("handwritten").name == "vision"

    def test_tesseract_only_engine_has_no_handwritten_capability(self) -> None:
        service = get_default_ocr_service(_settings_with_ocr(engine="tesseract"))
        assert service.select("scanned_pdf").name == "tesseract"
        with pytest.raises(OCRSelectionError, match="handwritten"):
            service.select("handwritten")

    def test_config_page_limits_flow_to_engines(self) -> None:
        service = get_default_ocr_service(
            _settings_with_ocr(page_limit=10, zoom=3.0, max_pages=50)
        )
        vision, tesseract = service.engines
        assert vision._page_limit == 10
        assert vision._zoom == 3.0
        assert vision._max_pages == 50
        assert tesseract._page_limit == 10
        assert tesseract._zoom == 3.0
        assert tesseract._max_pages == 50

    def test_page_limit_zero_means_all(self) -> None:
        service = get_default_ocr_service(_settings_with_ocr(page_limit=0))
        vision, _tesseract = service.engines
        assert vision._page_limit is None


# ── AC2 config-driven preprocessing bytes test ────────────────────────────────


class _SpyEngine:
    """Fake engine that applies the real bridge when ``preprocess=True``.

    Mirrors the production ``VisionOcrEngine`` behavior (apply bridge
    conditionally on the per-call flag) so the processor → extract → engine
    path is tested with real transform logic rather than a pure mock.
    """

    name = "spy"
    supported_kinds = {"image", "scanned_pdf", "handwritten"}

    def __init__(self, bridge: Callable[[bytes], bytes] | None = None) -> None:
        self._bridge = bridge
        self.seen: list[tuple[bytes, bool]] = []

    def run(self, source: Path, *, prompt: str, preprocess: bool = False) -> OcrResult:
        data = source.read_bytes()
        if preprocess and self._bridge is not None:
            data = self._bridge(data)
        self.seen.append((data, preprocess))
        return OcrResult(pages=[PageOcrResult(page_no=0, text="spy")])


class TestConfigDrivenPreprocess:
    """AC2: preprocess flag is config-driven through the production extract path.

    ``preprocess=false`` ⇒ identical bytes through ``VisionProcessor.process``;
    ``preprocess=true`` ⇒ transformed bytes (real bridge via Pillow).
    """

    @staticmethod
    def _png_bytes(tmp_path: Path) -> Path:
        """Write a small 64×64 grayscale PNG that the bridge can transform."""
        import numpy as np
        from PIL import Image as PILImage

        rng = np.random.default_rng(0)
        arr = rng.integers(0, 256, (64, 64), dtype=np.uint8)
        path = tmp_path / "scan.png"
        PILImage.fromarray(arr, mode="L").save(path)
        return path

    @staticmethod
    def _doc(path: Path) -> SourceDocument:
        return SourceDocument(
            source=str(path),
            source_path=path,
            source_type="image",
            filename=path.name,
            text="",
            metadata=DocumentMetadata(title="Scan"),
        )

    def test_preprocess_off_sends_identical_bytes(self, tmp_path: Path) -> None:
        """Default config (preprocess=False) ⇒ bytes unchanged through production path."""
        from app.infrastructure.routing.processor_impls import VisionProcessor

        source = self._png_bytes(tmp_path)
        raw = source.read_bytes()
        spy = _SpyEngine()  # no bridge — engine runs raw bytes
        service = DocumentOcrService(engines=[spy])
        doc = self._doc(source)

        # preprocess=False (default config) through the production path
        VisionProcessor(ocr_service=service, preprocess=False).process(doc)
        assert len(spy.seen) == 1
        received_bytes, flag = spy.seen[0]
        assert flag is False
        assert received_bytes == raw

    def test_preprocess_on_sends_transformed_bytes(self, tmp_path: Path) -> None:
        """Config preprocess=True ⇒ real bridge transforms bytes through production path."""
        import app.infrastructure.document_intelligence.ocr as ocr_pkg
        from app.infrastructure.routing.processor_impls import VisionProcessor

        settings = _settings_with_ocr(engine="vision", preprocess=True)
        settings.intelligence.images.preprocess = True
        bridge = ocr_pkg._shared_preprocessor(settings)
        assert bridge is not None

        source = self._png_bytes(tmp_path)
        raw = source.read_bytes()
        spy = _SpyEngine(bridge)
        service = DocumentOcrService(engines=[spy])
        doc = self._doc(source)

        # preprocess=True through the production path
        VisionProcessor(ocr_service=service, preprocess=True).process(doc)
        assert len(spy.seen) == 1
        received_bytes, flag = spy.seen[0]
        assert flag is True
        assert received_bytes != raw  # bytes actually transformed
        # Verify the transform is the real grayscale CLAHE pipeline
        import io

        from PIL import Image as PILImage
        with PILImage.open(io.BytesIO(received_bytes)) as img:
            assert img.mode == "L"
