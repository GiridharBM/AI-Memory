"""Tests for the V2 generation/job/artifact/mind-map HTTP API.

Every test is hermetic: settings point at tmp_path, the executor is faked
(no LLM, no search), and background threads run inline, so nothing here
touches durable state, a live Ollama server, or real time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.artifacts import Artifact, ArtifactKind
from app.domain.generation import GenerationRequest
from app.domain.jobs import (
    GenerationJob,
    GenerationJobStatus,
    fail,
    set_progress,
    transition,
)
from app.domain.scopes import MemoryScope
from app.infrastructure.artifacts import ArtifactStore, ProvenanceStore
from app.infrastructure.jobs import GenerationJobStore
from app.interfaces.web import deps
from app.interfaces.web.routes import generation as generation_routes
from app.interfaces.web.server import create_app


def _stores(settings: Settings) -> tuple[GenerationJobStore, ArtifactStore, ProvenanceStore]:
    root = settings.paths.manifest_root
    return (
        GenerationJobStore(root / "generation_jobs.json"),
        ArtifactStore(root / "artifacts.json"),
        ProvenanceStore(root / "provenance.json"),
    )


class _FakeExecutor:
    """Deterministic stand-in: runs inline, no LLM, no search."""

    _KINDS = {
        "flashcards": ArtifactKind.FLASHCARDS,
        "quiz": ArtifactKind.QUIZ,
        "report": ArtifactKind.REPORT,
        "ppt": ArtifactKind.PPT,
    }

    def __init__(self, settings: Settings) -> None:
        job_store, artifact_store, _ = _stores(settings)
        self.job_store = job_store
        self.artifact_store = artifact_store

    def submit(self, request: GenerationRequest) -> GenerationJob:
        from app.application.generation_errors import UnsupportedTaskError

        if request.task_type.value not in self._KINDS:
            raise UnsupportedTaskError(
                f"No handler registered for task '{request.task_type.value}'."
            )
        return self.job_store.create(request)

    def execute_job(self, job_id: str) -> GenerationJob:
        job = self.job_store.get(job_id)
        assert job is not None
        job = transition(job, GenerationJobStatus.PROCESSING)
        job = set_progress(job, 50, stage="generating")
        self.job_store.update(job)
        try:
            artifact = Artifact.create(
                kind=self._KINDS[job.request.task_type.value],
                title=f"{job.request.task_type.value} result",
                job_id=job.job_id,
                request=job.request,
                content=f"# {job.request.task_type.value}\n\nbody",
                metadata={},
            )
            self.artifact_store.create(artifact)
            finished = transition(job, GenerationJobStatus.DONE)
            finished = set_progress(finished, 100, stage="done")
        except Exception as exc:
            finished = fail(job, f"{type(exc).__name__}: {exc}")
        self.job_store.update(finished)
        return finished


@pytest.fixture()
def client(
    tmp_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    """A TestClient whose executor is faked and whose threads run inline."""

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
    monkeypatch.setattr(
        generation_routes,
        "_build_executor",
        lambda settings, **_kwargs: _FakeExecutor(settings),
    )
    monkeypatch.setattr(
        generation_routes, "_launch", lambda target, args=(): target(*args)
    )
    yield TestClient(create_app())
    _clear()


def _submit(client: TestClient, **overrides: object) -> dict[str, Any]:
    body: dict[str, object] = {
        "task_type": "flashcards",
        "memory_scope": {"kind": "all"},
        "config": {"count": 2},
    }
    body.update(overrides)
    response = client.post("/api/generation", json=body)
    assert response.status_code == 202, response.text
    return response.json()


def _write_graph(root: Path, nodes: list[dict], edges: list[dict]) -> None:
    manifests = root / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "knowledge_graph.json").write_text(
        json.dumps({"nodes": nodes, "edges": edges}), encoding="utf-8"
    )


def _node(node_id: str, label: str = "label") -> dict[str, object]:
    return {"id": node_id, "label": label, "node_type": "concept", "source": "a.md"}


def _edge(source_id: str, target_id: str) -> dict[str, object]:
    return {"source_id": source_id, "target_id": target_id, "edge_type": "related_to"}


def _request(**overrides: object) -> GenerationRequest:
    values: dict[str, object] = {
        "task_type": "flashcards",
        "memory_scope": MemoryScope.all(),
    }
    values.update(overrides)
    return GenerationRequest(**values)  # type: ignore[arg-type]


# ── Generation submission ─────────────────────────────────────────────


class TestGenerationSubmission:
    @pytest.mark.parametrize("task", ["flashcards", "quiz", "report", "ppt"])
    def test_submit_supported_task_returns_pending_job(
        self, client: TestClient, task: str
    ) -> None:
        response = client.post(
            "/api/generation",
            json={"task_type": task, "memory_scope": {"kind": "all"}, "config": {}},
        )

        assert response.status_code == 202
        body = response.json()
        assert body["task_type"] == task
        assert body["status"] == "pending"
        assert body["progress"] == 0
        assert body["job_id"]
        assert body["created_at"]
        assert body["updated_at"]
        assert body["error"] is None

    def test_invalid_task_is_422_with_no_job(self, client: TestClient) -> None:
        response = client.post(
            "/api/generation",
            json={"task_type": "teleport", "memory_scope": {"kind": "all"}},
        )

        assert response.status_code == 422
        assert client.get("/api/jobs").json() == {"jobs": [], "total": 0}

    @pytest.mark.parametrize("task", ["image", "video", "mindmap_enrich"])
    def test_unsupported_enum_task_is_400_with_no_job(
        self, client: TestClient, task: str
    ) -> None:
        response = client.post(
            "/api/generation",
            json={"task_type": task, "memory_scope": {"kind": "all"}},
        )

        assert response.status_code == 400
        assert client.get("/api/jobs").json() == {"jobs": [], "total": 0}

    def test_background_execution_completes_inline(self, client: TestClient) -> None:
        job_id = _submit(client)["job_id"]

        body = client.get(f"/api/jobs/{job_id}").json()

        assert body["status"] == "done"
        assert body["progress"] == 100


# ── Jobs ──────────────────────────────────────────────────────────────


class TestJobsApi:
    def test_get_existing_job(self, client: TestClient) -> None:
        job_id = _submit(client)["job_id"]

        body = client.get(f"/api/jobs/{job_id}").json()

        assert body["job_id"] == job_id
        assert body["status"] == "done"

    def test_missing_job_is_404(self, client: TestClient) -> None:
        assert client.get("/api/jobs/does-not-exist").status_code == 404

    def test_list_order_is_deterministic(self, client: TestClient) -> None:
        first = _submit(client)["job_id"]
        second = _submit(client)["job_id"]

        body = client.get("/api/jobs").json()

        assert body["total"] == 2
        assert [job["job_id"] for job in body["jobs"]] == [first, second]

    def test_cancel_pending_job(
        self, client: TestClient, tmp_settings: Settings
    ) -> None:
        root = tmp_settings.paths.manifest_root
        store = GenerationJobStore(root / "generation_jobs.json")
        job = store.create(_request())

        body = client.post(f"/api/jobs/{job.job_id}/cancel").json()

        assert body["status"] == "cancelled"
        assert body["job_id"] == job.job_id

    def test_cancel_terminal_job_is_409(self, client: TestClient) -> None:
        job_id = _submit(client)["job_id"]
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "done"

        response = client.post(f"/api/jobs/{job_id}/cancel")

        assert response.status_code == 409

    def test_cancel_missing_job_is_404(self, client: TestClient) -> None:
        assert client.post("/api/jobs/does-not-exist/cancel").status_code == 404


# ── Artifacts ─────────────────────────────────────────────────────────


class TestArtifactsApi:
    def test_list_and_get_artifact(self, client: TestClient) -> None:
        job_id = _submit(client)["job_id"]
        listed = client.get("/api/artifacts").json()

        assert listed["total"] == 1
        artifact_id = listed["artifacts"][0]["artifact_id"]
        body = client.get(f"/api/artifacts/{artifact_id}").json()

        assert body["job_id"] == job_id
        assert body["kind"] == "flashcards"
        assert body["version"] == 1
        assert body["content"] is not None

    def test_missing_artifact_is_404(self, client: TestClient) -> None:
        assert client.get("/api/artifacts/does-not-exist").status_code == 404
        assert client.get("/api/artifacts/does-not-exist/versions").status_code == 404
        assert client.get("/api/artifacts/does-not-exist/provenance").status_code == 404
        assert client.get("/api/artifacts/does-not-exist/content").status_code == 404

    def test_versions_and_provenance(self, client: TestClient) -> None:
        _submit(client)
        artifact_id = client.get("/api/artifacts").json()["artifacts"][0]["artifact_id"]

        versions = client.get(f"/api/artifacts/{artifact_id}/versions").json()
        assert versions["logical_id"]
        assert [row["artifact_id"] for row in versions["versions"]] == [artifact_id]

        provenance = client.get(f"/api/artifacts/{artifact_id}/provenance").json()
        assert provenance["artifact_id"] == artifact_id
        assert provenance["total"] == len(provenance["records"])

    def test_inline_content(self, client: TestClient) -> None:
        _submit(client)
        artifact_id = client.get("/api/artifacts").json()["artifacts"][0]["artifact_id"]

        body = client.get(f"/api/artifacts/{artifact_id}/content").json()

        assert body["content"] is not None
        assert body["content_ref"] is None

    def test_pptx_content_served_as_file(
        self, client: TestClient, tmp_settings: Settings
    ) -> None:
        root = tmp_settings.paths.artifact_root
        root.mkdir(parents=True, exist_ok=True)
        payload = b"%PDF-fake-pptx-bytes"
        (root / "deck.pptx").write_bytes(payload)
        store = ArtifactStore(tmp_settings.paths.manifest_root / "artifacts.json")
        artifact = Artifact.create(
            kind=ArtifactKind.PPT,
            title="Deck",
            job_id="job-1",
            request=_request(),
            content_ref="deck.pptx",
        )
        store.create(artifact)

        response = client.get(f"/api/artifacts/{artifact.artifact_id}/content")

        assert response.status_code == 200
        assert response.content == payload
        assert "presentationml.presentation" in response.headers["content-type"]

    def test_traversal_content_ref_is_404(
        self, client: TestClient, tmp_settings: Settings
    ) -> None:
        store = ArtifactStore(tmp_settings.paths.manifest_root / "artifacts.json")
        artifact = Artifact.create(
            kind=ArtifactKind.PPT,
            title="Evil",
            job_id="job-1",
            request=_request(),
            content_ref="../evil.pptx",
        )
        store.create(artifact)

        assert (
            client.get(f"/api/artifacts/{artifact.artifact_id}/content").status_code
            == 404
        )

    def test_missing_content_file_is_404(
        self, client: TestClient, tmp_settings: Settings
    ) -> None:
        store = ArtifactStore(tmp_settings.paths.manifest_root / "artifacts.json")
        artifact = Artifact.create(
            kind=ArtifactKind.PPT,
            title="Gone",
            job_id="job-1",
            request=_request(),
            content_ref="gone.pptx",
        )
        store.create(artifact)

        assert (
            client.get(f"/api/artifacts/{artifact.artifact_id}/content").status_code
            == 404
        )


# ── Mind map ──────────────────────────────────────────────────────────


class TestMindMapApi:
    def test_deterministic_root_projection(self, client: TestClient) -> None:
        from app.interfaces.web import deps as web_deps

        root = web_deps.get_settings().paths.project_root
        _write_graph(
            root,
            [_node("b"), _node("a"), _node("c")],
            [_edge("b", "a"), _edge("a", "c")],
        )

        first = client.get("/api/mindmap").json()
        second = client.get("/api/mindmap").json()

        assert first == second
        assert [node["id"] for node in first["nodes"]] == ["a", "b", "c"]
        assert first["root"] is None
        assert {"source_id": "b", "target_id": "a", "edge_type": "related_to"} in first[
            "edges"
        ]

    def test_node_expansion(self, client: TestClient) -> None:
        from app.interfaces.web import deps as web_deps

        root = web_deps.get_settings().paths.project_root
        _write_graph(
            root,
            [_node("a"), _node("b"), _node("far")],
            [_edge("a", "b"), _edge("b", "far")],
        )

        body = client.get("/api/mindmap", params={"node_id": "a", "depth": 1}).json()

        assert {node["id"] for node in body["nodes"]} == {"a", "b"}
        assert body["root"] == "a"
        deep = client.get("/api/mindmap", params={"node_id": "a", "depth": 2}).json()
        assert {node["id"] for node in deep["nodes"]} == {"a", "b", "far"}

    def test_depth_cap_rejected(self, client: TestClient) -> None:
        assert client.get("/api/mindmap", params={"depth": 99}).status_code == 422

    def test_unknown_node_is_404(self, client: TestClient) -> None:
        from app.interfaces.web import deps as web_deps

        _write_graph(web_deps.get_settings().paths.project_root, [_node("a")], [])

        assert client.get("/api/mindmap", params={"node_id": "ghost"}).status_code == 404

    def test_missing_graph_is_empty_projection(self, client: TestClient) -> None:
        body = client.get("/api/mindmap").json()

        assert body == {"available": True, "nodes": [], "edges": [], "root": None}


# ── Artifact content_ref resolution ───────────────────────────────────


class TestContentRefResolution:
    """Project-relative handler refs must serve; artifact-relative refs keep working.

    Regression for the live PPTX 404: handlers store project-relative refs
    (e.g. ``data/artifacts/deck.pptx``) while ``_resolve_content_ref`` only
    understood artifact-relative ones.
    """

    def _write_project_file(self, tmp_settings: Settings, ref: str, payload: bytes) -> None:
        root = tmp_settings.paths.project_root
        target = root / ref
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)

    def _store(
        self, tmp_settings: Settings, content_ref: str
    ) -> Artifact:
        store = ArtifactStore(tmp_settings.paths.manifest_root / "artifacts.json")
        artifact = Artifact.create(
            kind=ArtifactKind.PPT,
            title="Deck",
            job_id="job-1",
            request=_request(),
            content_ref=content_ref,
        )
        store.create(artifact)
        return artifact

    def test_project_relative_ref_serves_file(
        self, client: TestClient, tmp_settings: Settings
    ) -> None:
        payload = b"%PDF-fake-pptx-bytes"
        self._write_project_file(tmp_settings, "data/artifacts/deck.pptx", payload)
        artifact = self._store(tmp_settings, "data/artifacts/deck.pptx")

        response = client.get(f"/api/artifacts/{artifact.artifact_id}/content")

        assert response.status_code == 200
        assert response.content == payload
        assert "presentationml.presentation" in response.headers["content-type"]

    def test_artifact_relative_ref_still_serves_file(
        self, client: TestClient, tmp_settings: Settings
    ) -> None:
        payload = b"%PDF-fake-pptx-bytes"
        root = tmp_settings.paths.artifact_root
        root.mkdir(parents=True, exist_ok=True)
        (root / "deck.pptx").write_bytes(payload)
        artifact = self._store(tmp_settings, "deck.pptx")

        response = client.get(f"/api/artifacts/{artifact.artifact_id}/content")

        assert response.status_code == 200
        assert response.content == payload

    def test_missing_project_relative_ref_is_404(
        self, client: TestClient, tmp_settings: Settings
    ) -> None:
        artifact = self._store(tmp_settings, "data/artifacts/gone.pptx")

        assert (
            client.get(f"/api/artifacts/{artifact.artifact_id}/content").status_code
            == 404
        )

    def test_project_relative_traversal_is_404(
        self, client: TestClient, tmp_settings: Settings
    ) -> None:
        artifact = self._store(tmp_settings, "data/artifacts/../../evil.pptx")

        assert (
            client.get(f"/api/artifacts/{artifact.artifact_id}/content").status_code
            == 404
        )

    def test_relative_artifact_root_ignores_cwd(
        self, client: TestClient, tmp_settings: Settings, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.interfaces.web.routes import artifacts as artifact_routes

        elsewhere = tmp_path / "other-cwd"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        settings = tmp_settings.model_copy(
            update={
                "paths": tmp_settings.paths.model_copy(
                    update={"artifact_root": Path("data/artifacts")}
                )
            }
        )
        target = tmp_settings.paths.project_root / "data" / "artifacts" / "deck.pptx"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"%PDF-fake-pptx-bytes")

        resolved = artifact_routes._resolve_content_ref(settings, "data/artifacts/deck.pptx")

        assert resolved == target.resolve()

    def test_absolute_ref_outside_roots_is_404(
        self, client: TestClient, tmp_settings: Settings
    ) -> None:
        artifact = self._store(tmp_settings, "/etc/passwd")

        assert (
            client.get(f"/api/artifacts/{artifact.artifact_id}/content").status_code
            == 404
        )
