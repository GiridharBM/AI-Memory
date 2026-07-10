"""Tests for the Typer CLI."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from app.cli import entry
from app.domain.documents import DocumentMetadata, SourceDocument
from app.domain.notes import ObsidianNote
from app.infrastructure.vault import WikiUpdateResult

runner = CliRunner()


def test_cli_config_command_displays_resolved_config() -> None:
    result = runner.invoke(entry.cli, ["config"])

    assert result.exit_code == 0
    assert "Resolved Configuration" in result.output
    assert "Watcher" in result.output
    assert "Queue" in result.output
    assert "Manifest" in result.output
    assert "Processing" in result.output
    assert "qwen3:8b" in result.output


def test_cli_status_command_displays_watcher_queue_and_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(entry, "_ollama_status", lambda settings: "Connected")
    monkeypatch.setenv("PAM_WATCHER__INBOX_PATH", str(tmp_path / "inbox"))
    monkeypatch.setenv("PAM_WATCHER__PROCESSED_PATH", str(tmp_path / "processed"))
    monkeypatch.setenv("PAM_WATCHER__FAILED_PATH", str(tmp_path / "failed"))
    monkeypatch.setenv("PAM_PATHS__VAULT_ROOT", str(tmp_path / "vault"))
    monkeypatch.setenv("PAM_PATHS__LOG_ROOT", str(tmp_path / "logs"))
    monkeypatch.setenv("PAM_PATHS__CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("PAM_MANIFEST__PATH", str(tmp_path / "manifests" / "processed.json"))
    monkeypatch.setenv("PAM_QUEUE__STATE_PATH", str(tmp_path / "manifests" / "queue.json"))
    monkeypatch.setenv("PAM_PROCESSING__PROCESSED_PATH", str(tmp_path / "processed"))
    monkeypatch.setenv("PAM_PROCESSING__FAILED_PATH", str(tmp_path / "failed"))

    result = runner.invoke(entry.cli, ["status"])

    assert result.exit_code == 0
    assert "AI Memory Status" in result.output
    assert "Watcher" in result.output
    assert "Queue" in result.output
    assert "Manifest entries" in result.output
    assert "Generated notes" in result.output
    assert (tmp_path / "inbox").exists()
    assert (tmp_path / "processed").exists()
    assert (tmp_path / "failed").exists()


def test_cli_doctor_reports_mocked_ollama_available(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOllamaClient:
        def __init__(self, settings: object) -> None:
            self.settings = settings

        def is_available(self) -> bool:
            return True

    monkeypatch.setattr(entry, "OllamaClient", FakeOllamaClient)

    result = runner.invoke(entry.cli, ["doctor"])

    assert result.exit_code == 0
    assert "Doctor" in result.output
    assert "Ollama" in result.output


def test_cli_ingest_markdown_uses_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "note.md"
    source.write_text("# Note", encoding="utf-8")

    class FakeWorkflow:
        @classmethod
        def from_runtime(cls, *, ollama_client: object, writer: object) -> FakeWorkflow:
            return cls()

        def run(self, source_arg: str | Path, *, expected_source_type: str) -> SimpleNamespace:
            assert Path(source_arg) == source
            assert expected_source_type == "markdown"
            return _workflow_result(tmp_path)

    monkeypatch.setattr(entry, "IngestionWorkflow", FakeWorkflow)
    monkeypatch.setattr(entry, "OllamaClient", lambda settings: object())
    monkeypatch.setattr(
        entry.VaultWriter,
        "from_settings",
        classmethod(lambda cls, settings: object()),
    )

    result = runner.invoke(entry.cli, ["ingest", "markdown", str(source)])

    assert result.exit_code == 0
    assert "Ingestion Complete" in result.output
    assert "Local AI Memory" in result.output


def test_cli_watch_starts_service(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeWatchService:
        def __init__(self, settings: object) -> None:
            self.settings = settings

        def run(self) -> None:
            print("Queue started")
            print("Worker started")
            print("Waiting...")

    monkeypatch.setattr(entry, "WatchService", FakeWatchService)

    result = runner.invoke(entry.cli, ["watch"])

    assert result.exit_code == 0
    assert "AI Memory Watcher" in result.output
    assert "Watching" in result.output
    assert "Recursive" in result.output
    assert "Press Ctrl+C to stop" in result.output
    assert "data" in result.output
    assert "inbox" in result.output
    assert "Queue started" in result.output
    assert "Worker started" in result.output
    assert "Waiting..." in result.output


def _workflow_result(tmp_path: Path) -> SimpleNamespace:
    generated_at = datetime(2026, 7, 8, tzinfo=UTC)
    document = SourceDocument(
        source="note.md",
        source_type="markdown",
        filename="note.md",
        text="# Note",
        metadata=DocumentMetadata(title="Note"),
    )
    note = ObsidianNote(
        title="Local AI Memory",
        filename="Local AI Memory.md",
        markdown="# Local AI Memory",
        generated_at=generated_at,
        tags=["local-ai"],
        source="note.md",
        source_type="markdown",
    )
    write_result = WikiUpdateResult(
        note_path=tmp_path / "vault" / "Notes" / "Local AI Memory.md",
        created=True,
        updated=False,
        index_path=tmp_path / "vault" / "index.md",
        overview_path=tmp_path / "vault" / "overview.md",
        log_path=tmp_path / "vault" / "log.md",
    )
    ai_result = SimpleNamespace(document=document, analysis=SimpleNamespace(), attempts=1)
    return SimpleNamespace(
        document=document,
        ai_result=ai_result,
        note=note,
        write_result=write_result,
    )
