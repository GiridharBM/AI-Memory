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
    assert "OCR" in result.output
    assert "Vision model" in result.output
    assert "Tesseract binary" in result.output


def test_cli_ingest_markdown_uses_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "note.md"
    source.write_text("# Note", encoding="utf-8")

    class FakeWorkflow:
        @classmethod
        def create_default(
            cls,
            settings: object,
            *,
            vision_client: object | None = None,
            transcriber: object | None = None,
        ) -> FakeWorkflow:
            return cls()

        def run(self, source_arg: str | Path, *, expected_source_type: str) -> SimpleNamespace:
            assert Path(source_arg) == source
            assert expected_source_type == "markdown"
            return _workflow_result(tmp_path)

    monkeypatch.setattr(entry, "IngestionWorkflow", FakeWorkflow)

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


def test_cli_search_displays_ranked_results(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSearchService:
        last: tuple[object, ...] | None = None

        @classmethod
        def create_default(
            cls, settings: object, *, embed: object | None = None
        ) -> FakeSearchService:
            return cls()

        def search(
            self,
            query: str,
            *,
            top_k: int = 5,
            filter: object | None = None,
            min_score: float = 0.0,
        ) -> list[SimpleNamespace]:
            type(self).last = (query, top_k, filter, min_score)
            return [
                SimpleNamespace(
                    score=0.5,
                    source="doc.md",
                    source_type="markdown",
                    text="python async snippet " * 10,
                ),
            ]

    monkeypatch.setattr(entry, "SearchService", FakeSearchService)

    result = runner.invoke(entry.cli, ["search", "python async", "--top-k", "3"])

    assert result.exit_code == 0
    assert "Search: python async" in result.output
    assert "doc.md" in result.output
    assert "markdown" in result.output
    assert "0.5000" in result.output
    assert FakeSearchService.last == ("python async", 3, None, 0.0)


def test_cli_search_merges_source_type_and_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSearchService:
        last: tuple[object, ...] | None = None

        @classmethod
        def create_default(
            cls, settings: object, *, embed: object | None = None
        ) -> FakeSearchService:
            return cls()

        def search(
            self,
            query: str,
            *,
            top_k: int = 5,
            filter: object | None = None,
            min_score: float = 0.0,
        ) -> list[SimpleNamespace]:
            type(self).last = (query, top_k, filter, min_score)
            return []

    monkeypatch.setattr(entry, "SearchService", FakeSearchService)

    result = runner.invoke(
        entry.cli,
        [
            "search", "python",
            "--source-type", "pdf",
            "--filter", '{"heading": "Intro"}',
            "--min-score", "0.1",
        ],
    )

    assert result.exit_code == 0
    assert FakeSearchService.last == (
        "python", 5, {"heading": "Intro", "source_type": "pdf"}, 0.1,
    )


def test_cli_search_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSearchService:
        @classmethod
        def create_default(
            cls, settings: object, *, embed: object | None = None
        ) -> FakeSearchService:
            return cls()

        def search(
            self,
            query: str,
            *,
            top_k: int = 5,
            filter: object | None = None,
            min_score: float = 0.0,
        ) -> list[SimpleNamespace]:
            return []

    monkeypatch.setattr(entry, "SearchService", FakeSearchService)

    result = runner.invoke(entry.cli, ["search", "zzz"])

    assert result.exit_code == 0
    assert "No results found." in result.output


def test_cli_search_empty_query_exits_one() -> None:
    result = runner.invoke(entry.cli, ["search", "   "])
    assert result.exit_code == 1
    assert "must not be empty" in result.output


def test_cli_search_bad_filter_json_exits_one() -> None:
    result = runner.invoke(entry.cli, ["search", "python", "--filter", "{not-json"])
    assert result.exit_code == 1
    assert "Invalid --filter JSON" in result.output


def test_cli_search_non_object_filter_exits_one() -> None:
    result = runner.invoke(entry.cli, ["search", "python", "--filter", "[1, 2]"])
    assert result.exit_code == 1
    assert "must be a JSON object" in result.output


def test_cli_search_zero_top_k_exits_two() -> None:
    result = runner.invoke(entry.cli, ["search", "python", "--top-k", "0"])
    assert result.exit_code == 2


def test_cli_search_handles_service_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSearchService:
        @classmethod
        def create_default(
            cls, settings: object, *, embed: object | None = None
        ) -> FakeSearchService:
            return cls()

        def search(
            self,
            query: str,
            *,
            top_k: int = 5,
            filter: object | None = None,
            min_score: float = 0.0,
        ) -> list[SimpleNamespace]:
            raise RuntimeError("store corrupt")

    monkeypatch.setattr(entry, "SearchService", FakeSearchService)

    result = runner.invoke(entry.cli, ["search", "python"])

    assert result.exit_code == 1
    assert "Search failed" in result.output


def test_cli_ask_displays_answer_and_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeQAWorkflow:
        last: tuple[object, ...] | None = None

        @classmethod
        def create_default(
            cls, settings: object, *, model: object | None = None
        ) -> FakeQAWorkflow:
            return cls()

        def ask(
            self,
            question: str,
            *,
            top_k: int = 5,
            min_score: float = 0.0,
            filter: object | None = None,
        ) -> SimpleNamespace:
            type(self).last = (question, top_k, min_score, filter)
            return SimpleNamespace(
                answer="AI stands for artificial intelligence.",
                sources=[
                    SimpleNamespace(
                        score=0.5,
                        source="ai.md",
                        source_type="markdown",
                        text="AI is artificial intelligence.",
                    )
                ],
                model="qwen3:8b",
            )

    monkeypatch.setattr(entry, "QAWorkflow", FakeQAWorkflow)

    result = runner.invoke(entry.cli, ["ask", "What is AI?", "--top-k", "3"])

    assert result.exit_code == 0
    assert "Answer: What is AI?" in result.output
    assert "AI stands for artificial intelligence." in result.output
    assert "Sources" in result.output
    assert "ai.md" in result.output
    assert FakeQAWorkflow.last == ("What is AI?", 3, 0.0, None)


def test_cli_ask_empty_question_exits_one() -> None:
    result = runner.invoke(entry.cli, ["ask", "   "])
    assert result.exit_code == 1
    assert "must not be empty" in result.output


def test_cli_ask_reports_generation_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeQAWorkflow:
        @classmethod
        def create_default(
            cls, settings: object, *, model: object | None = None
        ) -> FakeQAWorkflow:
            return cls()

        def ask(
            self,
            question: str,
            *,
            top_k: int = 5,
            min_score: float = 0.0,
            filter: object | None = None,
        ) -> SimpleNamespace:
            raise entry.QAError(
                "Unable to generate an answer because the Ollama server is unavailable."
            )

    monkeypatch.setattr(entry, "QAWorkflow", FakeQAWorkflow)

    result = runner.invoke(entry.cli, ["ask", "What is AI?"])

    assert result.exit_code == 1
    assert "Ask failed" in result.output
    assert "Ollama server is unavailable" in result.output


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
