"""FastAPI server application and lifecycle management for QA Auto Studio."""

from __future__ import annotations

import logging
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from qa_auto import __version__
from qa_auto.ui.api import router as api_router

logger = logging.getLogger("qa_auto.ui.server")
STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    """Create and configure the FastAPI web application."""
    app = FastAPI(
        title="QA Auto Studio",
        description="Autonomous AI-style Web QA Studio for recording, replaying, and inspecting browser tests.",
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

    # Mount static assets if static directory exists
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
        return HTMLResponse("<h2>QA Auto Studio is running. Static UI not found.</h2>")

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
        # Schedule browser opening after brief delay
        import threading
        import time

        def _open() -> None:
            time.sleep(1.2)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level=log_level)
