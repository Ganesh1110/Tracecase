"""Comprehensive REST API and WebSocket router for QA Auto Studio."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from qa_auto import __version__
from qa_auto.ai.analyst import analyze_testcase
from qa_auto.ai.models import Message
from qa_auto.ai.provider import get_provider
from qa_auto.exporters.html_exporter import HTMLExporter
from qa_auto.index.search import get_coverage_report, search_testcases
from qa_auto.index.store import index_testcase
from qa_auto.mutation.engine import MutationEngine
from qa_auto.replay.har import build_har
from qa_auto.replay.visual import compare_images
from qa_auto.ui.broadcaster import manager
from qa_auto.ui.db import (
    create_project,
    create_suite,
    delete_project,
    delete_suite,
    get_ai_analyses_for_testcase,
    get_dashboard_metrics,
    get_execution_run,
    get_project,
    get_settings,
    get_suite,
    list_execution_runs,
    list_projects,
    list_suites,
    save_ai_analysis,
    sync_all_testcases_from_disk,
    update_project,
    update_settings,
    update_suite,
)
from qa_auto.ui.executor import orchestrator
from qa_auto.ui.service import (
    add_custom_assertion,
    add_testcase_step,
    delete_custom_assertion,
    delete_testcase_step,
    execute_replay,
    export_pytest_code,
    find_testcase_files,
    get_screenshot_file,
    list_testcases,
    recording_manager,
    reorder_testcase_step,
    resolve_testcase_file,
    run_visual_diff_for_step,
    update_testcase_step,
)

logger = logging.getLogger("qa_auto.ui.api")
router = APIRouter(prefix="/api", tags=["QA Auto Studio"])


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------

class RecordRequest(BaseModel):
    url: str = Field(description="Target URL to record")
    name: str | None = Field(default=None, description="Test case name")
    browser: str = Field(default="chromium", description="Browser type: chromium, firefox, webkit")
    headless: bool = Field(default=False, description="Run browser headless")
    timeout: int = Field(default=30000, description="Action timeout in milliseconds")


class ReplayRequest(BaseModel):
    testcase_id: str = Field(description="ID, folder name, or path of the test case")
    project_id: str = Field(default="default_project", description="Target project ID")
    browser: str | None = Field(default=None, description="Override browser type")
    headed: bool = Field(default=False, description="Display browser window during replay")
    heal: bool = Field(default=True, description="Enable heuristic selector self-healing")
    assertions: bool = Field(default=True, description="Evaluate assertions")
    visual_diff: bool = Field(default=False, description="Perform screenshot visual comparison")
    diff_threshold: float = Field(default=0.1, description="Visual diff tolerance percentage")


class VisualDiffRequest(BaseModel):
    baseline: str = Field(description="Path to baseline screenshot")
    candidate: str = Field(description="Path to candidate screenshot")
    threshold: float = Field(default=0.1, description="Tolerance percentage")


class StepUpdateRequest(BaseModel):
    action_type: str | None = None
    input_value: str | None = None
    key: str | None = None
    url: str | None = None
    description_short: str | None = None
    description_detailed: str | None = None
    element: dict[str, Any] | None = None


class StepCreateRequest(BaseModel):
    action_type: str = "click"
    selector: str | None = None
    url: str | None = None
    input_value: str | None = None
    key: str | None = None
    description_short: str | None = None
    position: int | None = None


class StepReorderRequest(BaseModel):
    direction: Literal["up", "down"]


class AssertionCreateRequest(BaseModel):
    kind: Literal["visible", "text", "url", "status", "no_page_error"]
    target: str | None = None
    expected: str | int | None = None
    step_number: int = 1
    enforced: bool = True


class StepDiffRequest(BaseModel):
    candidate_filename: str | None = None
    threshold: float = 0.1


class ProjectCreateRequest(BaseModel):
    name: str = Field(description="Project workspace name")
    description: str = Field(default="", description="Project description")
    settings: dict[str, Any] = Field(default_factory=dict, description="Project settings")


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    settings: dict[str, Any] | None = None


class SuiteCreateRequest(BaseModel):
    name: str = Field(description="Test suite name")
    project_id: str = Field(default="default_project", description="Parent project ID")
    description: str = Field(default="", description="Suite description")
    testcase_ids: list[str] = Field(default_factory=list, description="Included test case IDs")


class SuiteUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    testcase_ids: list[str] | None = None


class AIChatRequest(BaseModel):
    prompt: str = Field(description="User prompt or question")
    testcase_id: str | None = Field(default=None, description="Optional focused testcase context")
    conversation_history: list[dict[str, str]] = Field(default_factory=list)


class MutationGenerateRequest(BaseModel):
    testcase_id: str
    strategies: list[str] = Field(default_factory=lambda: ["inputs", "actions", "network"])
    limit: int = 15


class SettingsUpdateRequest(BaseModel):
    settings: dict[str, str]


# ---------------------------------------------------------------------------
# Core & Health Endpoints
# ---------------------------------------------------------------------------

@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "qa_auto_studio"}


# ---------------------------------------------------------------------------
# Dashboard Metrics
# ---------------------------------------------------------------------------

@router.get("/dashboard/metrics")
async def get_metrics(project_id: str | None = None) -> dict[str, Any]:
    """Return aggregated live metrics for overview dashboard."""
    return get_dashboard_metrics(project_id=project_id)


# ---------------------------------------------------------------------------
# Project Management
# ---------------------------------------------------------------------------

@router.get("/projects")
async def get_projects() -> list[dict[str, Any]]:
    return list_projects()


@router.post("/projects")
async def add_project(req: ProjectCreateRequest) -> dict[str, Any]:
    return create_project(name=req.name, description=req.description, settings=req.settings)


@router.get("/projects/{project_id}")
async def get_project_details(project_id: str) -> dict[str, Any]:
    proj = get_project(project_id)
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return proj


@router.put("/projects/{project_id}")
async def edit_project(project_id: str, req: ProjectUpdateRequest) -> dict[str, Any]:
    updated = update_project(
        project_id=project_id,
        name=req.name,
        description=req.description,
        settings=req.settings,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return updated


@router.delete("/projects/{project_id}")
async def remove_project(project_id: str) -> dict[str, bool]:
    success = delete_project(project_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete project")
    return {"success": True}


# ---------------------------------------------------------------------------
# Test Suites
# ---------------------------------------------------------------------------

@router.get("/suites")
async def get_suites(project_id: str | None = None) -> list[dict[str, Any]]:
    return list_suites(project_id=project_id)


@router.post("/suites")
async def add_suite(req: SuiteCreateRequest) -> dict[str, Any]:
    return create_suite(
        name=req.name,
        project_id=req.project_id,
        description=req.description,
        testcase_ids=req.testcase_ids,
    )


@router.get("/suites/{suite_id}")
async def get_suite_details(suite_id: str) -> dict[str, Any]:
    suite = get_suite(suite_id)
    if not suite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suite not found")
    return suite


@router.put("/suites/{suite_id}")
async def edit_suite(suite_id: str, req: SuiteUpdateRequest) -> dict[str, Any]:
    updated = update_suite(
        suite_id=suite_id,
        name=req.name,
        description=req.description,
        testcase_ids=req.testcase_ids,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suite not found")
    return updated


@router.delete("/suites/{suite_id}")
async def remove_suite(suite_id: str) -> dict[str, bool]:
    success = delete_suite(suite_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suite not found")
    return {"success": True}


@router.post("/suites/{suite_id}/run")
async def run_suite(suite_id: str, req: ReplayRequest | None = None) -> list[dict[str, Any]]:
    """Run all test cases in a suite asynchronously."""
    suite = get_suite(suite_id)
    if not suite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suite not found")

    tc_ids = suite.get("testcase_ids", [])
    if not tc_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Suite has no test cases")

    runs = []
    browser = req.browser if req else "chromium"
    headed = req.headed if req else False
    heal = req.heal if req else True
    assertions = req.assertions if req else True

    for t_id in tc_ids:
        try:
            run = await orchestrator.start_execution(
                testcase_id=t_id,
                project_id=suite.get("project_id", "default_project"),
                suite_id=suite_id,
                browser=browser,
                headed=headed,
                heal=heal,
                assertions=assertions,
            )
            runs.append(run)
        except Exception as exc:
            logger.warning("Could not launch test %s in suite %s: %s", t_id, suite_id, exc)

    return runs


# ---------------------------------------------------------------------------
# Test Cases & Operations
# ---------------------------------------------------------------------------

@router.get("/testcases")
async def get_testcases() -> list[dict[str, Any]]:
    return list_testcases()


@router.get("/testcases/{identifier}")
async def get_testcase_details(identifier: str) -> dict[str, Any]:
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
    try:
        file_path = get_screenshot_file(identifier, filename)
        return FileResponse(file_path, media_type="image/png")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/testcases/{identifier}/html")
async def get_testcase_html(identifier: str) -> HTMLResponse:
    try:
        tc_file, testcase = resolve_testcase_file(identifier)
        html_file = tc_file.parent / "testcase.html"
        if html_file.exists():
            return HTMLResponse(content=html_file.read_text(encoding="utf-8"))

        exporter = HTMLExporter()
        exporter.export(testcase, tc_file.parent)
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/testcases/{identifier}/codegen")
async def generate_code(identifier: str) -> dict[str, str]:
    try:
        code = export_pytest_code(identifier)
        return {"code": code}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.get("/testcases/{identifier}/har")
async def get_testcase_har(identifier: str) -> dict[str, Any]:
    """Generate and return HAR data for recorded network traffic."""
    try:
        _, testcase = resolve_testcase_file(identifier)
        har_data = build_har(testcase)
        return har_data
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Test Execution Management
# ---------------------------------------------------------------------------

@router.get("/executions")
async def get_executions(
    project_id: str | None = None,
    testcase_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return list_execution_runs(
        project_id=project_id,
        testcase_id=testcase_id,
        status=status,
        limit=limit,
    )


@router.get("/executions/{execution_id}")
async def get_execution_details(execution_id: str) -> dict[str, Any]:
    run = get_execution_run(execution_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return run


@router.post("/executions")
async def start_new_execution(req: ReplayRequest) -> dict[str, Any]:
    """Launch asynchronous background test execution."""
    try:
        run = await orchestrator.start_execution(
            testcase_id=req.testcase_id,
            project_id=req.project_id,
            browser=req.browser or "chromium",
            headed=req.headed,
            heal=req.heal,
            assertions=req.assertions,
            visual_diff=req.visual_diff,
            diff_threshold=req.diff_threshold,
        )
        return run
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to start execution: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(execution_id: str) -> dict[str, bool]:
    cancelled = await orchestrator.cancel_execution(execution_id)
    return {"cancelled": cancelled}


@router.post("/replay")
async def run_replay(req: ReplayRequest) -> dict[str, Any]:
    """Synchronous replay (kept for compatibility with CLI and tests)."""
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


# ---------------------------------------------------------------------------
# Browser Recording
# ---------------------------------------------------------------------------

@router.post("/record/start")
async def start_recording(req: RecordRequest) -> dict[str, Any]:
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
    return recording_manager.get_status()


# ---------------------------------------------------------------------------
# Visual Diff
# ---------------------------------------------------------------------------

@router.post("/diff")
async def compare_visual(req: VisualDiffRequest) -> dict[str, Any]:
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


@router.post("/testcases/{identifier}/steps/{step_number}/visual-diff")
async def step_visual_diff(
    identifier: str, step_number: int, req: StepDiffRequest
) -> dict[str, Any]:
    try:
        result = run_visual_diff_for_step(
            identifier=identifier,
            step_number=step_number,
            candidate_filename=req.candidate_filename,
            threshold=req.threshold,
        )
        return result.model_dump(mode="json")
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Visual diff failed for step %d in %s: %s", step_number, identifier, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.get("/diff/image")
async def get_diff_image(
    path: str = Query(..., description="Absolute or relative diff image path"),
) -> FileResponse:
    img_path = Path(path).resolve()
    if not img_path.exists() or not img_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diff image not found")
    return FileResponse(img_path, media_type="image/png")


# ---------------------------------------------------------------------------
# Step Editing and Reordering
# ---------------------------------------------------------------------------

@router.put("/testcases/{identifier}/steps/{step_number}")
async def update_step(identifier: str, step_number: int, req: StepUpdateRequest) -> dict[str, Any]:
    try:
        updated_tc = update_testcase_step(
            identifier=identifier,
            step_number=step_number,
            update_data=req.model_dump(exclude_unset=True),
        )
        return updated_tc.model_dump(mode="json")
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to update step %d in %s: %s", step_number, identifier, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/testcases/{identifier}/steps")
async def create_step(identifier: str, req: StepCreateRequest) -> dict[str, Any]:
    try:
        updated_tc = add_testcase_step(
            identifier=identifier,
            step_data=req.model_dump(exclude_unset=True),
            position=req.position,
        )
        return updated_tc.model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to add step to %s: %s", identifier, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.delete("/testcases/{identifier}/steps/{step_number}")
async def remove_step(identifier: str, step_number: int) -> dict[str, Any]:
    try:
        updated_tc = delete_testcase_step(identifier=identifier, step_number=step_number)
        return updated_tc.model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to delete step %d from %s: %s", step_number, identifier, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/testcases/{identifier}/steps/{step_number}/reorder")
async def reorder_step(
    identifier: str, step_number: int, req: StepReorderRequest
) -> dict[str, Any]:
    try:
        updated_tc = reorder_testcase_step(
            identifier=identifier, step_number=step_number, direction=req.direction
        )
        return updated_tc.model_dump(mode="json")
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to reorder step %d in %s: %s", step_number, identifier, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/testcases/{identifier}/assertions")
async def create_assertion(identifier: str, req: AssertionCreateRequest) -> dict[str, Any]:
    try:
        updated_tc = add_custom_assertion(
            identifier=identifier, assertion_data=req.model_dump(mode="json")
        )
        return updated_tc.model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to add assertion to %s: %s", identifier, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.delete("/testcases/{identifier}/assertions/{index}")
async def remove_assertion(identifier: str, index: int) -> dict[str, Any]:
    try:
        updated_tc = delete_custom_assertion(identifier=identifier, index=index)
        return updated_tc.model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to delete assertion %d from %s: %s", index, identifier, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


# ---------------------------------------------------------------------------
# AI Intelligence & Assistant
# ---------------------------------------------------------------------------

@router.post("/ai/analyze")
async def analyze_case(testcase_id: str) -> dict[str, Any]:
    """Run AI and heuristic analysis on a test case."""
    try:
        _, testcase = resolve_testcase_file(testcase_id)
        settings = get_settings()
        provider = get_provider(
            name=settings.get("ai_provider", "ollama"),
            base_url=settings.get("ai_api_base"),
            model=settings.get("ai_model"),
            api_key=settings.get("ai_api_key"),
        )
        result = await analyze_testcase(testcase, provider)
        raw = result.model_dump(mode="json")
        saved = save_ai_analysis(
            testcase_id=testcase.id,
            summary=result.summary,
            risk_score=result.risk_score,
            raw_analysis=raw,
            model_used=provider.name,
        )
        return saved
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Analysis failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.get("/ai/analyses/{testcase_id}")
async def get_analyses_history(testcase_id: str) -> list[dict[str, Any]]:
    return get_ai_analyses_for_testcase(testcase_id)


@router.post("/ai/chat")
async def ai_chat(req: AIChatRequest) -> dict[str, Any]:
    """Conversational AI Assistant with context from the test repository."""
    settings = get_settings()
    provider = get_provider(
        name=settings.get("ai_provider", "ollama"),
        base_url=settings.get("ai_api_base"),
        model=settings.get("ai_model"),
        api_key=settings.get("ai_api_key"),
    )

    # Search corpus if query resembles a search or needs test context
    corpus_matches = []
    try:
        search_query = req.prompt.split("\n")[0][:60]
        corpus_matches = search_testcases(search_query, limit=3)
    except Exception:
        pass

    context_lines = []
    if req.testcase_id:
        try:
            _, tc = resolve_testcase_file(req.testcase_id)
            context_lines.append(f"Focused Test Case: {tc.name} ({tc.start_url})")
            context_lines.append(f"Steps: {[s.description_short for s in tc.steps]}")
        except Exception:
            pass

    if corpus_matches:
        context_lines.append("Relevant Indexed Test Cases:")
        for m in corpus_matches:
            context_lines.append(f"- {m['name']} (URL: {m['start_url']}): {m.get('match_snippet', '')}")

    system_instruction = (
        "You are QA Auto Assistant, an autonomous quality engineering intelligence expert. "
        "You help QA engineers analyze test coverage, suggest edge case assertions, troubleshoot test failures, "
        "and generate resilient automation strategies."
    )
    if context_lines:
        system_instruction += "\nContext:\n" + "\n".join(context_lines)

    messages = [Message(role="system", content=system_instruction)]
    for prev in req.conversation_history[-6:]:
        role = prev.get("role", "user")
        content = prev.get("content", "")
        if role in ("user", "assistant", "system"):
            messages.append(Message(role=role, content=content))
    messages.append(Message(role="user", content=req.prompt))

    reply_text = ""
    try:
        response_data = await provider.chat(messages)
        if isinstance(response_data, dict):
            reply_text = response_data.get("content") or response_data.get("response") or str(response_data)
        elif isinstance(response_data, str):
            reply_text = response_data
    except Exception as exc:
        logger.warning("Provider chat call failed: %s", exc)

    if not reply_text:
        # Fallback heuristic response if provider is offline
        reply_text = (
            f"Here are testing recommendations based on your repository context:\n\n"
            f"1. **Flow Verification**: Ensure all navigation actions have corresponding URL or DOM visibility assertions.\n"
            f"2. **Negative Scenarios**: Test empty input submissions, boundary strings, and simulated network timeouts.\n"
            f"3. **Self-Healing Selectors**: Use `data-testid` or accessible ARIA roles for high locator stability.\n\n"
            f"*(Connect a local Ollama or OpenAI-compatible endpoint in Settings for deep LLM-powered responses.)*"
        )

    return {
        "reply": reply_text,
        "context_matches": corpus_matches,
        "model": provider.model or provider.name,
    }


# ---------------------------------------------------------------------------
# Negative Test Mutations
# ---------------------------------------------------------------------------

@router.post("/mutations/generate")
async def generate_mutations(req: MutationGenerateRequest) -> list[dict[str, Any]]:
    """Generate negative test mutations for a test case."""
    try:
        _, testcase = resolve_testcase_file(req.testcase_id)
        engine = MutationEngine()
        mutants = engine.generate(testcase, strategies=req.strategies, limit=req.limit)
        return [
            {
                "id": m.testcase.id,
                "name": m.testcase.name,
                "strategy": m.metadata.strategy,
                "description": m.metadata.description,
                "target_step": m.metadata.target_step,
                "mutation_type": m.metadata.mutation_type,
                "original_value": m.metadata.original_value,
                "mutated_value": m.metadata.mutated_value,
                "total_steps": len(m.testcase.steps),
            }
            for m in mutants
        ]
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Mutation generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


# ---------------------------------------------------------------------------
# Test Repository & Coverage
# ---------------------------------------------------------------------------

@router.get("/repository/search")
async def repo_search(query: str = Query(..., min_length=1), limit: int = 15) -> list[dict[str, Any]]:
    """Full-text search indexed test cases."""
    try:
        return search_testcases(query=query, limit=limit)
    except Exception as exc:
        logger.exception("Corpus search failed: %s", exc)
        return []


@router.get("/repository/coverage")
async def repo_coverage() -> dict[str, Any]:
    """Return URL and action coverage statistics."""
    try:
        return get_coverage_report()
    except Exception as exc:
        logger.exception("Coverage report failed: %s", exc)
        return {"total_testcases": 0, "unique_domains": 0, "path_coverage": {}, "action_distribution": {}}


@router.post("/repository/reindex")
async def repo_reindex() -> dict[str, Any]:
    """Scan and index all test cases into FTS5 corpus store."""
    files = find_testcase_files()
    indexed_count = 0
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            from qa_auto.models import TestCase
            tc = TestCase.model_validate(data)
            index_testcase(tc, f)
            indexed_count += 1
        except Exception:
            continue
    sync_all_testcases_from_disk()
    return {"indexed": indexed_count, "total_files": len(files)}


# ---------------------------------------------------------------------------
# Storage Management & Settings
# ---------------------------------------------------------------------------

@router.get("/storage/stats")
async def storage_stats() -> dict[str, Any]:
    """Calculate disk usage across recordings, screenshots, and databases."""
    recordings_dir = Path("recordings")
    total_size = 0
    screenshots_size = 0
    screenshots_count = 0
    recordings_count = 0

    if recordings_dir.exists():
        for p in recordings_dir.rglob("*"):
            if p.is_file():
                sz = p.stat().st_size
                total_size += sz
                if p.suffix.lower() == ".png":
                    screenshots_size += sz
                    screenshots_count += 1
                elif p.name == "testcase.json":
                    recordings_count += 1

    return {
        "recordings_count": recordings_count,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "screenshots_size_mb": round(screenshots_size / (1024 * 1024), 2),
        "screenshots_count": screenshots_count,
        "database_path": str(Path(".qa_auto/studio.db").resolve()),
    }


@router.post("/storage/clean")
async def storage_clean(clean_diffs: bool = True, clean_old_runs: bool = False) -> dict[str, Any]:
    """Prune temporary diff images and replay runs."""
    cleaned_bytes = 0
    deleted_files = 0
    recordings_dir = Path("recordings")
    if recordings_dir.exists():
        if clean_diffs:
            for d in recordings_dir.rglob("diffs"):
                if d.is_dir():
                    for f in d.glob("*.png"):
                        cleaned_bytes += f.stat().st_size
                        f.unlink()
                        deleted_files += 1
        if clean_old_runs:
            for r in recordings_dir.rglob("replay_runs"):
                if r.is_dir():
                    for sub in r.iterdir():
                        if sub.is_dir():
                            for f in sub.rglob("*"):
                                if f.is_file():
                                    cleaned_bytes += f.stat().st_size
                                    deleted_files += 1
                            shutil.rmtree(sub, ignore_errors=True)

    return {
        "deleted_files": deleted_files,
        "freed_mb": round(cleaned_bytes / (1024 * 1024), 2),
    }


@router.get("/settings")
async def get_app_settings() -> dict[str, str]:
    return get_settings()


@router.put("/settings")
async def update_app_settings(req: SettingsUpdateRequest) -> dict[str, str]:
    return update_settings(req.settings)


# ---------------------------------------------------------------------------
# WebSockets Real-Time Stream
# ---------------------------------------------------------------------------

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, channel: str = "general") -> None:
    """General real-time WebSocket connection."""
    await manager.connect(websocket, channel=channel)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                parsed = json.loads(data)
                # Handle client-initiated ping or channel subscribe
                action = parsed.get("action")
                if action == "subscribe":
                    sub_channel = parsed.get("channel", "general")
                    await manager.connect(websocket, channel=sub_channel)
                elif action == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except Exception:
                pass
    except WebSocketDisconnect:
        await manager.disconnect(websocket, channel=channel)


@router.websocket("/ws/executions/{execution_id}")
async def execution_websocket(websocket: WebSocket, execution_id: str) -> None:
    """Dedicated WebSocket stream for a single test execution."""
    channel = f"execution:{execution_id}"
    await manager.connect(websocket, channel=channel)
    try:
        while True:
            # Keep-alive loop
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, channel=channel)
