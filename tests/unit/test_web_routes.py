"""Tests for the GUI HTTP adapter (app/interfaces/web/).

These cover the adapter's contract only — that it projects authoritative PAM
state faithfully and never invents a value. Retrieval, BM25, RRF, QA and
abstention themselves are covered by the existing core test suite and are not
re-tested here.

Every test is hermetic: settings point at tmp_path and the LLM, embedding and
network paths are stubbed, so nothing here touches durable state or a live
Ollama server.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.application.qa_workflow import OUTCOME_ABSTAINED, OUTCOME_ANSWERED, QAAnswer
from app.core.config import Settings
from app.infrastructure.search import SearchHit
from app.interfaces.web import deps
from app.interfaces.web.server import create_app


def _write_store(root: Path, entries: list[dict[str, Any]]) -> None:
    manifests = root / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "vector_store.json").write_text(
        json.dumps({"version": 1, "entries": entries}), encoding="utf-8"
    )


def _entry(source: str, source_type: str, index: int, text: str = "chunk body") -> dict[str, Any]:
    return {
        "id": f"{source}#{index}",
        "text": text,
        "embedding": [0.1, 0.2],
        "source": source,
        "source_type": source_type,
        "chunk_index": index,
        "start_char": index * 100,
        "end_char": index * 100 + 80,
        "metadata": {"heading": f"Section {index}"},
    }


@pytest.fixture()
def client(tmp_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A TestClient bound to temporary settings with every cache cleared."""

    # Captured before patching so teardown can still clear the real lru_caches.
    cached = (
        deps.get_settings,
        deps.get_search_service,
        deps.get_qa_workflow,
        deps.get_vector_store,
    )

    def _clear() -> None:
        for fn in cached:
            fn.cache_clear()
        monkeypatch.setattr(deps, "_health_cache", None)

    _clear()
    monkeypatch.setattr(deps, "get_settings", lambda: tmp_settings)
    # Never touch a real Ollama server from a unit test.
    monkeypatch.setattr(
        deps,
        "ollama_health",
        lambda **_kwargs: {
            "reachable": True,
            "model_present": True,
            "model": tmp_settings.ollama.model,
            "detail": str(tmp_settings.ollama.host),
        },
    )
    yield TestClient(create_app())
    _clear()


class TestSystemEndpoint:
    def test_reports_counts_from_the_persisted_store(self, client: TestClient) -> None:
        settings = deps.get_settings()
        _write_store(
            settings.paths.project_root,
            [
                _entry("a.md", "markdown", 0),
                _entry("a.md", "markdown", 1),
                _entry("b.pdf", "pdf", 0),
            ],
        )

        body = client.get("/api/system").json()

        assert body["config_ok"] is True
        assert body["metrics"]["sources"] == 2
        assert body["metrics"]["chunks"] == 3
        assert body["state"] == "healthy"

    def test_unreadable_store_yields_null_not_zero(self, client: TestClient) -> None:
        """A store PAM cannot read must never be reported as an empty corpus."""

        manifests = deps.get_settings().paths.manifest_root
        manifests.mkdir(parents=True, exist_ok=True)
        (manifests / "vector_store.json").write_text("{ not json", encoding="utf-8")

        body = client.get("/api/system").json()

        assert body["metrics"]["sources"] is None
        assert body["metrics"]["chunks"] is None
        assert body["health"]["vector_store"]["status"] == "unavailable"

    def test_empty_store_is_reported_as_zero_sources(self, client: TestClient) -> None:
        _write_store(deps.get_settings().paths.project_root, [])

        body = client.get("/api/system").json()

        assert body["metrics"]["sources"] == 0
        assert body["metrics"]["chunks"] == 0

    def test_disabled_feature_flags_are_never_shown_as_active(self, client: TestClient) -> None:
        """reranker / HyDE / answerability default to off; the API must say so."""

        _write_store(deps.get_settings().paths.project_root, [])
        settings = deps.get_settings()
        assert settings.reranker.enabled is False
        assert settings.hyde.enabled is False
        assert settings.answerability.enabled is False

        body = client.get("/api/system").json()
        stages = {stage["id"]: stage for stage in body["retrieval"]["stages"]}

        assert stages["rerank"]["active"] is False
        assert stages["hyde"]["active"] is False
        assert stages["answerability"]["active"] is False
        # The always-on retrieval legs must still be reported.
        assert stages["semantic"]["active"] is True
        assert stages["bm25"]["active"] is True
        assert stages["rrf"]["active"] is True
        assert body["retrieval"]["rrf_k"] == 60

    def test_health_endpoint_reports_degraded_when_runtime_is_down(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            deps,
            "ollama_health",
            lambda **_kwargs: {
                "reachable": False,
                "model_present": None,
                "model": "qwen3:8b",
                "detail": "could not reach host",
            },
        )

        response = client.get("/api/health")

        assert response.status_code == 200
        assert response.json()["state"] == "degraded"
        assert client.get("/api/system").json()["state"] == "degraded"


class TestSourcesEndpoint:
    def test_lists_sources_with_types_and_chunk_counts(self, client: TestClient) -> None:
        _write_store(
            deps.get_settings().paths.project_root,
            [
                _entry("a.md", "markdown", 0),
                _entry("a.md", "markdown", 1),
                _entry("b.pdf", "pdf", 0),
            ],
        )

        body = client.get("/api/sources").json()

        assert body["available"] is True
        assert body["total"] == 2
        assert body["total_chunks"] == 3
        assert dict(body["by_type"]) == {"markdown": 2, "pdf": 1}
        assert {s["name"] for s in body["sources"]} == {"a.md", "b.pdf"}

    def test_empty_store_lists_nothing(self, client: TestClient) -> None:
        _write_store(deps.get_settings().paths.project_root, [])
        body = client.get("/api/sources").json()
        assert body["available"] is True
        assert body["total"] == 0
        assert body["sources"] == []

    def test_detail_exposes_chunk_text(self, client: TestClient) -> None:
        _write_store(
            deps.get_settings().paths.project_root,
            [_entry("a.md", "markdown", 0, "first chunk"), _entry("a.md", "markdown", 1, "second")],
        )
        source_id = client.get("/api/sources").json()["sources"][0]["id"]

        body = client.get(f"/api/sources/{source_id}").json()

        assert body["chunk_count"] == 2
        assert [chunk["text"] for chunk in body["chunks"]] == ["first chunk", "second"]

    def test_corrupt_ledger_is_unavailable_and_not_rewritten(
        self, client: TestClient
    ) -> None:
        """A read must not quarantine or recreate a corrupt ledger."""
        _write_store(deps.get_settings().paths.project_root, [_entry("a.md", "markdown", 0)])
        manifest = deps.get_settings().manifest.path
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("{ broken", encoding="utf-8")

        response = client.get("/api/sources")

        assert response.status_code == 503
        assert "ledger" in response.json()["detail"].lower()
        assert manifest.read_text(encoding="utf-8") == "{ broken"
        assert [p.name for p in manifest.parent.glob(f"{manifest.name}*")] == [
            manifest.name
        ]

    def test_corrupt_ledger_does_not_fabricate_a_detail_404(
        self, client: TestClient
    ) -> None:
        _write_store(deps.get_settings().paths.project_root, [_entry("a.md", "markdown", 0)])
        from app.interfaces.web.routes.knowledge import source_id

        source_id_value = source_id("a.md")
        manifest = deps.get_settings().manifest.path
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("{ broken", encoding="utf-8")

        response = client.get(f"/api/sources/{source_id_value}")

        # 503 (unavailable), never a fabricated 404 "Source not found".
        assert response.status_code == 503

    def test_missing_ledger_lists_sources_without_creating_it(
        self, client: TestClient
    ) -> None:
        _write_store(deps.get_settings().paths.project_root, [_entry("a.md", "markdown", 0)])
        manifest = deps.get_settings().manifest.path
        assert not manifest.exists()

        body = client.get("/api/sources").json()

        assert body["available"] is True
        assert {s["name"] for s in body["sources"]} == {"a.md"}
        assert not manifest.exists()

    def test_detail_404s_for_unknown_id(self, client: TestClient) -> None:
        _write_store(deps.get_settings().paths.project_root, [])
        assert client.get("/api/sources/deadbeef").status_code == 404


class TestSearchEndpoint:
    def test_passes_real_scores_through(self, client: TestClient, monkeypatch) -> None:
        hit = SearchHit(
            text="body",
            source="a.md",
            score=0.0325,
            entry_id="a.md#0",
            cosine_score=0.61,
            bm25_score=2.5,
            source_type="markdown",
        )
        monkeypatch.setattr(
            deps, "get_search_service", lambda: type("S", (), {"search": lambda *_a, **_k: [hit]})()
        )

        body = client.post("/api/search", json={"query": "anything", "top_k": 1}).json()

        assert body["count"] == 1
        assert body["latency_seconds"] is not None
        result = body["results"][0]
        assert result["score"] == pytest.approx(0.0325)
        assert result["cosine_score"] == pytest.approx(0.61)
        assert result["bm25_score"] == pytest.approx(2.5)

    def test_absent_rerank_score_is_null_not_zero(self, client: TestClient, monkeypatch) -> None:
        """0.0 is the "reranker did not score this" sentinel, so it maps to null."""

        hit = SearchHit(text="b", source="a.md", score=0.01, entry_id="e", rerank_score=0.0)
        monkeypatch.setattr(
            deps, "get_search_service", lambda: type("S", (), {"search": lambda *_a, **_k: [hit]})()
        )

        result = client.post("/api/search", json={"query": "q"}).json()["results"][0]

        assert result["rerank_score"] is None

    def test_rejects_empty_query(self, client: TestClient) -> None:
        assert client.post("/api/search", json={"query": ""}).status_code == 422


class TestAskEndpoint:
    def test_surfaces_citations_and_outcome(self, client: TestClient, monkeypatch) -> None:
        hit = SearchHit(text="body", source="a.md", score=0.04, entry_id="a.md#0", cosine_score=0.7)
        answer = QAAnswer(
            answer="Because [SOURCE 1].",
            sources=[hit],
            model="qwen3:8b",
            outcome=OUTCOME_ANSWERED,
            citations=[type("C", (), {"number": 1, "hit": hit})()],
            latency_seconds=1.25,
        )
        monkeypatch.setattr(
            deps, "get_qa_workflow", lambda: type("W", (), {"ask": lambda *_a, **_k: answer})()
        )

        body = client.post("/api/ask", json={"question": "why?"}).json()

        assert body["outcome"] == "answered"
        assert body["origin"] == "retrieval"
        assert body["citations"][0]["number"] == 1
        assert body["latency_seconds"] == pytest.approx(1.25)

    def test_abstention_is_distinguishable_from_a_failure(
        self, client: TestClient, monkeypatch
    ) -> None:
        answer = QAAnswer(
            answer="I don't have enough relevant information…",
            sources=[],
            outcome=OUTCOME_ABSTAINED,
            abstention_reason="cosine_below_threshold",
        )
        monkeypatch.setattr(
            deps, "get_qa_workflow", lambda: type("W", (), {"ask": lambda *_a, **_k: answer})()
        )

        body = client.post("/api/ask", json={"question": "unknown?"}).json()

        assert body["outcome"] == "abstained"
        assert body["abstention_reason"] == "cosine_below_threshold"
        assert body["sources"] == []

    def test_system_facts_answer_has_no_citations(self, client: TestClient, monkeypatch) -> None:
        answer = QAAnswer(answer="31 source(s) indexed (vector store)", origin="system")
        monkeypatch.setattr(
            deps, "get_qa_workflow", lambda: type("W", (), {"ask": lambda *_a, **_k: answer})()
        )

        body = client.post("/api/ask", json={"question": "how many sources?"}).json()

        assert body["origin"] == "system"
        assert body["citations"] == []

    def test_qa_failure_becomes_502_not_an_answer(self, client: TestClient, monkeypatch) -> None:
        from app.application.qa_workflow import QATimeoutError

        def _boom(*_args, **_kwargs):
            raise QATimeoutError("timed out")

        monkeypatch.setattr(deps, "get_qa_workflow", lambda: type("W", (), {"ask": _boom})())

        response = client.post("/api/ask", json={"question": "q"})

        assert response.status_code == 502
        assert "timed out" in response.json()["detail"]


class TestActivityAndLedger:
    def test_activity_is_scoped_to_ingestion(self, client: TestClient) -> None:
        manifest = deps.get_settings().manifest.path
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(
                {
                    "version": 1,
                    "files": [
                        {
                            "sha256": "abc",
                            "original_filename": "doc.md",
                            "original_path": "inbox/doc.md",
                            "processed_at": "2026-01-02T03:04:05Z",
                            "extension": ".md",
                            "status": "processed",
                            "chunks_stored": 4,
                        },
                        {
                            "sha256": "def",
                            "original_filename": "bad.pdf",
                            "original_path": "inbox/bad.pdf",
                            "processed_at": "2026-01-03T00:00:00Z",
                            "extension": ".pdf",
                            "status": "failed",
                            "error_reason": "boom",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        body = client.get("/api/activity").json()

        assert body["scope"] == "ingestion"
        assert body["total"] == 2
        # Newest first.
        assert body["events"][0]["filename"] == "bad.pdf"
        assert body["events"][0]["error_reason"] == "boom"

    def test_missing_manifest_is_empty_not_unavailable(self, client: TestClient) -> None:
        body = client.get("/api/activity").json()
        assert body["available"] is True
        assert body["events"] == []

    def test_corrupt_manifest_is_reported_unavailable(self, client: TestClient) -> None:
        manifest = deps.get_settings().manifest.path
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("{ broken", encoding="utf-8")

        assert client.get("/api/activity").json()["available"] is False


class TestConfigAndEvaluation:
    def test_config_is_a_faithful_projection_of_settings(self, client: TestClient) -> None:
        body = client.get("/api/config").json()

        assert body["available"] is True
        assert body["config"] == json.loads(deps.get_settings().model_dump_json())

    def test_evaluation_lists_real_artifacts_only(self, client: TestClient, tmp_path) -> None:
        results = deps.get_settings().paths.project_root / "eval" / "results"
        results.mkdir(parents=True, exist_ok=True)
        (results / "baseline_v1.json").write_text("{}", encoding="utf-8")

        body = client.get("/api/evaluation").json()

        assert body["artifact_count"] == 1
        assert body["artifacts"][0]["name"] == "baseline_v1.json"
        # No runtime evaluation service exists, so metrics must not be implied.
        assert body["runtime_metrics_available"] is False


class TestStaticSpa:
    """Static file serving is an input->filesystem trust boundary."""

    @staticmethod
    def _client_for(dist: Path) -> Any:
        """Build a TestClient whose ``_frontend_dist`` is a throwaway directory."""

        from app.interfaces.web import server as server_module

        original = server_module._frontend_dist
        server_module._frontend_dist = lambda: dist
        try:
            return server_module.create_app()
        finally:
            server_module._frontend_dist = original

    @staticmethod
    def _raw_get(app: Any, path: str) -> str:
        """GET an un-normalized path straight through the ASGI app.

        An HTTP client collapses ``..`` before the request is sent, so the
        traversal cases below must bypass the client to reach the handler.
        Returns the response body whatever the status: a 404 from the
        ``/assets`` mount is as safe as the SPA fallback, and both are fine.
        """

        import asyncio

        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "headers": [(b"host", b"testserver")],
        }
        chunks: list[bytes] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))

        asyncio.run(app(scope, receive, send))
        return b"".join(chunks).decode("utf-8", "replace")

    @staticmethod
    def _build_dist(tmp_path: Path) -> Path:
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<!doctype html><title>PAM</title>", encoding="utf-8")
        (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
        return dist

    def test_serves_built_index_and_assets(self, tmp_path: Path) -> None:
        app = self._client_for(self._build_dist(tmp_path))
        client = TestClient(app)

        assert "PAM" in client.get("/").text
        assert client.get("/assets/app.js").text == "console.log(1)"

    def test_client_route_falls_back_to_index(self, tmp_path: Path) -> None:
        app = self._client_for(self._build_dist(tmp_path))
        assert "PAM" in TestClient(app).get("/memories").text

    def test_refuses_to_escape_the_build_directory(self, tmp_path: Path) -> None:
        """A path that resolves outside dist/ must never be served as a file."""

        dist = self._build_dist(tmp_path)
        (tmp_path / "secret.txt").write_text("TOP SECRET", encoding="utf-8")
        app = self._client_for(dist)

        for attack in (
            "/../secret.txt",
            "/../../secret.txt",
            "/assets/../../secret.txt",
            "/./../secret.txt",
        ):
            assert "TOP SECRET" not in self._raw_get(app, attack), attack

    def test_sibling_prefix_directory_is_not_served(self, tmp_path: Path) -> None:
        """`dist-secrets` shares a string prefix with `dist` but is outside it.

        This is the case a ``str.startswith`` containment check gets wrong.
        """

        dist = self._build_dist(tmp_path)
        sibling = tmp_path / "dist-secrets"
        sibling.mkdir()
        (sibling / "leak.txt").write_text("LEAKED", encoding="utf-8")

        body = self._raw_get(self._client_for(dist), "/../dist-secrets/leak.txt")

        assert "LEAKED" not in body


class TestIngestEndpoint:
    def test_duplicate_is_skipped_without_touching_the_corpus(
        self, client: TestClient, monkeypatch
    ) -> None:
        from app.infrastructure.state.manifest import ManifestManager

        settings = deps.get_settings()
        source = settings.paths.project_root / "note.md"
        source.write_text("# hello", encoding="utf-8")

        manifest = ManifestManager(
            settings.manifest.path,
            project_root=settings.paths.project_root,
            enabled=settings.manifest.enabled,
        )
        manifest.add_processed_file(
            path=source, sha256=manifest.hash_for_path(source), extension=".md"
        )
        manifest.save()

        def _must_not_run(*_args, **_kwargs):
            raise AssertionError("the ingestion workflow must not run for a duplicate")

        monkeypatch.setattr(
            "app.interfaces.web.routes.interact.IngestionWorkflow.create_default", _must_not_run
        )

        with source.open("rb") as handle:
            response = client.post(
                "/api/ingest", files={"file": ("note.md", handle, "text/markdown")}
            )

        assert response.status_code == 200
        assert response.json()["status"] == "skipped_duplicate"

    def test_requires_a_file_or_url(self, client: TestClient) -> None:
        assert client.post("/api/ingest").status_code == 400

    def test_capabilities_come_from_the_live_registry(self, client: TestClient) -> None:
        body = client.get("/api/ingest/capabilities").json()

        assert body["available"] is True
        assert body["extension_count"] > 0
        assert {item["kind"] for item in body["url_inputs"]} == {"github", "youtube"}


class TestIngestFailedRetry:
    """D3-B: the GUI ingest path must not treat a failed non-hashable source
    as a duplicate. The defect exists independently of the CLI's."""

    @staticmethod
    def _post(client: TestClient, name: str) -> Any:
        return client.post(
            "/api/ingest", files={"file": (name, b"payload", "application/octet-stream")}
        )

    def _patch_workflow(self, monkeypatch: pytest.MonkeyPatch, behaviour: str) -> None:
        from types import SimpleNamespace

        from app.domain.documents import DocumentMetadata, SourceDocument
        from app.domain.notes import ObsidianNote
        from app.pipelines.ingest_workflow import IngestionWorkflow, IngestionWorkflowError

        if behaviour == "fail":

            def _create_default(*_args: object, **_kwargs: object) -> object:
                raise IngestionWorkflowError("upstream refused", category="unsupported")

        else:

            class _Workflow:
                @staticmethod
                def create_default(*_args: object, **_kwargs: object) -> object:
                    return _Workflow()

                def run(self, *_args: object, **_kwargs: object) -> object:
                    return SimpleNamespace(
                        document=SourceDocument(
                            source="weird.xyz",
                            source_type="unknown",
                            filename="weird.xyz",
                            text="payload",
                            metadata=DocumentMetadata(title="Weird"),
                        ),
                        note=ObsidianNote(
                            title="Weird",
                            filename="Weird.md",
                            markdown="# Weird",
                            generated_at="2026-07-08T00:00:00Z",
                            tags=["local-ai"],
                            source="weird.xyz",
                            source_type="unknown",
                        ),
                        write_result=SimpleNamespace(
                            note_path="notes/Weird.md",
                            created=True,
                            updated=False,
                        ),
                        chunks_stored=1,
                    )

            def _create_default(*_args: object, **_kwargs: object) -> object:
                return _Workflow()

        monkeypatch.setattr(
            IngestionWorkflow, "create_default", staticmethod(_create_default)
        )

    def test_failed_non_hashable_source_retries_instead_of_duplicate(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.infrastructure.state.manifest import ManifestManager

        settings = deps.get_settings()
        self._patch_workflow(monkeypatch, "fail")

        first = self._post(client, "weird.xyz")
        assert first.status_code == 502

        # The failed attempt is on disk before the retry.
        manifest = ManifestManager(
            settings.manifest.path,
            project_root=settings.paths.project_root,
            enabled=settings.manifest.enabled,
        )
        assert [e.status for e in manifest.list_entries()] == ["failed"]

        self._patch_workflow(monkeypatch, "succeed")
        second = self._post(client, "weird.xyz")

        assert second.status_code == 200
        assert second.json()["status"] == "processed"

        after = ManifestManager(
            settings.manifest.path,
            project_root=settings.paths.project_root,
            enabled=settings.manifest.enabled,
        )
        entries = after.list_entries()
        # Append-only: the failure is preserved, the retry is a new row.
        assert [e.status for e in entries] == ["failed", "processed"]
        assert entries[0].error_reason == "IngestionWorkflowError: upstream refused"

    def test_processed_non_hashable_source_still_duplicate(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Successful duplicate protection in the GUI is unchanged."""
        self._patch_workflow(monkeypatch, "succeed")
        assert self._post(client, "weird.xyz").json()["status"] == "processed"

        def _must_not_run(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("the ingestion workflow must not run for a duplicate")

        monkeypatch.setattr(
            "app.interfaces.web.routes.interact.IngestionWorkflow.create_default", _must_not_run
        )

        second = self._post(client, "weird.xyz")

        assert second.status_code == 200
        assert second.json()["status"] == "skipped_duplicate"


class TestIngestUrlIdentity:
    """D3-C: GUI URLs use the same CWD-independent exact identity as the CLI."""

    @staticmethod
    def _post_url(client: TestClient, url: str) -> Any:
        return client.post("/api/ingest", data={"url": url})

    @staticmethod
    def _patch_url_success(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
        from types import SimpleNamespace

        from app.domain.documents import DocumentMetadata, SourceDocument
        from app.domain.notes import ObsidianNote
        from app.pipelines.ingest_workflow import IngestionWorkflow

        class _Workflow:
            @staticmethod
            def create_default(*_args: object, **_kwargs: object) -> object:
                return _Workflow()

            def run(self, *_args: object, **_kwargs: object) -> object:
                return SimpleNamespace(
                    document=SourceDocument(
                        source=url,
                        source_type="github_readme",
                        filename="README.md",
                        text="# PAM",
                        metadata=DocumentMetadata(title="PAM"),
                    ),
                    note=ObsidianNote(
                        title="PAM",
                        filename="PAM.md",
                        markdown="# PAM",
                        generated_at="2026-07-08T00:00:00Z",
                        tags=["local-ai"],
                        source=url,
                        source_type="github_readme",
                    ),
                    write_result=SimpleNamespace(
                        note_path="notes/PAM.md",
                        created=True,
                        updated=False,
                    ),
                    chunks_stored=1,
                )

        monkeypatch.setattr(
            IngestionWorkflow, "create_default", staticmethod(_Workflow.create_default)
        )

    def test_successful_url_from_another_cwd_is_duplicate(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.infrastructure.state.manifest import ManifestManager

        settings = deps.get_settings()
        url = "https://github.com/example/pam"
        origin_directory = settings.paths.project_root / "origin-cwd"
        retry_directory = settings.paths.project_root / "retry-cwd"
        origin_directory.mkdir(exist_ok=True)
        retry_directory.mkdir(exist_ok=True)

        self._patch_url_success(monkeypatch, url)
        monkeypatch.chdir(origin_directory)
        first = self._post_url(client, url)
        assert first.status_code == 200
        assert first.json()["status"] == "processed"

        def _must_not_run(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("the ingestion workflow must not run for a duplicate")

        monkeypatch.setattr(
            "app.interfaces.web.routes.interact.IngestionWorkflow.create_default",
            _must_not_run,
        )
        monkeypatch.chdir(retry_directory)
        second = self._post_url(client, url)

        assert second.status_code == 200
        assert second.json()["status"] == "skipped_duplicate"
        manifest = ManifestManager(
            settings.manifest.path,
            project_root=settings.paths.project_root,
            enabled=settings.manifest.enabled,
        )
        entries = manifest.list_entries()
        assert [entry.status for entry in entries] == ["processed", "skipped_duplicate"]
        assert [entry.original_path for entry in entries] == [url, url]

    def test_padded_url_records_one_exact_identity(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.infrastructure.state.manifest import ManifestManager

        settings = deps.get_settings()
        url = "https://github.com/example/pam"

        self._patch_url_success(monkeypatch, url)
        first = self._post_url(client, f"  {url}  ")
        assert first.status_code == 200
        assert first.json()["status"] == "processed"

        self._patch_url_success(monkeypatch, url)
        second = self._post_url(client, url)
        assert second.status_code == 200
        assert second.json()["status"] == "skipped_duplicate"

        manifest = ManifestManager(
            settings.manifest.path,
            project_root=settings.paths.project_root,
            enabled=settings.manifest.enabled,
        )
        assert {entry.original_path for entry in manifest.list_entries()} == {url}
        assert manifest.contains_successful_url(url) is True
