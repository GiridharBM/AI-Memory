"""Tests for MIME detection (P2-203)."""

from __future__ import annotations

import logging
import os
import sys
import types
from pathlib import Path

import pytest

from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.document_intelligence.metadata import mime
from app.infrastructure.routing.classifier import DocumentClassifier

_MIME_LOGGER = "app.infrastructure.document_intelligence.metadata.mime"


@pytest.fixture()
def no_magic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guarantee python-magic is unavailable and reset the warn-once flag."""
    monkeypatch.delitem(sys.modules, "magic", raising=False)
    monkeypatch.setattr(mime, "_MAGIC_MISSING_WARNED", False)


def _write(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


class TestExtensionBasedDetection:
    def test_known_extension_does_not_read_file(self) -> None:
        assert mime.detect_mime(Path("readme.md")) == "text/markdown"

    def test_ipynb_supplemental_extension(self) -> None:
        assert mime.detect_mime(Path("analysis.ipynb")) == "application/x-ipynb+json"

    def test_known_extension_takes_precedence_over_content(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "file.md", b"%PDF-1.7\n%EOF\n")
        assert mime.detect_mime(path) == "text/markdown"

    def test_pdf_extension(self) -> None:
        assert mime.detect_mime(Path("doc.pdf")) == "application/pdf"


class TestSniffDetection:
    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            (b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n", "application/pdf"),
            (b"PK\x03\x04\x14\x00\x00\x00", "application/zip"),
            (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "image/png"),
            (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00", "image/jpeg"),
            (b"GIF89a\x01\x00\x01\x00", "image/gif"),
            (b"# Heading\n\nbody", "text/markdown"),
            (b'{"key": "value"}', "application/json"),
            (b'[1, 2, 3]', "application/json"),
            (b"<?xml version='1.0'?><root/>", "application/xml"),
            (b"<!DOCTYPE html><html></html>", "text/html"),
            (b"just some ordinary text\n", "text/plain"),
        ],
    )
    def test_extensionless_sniffing(
        self, no_magic, tmp_path: Path, content: bytes, expected: str
    ) -> None:
        path = _write(tmp_path, "extensionless", content)
        assert mime.detect_mime(path) == expected

    def test_binary_garbage_is_octet_stream(self, no_magic, tmp_path: Path) -> None:
        path = _write(tmp_path, "garbage", os.urandom(64))
        assert mime.detect_mime(path) == "application/octet-stream"

    def test_missing_file_returns_octet_stream(self, no_magic, tmp_path: Path) -> None:
        assert mime.detect_mime(tmp_path / "does-not-exist") == "application/octet-stream"


class TestMagicEnhancement:
    def test_missing_magic_warns_once_and_falls_back(
        self, no_magic, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = _write(tmp_path, "sample", b"# Markdown\n")
        with caplog.at_level(logging.WARNING, logger=_MIME_LOGGER):
            assert mime.detect_mime(path) == "text/markdown"
            assert mime.detect_mime(path) == "text/markdown"
        warnings = [
            record
            for record in caplog.records
            if record.name == _MIME_LOGGER and "python-magic" in record.getMessage()
        ]
        assert len(warnings) == 1

    def test_magic_verdict_wins_for_binary(
        self, no_magic, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake_magic = types.SimpleNamespace(
            from_buffer=lambda header, mime=True: "audio/mpeg"
        )
        monkeypatch.setitem(sys.modules, "magic", fake_magic)
        path = _write(tmp_path, "song", b"ID3\x04\x00\x00\x00\x00\x00\x00")
        assert mime.detect_mime(path) == "audio/mpeg"

    def test_generic_plain_text_from_magic_defers_to_markdown_sniff(
        self, no_magic, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake_magic = types.SimpleNamespace(
            from_buffer=lambda header, mime=True: "text/plain"
        )
        monkeypatch.setitem(sys.modules, "magic", fake_magic)
        path = _write(tmp_path, "notes", b"# Markdown\n")
        assert mime.detect_mime(path) == "text/markdown"

    def test_magic_error_falls_back(
        self, no_magic, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        class _BoomMagic:
            @staticmethod
            def from_buffer(header: bytes, mime: bool = True) -> str:
                raise OSError("libmagic unavailable")

        monkeypatch.setitem(sys.modules, "magic", _BoomMagic)
        path = _write(tmp_path, "plain", b"plain text\n")
        assert mime.detect_mime(path) == "text/plain"


class TestClassifierMimeConsult:
    def test_mime_enabled_detects_extensionless_markdown(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "readme", b"# Notes\n")
        doc = SourceDocument(
            source="readme",
            source_path=path,
            source_type="markdown",
            filename="readme",
            text="",
            metadata=DocumentMetadata(),
        )
        result = DocumentClassifier(mime_enabled=True).classify(doc)
        assert result.mime_type == "text/markdown"

    def test_mime_disabled_keeps_stdlib_behavior(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "readme", b"# Notes\n")
        doc = SourceDocument(
            source="readme",
            source_path=path,
            source_type="markdown",
            filename="readme",
            text="",
            metadata=DocumentMetadata(),
        )
        result = DocumentClassifier(mime_enabled=False).classify(doc)
        assert result.mime_type is None

    def test_no_source_path_falls_back_to_filename(self) -> None:
        doc = SourceDocument(
            source="readme.md",
            source_path=None,
            source_type="markdown",
            filename="readme.md",
            text="",
            metadata=DocumentMetadata(),
        )
        result = DocumentClassifier().classify(doc)
        assert result.mime_type == "text/markdown"


def _document_at(path: Path) -> SourceDocument:
    return SourceDocument(
        source=path.name,
        source_path=path,
        source_type="markdown",
        filename=path.name,
        text="",
        metadata=DocumentMetadata(),
    )


class TestWorkflowMimeEnabledConfig:
    """The workflow plumbs intelligence.metadata.mime_enabled into the classifier."""

    def _workflow(self, settings):
        from unittest.mock import MagicMock

        from app.pipelines.ingest_workflow import IngestionWorkflow

        return IngestionWorkflow(
            ingestion_service=MagicMock(),
            ollama_client=MagicMock(),
            note_generator=MagicMock(),
            writer=MagicMock(),
            settings=settings,
        )

    def test_true_uses_detect_mime(
        self, tmp_path: Path, tmp_settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.infrastructure.routing.classifier as classifier_module

        calls: list[str] = []
        monkeypatch.setattr(
            classifier_module,
            "detect_mime",
            lambda path: calls.append(str(path)) or "text/markdown",
        )
        path = _write(tmp_path, "notes", b"# Markdown\n")
        workflow = self._workflow(tmp_settings)
        result = workflow._classifier.classify(_document_at(path))
        assert result.mime_type == "text/markdown"
        assert calls == [str(path)]

    def test_false_bypasses_detect_mime(
        self, tmp_path: Path, tmp_settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.infrastructure.routing.classifier as classifier_module

        tmp_settings.intelligence.metadata.mime_enabled = False

        def _boom(_path) -> str:
            raise AssertionError("detect_mime must not be called when mime_enabled=false")

        monkeypatch.setattr(classifier_module, "detect_mime", _boom)
        path = _write(tmp_path, "notes", b"# Markdown\n")
        workflow = self._workflow(tmp_settings)
        result = workflow._classifier.classify(_document_at(path))
        assert result.mime_type is None

    def test_from_runtime_plumbs_settings(self, tmp_settings) -> None:
        from unittest.mock import MagicMock

        from app.pipelines.ingest_workflow import IngestionWorkflow

        tmp_settings.intelligence.metadata.mime_enabled = False
        workflow = IngestionWorkflow.from_runtime(
            ollama_client=MagicMock(),
            writer=MagicMock(),
            settings=tmp_settings,
        )
        assert workflow._classifier._mime_enabled is False
