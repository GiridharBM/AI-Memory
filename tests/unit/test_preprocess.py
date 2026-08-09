"""Tests for the shared image preprocessing pipeline (P2-104)."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from app.infrastructure.document_intelligence.imaging import Preprocessor, preprocess_image
from app.infrastructure.document_intelligence.imaging import preprocess as mod


def _rotated_text(angle: float) -> Image.Image:
    font = ImageFont.load_default(size=40)
    base = Image.new("L", (600, 200), 255)
    draw = ImageDraw.Draw(base)
    draw.text((20, 40), "The quick brown fox jumps over the lazy dog", font=font, fill=0)
    draw.text((20, 110), "Pack my box with five dozen liquor jugs", font=font, fill=0)
    return base.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)


class TestDeskew:
    def test_estimates_five_degree_rotation(self) -> None:
        image = _rotated_text(5.0)
        assert mod.estimate_skew_angle(image) == pytest.approx(-5.0, abs=1.0)

    def test_estimates_zero_for_straight_text(self) -> None:
        assert mod.estimate_skew_angle(_rotated_text(0.0)) == pytest.approx(0.0, abs=1.0)


class TestDenoise:
    def test_reduces_impulse_noise(self) -> None:
        clean = np.full((64, 64), 128, dtype=np.uint8)
        noisy = clean.copy()
        noisy[::6, ::6] = 0
        denoised = np.asarray(mod._denoise(Image.fromarray(noisy, mode="L")), dtype=np.uint8)
        assert (denoised == 0).mean() < (noisy == 0).mean()
        assert (denoised == 128).mean() > (noisy == 128).mean()


class TestClahe:
    def test_expands_low_contrast(self) -> None:
        rng = np.random.default_rng(0)
        arr = (100 + 10 * rng.random((128, 128))).astype(np.uint8)
        out = mod._clahe(arr)
        assert out.max() - out.min() > 50
        assert float(out.std()) > float(arr.std())

    def test_preserves_shape(self) -> None:
        arr = np.random.default_rng(1).integers(0, 256, size=(50, 37), dtype=np.uint8)
        assert mod._clahe(arr).shape == arr.shape


class TestPreprocessImage:
    def test_pipeline_returns_temp_processed_path(self, tmp_path: Path) -> None:
        src = tmp_path / "scan.png"
        rng = np.random.default_rng(1)
        arr = (100 + 15 * rng.random((64, 64))).astype(np.uint8)
        Image.fromarray(arr, mode="L").save(src)
        out = preprocess_image(src)
        try:
            assert out != src
            assert out.suffix == ".png"
            assert out.exists()
            with Image.open(out) as img:
                assert img.size == (64, 64)
                assert np.asarray(img).std() > float(arr.std())
        finally:
            out.unlink(missing_ok=True)

    def test_corrupt_file_returns_original(self, tmp_path: Path) -> None:
        src = tmp_path / "corrupt.png"
        src.write_bytes(b"not an image")
        assert preprocess_image(src) == src

    def test_missing_dependencies_skip_with_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        src = tmp_path / "scan.png"
        Image.new("L", (16, 16), 128).save(src)
        monkeypatch.setattr(mod, "_DEPENDENCIES_AVAILABLE", False)
        with caplog.at_level(logging.WARNING):
            assert preprocess_image(src) == src
        assert "skipping image preprocessing" in caplog.text

    def test_oversized_image_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        src = tmp_path / "big.png"
        Image.new("L", (64, 64), 128).save(src)
        monkeypatch.setattr(mod, "MAX_EDGE", 32)
        with caplog.at_level(logging.WARNING):
            assert preprocess_image(src) == src
        assert "dimension guard" in caplog.text

    def test_transform_error_returns_original(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        src = tmp_path / "scan.png"
        Image.new("L", (16, 16), 128).save(src)

        def boom(image: Image.Image) -> Image.Image:
            raise RuntimeError("boom")

        monkeypatch.setattr(mod, "_apply_transforms", boom)
        with caplog.at_level(logging.WARNING):
            assert preprocess_image(src) == src
        assert "returning original" in caplog.text


class TestPreprocessor:
    def test_disabled_returns_original(self, tmp_path: Path) -> None:
        src = tmp_path / "scan.png"
        Image.new("L", (16, 16), 128).save(src)
        assert Preprocessor().process(src) == src

    def test_enabled_returns_processed(self, tmp_path: Path) -> None:
        src = tmp_path / "scan.png"
        Image.new("L", (16, 16), 128).save(src)
        out = Preprocessor(enabled=True).process(src)
        try:
            assert out != src
            assert out.exists()
        finally:
            out.unlink(missing_ok=True)
