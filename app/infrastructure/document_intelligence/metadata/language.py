"""Language detection service (P2-204).

Frozen §P2-204: ``detect_language(text) -> tuple[str, float]`` with an
optional ``py3langid`` fast path and a pure-stdlib ``_language_heuristic``
fallback (stopwords/character sets for en/fr/de/ja). Confidence below the
threshold returns ``("en", 0.0)`` (R7 mitigation). Only the first
``_MAX_TEXT_BYTES`` of input are inspected (performance ceiling).

The ``language_detection_enabled`` gate is applied at the call site by P2-205
(its frozen step 1); this module is strategy-agnostic and additive.
"""

from __future__ import annotations

import math
import re
from typing import Any, Protocol, runtime_checkable

from app.core.logging import get_logger

logger = get_logger(__name__)

# Performance ceiling: inspect only the first 10 KB (frozen §P2-204 step 5).
_MAX_TEXT_BYTES = 10_000
# ponytail: fixed default per frozen spec; make configurable only if a phase
# needs a tunable threshold.
_CONFIDENCE_THRESHOLD = 0.5
_DEFAULT_LANGUAGE = "en"

_JAPANESE_KANA = re.compile(r"[\u3040-\u30ff]")
_WORD = re.compile(r"[a-zà-öø-ÿœæ]+")

_STOPWORDS: dict[str, frozenset[str]] = {
    "en": frozenset(
        {
            "the", "and", "is", "of", "to", "in", "that", "it", "for", "was",
            "on", "are", "with", "as", "this", "not", "have", "but", "be",
            "or", "by", "from", "at", "an", "you", "your", "they",
        }
    ),
    "fr": frozenset(
        {
            "le", "la", "les", "et", "est", "de", "des", "du", "un", "une",
            "que", "qui", "dans", "pour", "pas", "avec", "sur", "ce", "cette",
            "au", "aux", "plus", "se", "son", "sa", "ne", "mais", "tout",
            "nous", "vous", "ils", "elles",
        }
    ),
    "de": frozenset(
        {
            "der", "die", "das", "und", "ist", "von", "zu", "den", "dem",
            "ein", "eine", "einer", "mit", "sich", "auf", "für", "nicht",
            "im", "auch", "an", "als", "es", "sie", "er", "wir", "ich",
            "dass", "bei", "aus", "nach",
        }
    ),
}


@runtime_checkable
class LanguageDetector(Protocol):
    """Contract implemented by language detectors (frozen §2)."""

    def detect(self, text: str) -> tuple[str, float]:
        """Return ``(language, confidence)`` for ``text``."""
        ...


def detect_language(text: str) -> tuple[str, float]:
    """Detect the language of ``text`` using only its first 10 KB.

    Delegates to the default detector (``py3langid`` when importable, else the
    stdlib heuristic). Confidence below ``_CONFIDENCE_THRESHOLD`` returns
    ``("en", 0.0)`` with a warning (R7 mitigation).
    """
    lang, confidence = get_default_language_detector().detect(text[:_MAX_TEXT_BYTES])
    if confidence < _CONFIDENCE_THRESHOLD:
        logger.warning(
            "Language detection confidence below threshold; defaulting to 'en'."
        )
        return _DEFAULT_LANGUAGE, 0.0
    return lang, confidence


def _language_heuristic(text: str) -> tuple[str, float]:
    """Pure-stdlib fallback: stopword/character-set detection (en/fr/de/ja)."""
    if _JAPANESE_KANA.search(text):
        return "ja", 0.95
    words = _WORD.findall(text.lower())
    if not words:
        return _DEFAULT_LANGUAGE, 0.0
    scores = {
        lang: sum(1 for word in words if word in stops)
        for lang, stops in _STOPWORDS.items()
    }
    best_lang = max(scores, key=scores.get)
    best = scores[best_lang]
    if best == 0:
        return _DEFAULT_LANGUAGE, 0.0
    return best_lang, best / len(words)


class _Py3LangIdDetector:
    """Default detector: py3langid when available, heuristic fallback."""

    def detect(self, text: str) -> tuple[str, float]:
        langid_module = _try_import_langid()
        if langid_module is None:
            logger.debug("py3langid not installed; using the stdlib heuristic fallback.")
            return _language_heuristic(text)
        lang, log_confidence = langid_module.classify(text)
        return str(lang), math.exp(float(log_confidence))


def _try_import_langid() -> Any | None:
    try:
        import langid  # type: ignore[import-not-found]

        return langid
    except ImportError:
        return None


_default_detector: LanguageDetector | None = None


def get_default_language_detector() -> LanguageDetector:
    """Return the process-wide default language detector, creating it lazily."""
    global _default_detector
    if _default_detector is None:
        _default_detector = _Py3LangIdDetector()
    return _default_detector


def register_language_detector(detector: LanguageDetector) -> None:
    """Replace the default language detector (public registration alias)."""
    global _default_detector
    _default_detector = detector


__all__ = [
    "LanguageDetector",
    "detect_language",
    "get_default_language_detector",
    "register_language_detector",
]
