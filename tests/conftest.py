"""Shared test fixtures for the Personal AI Memory System."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import (
    AppSettings,
    LoggingSettings,
    ManifestSettings,
    ModelRoutingSettings,
    OllamaSettings,
    PathSettings,
    ProcessingSettings,
    QueueSettings,
    Settings,
    WatcherSettings,
)
from app.domain.analysis import (
    Definition,
    DocumentAnalysis,
    DocumentSummary,
    ImportantEntity,
    KeyConcept,
    RelatedTopic,
)
from app.domain.documents import DocumentMetadata, SourceDocument


def pytest_configure(config: pytest.Config) -> None:
    """Register markers used across the test suite."""
    config.addinivalue_line(
        "markers",
        "integration: tests that hit live external services (skipped by default)",
    )


@pytest.fixture()
def tmp_settings(tmp_path: Path) -> Settings:
    """Create a minimal Settings object using a temporary directory."""
    return _make_settings(tmp_path)


@pytest.fixture()
def sample_analysis() -> DocumentAnalysis:
    """Return a fully populated DocumentAnalysis for testing."""
    return DocumentAnalysis(
        suggested_note_title="Test Note",
        summary=DocumentSummary(short="Short summary.", detailed="Detailed summary."),
        keywords=["python", "testing"],
        categories=["Programming"],
        reading_time_minutes=5,
        difficulty="beginner",
        key_concepts=[
            KeyConcept(name="Pytest", explanation="Testing framework", importance="high"),
            KeyConcept(name="Coverage", explanation="Code coverage", importance="medium"),
        ],
        definitions=[Definition(term="Fixture", definition="Test setup helper")],
        important_entities=[
            ImportantEntity(name="Python", type="technology", description="Programming language"),
        ],
        tags=["test", "example"],
        related_topics=[RelatedTopic(topic="TDD", reason="Related methodology")],
        suggested_related_notes=["Other Note"],
        suggested_backlinks=["Parent Note"],
    )


@pytest.fixture()
def sample_document() -> SourceDocument:
    """Return a minimal SourceDocument for testing."""
    return SourceDocument(
        source="test.md",
        source_path=None,
        source_type="markdown",
        filename="test.md",
        text="# Hello\n\nWorld",
        metadata=DocumentMetadata(title="Test"),
    )


def _make_settings(
    tmp_path: Path,
    *,
    logging_settings: LoggingSettings | None = None,
    watcher_enabled: bool = True,
    queue_enabled: bool = True,
) -> Settings:
    """Build a Settings object rooted in tmp_path. Used by conftest and test files."""
    return Settings(
        app=AppSettings(name="personal-ai-memory", environment="development"),
        paths=PathSettings(
            project_root=tmp_path,
            vault_root=tmp_path / "vault",
            inbox_root=tmp_path / "inbox",
            staging_root=tmp_path / "staging",
            manifest_root=tmp_path / "manifests",
            cache_root=tmp_path / "cache",
            log_root=tmp_path / "logs",
        ),
        ollama=OllamaSettings(),
        logging=logging_settings or LoggingSettings(
            console_enabled=False, file_enabled=False,
        ),
        models=ModelRoutingSettings(),
        watcher=WatcherSettings(
            inbox_path=tmp_path / "inbox",
            processed_path=tmp_path / "processed",
            failed_path=tmp_path / "failed",
            enabled=watcher_enabled,
        ),
        queue=QueueSettings(
            state_path=tmp_path / "manifests" / "queue_state.json",
            enabled=queue_enabled,
        ),
        manifest=ManifestSettings(
            path=tmp_path / "manifests" / "processed_files.json",
        ),
        processing=ProcessingSettings(
            processed_path=tmp_path / "processed",
            failed_path=tmp_path / "failed",
        ),
    )
