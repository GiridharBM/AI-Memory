"""Tests for Phase 6A QA generation timeout guard."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.application.qa_workflow import QAError, QATimeoutError, QAWorkflow
from app.core.config import (
    AppSettings,
    LoggingSettings,
    OllamaSettings,
    PathSettings,
    QaSettings,
    Settings,
)
from app.infrastructure.llm import (
    OllamaClientError,
    OllamaRequest,
    OllamaTextResponse,
    OllamaTimeoutError,
)
from app.infrastructure.search import SearchHit


class FakeSearchService:
    def __init__(self, hits: list[SearchHit] | None = None) -> None:
        self.hits = hits or []

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filter: dict[str, object] | None = None,
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        return self.hits


class FakeOllamaClient:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    def generate_text(self, request: OllamaRequest) -> OllamaTextResponse:
        if self.error is not None:
            raise self.error
        return OllamaTextResponse(model="qwen3:8b", response="answer", raw={})


def _hit() -> SearchHit:
    return SearchHit(
        text="Python is a programming language.",
        source="doc.md",
        score=0.5,
        entry_id="doc.md::chunk_0",
        cosine_score=0.5,
        bm25_score=0.5,
        source_type="markdown",
        metadata={},
    )


def _settings(tmp_path: Path, *, qa_timeout: int = 120, ollama_timeout: int = 300) -> Settings:
    return Settings(
        app=AppSettings(),
        paths=PathSettings(
            project_root=tmp_path,
            vault_root=tmp_path / "vault",
            inbox_root=tmp_path / "inbox",
            staging_root=tmp_path / "staging",
            manifest_root=tmp_path / "manifests",
            cache_root=tmp_path / "cache",
            log_root=tmp_path / "logs",
        ),
        ollama=OllamaSettings(timeout_seconds=ollama_timeout),
        logging=LoggingSettings(console_enabled=False, file_enabled=False),
        qa=QaSettings(timeout_seconds=qa_timeout),
    )


def test_qa_settings_default_timeout() -> None:
    assert QaSettings().timeout_seconds == 120


def test_qa_timeout_is_distinct_from_unavailable() -> None:
    search = FakeSearchService([_hit()])

    timeout_workflow = QAWorkflow(
        search, FakeOllamaClient(error=OllamaTimeoutError("timed out after 120 seconds")),
    )
    with pytest.raises(QATimeoutError, match="timed out"):
        timeout_workflow.ask("What is Python?")

    unavailable_workflow = QAWorkflow(
        search, FakeOllamaClient(error=OllamaClientError("connection refused")),
    )
    with pytest.raises(QAError) as excinfo:
        unavailable_workflow.ask("What is Python?")
    assert not isinstance(excinfo.value, QATimeoutError)
    assert "unavailable" in str(excinfo.value)


def test_qa_timeout_error_is_qa_error_subclass() -> None:
    assert issubclass(QATimeoutError, QAError)


def test_create_default_applies_qa_timeout_to_generation_client_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import app.application.qa_workflow as qa_module

    captured: list[Settings] = []

    class FakeClient:
        def __init__(self, settings: Settings) -> None:
            captured.append(settings)

    class FakeSearchService:
        @classmethod
        def create_default(cls, settings: Settings) -> object:
            return object()

    monkeypatch.setattr(qa_module, "SearchService", FakeSearchService)
    monkeypatch.setattr(qa_module, "OllamaClient", FakeClient)

    settings = _settings(tmp_path, qa_timeout=60, ollama_timeout=300)
    QAWorkflow.create_default(settings)

    # Generation client first (bounded by qa.timeout_seconds), gate client
    # second (keeps the default ollama timeout).
    assert [client.timeout_seconds for client in captured] == [60, 300]