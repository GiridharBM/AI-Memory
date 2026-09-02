"""Tests for the Typer CLI."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from app.application.qa_workflow import QAEmptyAnswerError, QATimeoutError
from app.cli import entry
from app.domain.documents import DocumentMetadata, SourceDocument
from app.domain.notes import ObsidianNote
from app.infrastructure.state.manifest import ManifestManager
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
    assert "PAM Status (read-only)" in result.output
    assert "Watcher" in result.output
    assert "Queue" in result.output
    assert "Manifest entries" in result.output
    assert "Real generated notes" in result.output
    # A5: status is read-only — it must not create runtime directories
    assert not (tmp_path / "inbox").exists()
    assert not (tmp_path / "processed").exists()
    assert not (tmp_path / "failed").exists()


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
    # Phase 6A: direct ingest records into the ledger, so point it at tmp.
    monkeypatch.setenv("PAM_MANIFEST__PATH", str(tmp_path / "manifests" / "processed.json"))

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


def test_cli_ask_timeout_reports_failure_exit_one(monkeypatch: pytest.MonkeyPatch) -> None:
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
            raise QATimeoutError("QA generation exceeded the wall-clock timeout.")

    monkeypatch.setattr(entry, "QAWorkflow", FakeQAWorkflow)

    result = runner.invoke(entry.cli, ["ask", "What is AI?"])

    assert result.exit_code == 1
    assert "Ask failed" in result.output
    assert "wall-clock timeout" in result.output


def _qa_result(
    *,
    answer: str = "AI is a field.",
    sources: list[object] | None = None,
    outcome: str | None = None,
    citations: list[object] | None = None,
    invalid: list[int] | None = None,
    duplicates: int = 0,
    reason: str | None = None,
    model: str = "qwen3:8b",
) -> SimpleNamespace:
    namespace: dict[str, object] = {
        "answer": answer,
        "sources": sources or [],
        "model": model,
    }
    if outcome is not None:
        namespace["outcome"] = outcome
    if citations is not None:
        namespace["citations"] = citations
    if invalid is not None:
        namespace["invalid_citations"] = invalid
    if duplicates:
        namespace["duplicate_citations"] = duplicates
    if reason is not None:
        namespace["abstention_reason"] = reason
    return SimpleNamespace(**namespace)


def _fake_workflow_factory(result: SimpleNamespace) -> type[object]:
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
            return result

    return FakeQAWorkflow


@pytest.mark.parametrize("outcome", ["answered", None])
def test_cli_ask_answered_outcome_renders_answer_and_sources(
    monkeypatch: pytest.MonkeyPatch, outcome: str | None
) -> None:
    result = _qa_result(
        answer="AI stands for artificial intelligence.",
        sources=[
            SimpleNamespace(
                score=0.5,
                source="ai.md",
                source_type="markdown",
                text="AI is artificial intelligence.",
            )
        ],
        outcome=outcome,
    )
    monkeypatch.setattr(entry, "QAWorkflow", _fake_workflow_factory(result))

    cli_result = runner.invoke(entry.cli, ["ask", "What is AI?", "--top-k", "3"])

    assert cli_result.exit_code == 0
    assert "Answer: What is AI?" in cli_result.output
    assert "AI stands for artificial intelligence." in cli_result.output
    assert "Sources" in cli_result.output
    assert "ai.md" in cli_result.output


def test_cli_ask_renders_cited_sources_with_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _qa_result(
        answer="AI is covered in [SOURCE 1].",
        sources=[],
        citations=[
            SimpleNamespace(
                number=1,
                hit=SimpleNamespace(
                    source="C:\\vault\\ai.md",
                    source_type="markdown",
                    score=0.42,
                    text="AI is artificial intelligence.",
                    metadata={"heading": "History"},
                ),
            )
        ],
    )
    monkeypatch.setattr(entry, "QAWorkflow", _fake_workflow_factory(result))

    cli_result = runner.invoke(entry.cli, ["ask", "What is AI?"])

    assert cli_result.exit_code == 0
    assert "Sources" in cli_result.output  # cited-sources table rendered
    assert "ai.md" in cli_result.output  # basename of the source
    assert "History" in cli_result.output  # section heading from metadata
    assert "markdown" in cli_result.output  # source type


def test_cli_ask_abstention_renders_insufficient_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _qa_result(
        answer="I don't have enough relevant information to answer.",
        sources=[],
        outcome="abstained",
        reason="no_results",
    )
    monkeypatch.setattr(entry, "QAWorkflow", _fake_workflow_factory(result))

    cli_result = runner.invoke(entry.cli, ["ask", "Can I buy a home in Denmark?"])

    assert cli_result.exit_code == 0
    assert "Insufficient evidence" in cli_result.output
    assert "I don't have enough relevant information" in cli_result.output
    assert "no_results" in cli_result.output  # abstention reason preserved


def test_cli_ask_renders_invalid_citation_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _qa_result(
        answer="The answer. [SOURCE 9]",
        sources=[SimpleNamespace(score=0.5, source="ai.md", text="AI.")],
        citations=[],
        invalid=[9],
    )
    monkeypatch.setattr(entry, "QAWorkflow", _fake_workflow_factory(result))

    cli_result = runner.invoke(entry.cli, ["ask", "What is AI?"])

    assert cli_result.exit_code == 0  # warning, not a hard failure
    assert "Invalid citations" in cli_result.output
    assert "[SOURCE 9]" in cli_result.output
    assert "no citation was renumbered" in cli_result.output
    assert "The answer." in cli_result.output  # answer text unchanged


def test_cli_ask_renders_duplicate_citation_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _qa_result(
        answer="A [SOURCE 1] B [SOURCE 1].",
        sources=[SimpleNamespace(score=0.5, source="ai.md", text="AI.")],
        citations=[SimpleNamespace(number=1, hit=SimpleNamespace(
            source="ai.md", source_type="markdown", score=0.5,
            text="AI is artificial intelligence.", metadata={"heading": "X"},
        ))],
        duplicates=1,
    )
    monkeypatch.setattr(entry, "QAWorkflow", _fake_workflow_factory(result))

    cli_result = runner.invoke(entry.cli, ["ask", "What is AI?"])

    assert cli_result.exit_code == 0
    assert "repeated citation" in cli_result.output


def test_cli_ask_labels_uncited_answer_honestly(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _qa_result(
        answer="AI stands for artificial intelligence.",
        sources=[
            SimpleNamespace(
                score=0.5, source="ai.md", source_type="markdown",
                text="AI is artificial intelligence.",
            )
        ],
    )
    monkeypatch.setattr(entry, "QAWorkflow", _fake_workflow_factory(result))

    cli_result = runner.invoke(entry.cli, ["ask", "What is AI?"])

    assert cli_result.exit_code == 0
    # Honest presentation: uncited answers are labeled, not passed off as
    # verified sources.
    assert "ANSWERED — NO CITATIONS PROVIDED" in cli_result.output
    assert "SOURCES VERIFIED" not in cli_result.output


def test_cli_ask_labels_cited_answer_as_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _qa_result(
        answer="AI is covered in [SOURCE 1].",
        citations=[
            SimpleNamespace(
                number=1,
                hit=SimpleNamespace(
                    source="ai.md", source_type="markdown", score=0.42,
                    text="AI is artificial intelligence.", metadata={"heading": "History"},
                ),
            )
        ],
    )
    monkeypatch.setattr(entry, "QAWorkflow", _fake_workflow_factory(result))

    cli_result = runner.invoke(entry.cli, ["ask", "What is AI?"])

    assert cli_result.exit_code == 0
    assert "ANSWERED — SOURCES VERIFIED" in cli_result.output
    assert "NO CITATIONS PROVIDED" not in cli_result.output


def test_cli_ask_empty_answer_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
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
        ) -> object:
            raise QAEmptyAnswerError(
                "Unable to generate an answer: the model returned an empty response."
            )

    monkeypatch.setattr(entry, "QAWorkflow", FakeQAWorkflow)

    cli_result = runner.invoke(entry.cli, ["ask", "What is AI?"])

    assert cli_result.exit_code == 1
    assert "Ask failed" in cli_result.output
    assert "empty response" in cli_result.output


def test_cli_ingest_file_generic_command_dedups_and_records_ledger(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "note.md"
    source.write_text("# Note", encoding="utf-8")
    manifest_path = tmp_path / "manifests" / "processed.json"
    monkeypatch.setenv("PAM_MANIFEST__PATH", str(manifest_path))
    calls: list[str | Path] = []

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

        def run(
            self, source_arg: str | Path, *, expected_source_type: str | None,
        ) -> SimpleNamespace:
            assert expected_source_type is None  # generic auto-detect
            calls.append(source_arg)
            return _workflow_result(tmp_path)

    monkeypatch.setattr(entry, "IngestionWorkflow", FakeWorkflow)

    result = runner.invoke(entry.cli, ["ingest", "file", str(source)])

    assert result.exit_code == 0
    assert "Ingestion Complete" in result.output
    assert "Chunks indexed" in result.output
    assert calls == [source]

    # A re-drop of identical content is skipped and recorded as a duplicate.
    result2 = runner.invoke(entry.cli, ["ingest", "file", str(source)])

    assert result2.exit_code == 0
    assert "Ingest skipped (duplicate)" in result2.output
    assert calls == [source]  # workflow not re-run

    manager = ManifestManager(manifest_path, project_root=tmp_path)
    assert [entry.status for entry in manager.list_entries()] == [
        "processed",
        "skipped_duplicate",
    ]


def test_cli_ingest_file_records_failure_in_ledger(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "note.md"
    source.write_text("# Note", encoding="utf-8")
    manifest_path = tmp_path / "manifests" / "processed.json"
    monkeypatch.setenv("PAM_MANIFEST__PATH", str(manifest_path))

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

        def run(
            self, source_arg: str | Path, *, expected_source_type: str | None,
        ) -> SimpleNamespace:
            raise entry.IngestionWorkflowError("unsupported content")

    monkeypatch.setattr(entry, "IngestionWorkflow", FakeWorkflow)

    result = runner.invoke(entry.cli, ["ingest", "file", str(source)])

    assert result.exit_code == 1
    assert "Processing failed" in result.output

    manager = ManifestManager(manifest_path, project_root=tmp_path)
    assert manager.count() == 1
    entry_out = manager.list_entries()[0]
    assert entry_out.status == "failed"
    assert "IngestionWorkflowError" in entry_out.error_reason


def test_cli_status_shows_durable_ledger_counts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_runtime_env_overrides(monkeypatch, tmp_path)
    monkeypatch.setenv("PAM_PATHS__MANIFEST_ROOT", str(tmp_path / "manifests"))

    vault = tmp_path / "vault" / "Notes"
    vault.mkdir(parents=True)

    manifest_path = tmp_path / "manifests" / "processed.json"
    manager = ManifestManager(manifest_path, project_root=tmp_path)
    source = tmp_path / "inbox" / "x.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# x", encoding="utf-8")
    (vault / "A.md").write_text(
        "---\ntitle: A\nsource: " + str(source).replace("\\", "\\\\") + "\nsource_type: markdown\n---\n# A",
        encoding="utf-8",
    )
    digest = manager.hash_for_path(source)
    manager.add_processed_file(path=source, sha256=digest, extension=".md")
    manager.add_processed_file(path=source, sha256=digest, extension=".md", status="skipped_duplicate")
    manager.add_failed_file(path=source, sha256=digest, extension=".md", error_reason="boom")
    manager.save()
    (tmp_path / "manifests" / "vector_store.json").write_text(
        '{"entries":[{},{}]}', encoding="utf-8",
    )

    result = runner.invoke(entry.cli, ["status"])

    assert result.exit_code == 0
    assert "PAM Status (read-only)" in result.output
    ledger_rows = [
        line for line in result.output.splitlines() if "Durable ledger" in line
    ]
    assert len(ledger_rows) == 4  # manifest entries, processed, skipped, failed
    manifest_row = next(
        line for line in ledger_rows if "Manifest entries" in line
    )
    assert "3" in manifest_row  # processed + skipped + failed
    assert all("1" in row for row in ledger_rows if "Manifest" not in row)
    chunk_row = next(line for line in result.output.splitlines() if "Indexed chunks" in line)
    assert "2" in chunk_row  # vector store holds two entries
    note_row = next(line for line in result.output.splitlines() if "Real generated notes" in line)
    assert "1" in note_row


def _set_runtime_env_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
