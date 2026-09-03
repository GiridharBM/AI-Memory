"""Tests for the deterministic System Facts layer (Phase 6I-B)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.application.qa_workflow import ORIGIN_SYSTEM, OUTCOME_ANSWERED, QAAnswer, QAWorkflow
from app.application.system_facts import (
    Intent,
    SystemFactsRouter,
    SystemFactsService,
)


def _fake_settings(tmp_path: Path) -> SimpleNamespace:
    """Build a minimal settings namespace for SystemFactsService."""
    manifest_path = tmp_path / "processed_files.json"
    return SimpleNamespace(
        paths=SimpleNamespace(
            project_root=tmp_path,
            manifest_root=tmp_path,
        ),
        manifest=SimpleNamespace(path=manifest_path, enabled=True),
        app=SimpleNamespace(name="personal-ai-memory", environment="development"),
        ollama=SimpleNamespace(model="qwen3:8b"),
        models=SimpleNamespace(embeddings="nomic-embed-text"),
        qa=SimpleNamespace(timeout_seconds=120),
        reranker=SimpleNamespace(enabled=False),
        hyde=SimpleNamespace(enabled=False),
        answerability=SimpleNamespace(enabled=False),
        watcher=SimpleNamespace(supported_extensions=[".md", ".pdf", ".txt"]),
    )


def _write_vector_store(tmp_path: Path, entries: list[dict]) -> None:
    (tmp_path / "vector_store.json").write_text(
        json.dumps({"entries": entries}), encoding="utf-8"
    )


def _write_pyproject(tmp_path: Path, version: str = "1.0.0") -> None:
    (tmp_path / "pyproject.toml").write_text(
        f"[project]\nversion = \"{version}\"\n", encoding="utf-8"
    )


@pytest.fixture
def router() -> SystemFactsRouter:
    return SystemFactsRouter()


def test_router_version_query(router: SystemFactsRouter) -> None:
    assert router.route("What version of PAM am I running?") == Intent.VERSION


def test_router_source_count_query(router: SystemFactsRouter) -> None:
    assert router.route("How many sources are indexed?") == Intent.SOURCE_COUNT


def test_router_documents_indexed_query(router: SystemFactsRouter) -> None:
    assert router.route("How many documents are indexed?") == Intent.SOURCE_COUNT


def test_router_chunk_count_query(router: SystemFactsRouter) -> None:
    assert router.route("How many chunks are indexed?") == Intent.CHUNK_COUNT


def test_router_feature_status_query(router: SystemFactsRouter) -> None:
    assert router.route("Is the reranker enabled?") == Intent.FEATURE_STATUS


def test_router_qa_model_query(router: SystemFactsRouter) -> None:
    assert router.route("What model answers my questions?") == Intent.QA_MODEL


def test_router_qa_model_pam_phrasing(router: SystemFactsRouter) -> None:
    # Regression: "What QA model is PAM using?" (intervening "QA") must be
    # intercepted (Phase 6I-C cleanup).
    assert router.route("What QA model is PAM using?") == Intent.QA_MODEL


def test_router_generic_qa_model_not_intercepted(router: SystemFactsRouter) -> None:
    # A generic knowledge question about "QA model" (no self/tool signal) must
    # NOT be hijacked by System Facts.
    assert router.route("What is QA model evaluation?") is None
    assert router.route("How does QA model the text?") is None


def test_router_capabilities_query(router: SystemFactsRouter) -> None:
    assert router.route("What can PAM ingest?") == Intent.CAPABILITIES


def test_router_status_query(router: SystemFactsRouter) -> None:
    assert router.route("What is the PAM status?") == Intent.STATUS


def test_normal_knowledge_question_bypasses(router: SystemFactsRouter) -> None:
    assert router.route("What is PAM?") is None
    assert router.route("What did I learn about Docker?") is None
    assert router.route("When was Utthunga founded?") is None


def test_unrelated_question_bypasses(router: SystemFactsRouter) -> None:
    assert router.route("How do I make a good cup of coffee?") is None


def test_ambiguous_question_not_intercepted(router: SystemFactsRouter) -> None:
    # "how many questions" is about the DAA assignment, not indexed chunks.
    assert router.route("How many questions does the DAA assignment contain?") is None


def test_malformed_or_unknown_query_falls_through(router: SystemFactsRouter) -> None:
    assert router.route("") is None
    assert router.route(None) is None  # type: ignore[arg-type]
    assert router.route("zzz") is None
    assert router.route("!@#$%") is None


def test_service_facts_do_not_expose_secrets(tmp_path: Path) -> None:
    _write_pyproject(tmp_path)
    _write_vector_store(tmp_path, [{"source": "a.md"}, {"source": "b.md"}])
    svc = SystemFactsService(_fake_settings(tmp_path))
    value = svc.resolve(Intent.VERSION).answer
    assert "secret" not in value.lower()
    assert "api_key" not in value.lower()
    assert "token" not in value.lower()
    assert "password" not in value.lower()


def test_service_version_from_pyproject(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, "9.9.9")
    svc = SystemFactsService(_fake_settings(tmp_path))
    assert "9.9.9" in svc.resolve(Intent.VERSION).answer


def test_service_source_count(tmp_path: Path) -> None:
    _write_pyproject(tmp_path)
    _write_vector_store(
        tmp_path,
        [{"source": "a.md"}, {"source": "a.md"}, {"source": "b.md"}],
    )
    svc = SystemFactsService(_fake_settings(tmp_path))
    assert svc.resolve(Intent.SOURCE_COUNT).value.startswith("2 source")


def test_service_chunk_count(tmp_path: Path) -> None:
    _write_pyproject(tmp_path)
    _write_vector_store(tmp_path, [{"source": "a.md"}] * 4)
    svc = SystemFactsService(_fake_settings(tmp_path))
    assert svc.resolve(Intent.CHUNK_COUNT).value.startswith("4 chunk")


def test_service_chunk_count_unavailable(tmp_path: Path) -> None:
    _write_pyproject(tmp_path)
    svc = SystemFactsService(_fake_settings(tmp_path))
    assert svc.resolve(Intent.CHUNK_COUNT).value == "unavailable chunk(s) indexed"


def test_service_feature_status_all_off(tmp_path: Path) -> None:
    _write_pyproject(tmp_path)
    svc = SystemFactsService(_fake_settings(tmp_path))
    assert "none" in svc.resolve(Intent.FEATURE_STATUS).value


def test_service_feature_status_reflects_config(tmp_path: Path) -> None:
    _write_pyproject(tmp_path)
    settings = _fake_settings(tmp_path)
    settings.hyde.enabled = True
    svc = SystemFactsService(settings)
    assert "HyDE" in svc.resolve(Intent.FEATURE_STATUS).value


def test_service_qa_model(tmp_path: Path) -> None:
    _write_pyproject(tmp_path)
    svc = SystemFactsService(_fake_settings(tmp_path))
    assert "qwen3:8b" in svc.resolve(Intent.QA_MODEL).answer


def test_service_capabilities(tmp_path: Path) -> None:
    _write_pyproject(tmp_path)
    svc = SystemFactsService(_fake_settings(tmp_path))
    assert "PAM can ingest" in svc.resolve(Intent.CAPABILITIES).answer


def test_unknown_intent_raises(tmp_path: Path) -> None:
    _write_pyproject(tmp_path)
    svc = SystemFactsService(_fake_settings(tmp_path))
    with pytest.raises(ValueError):
        svc.resolve("not-an-intent")  # type: ignore[arg-type]


class FakeSearchService:
    def __init__(self) -> None:
        self.calls = 0

    def search(self, *_a, **_k) -> list:
        self.calls += 1
        return []


class FakeOllamaClient:
    def __init__(self) -> None:
        self.calls = 0

    def generate_text(self, *_a, **_k):
        self.calls += 1
        raise AssertionError("LLM must not be called for system facts")


def _workflow_with_system_facts(
    tmp_path: Path,
) -> tuple[QAWorkflow, FakeSearchService, FakeOllamaClient]:
    _write_pyproject(tmp_path)
    _write_vector_store(tmp_path, [{"source": "a.md"}])
    svc = SystemFactsService(_fake_settings(tmp_path))
    search = FakeSearchService()
    client = FakeOllamaClient()
    workflow = QAWorkflow(search, client, system_facts=svc)
    return workflow, search, client


def test_system_facts_no_llm_no_retrieval(tmp_path: Path) -> None:
    workflow, search, client = _workflow_with_system_facts(tmp_path)
    result = workflow.ask("What version of PAM am I running?")
    assert isinstance(result, QAAnswer)
    assert result.origin == ORIGIN_SYSTEM
    assert result.outcome == OUTCOME_ANSWERED
    assert result.sources == []
    assert result.citations == []
    assert search.calls == 0
    assert client.calls == 0


def test_normal_question_bypasses_system_facts_and_uses_retrieval(tmp_path: Path) -> None:
    # Without a client that raises, we patch the search to return hits and let
    # the LLM be reached; here we only assert the router did not match by
    # checking search IS called (system facts would have short-circuited it).
    svc = SystemFactsService(_fake_settings(tmp_path))
    search = FakeSearchService()
    client = FakeOllamaClient()
    workflow = QAWorkflow(search, client, system_facts=svc)
    result = workflow.ask("When was Utthunga founded?")
    assert result.origin != ORIGIN_SYSTEM
    assert search.calls == 1


def test_system_facts_never_fabricates_citations(tmp_path: Path) -> None:
    workflow, search, client = _workflow_with_system_facts(tmp_path)
    result = workflow.ask("How many chunks are indexed?")
    assert result.invalid_citations == []
    assert result.citations == []
    assert result.sources == []


def test_qa_model_query_intercepted_no_llm_no_retrieval(tmp_path: Path) -> None:
    # Regression (Phase 6I-C cleanup): "What QA model is PAM using?" must be
    # answered by System Facts with origin="system", the correct model, and no
    # retrieval / LLM / network calls.
    workflow, search, client = _workflow_with_system_facts(tmp_path)
    result = workflow.ask("What QA model is PAM using?")
    assert isinstance(result, QAAnswer)
    assert result.origin == ORIGIN_SYSTEM
    assert result.outcome == OUTCOME_ANSWERED
    assert "qwen3:8b" in result.answer
    assert result.sources == []
    assert result.citations == []
    assert result.invalid_citations == []
    assert search.calls == 0
    assert client.calls == 0


def test_machine_learning_question_not_intercepted(tmp_path: Path) -> None:
    # Nearby normal knowledge question must still bypass System Facts and use
    # normal QA (search is called; origin is not "system").
    svc = SystemFactsService(_fake_settings(tmp_path))
    search = FakeSearchService()
    client = FakeOllamaClient()
    workflow = QAWorkflow(search, client, system_facts=svc)
    result = workflow.ask("What did I learn about machine learning?")
    assert result.origin != ORIGIN_SYSTEM
    assert search.calls == 1
