"""Tests for language detection (P2-204)."""

from __future__ import annotations

import logging
import math
import sys
import types

import pytest

from app.infrastructure.document_intelligence.metadata import language

_LANG_LOGGER = "app.infrastructure.document_intelligence.metadata.language"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the cached default detector and drop any fake langid module."""
    monkeypatch.delitem(sys.modules, "langid", raising=False)
    monkeypatch.setattr(language, "_default_detector", None)


class TestHeuristicFallback:
    def test_detects_english(self) -> None:
        text = (
            "The dog is in the garden and it was with the cat, "
            "but the bird is on the tree."
        )
        lang, confidence = language.detect_language(text)
        assert lang == "en"
        assert confidence >= 0.5

    def test_detects_french(self) -> None:
        text = (
            "Le chat et le chien sont dans le jardin, mais les oiseaux "
            "sont dans les arbres et ils jouent avec nous."
        )
        lang, confidence = language.detect_language(text)
        assert lang == "fr"
        assert confidence >= 0.5

    def test_detects_german(self) -> None:
        text = (
            "Der Mann ist in dem Haus und er hat eine Katze, "
            "aber sie ist nicht zu Hause."
        )
        lang, confidence = language.detect_language(text)
        assert lang == "de"
        assert confidence >= 0.5

    def test_detects_japanese_kana(self) -> None:
        lang, confidence = language.detect_language(
            "今日はいい天気です。猫が庭で遊んでいます。"
        )
        assert lang == "ja"
        assert confidence == 0.95

    def test_empty_text_defaults_to_english(self) -> None:
        assert language.detect_language("") == ("en", 0.0)

    def test_whitespace_defaults_to_english(self) -> None:
        assert language.detect_language("   \n\t ") == ("en", 0.0)

    def test_no_stopwords_defaults_to_english(self) -> None:
        assert language.detect_language("xyzabc 12345") == ("en", 0.0)


class TestConfidenceThreshold:
    def test_low_confidence_returns_default_and_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        text = "the " + " ".join(["zzz"] * 20)
        with caplog.at_level(logging.WARNING, logger=_LANG_LOGGER):
            assert language.detect_language(text) == ("en", 0.0)
        assert any("below threshold" in r.getMessage() for r in caplog.records)


class TestTextSlice:
    def test_only_first_max_bytes_are_inspected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[str] = []
        fake = types.SimpleNamespace(
            classify=lambda text: seen.append(text) or ("en", 0.0)
        )
        monkeypatch.setitem(sys.modules, "langid", fake)
        language.detect_language("a" * (language._MAX_TEXT_BYTES * 3))
        assert seen == ["a" * language._MAX_TEXT_BYTES]


class TestPy3LangIdPath:
    def test_langid_verdict_used_when_importable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = types.SimpleNamespace(classify=lambda text: ("fr", -0.3))
        monkeypatch.setitem(sys.modules, "langid", fake)
        lang, confidence = language.detect_language("bonjour le monde")
        assert lang == "fr"
        assert confidence == pytest.approx(math.exp(-0.3))

    def test_missing_langid_logs_fallback_and_uses_heuristic(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger=_LANG_LOGGER):
            lang, _ = language.detect_language("The dog is in the garden.")
        assert lang == "en"
        assert any("heuristic fallback" in r.getMessage() for r in caplog.records)


class TestDetectorRegistry:
    def test_default_detector_is_lazy_singleton(self) -> None:
        assert language.get_default_language_detector() is (
            language.get_default_language_detector()
        )

    def test_register_replaces_default(self) -> None:
        stub = types.SimpleNamespace(detect=lambda text: ("de", 0.9))
        language.register_language_detector(stub)  # type: ignore[arg-type]
        assert language.detect_language("whatever") == ("de", 0.9)

    def test_module_exports(self) -> None:
        assert language.__all__ == [
            "LanguageDetector",
            "detect_language",
            "get_default_language_detector",
            "register_language_detector",
        ]
