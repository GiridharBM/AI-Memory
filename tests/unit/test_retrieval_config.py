"""Tests for runtime retrieval-stage toggles (HyDE/reranker/answerability)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.interfaces.web import deps
from app.interfaces.web.server import create_app


@pytest.fixture()
def client(
    tmp_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """A TestClient with isolated settings and clean retrieval flag state."""

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
        deps.clear_retrieval_overrides()

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
    yield TestClient(create_app())
    _clear()
    deps.clear_retrieval_overrides()


def _flags(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/config/retrieval")
    assert response.status_code == 200, response.text
    return response.json()


def test_defaults_are_all_disabled(client: TestClient) -> None:
    assert _flags(client) == {
        "hyde_enabled": False,
        "reranker_enabled": False,
        "answerability_enabled": False,
    }


def test_enable_and_disable_hyde(client: TestClient) -> None:
    assert client.post("/api/config/retrieval", json={"hyde_enabled": True}).json() == {
        "hyde_enabled": True,
        "reranker_enabled": False,
        "answerability_enabled": False,
    }
    assert _flags(client)["hyde_enabled"] is True
    assert client.post("/api/config/retrieval", json={"hyde_enabled": False}).json()[
        "hyde_enabled"
    ] is False


def test_enable_and_disable_reranker(client: TestClient) -> None:
    assert client.post(
        "/api/config/retrieval", json={"reranker_enabled": True}
    ).json() == {
        "hyde_enabled": False,
        "reranker_enabled": True,
        "answerability_enabled": False,
    }
    assert _flags(client)["reranker_enabled"] is True
    client.post("/api/config/retrieval", json={"reranker_enabled": False})

    assert _flags(client)["reranker_enabled"] is False


def test_enable_and_disable_answerability(client: TestClient) -> None:
    assert client.post(
        "/api/config/retrieval", json={"answerability_enabled": True}
    ).json() == {
        "hyde_enabled": False,
        "reranker_enabled": False,
        "answerability_enabled": True,
    }
    assert _flags(client)["answerability_enabled"] is True
    client.post("/api/config/retrieval", json={"answerability_enabled": False})

    assert _flags(client)["answerability_enabled"] is False


def test_settings_change_one_flag_at_a_time(client: TestClient) -> None:
    client.post("/api/config/retrieval", json={"hyde_enabled": True})
    client.post("/api/config/retrieval", json={"answerability_enabled": True})

    assert _flags(client) == {
        "hyde_enabled": True,
        "reranker_enabled": False,
        "answerability_enabled": True,
    }


def test_unknown_field_is_rejected_without_state_change(client: TestClient) -> None:
    assert (
        client.post("/api/config/retrieval", json={"unknown_stage": True}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/config/retrieval", json={"hyde_enabled": True, "bogus": 1}
        ).status_code
        == 422
    )

    assert _flags(client) == {
        "hyde_enabled": False,
        "reranker_enabled": False,
        "answerability_enabled": False,
    }


def test_non_boolean_values_are_rejected(client: TestClient) -> None:
    assert (
        client.post("/api/config/retrieval", json={"hyde_enabled": "yes"}).status_code
        == 422
    )
    assert (
        client.post("/api/config/retrieval", json={"hyde_enabled": 1}).status_code
        == 422
    )
    assert client.post("/api/config/retrieval", json={}).status_code == 422

    assert _flags(client)["hyde_enabled"] is False


def test_future_search_service_observes_hyde_toggle(
    client: TestClient, tmp_settings: Settings
) -> None:
    before = deps.get_search_service()
    assert before._hyde is None

    client.post("/api/config/retrieval", json={"hyde_enabled": True})

    after = deps.get_search_service()
    assert after is not before
    assert after._hyde is not None

    client.post("/api/config/retrieval", json={"hyde_enabled": False})

    assert deps.get_search_service()._hyde is None


def test_future_qa_workflow_observes_reranker_and_answerability(
    client: TestClient,
) -> None:
    assert deps.get_qa_workflow()._reranker is None
    assert deps.get_qa_workflow()._answerability_gate is None

    client.post("/api/config/retrieval", json={"reranker_enabled": True})
    assert deps.get_qa_workflow()._reranker is not None

    client.post("/api/config/retrieval", json={"answerability_enabled": True})
    workflow = deps.get_qa_workflow()
    assert workflow._reranker is not None
    assert workflow._answerability_gate is not None


def test_pipeline_diagram_reflects_toggles(client: TestClient) -> None:
    stages = {row["id"]: row for row in client.get("/api/retrieval").json()["stages"]}
    assert stages["hyde"]["active"] is False

    client.post("/api/config/retrieval", json={"hyde_enabled": True})

    stages = {row["id"]: row for row in client.get("/api/retrieval").json()["stages"]}
    assert stages["hyde"]["active"] is True
    assert stages["rerank"]["active"] is False
