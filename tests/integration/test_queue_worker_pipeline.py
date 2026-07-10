"""Integration tests for queue worker processing through the V1 ingestion pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.application import AIProcessingResult
from app.core.config import (
    AppSettings,
    LoggingSettings,
    ManifestSettings,
    OllamaSettings,
    PathSettings,
    ProcessingSettings,
    Settings,
)
from app.domain.analysis import DocumentAnalysis
from app.domain.documents import SourceDocument
from app.infrastructure.ingestion import DocumentIngestionService
from app.infrastructure.state.manifest import ManifestManager
from app.infrastructure.vault import VaultWriter
from app.pipelines import IngestionWorkflow
from app.queue import QueueItem, QueueManager, QueueStatus, QueueWorker
from app.templates import ObsidianMarkdownGenerator


class FakeDocumentProcessor:
    """Fake AI processor used to exercise the real pipeline without Ollama."""

    def process(self, document: SourceDocument) -> AIProcessingResult:
        return AIProcessingResult(
            document=document,
            analysis=_analysis(document.metadata.title or document.source_type.title()),
            attempts=1,
        )


def test_worker_processes_markdown_updates_vault_manifest_and_moves_file(tmp_path: Path) -> None:
    source = tmp_path / "inbox" / "python.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Python\n\nUseful language notes.", encoding="utf-8")

    item, queue, worker, settings = _worker_for_source(tmp_path, source)

    assert worker.process_next()

    assert item.status == QueueStatus.DONE
    assert queue.is_empty()
    assert not source.exists()
    assert (settings.processing.processed_path / "python.md").exists()
    assert (settings.paths.vault_root / "Notes" / "Python.md").exists()
    manifest = ManifestManager(settings.manifest.path, project_root=tmp_path)
    assert manifest.count() == 1
    assert manifest.list_entries()[0].generated_note == "Python.md"


def test_worker_processes_multiple_markdown_files_in_fifo_order(tmp_path: Path) -> None:
    first = tmp_path / "inbox" / "first.md"
    second = tmp_path / "inbox" / "second.md"
    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_text("# First\n\nFirst note.", encoding="utf-8")
    second.write_text("# Second\n\nSecond note.", encoding="utf-8")
    settings = _settings(tmp_path)
    queue = QueueManager()
    first_item = QueueItem(path=first, extension=".md", created_at=datetime.now(UTC))
    second_item = QueueItem(path=second, extension=".md", created_at=datetime.now(UTC))
    queue.enqueue(first_item)
    queue.enqueue(second_item)
    workflow = IngestionWorkflow(
        ingestion_service=DocumentIngestionService(),
        processor=FakeDocumentProcessor(),
        note_generator=ObsidianMarkdownGenerator(),
        writer=VaultWriter(settings.paths.vault_root),
    )
    worker = QueueWorker(queue, settings, workflow=workflow, processing_seconds=0)

    assert worker.process_next()
    assert first_item.status == QueueStatus.DONE
    assert (settings.processing.processed_path / "first.md").exists()
    assert worker.process_next()
    assert second_item.status == QueueStatus.DONE

    assert queue.is_empty()
    assert (settings.processing.processed_path / "second.md").exists()
    assert (settings.paths.vault_root / "Notes" / "First.md").exists()
    assert (settings.paths.vault_root / "Notes" / "Second.md").exists()
    assert ManifestManager(settings.manifest.path, project_root=tmp_path).count() == 2


def test_worker_processes_txt_updates_vault_manifest_and_moves_file(tmp_path: Path) -> None:
    source = tmp_path / "inbox" / "plain.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("Plain text knowledge.", encoding="utf-8")

    item, queue, worker, settings = _worker_for_source(tmp_path, source)

    assert worker.process_next()

    assert item.status == QueueStatus.DONE
    assert queue.is_empty()
    assert not source.exists()
    assert (settings.processing.processed_path / "plain.txt").exists()
    assert (settings.paths.vault_root / "Notes" / "Plain.md").exists()
    assert ManifestManager(settings.manifest.path, project_root=tmp_path).count() == 1


def test_worker_processes_pdf_updates_vault_manifest_and_moves_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "inbox" / "paper.pdf"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"%PDF fake")

    class FakeReader:
        metadata = {"/Title": "Paper"}
        pages = [SimpleNamespace(extract_text=lambda: "Extracted PDF knowledge.")]

    monkeypatch.setattr(
        "app.infrastructure.ingestion.pdf_ingestor.PdfReader",
        lambda _: FakeReader(),
    )

    item, queue, worker, settings = _worker_for_source(tmp_path, source)

    assert worker.process_next()

    assert item.status == QueueStatus.DONE
    assert queue.is_empty()
    assert not source.exists()
    assert (settings.processing.processed_path / "paper.pdf").exists()
    assert (settings.paths.vault_root / "Notes" / "Paper.md").exists()
    assert ManifestManager(settings.manifest.path, project_root=tmp_path).count() == 1


def test_worker_moves_invalid_file_to_failed(tmp_path: Path) -> None:
    source = tmp_path / "inbox" / "data.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("a,b", encoding="utf-8")

    item, queue, worker, settings = _worker_for_source(tmp_path, source)

    assert worker.process_next()

    assert item.status == QueueStatus.FAILED
    assert queue.is_empty()
    assert not source.exists()
    assert (settings.processing.failed_path / "data.csv").exists()
    assert not (settings.paths.vault_root / "Notes").exists()
    assert ManifestManager(settings.manifest.path, project_root=tmp_path).count() == 0


def test_worker_skips_duplicate_without_processing_or_moving(tmp_path: Path) -> None:
    source = tmp_path / "inbox" / "duplicate.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Duplicate\n\nAlready known.", encoding="utf-8")

    item, queue, worker, settings = _worker_for_source(tmp_path, source)
    digest = worker.manifest_manager.hash_for_path(source)
    worker.manifest_manager.add_processed_file(path=source, sha256=digest, extension=".md")
    worker.manifest_manager.save()

    assert worker.process_next()

    assert item.status == QueueStatus.DONE
    assert queue.is_empty()
    assert source.exists()
    assert not (settings.processing.processed_path / "duplicate.md").exists()
    assert not (settings.paths.vault_root / "Notes").exists()
    assert ManifestManager(settings.manifest.path, project_root=tmp_path).count() == 1


def _worker_for_source(
    tmp_path: Path,
    source: Path,
) -> tuple[QueueItem, QueueManager, QueueWorker, Settings]:
    settings = _settings(tmp_path)
    queue = QueueManager()
    item = QueueItem(
        path=source,
        extension=source.suffix.lower(),
        created_at=datetime.now(UTC),
    )
    queue.enqueue(item)
    workflow = IngestionWorkflow(
        ingestion_service=DocumentIngestionService(),
        processor=FakeDocumentProcessor(),
        note_generator=ObsidianMarkdownGenerator(),
        writer=VaultWriter(settings.paths.vault_root),
    )
    worker = QueueWorker(
        queue,
        settings,
        workflow=workflow,
        processing_seconds=0,
    )
    return item, queue, worker, settings


def _settings(tmp_path: Path) -> Settings:
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
        logging=LoggingSettings(console_enabled=False, file_enabled=False),
        manifest=ManifestSettings(path=tmp_path / "manifests" / "processed_files.json"),
        processing=ProcessingSettings(
            processed_path=tmp_path / "processed",
            failed_path=tmp_path / "failed",
        ),
    )


def _analysis(title: str) -> DocumentAnalysis:
    payload: dict[str, Any] = {
        "suggested_note_title": title,
        "summary": {
            "short": f"{title} summary.",
            "detailed": f"{title} detailed summary.",
        },
        "key_concepts": [
            {
                "name": title,
                "explanation": f"Core idea from {title}.",
                "importance": "high",
            }
        ],
        "definitions": [],
        "important_entities": [],
        "tags": ["queue-worker"],
        "related_topics": [],
    }
    return DocumentAnalysis.model_validate(payload)
