"""Tests for model routing settings and processor selection."""

from __future__ import annotations

from app.core.config import ModelRoutingSettings


class TestModelRoutingSettings:
    def test_default_models(self) -> None:
        settings = ModelRoutingSettings()
        assert settings.general_text == "qwen3:8b"
        assert settings.programming == "qwen2.5-coder:7b"
        assert settings.vision == "qwen2.5vl:latest"
        assert settings.audio == "faster-whisper"
        assert settings.embeddings == "nomic-embed-text"

    def test_model_for_general_text(self) -> None:
        settings = ModelRoutingSettings()
        assert settings.model_for("general_text") == "qwen3:8b"

    def test_model_for_programming(self) -> None:
        settings = ModelRoutingSettings()
        assert settings.model_for("programming") == "qwen2.5-coder:7b"

    def test_model_for_vision(self) -> None:
        settings = ModelRoutingSettings()
        assert settings.model_for("vision") == "qwen2.5vl:latest"

    def test_model_for_unknown_falls_back(self) -> None:
        settings = ModelRoutingSettings()
        assert settings.model_for("nonexistent_key") == "qwen3:8b"

    def test_custom_models(self) -> None:
        settings = ModelRoutingSettings(
            general_text="llama3.1:8b",
            programming="deepseek-coder:6.7b",
        )
        assert settings.general_text == "llama3.1:8b"
        assert settings.programming == "deepseek-coder:6.7b"
        assert settings.vision == "qwen2.5vl:latest"  # unchanged
