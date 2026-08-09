"""Tests for the ingestion hook chain and size/time limits (P2-206)."""

from __future__ import annotations

from pathlib import Path

from app.core.config import IntelligenceSettings, MetadataSettings, Settings, load_settings
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.document_intelligence.metadata.hooks import (
    HookRegistry,
    IngestionHook,
)
from app.infrastructure.ingestion.base import BaseIngestor, IngestionError, SourceReference
from app.infrastructure.ingestion.github_readme_ingestor import _REQUEST_TIMEOUT_SECONDS
from app.infrastructure.ingestion.service import DocumentIngestionService


def _settings(metadata: MetadataSettings) -> Settings:
    base = load_settings()
    return base.model_copy(update={"intelligence": IntelligenceSettings(metadata=metadata)})


def _document(source: Path, text: str = "original") -> SourceDocument:
    return SourceDocument(
        source=str(source),
        source_path=source,
        source_type="text",
        filename=source.name,
        text=text,
        metadata=DocumentMetadata(),
    )


class _SpyIngestor(BaseIngestor):
    source_type = "text"
    supported_suffixes = (".txt",)

    def __init__(self) -> None:
        self.calls = 0

    def ingest(self, source: SourceReference) -> SourceDocument:
        self.calls += 1
        assert isinstance(source, Path)
        return _document(source)


class _RedirectingPreHook:
    name = "redirector"

    def __init__(self, target: Path) -> None:
        self.target = target

    def pre(self, source: SourceReference) -> SourceReference:
        return self.target

    def post(self, document: SourceDocument) -> SourceDocument:
        return document


class _AppendingPostHook:
    name = "appender"

    def pre(self, source: SourceReference) -> SourceReference:
        return source

    def post(self, document: SourceDocument) -> SourceDocument:
        return document.model_copy(update={"text": document.text + "\nAPPENDED"})


class _RecordingHook:
    def __init__(self, name: str, calls: list[str]) -> None:
        self.name = name
        self.calls = calls

    def pre(self, source: SourceReference) -> SourceReference:
        self.calls.append(self.name)
        return source

    def post(self, document: SourceDocument) -> SourceDocument:
        self.calls.append(self.name)
        return document


class _RaisingPreHook:
    name = "raiser"

    def __init__(self, error: Exception) -> None:
        self.error = error

    def pre(self, source: SourceReference) -> SourceReference:
        raise self.error

    def post(self, document: SourceDocument) -> SourceDocument:
        return document


def test_size_guard_rejects_over_limit_before_read(tmp_path: Path) -> None:
    source = tmp_path / "big.txt"
    source.write_bytes(b"x" * (2 * 1024 * 1024))
    spy = _SpyIngestor()
    service = DocumentIngestionService(
        ingestors=[spy],
        settings=_settings(MetadataSettings(max_file_size_mb=1)),
    )

    result = service.ingest(source)

    assert not result.succeeded
    assert result.error is not None
    assert "size limit" in result.error.reason
    assert spy.calls == 0


def test_size_guard_disabled_bypasses_limit(tmp_path: Path) -> None:
    source = tmp_path / "big.txt"
    source.write_bytes(b"x" * (2 * 1024 * 1024))
    spy = _SpyIngestor()
    service = DocumentIngestionService(
        ingestors=[spy],
        settings=_settings(MetadataSettings(enabled=False, max_file_size_mb=1)),
    )

    result = service.ingest(source)

    assert result.succeeded
    assert spy.calls == 1


def test_disabled_skips_hooks(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")
    calls: list[str] = []
    recording = _RecordingHook("recorder", calls)
    settings = _settings(
        MetadataSettings(
            enabled=False,
            hooks={"pre": ["recorder"], "post": ["recorder"]},
        )
    )

    result = DocumentIngestionService(
        settings=settings,
        hooks=[recording],
    ).ingest(source)

    assert result.succeeded
    assert calls == []


def test_pre_hook_redirects_source(tmp_path: Path) -> None:
    original = tmp_path / "original.txt"
    original.write_text("original", encoding="utf-8")
    target = tmp_path / "target.txt"
    target.write_text("redirected", encoding="utf-8")
    settings = _settings(MetadataSettings(hooks={"pre": ["redirector"]}))

    result = DocumentIngestionService(
        settings=settings,
        hooks=[_RedirectingPreHook(target)],
    ).ingest(original)

    assert result.succeeded
    assert result.document is not None
    assert result.document.text == "redirected"
    assert result.document.source_path == target


def test_pre_hook_ingestion_error_aborts(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")
    settings = _settings(MetadataSettings(hooks={"pre": ["raiser"]}))

    result = DocumentIngestionService(
        settings=settings,
        hooks=[_RaisingPreHook(IngestionError("rejected by hook"))],
    ).ingest(source)

    assert not result.succeeded
    assert result.error is not None
    assert result.error.reason == "rejected by hook"


def test_post_hook_rewrites_text(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")
    settings = _settings(MetadataSettings(hooks={"post": ["appender"]}))

    result = DocumentIngestionService(
        settings=settings,
        hooks=[_AppendingPostHook()],
    ).ingest(source)

    assert result.succeeded
    assert result.document is not None
    assert result.document.text == "hello\nAPPENDED"


def test_hook_error_logged_and_skipped(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")
    settings = _settings(MetadataSettings(hooks={"pre": ["raiser"]}))

    result = DocumentIngestionService(
        settings=settings,
        hooks=[_RaisingPreHook(RuntimeError("boom"))],
    ).ingest(source)

    assert result.succeeded
    assert result.document is not None
    assert result.document.text == "hello"


def test_chain_order_preserved(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")
    calls: list[str] = []
    settings = _settings(
        MetadataSettings(hooks={"pre": ["first", "second"], "post": ["third"]})
    )

    result = DocumentIngestionService(
        settings=settings,
        hooks=[
            _RecordingHook("first", calls),
            _RecordingHook("second", calls),
            _RecordingHook("third", calls),
        ],
    ).ingest(source)

    assert result.succeeded
    assert calls == ["first", "second", "third"]


def test_unknown_hook_name_warns_and_continues(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")
    settings = _settings(MetadataSettings(hooks={"pre": ["missing"]}))

    result = DocumentIngestionService(settings=settings).ingest(source)

    assert result.succeeded


def test_register_hook_public_alias_resolves_by_name(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")
    settings = _settings(MetadataSettings(hooks={"post": ["appender"]}))
    registry = HookRegistry()
    registry.register(_AppendingPostHook())
    from app.infrastructure.document_intelligence.metadata import get_default_hook_registry

    get_default_hook_registry()._hooks.update(registry._hooks)
    try:
        result = DocumentIngestionService(settings=settings).ingest(source)
    finally:
        get_default_hook_registry()._hooks.clear()

    assert result.succeeded
    assert result.document is not None
    assert result.document.text == "hello\nAPPENDED"


def test_protocol_is_runtime_checkable() -> None:
    assert isinstance(_AppendingPostHook(), IngestionHook)


def test_url_timeout_default_matches_remote_fetch() -> None:
    assert MetadataSettings().url_timeout_seconds == _REQUEST_TIMEOUT_SECONDS == 30
