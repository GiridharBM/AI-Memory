"""Sentence tokenizer protocol, registry, and factory (G12, P3-101).

The protocol contract is D5 from the M3.1 roadmap: ``split(text)``
partitions ``text`` into a contiguous sequence of sentence spans
``s1 ... sn`` such that ``text == s1 + w1 + s2 + ... + w(n-1) + sn``,
where each ``wi`` is a (possibly empty) whitespace-only separator consumed
at the boundary. Whitespace may be normalized only at sentence boundaries;
no other transformation is applied.

This module is the P3-101 scaffold plus the P3-102 stdlib heuristic engine
and the P3-103 optional NLTK ``punkt_tab`` engine: the protocol, the engine
registry/factory, the abbreviation-aware ``_HeuristicSentenceTokenizer``
(registered unconditionally at import — it is the guaranteed ``"auto"``
fallback), and the import-guarded ``_NltkSentenceTokenizer`` (registered only
when nltk is importable and its ``punkt_tab`` data is present; one-time
setup: ``nltk.download("punkt_tab")``). The ``SemanticChunker`` resolves its
engine through ``get_sentence_tokenizer`` (P3-104); the engine selection is
configurable via ``settings.chunking.sentence_tokenizer`` (P3-105).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

try:
    from nltk.tokenize.punkt import (  # type: ignore[import-not-found, import-untyped]
        PunktTokenizer as _PunktTokenizer,
    )
except ImportError:  # pragma: no cover - exercised only when nltk is not installed
    _PunktTokenizer = None  # type: ignore[assignment, misc]

from app.core.logging import get_logger

logger = get_logger(__name__)


class SentenceTokenizerSelectionError(RuntimeError):
    """Raised when no sentence tokenizer engine is available for a selection."""


@runtime_checkable
class SentenceTokenizer(Protocol):
    """Contract implemented by every sentence tokenizer engine (D5).

    ``split`` partitions ``text`` into a contiguous sequence of sentence
    spans ``s1 ... sn`` such that ``text == s1 + w1 + s2 + ... + w(n-1) + sn``,
    where each ``wi`` is a (possibly empty) whitespace-only separator consumed
    at the boundary. Whitespace may be normalized only at sentence boundaries;
    no other transformation is applied (no intra-sentence whitespace changes,
    no stripping of sentence content, no case/Unicode changes). Empty or
    whitespace-only text yields ``[]``.
    """

    def split(self, text: str) -> list[str]:
        """Return the sentence spans of ``text``."""
        ...


_ENGINE_REGISTRY: dict[str, type[SentenceTokenizer]] = {}

_KNOWN_ENGINES = frozenset({"auto", "heuristic", "nltk"})


def register_sentence_tokenizer(name: str, engine: type[SentenceTokenizer]) -> None:
    """Register a sentence tokenizer engine under a selection name.

    Names follow D3: ``"heuristic"`` and ``"nltk"``. ``"auto"`` is resolved
    by the factory, not registered.
    """
    _ENGINE_REGISTRY[name] = engine


_SENTENCE_TERMINATORS = ".!?。！？"

_CLOSING_QUOTES = "\"'”’»」』)]"

_ABBREVIATIONS = frozenset(
    {
        # titles and honorifics
        "adm", "appt", "approx", "assn", "bros", "capt", "cmdr", "co", "col",
        "corp", "dept", "dr", "est", "ft", "gen", "gov", "hon", "inc", "jr",
        "lt", "ltd", "maj", "messrs", "mons", "mr", "mrs", "ms", "mt", "mx",
        "pres", "prof", "rep", "rev", "sen", "sgt", "sr", "st", "supt", "univ",
        # latin abbreviations
        "a.d", "a.m", "b.c", "b.c.e", "c.e", "e.g", "etc", "i.e", "p.m", "viz", "vs",
        # academic degrees
        "b.a", "d.d.s", "m.a", "m.d", "ph.d",
        # geographic / organization
        "d.c", "u.k", "u.n", "u.s", "u.s.a",
        # months
        "aug", "dec", "feb", "jan", "jul", "jun", "mar", "nov", "oct", "sep",
        "sept",
        # days
        "fri", "mon", "sat", "sun", "thu", "thur", "thurs", "tue", "tues", "wed",
    }
)


def _is_abbreviation(text: str, i: int) -> bool:
    """True when the token ending at ``text[i] == "."`` is a known abbreviation.

    The token may contain internal periods (e.g. ``"a.m"``, ``"u.s.a"``), so
    the backward scan collects both letters and periods.
    """
    j = i - 1
    while j >= 0 and (text[j].isalpha() or text[j] == "."):
        j -= 1
    return text[j + 1 : i].lower() in _ABBREVIATIONS


def _boundary_at(text: str, i: int) -> tuple[bool, int]:
    """Decide whether ``text[i]`` is a sentence boundary.

    Returns ``(is_boundary, chars_to_consume)`` where ``chars_to_consume``
    covers the terminator plus any trailing closing quotes. Separator
    whitespace is consumed by the caller, not here.
    """
    ch = text[i]
    if ch == ".":
        if (i > 0 and text[i - 1] == ".") or (i + 1 < len(text) and text[i + 1] == "."):
            return False, 0  # period inside an ellipsis run
        if i > 0 and text[i - 1].isdigit() and i + 1 < len(text) and text[i + 1].isdigit():
            return False, 0  # decimal number
        if _is_abbreviation(text, i):
            j = i + 1
            while j < len(text) and text[j].isspace():
                j += 1
            if j >= len(text):
                return True, 1  # abbreviation ends the text
            return False, 0  # never split mid-abbreviation
    consumed = 1
    j = i + 1
    while j < len(text) and text[j] in _CLOSING_QUOTES:
        consumed += 1
        j += 1
    if ch in "。！？":
        return True, consumed  # CJK terminators need no whitespace separator (D7)
    if j >= len(text):
        return True, consumed
    if text[j].isspace():
        return True, consumed
    return False, 0


class _HeuristicSentenceTokenizer:
    """Stdlib, abbreviation-aware sentence tokenizer (P3-102).

    Splits on ``.!?`` and CJK ``。！？`` terminators, consuming the following
    whitespace as the D5 boundary separator. A ``.`` is not a boundary inside
    an ellipsis, a decimal number, or a known abbreviation unless the
    abbreviation ends the text. CJK terminators are boundaries with an empty
    separator (D7). Empty or whitespace-only text yields ``[]``.
    """

    def split(self, text: str) -> list[str]:
        if not text.strip():
            return []
        spans: list[str] = []
        start = 0
        i = 0
        n = len(text)
        while i < n:
            if text[i] in _SENTENCE_TERMINATORS:
                boundary, consumed = _boundary_at(text, i)
                if boundary:
                    end = i + consumed
                    j = end
                    while j < n and text[j].isspace():
                        j += 1
                    spans.append(text[start:end])
                    start = j
                    i = j
                    continue
            i += 1
        if start < n:
            spans.append(text[start:])
        return spans


register_sentence_tokenizer("heuristic", _HeuristicSentenceTokenizer)


class _NltkSentenceTokenizer:
    """Optional NLTK ``punkt_tab`` sentence tokenizer (P3-103).

    Uses the pretrained English model from ``nltk.download("punkt_tab")``
    (one-time setup for the optional ``intelligence`` extra; nltk ships no
    bundled data). Conforms to D5: nltk spans partition the text with
    whitespace-only gaps. Empty or whitespace-only text yields ``[]``.
    """

    def __init__(self) -> None:
        assert _PunktTokenizer is not None  # registered only when available
        self._tokenizer = _PunktTokenizer("english")

    def split(self, text: str) -> list[str]:
        if not text.strip():
            return []
        return self._tokenizer.tokenize(text)


def _nltk_available() -> bool:
    """True when the NLTK engine can be constructed (nltk importable and its
    ``punkt_tab`` data present); False otherwise."""
    if _PunktTokenizer is None:
        return False
    try:
        _PunktTokenizer("english")
    except LookupError:
        return False
    return True


if _nltk_available():
    register_sentence_tokenizer("nltk", _NltkSentenceTokenizer)


def get_sentence_tokenizer(engine: str = "auto") -> SentenceTokenizer:
    """Resolve and return a sentence tokenizer engine instance.

    ``engine="auto"`` (default) prefers the NLTK engine when it is registered
    and importable; otherwise it falls back to the registered heuristic engine
    with one logged warning (D4/C-3 DoD). An explicit ``"heuristic"`` or
    ``"nltk"`` returns the registered engine of that name. An unknown engine
    value, or a known engine that is not registered, raises a clear
    ``SentenceTokenizerSelectionError``.
    """
    if engine == "auto":
        if "nltk" in _ENGINE_REGISTRY and _nltk_available():
            return _ENGINE_REGISTRY["nltk"]()
        if "heuristic" in _ENGINE_REGISTRY:
            logger.warning("NLTK sentence tokenizer unavailable; using heuristic engine.")
            return _ENGINE_REGISTRY["heuristic"]()
        raise SentenceTokenizerSelectionError(
            "No sentence tokenizer engine registered for 'auto'. "
            "Register a heuristic engine (P3-102) to enable fallback."
        )
    if engine not in _KNOWN_ENGINES:
        raise SentenceTokenizerSelectionError(
            f"Unknown sentence tokenizer engine {engine!r}. "
            "Expected one of: auto, heuristic, nltk."
        )
    engine_cls = _ENGINE_REGISTRY.get(engine)
    if engine_cls is None:
        raise SentenceTokenizerSelectionError(
            f"Sentence tokenizer engine {engine!r} is not registered."
        )
    return engine_cls()
