"""FastAPI server application and lifecycle management for Tracecase Studio."""

from __future__ import annotations

import logging
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from tracecase import __version__
from tracecase.ui.api import router as api_router

logger = logging.getLogger("tracecase.ui.server")
STATIC_DIR = Path(__file__).parent / "static"
ASSETS_DIR = STATIC_DIR / "assets"


def create_app() -> FastAPI:
    """Create and configure the FastAPI web application."""
    app = FastAPI(
        title="Tracecase Studio",
        description="Autonomous Web QA Studio for recording, replaying, and inspecting browser tests.",
        version=__version__,
    )

    # Enable CORS for development flexibility
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API routes
    app.include_router(api_router)

    # Mount static assets if assets directory exists
    if ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    def _serve_index() -> HTMLResponse:
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
        return HTMLResponse("<h2>Tracecase Studio is running. Static UI not found.</h2>")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return _serve_index()

    # SPA catch-all for client-side routing (React Router)
    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def catch_all(request: Request, full_path: str) -> HTMLResponse:
        # Don't intercept API or static routes
        if full_path.startswith(("api/", "assets/", "static/")):
            return HTMLResponse(status_code=404, content="Not Found")
        return _serve_index()

    return app


def start_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = True,
    log_level: str = "info",
) -> None:
    """Launch the uvicorn web server."""
    app = create_app()

    if open_browser:
        url = f"http://{host}:{port}"
        import threading
        import time

        def _open() -> None:
            time.sleep(1.2)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level=log_level)
