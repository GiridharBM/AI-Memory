"""Tests for the sentence tokenizer protocol, registry, and factory (P3-101)."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pytest

import app.infrastructure.sentence_tokenizer as tokenizer_mod
from app.infrastructure.sentence_tokenizer import (
    SentenceTokenizer,
    SentenceTokenizerSelectionError,
    _HeuristicSentenceTokenizer,
    _NltkSentenceTokenizer,
    get_sentence_tokenizer,
    register_sentence_tokenizer,
)


class _FakeHeuristic:
    """Minimal SentenceTokenizer fake used to smoke-test the protocol."""

    def split(self, text: str) -> list[str]:
        if not text.strip():
            return []
        return [text]


class _FakeNltk:
    """Fake NLTK-backed engine used to exercise auto resolution."""

    def split(self, text: str) -> list[str]:
        if not text.strip():
            return []
        return [text]


@pytest.fixture(autouse=True)
def _isolated_registry() -> None:
    """Snapshot and restore the module-level engine registry per test."""
    saved = dict(tokenizer_mod._ENGINE_REGISTRY)
    tokenizer_mod._ENGINE_REGISTRY.clear()
    yield
    tokenizer_mod._ENGINE_REGISTRY.clear()
    tokenizer_mod._ENGINE_REGISTRY.update(saved)


class TestRegistry:
    def test_register_engine_by_name(self) -> None:
        register_sentence_tokenizer("heuristic", _FakeHeuristic)
        assert "heuristic" in tokenizer_mod._ENGINE_REGISTRY

    def test_register_overwrites_previous(self) -> None:
        register_sentence_tokenizer("heuristic", _FakeHeuristic)
        register_sentence_tokenizer("heuristic", _FakeNltk)
        assert tokenizer_mod._ENGINE_REGISTRY["heuristic"] is _FakeNltk


class TestFactorySelection:
    def test_explicit_heuristic(self) -> None:
        register_sentence_tokenizer("heuristic", _FakeHeuristic)
        assert get_sentence_tokenizer("heuristic").split("Hi there.") == ["Hi there."]

    def test_explicit_nltk(self) -> None:
        register_sentence_tokenizer("nltk", _FakeNltk)
        assert isinstance(get_sentence_tokenizer("nltk"), _FakeNltk)

    def test_unknown_engine_value_raises_clear_error(self) -> None:
        with pytest.raises(SentenceTokenizerSelectionError, match="Unknown sentence tokenizer"):
            get_sentence_tokenizer("regex")

    def test_known_but_unregistered_raises(self) -> None:
        with pytest.raises(SentenceTokenizerSelectionError, match="'heuristic' is not registered"):
            get_sentence_tokenizer("heuristic")

    def test_empty_registry_auto_raises_clear_error(self) -> None:
        with pytest.raises(SentenceTokenizerSelectionError, match="No sentence tokenizer engine"):
            get_sentence_tokenizer("auto")

    def test_selection_is_stable_per_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        register_sentence_tokenizer("heuristic", _FakeHeuristic)
        register_sentence_tokenizer("nltk", _FakeNltk)
        monkeypatch.setattr(tokenizer_mod, "_nltk_available", lambda: False)
        assert isinstance(get_sentence_tokenizer("auto"), _FakeHeuristic)
        assert isinstance(get_sentence_tokenizer("auto"), _FakeHeuristic)


class TestAutoResolution:
    def test_auto_prefers_nltk_when_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        register_sentence_tokenizer("heuristic", _FakeHeuristic)
        register_sentence_tokenizer("nltk", _FakeNltk)
        monkeypatch.setattr(tokenizer_mod, "_nltk_available", lambda: True)
        assert isinstance(get_sentence_tokenizer("auto"), _FakeNltk)

    def test_auto_falls_back_to_heuristic_with_one_warning_when_nltk_absent(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        register_sentence_tokenizer("heuristic", _FakeHeuristic)
        register_sentence_tokenizer("nltk", _FakeNltk)
        monkeypatch.setattr(tokenizer_mod, "_nltk_available", lambda: False)
        with caplog.at_level(logging.WARNING, logger="app.infrastructure.sentence_tokenizer"):
            engine = get_sentence_tokenizer("auto")
        assert isinstance(engine, _FakeHeuristic)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "heuristic" in warnings[0].message


class TestProtocolConformance:
    def test_runtime_checkable(self) -> None:
        register_sentence_tokenizer("heuristic", _FakeHeuristic)
        engine = get_sentence_tokenizer("heuristic")
        assert isinstance(engine, SentenceTokenizer)

    def test_empty_and_whitespace_text_yield_empty_list(self) -> None:
        """D5 contract expectation locked at the protocol surface."""
        register_sentence_tokenizer("heuristic", _FakeHeuristic)
        engine = get_sentence_tokenizer("heuristic")
        assert engine.split("") == []
        assert engine.split("   \n\t  ") == []


def _assert_d5_reconstruction(text: str, spans: list[str]) -> None:
    """Assert spans reconstruct the source with whitespace-only separators (D5)."""
    pos = 0
    for span in spans:
        idx = text.index(span, pos)
        assert text[pos:idx] == "" or text[pos:idx].isspace()
        pos = idx + len(span)
    assert text[pos:] == "" or text[pos:].isspace()


class TestHeuristicTokenizer:
    @pytest.fixture(autouse=True)
    def _register_heuristic(self) -> None:
        register_sentence_tokenizer("heuristic", _HeuristicSentenceTokenizer)

    def split(self, text: str) -> list[str]:
        engine = get_sentence_tokenizer("heuristic")
        assert isinstance(engine, _HeuristicSentenceTokenizer)
        return engine.split(text)

    def test_ac1_dr_smith_splits_into_two(self) -> None:
        assert self.split("Dr. Smith went to Washington. He arrived at 9:00 a.m.") == [
            "Dr. Smith went to Washington.",
            "He arrived at 9:00 a.m.",
        ]

    def test_ac2_usa_is_one_sentence(self) -> None:
        assert self.split("U.S.A. is large.") == ["U.S.A. is large."]

    def test_ac3_decimals_are_one_sentence(self) -> None:
        assert self.split("3.14 and 2.71 are constants.") == ["3.14 and 2.71 are constants."]

    def test_boundary_never_falls_mid_abbreviation(self) -> None:
        assert self.split("Mr. Jones left. St. Louis is in Missouri.") == [
            "Mr. Jones left.",
            "St. Louis is in Missouri.",
        ]

    def test_e_g_and_etc_mid_sentence(self) -> None:
        assert self.split("He likes fruit, e.g. apples and pears, etc.") == [
            "He likes fruit, e.g. apples and pears, etc."
        ]

    def test_ellipsis_is_not_a_boundary(self) -> None:
        assert self.split("He said... then paused.") == ["He said... then paused."]

    def test_exclamation_and_question_terminators(self) -> None:
        assert self.split("Really! Are you sure? Yes.") == [
            "Really!",
            "Are you sure?",
            "Yes.",
        ]

    def test_quoted_sentence(self) -> None:
        assert self.split('She said, "Wait here." Then she left.') == [
            'She said, "Wait here."',
            "Then she left.",
        ]

    def test_cjk_terminators_with_empty_separator(self) -> None:
        assert self.split("甲。乙！丙？") == ["甲。", "乙！", "丙？"]

    def test_no_trailing_empty_fragment(self) -> None:
        assert self.split("Hello. World.") == ["Hello.", "World."]
        assert self.split("Hello.   ") == ["Hello."]
        assert self.split("Hello. World") == ["Hello.", "World"]

    def test_empty_and_whitespace_yield_empty_list(self) -> None:
        assert self.split("") == []
        assert self.split("   \n\t  ") == []

    def test_deterministic(self) -> None:
        text = "Dr. Smith went to Washington. He arrived at 9:00 a.m."
        assert self.split(text) == self.split(text)

    @pytest.mark.parametrize(
        "text",
        [
            "AAAA. BBBB.",
            "甲。乙。",
            "Dr. Smith went to Washington. He arrived at 9:00 a.m.",
            "U.S.A. is large.",
            "3.14 and 2.71 are constants.",
            'She said, "Wait here." Then she left.',
            "Really! Are you sure? Yes.",
            "  A. B.",
        ],
    )
    def test_d5_whitespace_only_separators(self, text: str) -> None:
        _assert_d5_reconstruction(text, self.split(text))


class TestHeuristicIsDefaultFallback:
    @pytest.fixture(autouse=True)
    def _register_heuristic(self) -> None:
        register_sentence_tokenizer("heuristic", _HeuristicSentenceTokenizer)

    def test_auto_returns_heuristic_when_nltk_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tokenizer_mod, "_nltk_available", lambda: False)
        engine = get_sentence_tokenizer("auto")
        assert isinstance(engine, _HeuristicSentenceTokenizer)

    def test_auto_never_raises_and_handles_empty_text(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Closes P3-101 AC: 'auto' returns a working tokenizer; empty/whitespace → []."""
        monkeypatch.setattr(tokenizer_mod, "_nltk_available", lambda: False)
        with caplog.at_level(logging.WARNING, logger="app.infrastructure.sentence_tokenizer"):
            engine = get_sentence_tokenizer("auto")
        assert engine.split("") == []
        assert engine.split("   ") == []


_NLTK_ENGINE_AVAILABLE = "nltk" in tokenizer_mod._ENGINE_REGISTRY
_NLTK_SKIP_REASON = (
    "nltk punkt_tab engine unavailable "
    "(pip install nltk, then nltk.download('punkt_tab'))"
)


@pytest.mark.skipif(not _NLTK_ENGINE_AVAILABLE, reason=_NLTK_SKIP_REASON)
class TestNltkTokenizer:
    @pytest.fixture(autouse=True)
    def _register_engines(self) -> None:
        register_sentence_tokenizer("heuristic", _HeuristicSentenceTokenizer)
        register_sentence_tokenizer("nltk", _NltkSentenceTokenizer)

    def split(self, text: str) -> list[str]:
        engine = get_sentence_tokenizer("nltk")
        assert isinstance(engine, _NltkSentenceTokenizer)
        return engine.split(text)

    def test_ac1_fixture_is_exactly_two_sentences(self) -> None:
        """P3-103 AC: with nltk installed, the AC1 fixture → exactly 2 sentences."""
        assert self.split("Dr. Smith went to Washington. He arrived at 9:00 a.m.") == [
            "Dr. Smith went to Washington.",
            "He arrived at 9:00 a.m.",
        ]

    def test_governing_fixture_produces_four_spans(self) -> None:
        """D9 governing fixture: spans match the regex engine, preserving the
        'AAAA.BBBB.' overlap regression contract."""
        assert self.split("AAAA. BBBB. CCCC. DDDD.") == ["AAAA.", "BBBB.", "CCCC.", "DDDD."]

    def test_d9_punkt_tab_reproduces_governing_fixture_byte_exact(self) -> None:
        """D9 dedicated boundary: punkt_tab spans, when concatenated with no
        separator, reproduce the governing 'AAAA.BBBB.CCCC.DDDD.' byte-exact
        expectation — the source of the chunker overlap contract."""
        spans = self.split("AAAA. BBBB. CCCC. DDDD.")
        assert "".join(spans) == "AAAA.BBBB.CCCC.DDDD."

    def test_mid_sentence_abbreviations_not_boundaries(self) -> None:
        assert self.split("He brought pens, pencils, etc. She brought paper.") == [
            "He brought pens, pencils, etc.",
            "She brought paper.",
        ]

    def test_empty_and_whitespace_yield_empty_list(self) -> None:
        assert self.split("") == []
        assert self.split("   \n\t  ") == []

    def test_trailing_fragment_preserved(self) -> None:
        """No sentence content is dropped at end-of-text (D5)."""
        assert self.split("Hello. World") == ["Hello.", "World"]

    def test_deterministic(self) -> None:
        text = "Dr. Smith went to Washington. He arrived at 9:00 a.m."
        assert self.split(text) == self.split(text)

    @pytest.mark.parametrize(
        "text",
        [
            "AAAA. BBBB.",
            "甲。乙。",
            "Dr. Smith went to Washington. He arrived at 9:00 a.m.",
            "U.S.A. is large.",
            "3.14 and 2.71 are constants.",
            'She said, "Wait here." Then she left.',
            "Really! Are you sure? Yes.",
            "  A. B.",
        ],
    )
    def test_d5_whitespace_only_separators(self, text: str) -> None:
        """D5 span-reconstruction per the frozen contract, incl. the CJK fixture
        without inserted whitespace (P3-103 test list)."""
        _assert_d5_reconstruction(text, self.split(text))


@pytest.mark.skipif(not _NLTK_ENGINE_AVAILABLE, reason=_NLTK_SKIP_REASON)
class TestNltkEngineSelection:
    @pytest.fixture(autouse=True)
    def _register_engines(self) -> None:
        register_sentence_tokenizer("heuristic", _HeuristicSentenceTokenizer)
        register_sentence_tokenizer("nltk", _NltkSentenceTokenizer)

    def test_auto_prefers_registered_nltk_engine(self) -> None:
        assert isinstance(get_sentence_tokenizer("auto"), _NltkSentenceTokenizer)

    def test_explicit_nltk_returns_real_engine(self) -> None:
        assert isinstance(get_sentence_tokenizer("nltk"), _NltkSentenceTokenizer)


class TestNltkAbsentFallback:
    def test_auto_falls_back_to_real_heuristic_with_one_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """D4/C-3: with nltk/data absent, 'auto' returns the heuristic engine and
        logs one warning — never a crash."""
        register_sentence_tokenizer("heuristic", _HeuristicSentenceTokenizer)
        monkeypatch.setattr(tokenizer_mod, "_nltk_available", lambda: False)
        with caplog.at_level(logging.WARNING, logger="app.infrastructure.sentence_tokenizer"):
            engine = get_sentence_tokenizer("auto")
        assert isinstance(engine, _HeuristicSentenceTokenizer)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "heuristic" in warnings[0].message


_CHUNKING_FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "chunking"
_FIXTURE_FILES = ["abbreviations.md", "cjk.md"]


def _register_real_engines() -> None:
    register_sentence_tokenizer("heuristic", _HeuristicSentenceTokenizer)
    if _NLTK_ENGINE_AVAILABLE:
        register_sentence_tokenizer("nltk", _NltkSentenceTokenizer)


@pytest.mark.parametrize("fixture", _FIXTURE_FILES)
class TestCommittedFixtureSpanReconstruction:
    """P3-106: D5 span-reconstruction on the committed fixtures — every engine
    must reproduce the file content with whitespace normalized only at
    sentence boundaries."""

    @pytest.fixture(autouse=True)
    def _register(self) -> None:
        _register_real_engines()

    @pytest.mark.parametrize(
        "engine",
        [
            "heuristic",
            pytest.param(
                "nltk",
                marks=pytest.mark.skipif(not _NLTK_ENGINE_AVAILABLE, reason=_NLTK_SKIP_REASON),
            ),
            "auto",
        ],
    )
    def test_fixture_spans_reconstruct_d5(self, fixture: str, engine: str) -> None:
        text = (_CHUNKING_FIXTURE_DIR / fixture).read_text(encoding="utf-8")
        spans = get_sentence_tokenizer(engine).split(text)
        assert spans
        _assert_d5_reconstruction(text, spans)


@pytest.mark.parametrize(
    "engine",
    [
        "heuristic",
        pytest.param(
            "nltk",
            marks=pytest.mark.skipif(not _NLTK_ENGINE_AVAILABLE, reason=_NLTK_SKIP_REASON),
        ),
    ],
)
class TestPerformance:
    """P3-106: 1 MB sentence split stays within a generous 1 s ceiling."""

    @pytest.fixture(autouse=True)
    def _register(self) -> None:
        _register_real_engines()

    def test_one_mb_split_under_one_second(self, engine: str) -> None:
        text = "The quick brown fox jumps over the lazy dog. " * 24000
        assert len(text) >= 1_000_000
        start = time.perf_counter()
        spans = get_sentence_tokenizer(engine).split(text)
        elapsed = time.perf_counter() - start
        assert spans
        assert elapsed <= 1.0
