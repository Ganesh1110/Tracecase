"""FastAPI router for QA Auto Web Studio."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from qa_auto.exporters.html_exporter import HTMLExporter
from qa_auto.replay.visual import compare_images
from qa_auto.ui.service import (
    execute_replay,
    export_pytest_code,
    get_screenshot_file,
    list_testcases,
    recording_manager,
    resolve_testcase_file,
)

logger = logging.getLogger("qa_auto.ui.api")
router = APIRouter(prefix="/api", tags=["QA Auto Studio"])


class RecordRequest(BaseModel):
    """Payload to start a recording session."""

    url: str = Field(description="Target URL to record")
    name: str | None = Field(default=None, description="Test case name")
    browser: str = Field(default="chromium", description="Browser type: chromium, firefox, webkit")
    headless: bool = Field(default=False, description="Run browser headless")
    timeout: int = Field(default=30000, description="Action timeout in milliseconds")


class ReplayRequest(BaseModel):
    """Payload to run a replay."""

    testcase_id: str = Field(description="ID, folder name, or path of the test case")
    browser: str | None = Field(default=None, description="Override browser type")
    headed: bool = Field(default=False, description="Display browser window during replay")
    heal: bool = Field(default=True, description="Enable heuristic selector self-healing")
    assertions: bool = Field(default=True, description="Evaluate assertions")
    visual_diff: bool = Field(default=False, description="Perform screenshot visual comparison")
    diff_threshold: float = Field(default=0.1, description="Visual diff tolerance percentage")


class VisualDiffRequest(BaseModel):
    """Payload for custom visual diff."""

    baseline: str = Field(description="Path to baseline screenshot")
    candidate: str = Field(description="Path to candidate screenshot")
    threshold: float = Field(default=0.1, description="Tolerance percentage")


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "qa_auto_studio"}


@router.get("/testcases")
async def get_testcases() -> list[dict[str, Any]]:
    """List all available recorded test cases."""
    return list_testcases()


@router.get("/testcases/{identifier}")
async def get_testcase_details(identifier: str) -> dict[str, Any]:
    """Fetch complete testcase JSON by ID or folder name."""
    try:
        tc_file, testcase = resolve_testcase_file(identifier)
        data = testcase.model_dump(mode="json")
        data["_folder"] = str(tc_file.parent)
        data["_file_path"] = str(tc_file)
        return data
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error loading test case %s: %s", identifier, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.get("/testcases/{identifier}/screenshots/{filename:path}")
async def get_testcase_screenshot(identifier: str, filename: str) -> FileResponse:
    """Serve a screenshot file for a test case."""
    try:
        file_path = get_screenshot_file(identifier, filename)
        return FileResponse(file_path, media_type="image/png")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/testcases/{identifier}/html")
async def get_testcase_html(identifier: str) -> HTMLResponse:
    """Return the generated HTML report for a test case."""
    try:
        tc_file, testcase = resolve_testcase_file(identifier)
        html_file = tc_file.parent / "testcase.html"
        if html_file.exists():
            return HTMLResponse(content=html_file.read_text(encoding="utf-8"))

        # If not already written, generate on the fly
        exporter = HTMLExporter()
        exporter.export(testcase, tc_file.parent)
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/testcases/{identifier}/codegen")
async def generate_code(identifier: str) -> dict[str, str]:
    """Generate Pytest Playwright code for a test case."""
    try:
        code = export_pytest_code(identifier)
        return {"code": code}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/record/start")
async def start_recording(req: RecordRequest) -> dict[str, Any]:
    """Start an interactive browser recording session."""
    try:
        session = await recording_manager.start(
            url=req.url,
            name=req.name,
            browser_type=req.browser,
            headless=req.headless,
            timeout=req.timeout,
        )
        return session
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to start recording: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.get("/record/status")
async def get_recording_status() -> dict[str, Any]:
    """Get the current recording session state."""
    return recording_manager.get_status()


@router.post("/replay")
async def run_replay(req: ReplayRequest) -> dict[str, Any]:
    """Execute test case replay and evaluate assertions."""
    try:
        result = await execute_replay(
            identifier=req.testcase_id,
            browser_type=req.browser,
            headed=req.headed,
            heal=req.heal,
            assertions_enabled=req.assertions,
            visual_diff=req.visual_diff,
            diff_threshold=req.diff_threshold,
        )
        return result.model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Replay execution failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/diff")
async def compare_visual(req: VisualDiffRequest) -> dict[str, Any]:
    """Run visual diff between two images."""
    try:
        diff_res = compare_images(
            baseline=req.baseline,
            candidate=req.candidate,
            threshold_percent=req.threshold,
        )
        return diff_res.model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
