"""Artifact routes: metadata, versions, provenance, and safe content serving.

Clients address artifacts by id only — filesystem paths are never accepted.
Binary content resolves against the configured artifact root first, then the
project root (handler-generated refs are project-relative), each with the
same ``resolve()`` + ``is_relative_to()`` containment the SPA fallback uses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import Settings
from app.infrastructure.artifacts import ArtifactStore, ProvenanceStore
from app.interfaces.web import deps

router = APIRouter()

_PPTX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)

_EXTENSION_MEDIA_TYPES = {
    ".pptx": _PPTX_MEDIA_TYPE,
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _stores(settings: Settings) -> tuple[ArtifactStore, ProvenanceStore]:
    """Build the artifact and provenance stores under the manifest root."""

    root = settings.paths.manifest_root
    return (
        ArtifactStore(root / "artifacts.json"),
        ProvenanceStore(root / "provenance.json"),
    )


def _require_settings() -> Settings:
    error = deps.settings_error()
    if error is not None:
        raise HTTPException(status_code=503, detail=error)
    return deps.get_settings()


def _artifact_payload(artifact: Any) -> dict[str, Any]:
    """Project an artifact row to its stable API representation."""

    return {
        "artifact_id": artifact.artifact_id,
        "logical_id": artifact.logical_id,
        "kind": artifact.kind.value,
        "title": artifact.title,
        "version": artifact.version,
        "created_at": artifact.created_at.isoformat(),
        "updated_at": artifact.updated_at.isoformat(),
        "job_id": artifact.job_id,
        "model_role": artifact.model_role,
        "memory_scope": artifact.request.memory_scope.model_dump(mode="json"),
        "metadata": dict(artifact.metadata),
        "content": artifact.content,
        "content_ref": artifact.content_ref,
    }


@router.get("/artifacts")
def list_artifacts() -> dict[str, Any]:
    """All artifact rows in deterministic creation order."""

    settings = _require_settings()
    artifact_store, _ = _stores(settings)
    artifacts = artifact_store.list_artifacts()
    return {
        "artifacts": [_artifact_payload(artifact) for artifact in artifacts],
        "total": len(artifacts),
    }


@router.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: str) -> dict[str, Any]:
    """One artifact row, or 404 when unknown."""

    settings = _require_settings()
    artifact_store, _ = _stores(settings)
    artifact = artifact_store.get(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return _artifact_payload(artifact)


@router.get("/artifacts/{artifact_id}/versions")
def get_artifact_versions(artifact_id: str) -> dict[str, Any]:
    """Every version row sharing the artifact's logical id, oldest first."""

    settings = _require_settings()
    artifact_store, _ = _stores(settings)
    artifact = artifact_store.get(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    versions = artifact_store.list_versions(artifact.logical_id)
    return {
        "artifact_id": artifact_id,
        "logical_id": artifact.logical_id,
        "versions": [_artifact_payload(row) for row in versions],
    }


@router.get("/artifacts/{artifact_id}/provenance")
def get_artifact_provenance(artifact_id: str) -> dict[str, Any]:
    """Provenance records for one artifact, in stored order."""

    settings = _require_settings()
    artifact_store, provenance_store = _stores(settings)
    if artifact_store.get(artifact_id) is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    records = provenance_store.for_artifact(artifact_id)
    return {
        "artifact_id": artifact_id,
        "records": [record.model_dump(mode="json") for record in records],
        "total": len(records),
    }


def _resolve_content_ref(settings: Settings, content_ref: str) -> Path | None:
    """Resolve a stored ref inside the artifact or project root, else ``None``.

    Artifact-root-relative refs keep resolving exactly as before; handler
    generated project-relative refs (e.g. ``data/artifacts/deck.pptx``) fall
    through to the project root. A relative ``artifact_root`` is anchored at
    the project root first so resolution never depends on the launch CWD.
    Absolute and escaping refs resolve outside both roots and return ``None``.
    """

    try:
        project_root = settings.paths.project_root.resolve()
    except OSError:
        return None
    configured = settings.paths.artifact_root
    artifact_root = (
        configured if configured.is_absolute() else project_root / configured
    )
    try:
        artifact_root = artifact_root.resolve()
    except OSError:
        return None
    for base in (artifact_root, project_root):
        candidate = (base / content_ref).resolve()
        if candidate.is_relative_to(base) and candidate.is_file():
            return candidate
    return None


@router.get("/artifacts/{artifact_id}/content")
def get_artifact_content(artifact_id: str) -> Any:
    """Inline content as JSON, or the referenced file as a download.

    Only the stored ``content_ref`` is ever resolved — the client cannot
    influence the filesystem path. Traversal, absolute, missing, and
    out-of-root refs all 404.
    """

    settings = _require_settings()
    artifact_store, _ = _stores(settings)
    artifact = artifact_store.get(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    if artifact.content is not None:
        return {
            "artifact_id": artifact.artifact_id,
            "kind": artifact.kind.value,
            "title": artifact.title,
            "content": artifact.content,
            "content_ref": None,
        }
    if artifact.content_ref is None:
        raise HTTPException(status_code=404, detail="Artifact has no content.")
    resolved = _resolve_content_ref(settings, artifact.content_ref)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Artifact content not found.")
    media_type = _EXTENSION_MEDIA_TYPES.get(
        resolved.suffix.lower(), "application/octet-stream"
    )
    return FileResponse(
        path=resolved, media_type=media_type, filename=f"{artifact.title}{resolved.suffix}"
    )
