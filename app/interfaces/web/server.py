"""FastAPI application factory for the PAM GUI.

Run it with either::

    pam-gui
    uvicorn app.interfaces.web.server:app --port 8000

The app is served on localhost only and mounted with the built Vite build when
``frontend/dist`` exists, so a single process backs the whole GUI.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import ConfigurationError
from app.interfaces.web import deps
from app.interfaces.web.routes import (
    artifacts,
    conversations,
    generation,
    interact,
    knowledge,
    memories,
    mindmap,
    system,
)

API_PREFIX = "/api"


def _frontend_dist() -> Path | None:
    """Return the built frontend directory, if it has been built."""

    project_root = Path(__file__).resolve().parents[3]
    candidate = project_root / "frontend" / "dist"
    return candidate if (candidate / "index.html").exists() else None


def create_app() -> FastAPI:
    app = FastAPI(
        title="PAM — Personal AI Memory",
        version="2.0.1",
        description=(
            "Local HTTP interface over the PAM CLI and application services. "
            "Read-mostly: it exposes existing PAM operations and does not "
            "implement retrieval, QA or configuration logic of its own."
        ),
    )

    # The Vite dev server runs on a different port during development; in
    # production the bundle is served same-origin so no CORS is needed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(system.router, prefix=API_PREFIX)
    app.include_router(knowledge.router, prefix=API_PREFIX)
    app.include_router(interact.router, prefix=API_PREFIX)
    app.include_router(generation.router, prefix=API_PREFIX)
    app.include_router(artifacts.router, prefix=API_PREFIX)
    app.include_router(mindmap.router, prefix=API_PREFIX)
    app.include_router(conversations.router, prefix=API_PREFIX)
    app.include_router(memories.router, prefix=API_PREFIX)

    @app.get(f"{API_PREFIX}/health", tags=["system"])
    def health() -> JSONResponse:
        """Liveness for the UI's top bar. Never claims health it cannot verify."""

        config_error = deps.settings_error()
        if config_error is not None:
            return JSONResponse(
                status_code=503,
                content={"state": "unknown", "config_error": config_error},
            )
        ollama = deps.ollama_health()
        state = "healthy" if ollama["reachable"] else "degraded"
        return JSONResponse(
            content={
                "state": state,
                "config_ok": True,
                "ollama_reachable": ollama["reachable"],
                "ollama_model_present": ollama["model_present"],
                "detail": ollama["detail"],
            },
        )

    dist = _frontend_dist()
    if dist is not None:
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> Any:
            """Serve the SPA, falling back to index.html for client routes."""

            root = dist.resolve()
            candidate = (dist / full_path).resolve()
            # is_relative_to, not str.startswith: a sibling directory such as
            # `dist-secrets` must not pass the containment check.
            if full_path and candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate)
            return FileResponse(root / "index.html")

    else:

        @app.get("/", include_in_schema=False)
        def no_frontend() -> JSONResponse:
            return JSONResponse(
                {
                    "message": (
                        "PAM API is running. The GUI bundle is not built yet — "
                        "run `npm run build` in frontend/, or use the Vite dev server."
                    ),
                    "api_docs": "/docs",
                },
            )

    return app


app = create_app()


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    from app.core.logging import setup_logging

    try:
        setup_logging(deps.get_settings())
    except ConfigurationError:
        # A broken config must still let the server start so the UI can report
        # "STATUS UNKNOWN" instead of the process dying with a stack trace.
        pass

    uvicorn.run(
        "app.interfaces.web.server:app",
        host="127.0.0.1",
        port=int(os.environ.get("PAM_GUI_PORT", "8000")),
        log_level="info",
    )


if __name__ == "__main__":  # pragma: no cover
    main()
