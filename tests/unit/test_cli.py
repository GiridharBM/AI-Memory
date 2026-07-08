"""Tests for the Typer CLI."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

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
    assert "qwen3:8b" in result.output


def test_cli_status_command_displays_vault_status() -> None:
    result = runner.invoke(entry.cli, ["status"])

    assert result.exit_code == 0
    assert "Personal AI Memory Status" in result.output
    assert "Generated notes" in result.output


def test_cli_doctor_reports_mocked_ollama_available(monkeypatch) -> None:
    class FakeOllamaClient:
        def __init__(self, settings):
            self.settings = settings

        def is_available(self) -> bool:
            return True

    monkeypatch.setattr(entry, "OllamaClient", FakeOllamaClient)

    result = runner.invoke(entry.cli, ["doctor"])

    assert result.exit_code == 0
    assert "Doctor" in result.output
    assert "Ollama" in result.output


def test_cli_ingest_markdown_uses_workflow(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "note.md"
    source.write_text("# Note", encoding="utf-8")

    class FakeWorkflow:
        @classmethod
        def from_runtime(cls, *, ollama_client, writer):
            return cls()

        def run(self, source_arg, *, expected_source_type):
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


def _workflow_result(tmp_path: Path):
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
