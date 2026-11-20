"""Comprehensive REST API and WebSocket router for Tracecase Studio."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from tracecase.ai.analyst import analyze_testcase
from tracecase.ai.assertion_generator import suggest_assertions
from tracecase.ai.coverage_analyst import analyze_corpus_coverage
from tracecase.ai.failure_analyst import analyze_execution_failure
from tracecase.ai.models import Message
from tracecase.ai.provider import get_provider
from tracecase.ai.selectors import audit_testcase_selectors
from tracecase.ai.variations import generate_smart_variations
from tracecase.exploration.controller import exploration_controller
from tracecase.exploration.models import AppNavigationGraph, ExplorationConfig
from tracecase.exploration.planner import plan_requirement_against_graph
from tracecase.exploration.regression import select_intelligent_regression_suite
from tracecase.exploration.synthesizer import synthesize_test_journeys
from tracecase.exporters.html_exporter import HTMLExporter
from tracecase.artifact_manager import (
    ArtifactManager,
    PrunePolicy,
    PruneRequest,
    PruneResult,
    RetentionPolicy,
    StorageSummary,
)
from tracecase.index.search import get_coverage_report, search_testcases
from tracecase.index.store import index_testcase
from tracecase.intelligence.code_mapper import TestToCodeMapper
from tracecase.intelligence.explainer import PrioritizationExplainer
from tracecase.intelligence.git_analyzer import GitChangeAnalyzer
from tracecase.intelligence.models import (
    CodeImpactReport,
    DecisionTraceRecord,
    GitChangeSet,
    ImpactedTestResult,
    PredictiveRiskReport,
    PrioritizationReport,
    RegressionSelectionResult,
    RiskScoringWeights,
    SelectedTestItem,
    SelectionStrategy,
    TestCodeMapping,
    TestPrioritizationExplanation,
    TestRiskScore,
)
from tracecase.intelligence.risk_scorer import PredictiveRiskScorer
from tracecase.intelligence.selector import IntelligentRegressionSelector
from tracecase.models import TestCase
from tracecase.mutation.engine import MutationEngine
from tracecase.replay.har import build_har
from tracecase.replay.visual import compare_images
from tracecase.ui.broadcaster import manager
from tracecase.ui.db import (
    add_testcase_to_suite,
    approve_synthesized_draft,
    create_project,
    create_suite,
    delete_project,
    delete_suite,
    get_ai_analyses_for_testcase,
    get_dashboard_metrics,
    get_decision_traces,
    get_execution_attempts,
    get_execution_batch,
    get_execution_matrix,
    get_execution_run,
    get_project,
    get_regression_selection_by_id,
    get_regression_selections,
    get_risk_scores_snapshots,
    get_settings,
    get_suite,
    get_synthesized_draft,
    get_test_code_mappings,
    get_testcase_flakiness_stats,
    list_execution_batches,
    list_execution_matrices,
    list_execution_runs,
    list_projects,
    list_suites,
    list_synthesized_drafts,
    record_user_decision_override,
    reject_synthesized_draft,
    remove_testcase_from_suite,
    save_ai_analysis,
    save_decision_traces,
    save_regression_selection,
    save_synthesized_draft,
    sync_all_testcases_from_disk,
    update_project,
    update_settings,
    update_suite,
    update_synthesized_draft,
)
from tracecase.ui.executor import orchestrator
from tracecase.ui.service import (
    add_custom_assertion,
    add_testcase_step,
    create_manual_testcase,
    delete_custom_assertion,
    delete_testcase,
    delete_testcase_step,
    execute_replay,
    export_pytest_code,
    find_testcase_files,
    get_screenshot_file,
    list_testcases,
    persist_generated_testcase,
    recording_manager,
    reorder_testcase_step,
    resolve_testcase_file,
    run_visual_diff_for_step,
    update_custom_assertion,
    update_testcase_metadata,
    update_testcase_step,
)

logger = logging.getLogger("tracecase.ui.api")
router = APIRouter(prefix="/api", tags=["Tracecase Studio"])


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------

class RecordRequest(BaseModel):
    url: str = Field(description="Target URL to record")
    name: str | None = Field(default=None, description="Test case name")
    browser: str = Field(default="chromium", description="Browser type: chromium, firefox, webkit")
    headless: bool = Field(default=False, description="Run browser headless")
    timeout: int = Field(default=30000, description="Action timeout in milliseconds")
    project_id: str = Field(default="default_project", description="Target project ID")


class TestCaseUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    start_url: str | None = None


class AssertionUpdateRequest(BaseModel):
    kind: str | None = None
    target: str | None = None
    expected: Any = None
    step_number: int | None = None
    enforced: bool | None = None


class TestCaseCreateRequest(BaseModel):
    name: str = Field(description="Test case name")
    start_url: str = Field(description="Start URL")
    browser: str = Field(default="chromium", description="Browser engine")
    description: str = Field(default="", description="Description")
    project_id: str = Field(default="default_project", description="Target project ID")


class ReplayRequest(BaseModel):
    testcase_id: str | None = Field(default=None, description="ID, folder name, or path of the test case")
    project_id: str = Field(default="default_project", description="Target project ID")
    browser: str | None = Field(default=None, description="Override browser type")
    headed: bool = Field(default=False, description="Display browser window during replay")
    heal: bool = Field(default=True, description="Enable heuristic selector self-healing")
    assertions: bool = Field(default=True, description="Evaluate assertions")
    visual_diff: bool = Field(default=False, description="Perform screenshot visual comparison")
    diff_threshold: float = Field(default=0.1, description="Visual diff tolerance percentage")
    concurrency: int = Field(default=2, ge=1, le=8, description="Parallel worker count for batch/suite execution")
    retries: int = Field(default=2, ge=0, le=3, description="Number of retry attempts on failure (0 to 3)")


class BatchExecutionRequest(BaseModel):
    testcase_ids: list[str] = Field(description="List of testcase IDs or paths to execute")
    project_id: str = Field(default="default_project", description="Target project ID")
    suite_id: str | None = Field(default=None, description="Optional associated suite ID")
    concurrency: int = Field(default=2, ge=1, le=8, description="Number of parallel workers (1 to 8)")
    browser: str = Field(default="chromium", description="Browser engine")
    headed: bool = Field(default=False, description="Display browser window during replay")
    heal: bool = Field(default=True, description="Enable selector self-healing")
    assertions: bool = Field(default=True, description="Evaluate assertions")
    visual_diff: bool = Field(default=False, description="Perform screenshot visual comparison")
    diff_threshold: float = Field(default=0.1, description="Visual diff tolerance percentage")
    retries: int = Field(default=2, ge=0, le=3, description="Number of retry attempts on failure (0 to 3)")


class MatrixExecutionRequest(BaseModel):
    testcase_ids: list[str] = Field(default_factory=list, description="List of testcase IDs or paths to execute")
    browsers: list[str] = Field(
        default=["chromium", "firefox", "webkit"],
        description="Target browser engines (e.g. ['chromium', 'firefox', 'webkit'])",
    )
    concurrency: int = Field(default=2, ge=1, le=8, description="Number of parallel workers (1 to 8)")
    project_id: str = Field(default="default_project", description="Target project ID")
    suite_id: str | None = Field(default=None, description="Optional associated suite ID")
    matrix_name: str | None = Field(default=None, description="Descriptive name for matrix execution")
    headed: bool = Field(default=False, description="Display browser window during replay")
    heal: bool = Field(default=True, description="Enable selector self-healing")
    assertions: bool = Field(default=True, description="Evaluate assertions")
    visual_diff: bool = Field(default=False, description="Perform screenshot visual comparison")
    diff_threshold: float = Field(default=0.1, description="Visual diff tolerance percentage")
    retries: int = Field(default=2, ge=0, le=3, description="Number of retry attempts on failure (0 to 3)")


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
    settings: dict[str, str] | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_api_base: str | None = None
    ai_api_key: str | None = None
    default_browser: str | None = None
    viewport_width: str | None = None
    viewport_height: str | None = None
    heal_default: str | None = None
    assertions_default: str | None = None
    visual_diff_threshold: str | None = None

    def get_dict(self) -> dict[str, str]:
        if self.settings is not None:
            return self.settings
        d = self.model_dump(exclude_none=True)
        d.pop("settings", None)
        return {k: str(v) for k, v in d.items()}


# ---------------------------------------------------------------------------
# Core & Health Endpoints
# ---------------------------------------------------------------------------

@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "tracecase_studio"}


# ---------------------------------------------------------------------------
# Dashboard Metrics
# ---------------------------------------------------------------------------

@router.get("/dashboard/metrics")
@router.get("/metrics")
async def get_metrics(
    project_id: str | None = None,
    days: int = 7,
) -> dict[str, Any]:
    """Return aggregated live metrics for overview dashboard."""
    return get_dashboard_metrics(project_id=project_id, days=days)


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
async def remove_project(project_id: str, force: bool = False) -> dict[str, Any]:
    try:
        success = delete_project(project_id, force=force)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or cannot be deleted",
            )
        return {"success": True, "message": "Project deleted successfully"}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


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


@router.post("/suites/{suite_id}/testcases/{testcase_id}")
async def add_case_to_suite(suite_id: str, testcase_id: str) -> dict[str, Any]:
    suite = add_testcase_to_suite(suite_id, testcase_id)
    if not suite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suite not found")
    return suite


@router.delete("/suites/{suite_id}/testcases/{testcase_id}")
async def remove_case_from_suite(suite_id: str, testcase_id: str) -> dict[str, Any]:
    suite = remove_testcase_from_suite(suite_id, testcase_id)
    if not suite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suite not found")
    return suite


@router.get("/suites/{suite_id}/executions")
async def get_suite_executions(suite_id: str) -> list[dict[str, Any]]:
    return list_execution_runs(suite_id=suite_id)


@router.post("/suites/{suite_id}/run")
async def run_suite(suite_id: str, req: ReplayRequest | None = None) -> list[dict[str, Any]]:
    """Run all test cases in a suite asynchronously via the bounded worker pool."""
    suite = get_suite(suite_id)
    if not suite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suite not found")

    tc_ids = suite.get("testcase_ids", [])
    if not tc_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Suite has no test cases")

    browser = (req.browser if req and req.browser else "chromium")
    headed = req.headed if req else False
    heal = req.heal if req else True
    assertions = req.assertions if req else True
    visual_diff = req.visual_diff if req else False
    diff_threshold = req.diff_threshold if req else 0.1
    concurrency = req.concurrency if req else 2
    retries = req.retries if req else 2

    try:
        batch = await orchestrator.start_batch_execution(
            testcase_ids=tc_ids,
            concurrency=concurrency,
            project_id=suite.get("project_id", "default_project"),
            suite_id=suite_id,
            browser=browser,
            headed=headed,
            heal=heal,
            assertions=assertions,
            visual_diff=visual_diff,
            diff_threshold=diff_threshold,
            retries=retries,
        )
        return batch.get("runs", [])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Could not launch suite %s: %s", suite_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/suites/{suite_id}/run_matrix")
async def run_suite_matrix(suite_id: str, req: MatrixExecutionRequest | None = None) -> dict[str, Any]:
    """Run all test cases in a suite as a cross-browser execution matrix."""
    suite = get_suite(suite_id)
    if not suite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suite not found")

    tc_ids = (req.testcase_ids if req and req.testcase_ids else suite.get("testcase_ids", []))
    if not tc_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Suite has no test cases")

    browsers = req.browsers if req and req.browsers else ["chromium", "firefox", "webkit"]
    concurrency = req.concurrency if req else 2
    retries = req.retries if req else 2
    matrix_name = req.matrix_name if req and req.matrix_name else f"Matrix Suite: {suite.get('name', suite_id)}"
    headed = req.headed if req else False
    heal = req.heal if req else True
    assertions = req.assertions if req else True
    visual_diff = req.visual_diff if req else False
    diff_threshold = req.diff_threshold if req else 0.1

    try:
        matrix = await orchestrator.start_matrix_execution(
            testcase_ids=tc_ids,
            browsers=browsers,
            concurrency=concurrency,
            project_id=suite.get("project_id", "default_project"),
            suite_id=suite_id,
            matrix_name=matrix_name,
            headed=headed,
            heal=heal,
            assertions=assertions,
            visual_diff=visual_diff,
            diff_threshold=diff_threshold,
            retries=retries,
        )
        return matrix
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Could not launch matrix for suite %s: %s", suite_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Test Cases & Operations
# ---------------------------------------------------------------------------

@router.get("/testcases")
async def get_testcases(project_id: str | None = None) -> list[dict[str, Any]]:
    return list_testcases(project_id=project_id)


@router.post("/testcases")
async def add_testcase(req: TestCaseCreateRequest) -> dict[str, Any]:
    """Manually create a testcase scaffold."""
    try:
        tc = create_manual_testcase(
            name=req.name,
            start_url=req.start_url,
            browser=req.browser,
            description=req.description,
            project_id=req.project_id,
        )
        return tc.model_dump(mode="json")
    except Exception as exc:
        logger.exception("Failed to create testcase: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.delete("/testcases/{identifier}")
async def remove_testcase(identifier: str) -> dict[str, bool]:
    """Delete a testcase and clean up its filesystem artifacts."""
    try:
        success = delete_testcase(identifier)
        return {"success": success}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to delete testcase: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


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
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error loading test case %s: %s", identifier, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.put("/testcases/{identifier}")
async def edit_testcase(identifier: str, req: TestCaseUpdateRequest) -> dict[str, Any]:
    try:
        updated_tc = update_testcase_metadata(
            identifier=identifier,
            name=req.name,
            description=req.description,
            start_url=req.start_url,
        )
        data = updated_tc.model_dump(mode="json")
        tc_file, _ = resolve_testcase_file(identifier)
        data["_folder"] = str(tc_file.parent)
        data["_file_path"] = str(tc_file)
        return data
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to update testcase %s: %s", identifier, exc)
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
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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
    suite_id: str | None = None,
    status: str | None = None,
    batch_id: str | None = None,
    worker_id: str | None = None,
    matrix_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return list_execution_runs(
        project_id=project_id,
        testcase_id=testcase_id,
        suite_id=suite_id,
        status=status,
        batch_id=batch_id,
        worker_id=worker_id,
        matrix_id=matrix_id,
        limit=limit,
    )


@router.post("/executions/batch")
async def start_batch_execution_endpoint(req: BatchExecutionRequest) -> dict[str, Any]:
    """Launch parallel or sequential execution of multiple test cases."""
    try:
        batch = await orchestrator.start_batch_execution(
            testcase_ids=req.testcase_ids,
            concurrency=req.concurrency,
            project_id=req.project_id,
            suite_id=req.suite_id,
            browser=req.browser,
            headed=req.headed,
            heal=req.heal,
            assertions=req.assertions,
            visual_diff=req.visual_diff,
            diff_threshold=req.diff_threshold,
            retries=req.retries,
        )
        return batch
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to start batch execution: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.get("/executions/batches")
async def get_execution_batches_endpoint(
    project_id: str | None = None,
    suite_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List execution batches."""
    return list_execution_batches(
        project_id=project_id,
        suite_id=suite_id,
        status=status,
        limit=limit,
    )


@router.get("/executions/batches/{batch_id}")
async def get_execution_batch_endpoint(batch_id: str) -> dict[str, Any]:
    """Fetch batch execution status and child test runs."""
    batch = get_execution_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch execution not found")
    return batch


@router.post("/executions/batches/{batch_id}/cancel")
async def cancel_batch_execution_endpoint(batch_id: str) -> dict[str, bool]:
    """Cancel a running batch execution and its workers."""
    cancelled = await orchestrator.cancel_batch_execution(batch_id)
    return {"cancelled": cancelled}


@router.post("/executions/matrix")
async def start_matrix_execution_endpoint(req: MatrixExecutionRequest) -> dict[str, Any]:
    """Launch cross-browser matrix execution of test cases across configured browsers."""
    try:
        matrix = await orchestrator.start_matrix_execution(
            testcase_ids=req.testcase_ids,
            browsers=req.browsers,
            concurrency=req.concurrency,
            project_id=req.project_id,
            suite_id=req.suite_id,
            matrix_name=req.matrix_name,
            headed=req.headed,
            heal=req.heal,
            assertions=req.assertions,
            visual_diff=req.visual_diff,
            diff_threshold=req.diff_threshold,
            retries=req.retries,
        )
        return matrix
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to start matrix execution: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.get("/executions/matrices")
async def get_execution_matrices_endpoint(
    project_id: str | None = None,
    suite_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List cross-browser execution matrices."""
    return list_execution_matrices(
        project_id=project_id,
        suite_id=suite_id,
        status=status,
        limit=limit,
    )


@router.get("/executions/matrices/{matrix_id}")
async def get_execution_matrix_endpoint(matrix_id: str) -> dict[str, Any]:
    """Fetch matrix execution status, consolidated test case grid, and divergence metrics."""
    matrix = get_execution_matrix(matrix_id)
    if not matrix:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matrix execution not found")
    return matrix


@router.post("/executions/matrices/{matrix_id}/cancel")
async def cancel_matrix_execution_endpoint(matrix_id: str) -> dict[str, bool]:
    """Cancel a running matrix execution and terminate its workers."""
    cancelled = await orchestrator.cancel_matrix_execution(matrix_id)
    return {"cancelled": cancelled}


@router.get("/executions/{execution_id}")
async def get_execution_details(execution_id: str) -> dict[str, Any]:
    run = get_execution_run(execution_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return run


@router.get("/executions/{execution_id}/attempts")
async def get_execution_attempts_endpoint(execution_id: str) -> list[dict[str, Any]]:
    """Fetch all recorded attempts for a specific execution run."""
    run = get_execution_run(execution_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return get_execution_attempts(execution_id)


@router.get("/testcases/{testcase_id}/flakiness")
async def get_testcase_flakiness_endpoint(
    testcase_id: str,
    limit: int = Query(default=30, ge=1, le=100),
) -> dict[str, Any]:
    """Calculate historical flakiness score, reliability rating, and per-browser breakdown."""
    return get_testcase_flakiness_stats(testcase_id, limit=limit)


@router.post("/executions")
async def start_new_execution(req: ReplayRequest) -> dict[str, Any]:
    """Launch asynchronous background test execution."""
    try:
        run = await orchestrator.start_execution(
            testcase_id=req.testcase_id or "",
            project_id=req.project_id,
            browser=req.browser or "chromium",
            headed=req.headed,
            heal=req.heal,
            assertions=req.assertions,
            visual_diff=req.visual_diff,
            diff_threshold=req.diff_threshold,
            retries=req.retries,
        )
        return run
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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
            identifier=req.testcase_id or "",
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
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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
            project_id=req.project_id,
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


@router.post("/record/pause")
async def pause_recording() -> dict[str, Any]:
    """Pause active recording session."""
    try:
        return await recording_manager.pause()
    except Exception as exc:
        logger.exception("Failed to pause recording: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/record/resume")
async def resume_recording() -> dict[str, Any]:
    """Resume active recording session."""
    try:
        return await recording_manager.resume()
    except Exception as exc:
        logger.exception("Failed to resume recording: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/record/stop")
async def stop_recording() -> dict[str, Any]:
    """Stop active recording session and finalize test case."""
    try:
        status_info = await recording_manager.stop()
        return status_info
    except Exception as exc:
        logger.exception("Failed to stop recording: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


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
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to delete assertion %d from %s: %s", index, identifier, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.put("/testcases/{identifier}/assertions/{index}")
async def edit_assertion(
    identifier: str, index: int, req: AssertionUpdateRequest
) -> dict[str, Any]:
    try:
        updated_tc = update_custom_assertion(
            identifier=identifier,
            index=index,
            assertion_data=req.model_dump(exclude_unset=True),
        )
        return updated_tc.model_dump(mode="json")
    except (FileNotFoundError, IndexError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to update assertion %d in %s: %s", index, identifier, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


# ---------------------------------------------------------------------------
# AI Intelligence & Assistant
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    testcase_id: str | None = None
    mode: str | None = "summary"


@router.post("/ai/analyze")
async def analyze_case(
    testcase_id: str | None = None,
    body: AnalyzeRequest | None = None,
) -> dict[str, Any]:
    """Run AI and heuristic analysis on a test case."""
    target_id = (body.testcase_id if body and body.testcase_id else None) or testcase_id
    if not target_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="testcase_id is required",
        )
    try:
        _, testcase = resolve_testcase_file(target_id)
        settings = get_settings()
        provider = get_provider(
            name=settings.get("ai_provider", "ollama"),
            base_url=settings.get("ai_api_base"),
            model=settings.get("ai_model"),
            api_key=settings.get("ai_api_key"),
        )
        result = await analyze_testcase(testcase, provider)
        raw = result.model_dump(mode="json")
        risk_score = min(100, len(result.risks) * 25 + len(result.annotations) * 10)
        saved = save_ai_analysis(
            testcase_id=testcase.id,
            summary=result.summary,
            risk_score=risk_score,
            raw_analysis=raw,
            model_used=provider.name,
        )
        return saved
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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
        "You are Tracecase Assistant, an autonomous quality engineering intelligence expert. "
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
            messages.append(Message(role=cast(Literal["user", "assistant", "system"], role), content=content))
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
            "Here are testing recommendations based on your repository context:\n\n"
            "1. **Flow Verification**: Ensure all navigation actions have corresponding URL or DOM visibility assertions.\n"
            "2. **Negative Scenarios**: Test empty input submissions, boundary strings, and simulated network timeouts.\n"
            "3. **Self-Healing Selectors**: Use `data-testid` or accessible ARIA roles for high locator stability.\n\n"
            "*(Connect a local Ollama or OpenAI-compatible endpoint in Settings for deep LLM-powered responses.)*"
        )

    return {
        "reply": reply_text,
        "context_matches": corpus_matches,
        "model": provider.model or provider.name,
    }


# ---------------------------------------------------------------------------
# Phase 5: AI-Powered QA Intelligence
# ---------------------------------------------------------------------------

class SuggestAssertionsRequest(BaseModel):
    testcase_id: str


class ApplyAssertionsRequest(BaseModel):
    suggestions: list[dict[str, Any]]


class ApplySelectorFixRequest(BaseModel):
    step_number: int
    selector: str
    require_verification: bool = False
    target_url: str | None = None


class VerifySelectorRequest(BaseModel):
    step_number: int
    selector: str
    target_url: str | None = None


class FailureAnalysisRequest(BaseModel):
    execution_id: str


class GenerateVariationsRequest(BaseModel):
    testcase_id: str
    strategies: list[str] | None = None
    allow_security_probes: bool = False
    auto_save: bool = False


@router.post("/ai/suggest-assertions")
async def api_suggest_assertions(req: SuggestAssertionsRequest) -> dict[str, Any]:
    """Generate intelligent assertion recommendations for a test case."""
    try:
        _, testcase = resolve_testcase_file(req.testcase_id)
        settings = get_settings()
        provider = get_provider(
            name=settings.get("ai_provider", "ollama"),
            base_url=settings.get("ai_api_base"),
            model=settings.get("ai_model"),
            api_key=settings.get("ai_api_key"),
        )
        res = await suggest_assertions(testcase, provider)
        return res.model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Suggest assertions failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/testcases/{identifier}/assertions/apply-suggestions")
async def api_apply_suggested_assertions(
    identifier: str, req: ApplyAssertionsRequest
) -> dict[str, Any]:
    """Batch attach AI suggested assertions to a testcase."""
    try:
        updated_tc = None
        for suggestion in req.suggestions:
            updated_tc = add_custom_assertion(identifier, suggestion)
        if updated_tc is None:
            _, updated_tc = resolve_testcase_file(identifier)
        return updated_tc.model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Apply suggested assertions failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.get("/testcases/{identifier}/selectors/audit")
async def api_audit_selectors(identifier: str) -> dict[str, Any]:
    """Audit all selectors in a testcase for fragility, dynamic IDs, and locators."""
    try:
        _, testcase = resolve_testcase_file(identifier)
        report = audit_testcase_selectors(testcase)
        return report.model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Selector audit failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/testcases/{identifier}/selectors/verify-live")
async def api_verify_selector_live(
    identifier: str, req: VerifySelectorRequest
) -> dict[str, Any]:
    """Probe candidate locator against live DOM, verifying it uniquely resolves to intended element."""
    try:
        _, testcase = resolve_testcase_file(identifier)
        target_step = next((s for s in testcase.steps if s.number == req.step_number), None)
        if target_step is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Step #{req.step_number} not found in testcase {identifier}",
            )

        target_url = req.target_url or target_step.url or testcase.start_url
        if not target_url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No target URL found for DOM verification",
            )

        # Enforce allowed hosts (loopback + testcase start_url host)
        allowed_hosts = ["localhost", "127.0.0.1", "::1", "0.0.0.0"]
        if testcase.start_url:
            parsed = urlparse(testcase.start_url)
            if parsed.hostname:
                allowed_hosts.append(parsed.hostname)

        expected_tag = target_step.element.tag_name if target_step.element else None
        expected_text = (target_step.element.text if target_step.element else None) or (
            target_step.element.placeholder if target_step.element else None
        )

        from tracecase.ai.selectors import verify_locator_in_live_dom

        result = await verify_locator_in_live_dom(
            target_url=target_url,
            candidate_selector=req.selector,
            step_number=req.step_number,
            expected_tag=expected_tag,
            expected_text=expected_text,
            allowed_hosts=allowed_hosts,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Live selector verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/testcases/{identifier}/selectors/apply-fix")
async def api_apply_selector_fix(
    identifier: str, req: ApplySelectorFixRequest
) -> dict[str, Any]:
    """Update a step's selector to a resilient locator with optional live DOM verification."""
    try:
        _, testcase = resolve_testcase_file(identifier)

        if req.require_verification:
            target_step = next((s for s in testcase.steps if s.number == req.step_number), None)
            if target_step is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Step #{req.step_number} not found",
                )
            target_url = req.target_url or target_step.url or testcase.start_url
            allowed_hosts = ["localhost", "127.0.0.1", "::1", "0.0.0.0"]
            if testcase.start_url:
                parsed = urlparse(testcase.start_url)
                if parsed.hostname:
                    allowed_hosts.append(parsed.hostname)

            from tracecase.ai.selectors import verify_locator_in_live_dom

            v_res = await verify_locator_in_live_dom(
                target_url=target_url,
                candidate_selector=req.selector,
                step_number=req.step_number,
                expected_tag=target_step.element.tag_name if target_step.element else None,
                expected_text=target_step.element.text if target_step.element else None,
                allowed_hosts=allowed_hosts,
            )
            if not v_res.get("verified"):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Live DOM verification failed: {v_res.get('reason')}",
                )

        updated_tc = update_testcase_step(
            identifier,
            req.step_number,
            {"element": {"selector": req.selector}},
        )
        return updated_tc.model_dump(mode="json")
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Apply selector fix failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/ai/failure-analysis")
async def api_failure_analysis(req: FailureAnalysisRequest) -> dict[str, Any]:
    """Analyze a failed execution run for root cause, category, and remediation."""
    run = get_execution_run(req.execution_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution run {req.execution_id} not found",
        )
    try:
        settings = get_settings()
        provider = get_provider(
            name=settings.get("ai_provider", "ollama"),
            base_url=settings.get("ai_api_base"),
            model=settings.get("ai_model"),
            api_key=settings.get("ai_api_key"),
        )
        result = await analyze_execution_failure(run, provider)
        return result.model_dump(mode="json")
    except Exception as exc:
        logger.exception("Failure analysis failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/ai/generate-variations")
async def api_generate_variations(req: GenerateVariationsRequest) -> list[dict[str, Any]]:
    """Synthesize boundary, security, and format test variations."""
    try:
        _, testcase = resolve_testcase_file(req.testcase_id)
        settings = get_settings()
        provider = get_provider(
            name=settings.get("ai_provider", "ollama"),
            base_url=settings.get("ai_api_base"),
            model=settings.get("ai_model"),
            api_key=settings.get("ai_api_key"),
        )
        variations = await generate_smart_variations(
            testcase,
            strategies=req.strategies,  # type: ignore
            provider=provider,
            allow_security_probes=req.allow_security_probes,
        )

        if req.auto_save:
            for v in variations:
                persist_generated_testcase(v.test_case)

        return [v.model_dump(mode="json") for v in variations]
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Generate variations failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.get("/ai/coverage-insights")
async def api_coverage_insights(
    project_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Compute corpus coverage intelligence, untested routes, and test gaps."""
    try:
        testcase_summaries = list_testcases(project_id=project_id)
        testcases: list[TestCase] = []
        for s in testcase_summaries:
            try:
                _, tc = resolve_testcase_file(s["id"])
                testcases.append(tc)
            except Exception:
                continue

        result = analyze_corpus_coverage(testcases)
        return result.model_dump(mode="json")
    except Exception as exc:
        logger.exception("Coverage insights failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


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
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Mutation generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


# ---------------------------------------------------------------------------
# Test Repository & Coverage
# ---------------------------------------------------------------------------

@router.get("/repository/search")
async def repo_search(
    query: str | None = None,
    q: str | None = None,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """Full-text search indexed test cases."""
    search_term = query or q or ""
    if not search_term:
        return []
    try:
        return search_testcases(query=search_term, limit=limit)
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
            from tracecase.models import TestCase
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

@router.get("/storage/summary", response_model=StorageSummary)
async def get_storage_summary_endpoint() -> StorageSummary:
    """Detailed storage metrics across recordings, runs, diffs, explorations, and DB."""
    manager = ArtifactManager()
    return manager.get_storage_summary()


@router.post("/storage/prune", response_model=PruneResult)
async def prune_storage_endpoint(req: PruneRequest) -> PruneResult:
    """Execute fine-grained artifact pruning across age, runs, diffs, or quota."""
    manager = ArtifactManager()
    return manager.prune_artifacts(req)


@router.get("/storage/retention", response_model=RetentionPolicy)
async def get_retention_policy_endpoint() -> RetentionPolicy:
    """Retrieve active artifact retention policy."""
    manager = ArtifactManager()
    return manager.get_policy()


@router.put("/storage/retention", response_model=RetentionPolicy)
async def update_retention_policy_endpoint(policy: RetentionPolicy) -> RetentionPolicy:
    """Update active artifact retention policy."""
    manager = ArtifactManager()
    return manager.save_policy(policy)


@router.get("/storage/stats")
async def storage_stats() -> dict[str, Any]:
    """Calculate disk usage across recordings, screenshots, and databases."""
    manager = ArtifactManager()
    summary = manager.get_storage_summary()
    return {
        "recordings_count": summary.recordings_count,
        "total_size_mb": summary.total_size_mb,
        "screenshots_size_mb": summary.diffs_size_mb + summary.replay_runs_size_mb,
        "screenshots_count": summary.diffs_count + summary.replay_screenshots_count,
        "database_path": summary.database_path,
    }


@router.post("/storage/clean")
async def storage_clean(clean_diffs: bool = True, clean_old_runs: bool = False) -> dict[str, Any]:
    """Prune temporary diff images and replay runs."""
    manager = ArtifactManager()
    req = PruneRequest(clean_diffs=clean_diffs, clean_old_runs=clean_old_runs, dry_run=False)
    res = manager.prune_artifacts(req)
    return {
        "deleted_files": res.deleted_files,
        "freed_mb": res.freed_mb,
    }


@router.get("/settings")
async def get_app_settings() -> dict[str, str]:
    return get_settings()


@router.put("/settings")
async def update_app_settings(req: SettingsUpdateRequest) -> dict[str, str]:
    return update_settings(req.get_dict())


# ---------------------------------------------------------------------------
# Intelligence Endpoints (Phase 7.5)
# ---------------------------------------------------------------------------

@router.get("/intelligence/git-changes", response_model=GitChangeSet)
async def get_git_changes_endpoint(
    repo_path: str = Query(".", description="Path to repository directory"),
    base_ref: str | None = Query(None, description="Optional base git ref (e.g. main, HEAD~1)"),
    target_ref: str | None = Query(None, description="Optional target git ref (defaults to HEAD)"),
    staged_only: bool = Query(False, description="Whether to inspect only staged changes"),
) -> GitChangeSet:
    """Analyze git changes, diffs, changed selectors, routes, and symbols."""
    analyzer = GitChangeAnalyzer(repo_path)
    return analyzer.analyze_repo(base_ref=base_ref, target_ref=target_ref, staged_only=staged_only)


@router.post("/intelligence/map")
async def build_test_code_mappings_endpoint(
    repo_path: str = Query(".", description="Path to repository workspace"),
    project_id: str = Query("default_project", description="Project ID"),
) -> dict[str, Any]:
    """Scan codebase and testcases to build and persist bidirectional test-to-code mappings."""
    from tracecase.ui.service import find_testcase_files, resolve_testcase_file

    mapper = TestToCodeMapper(repo_path=repo_path, project_id=project_id)
    mapper.scan_codebase()

    tc_files = find_testcase_files()
    testcases: list[TestCase] = []
    for f in tc_files:
        try:
            _, tc = resolve_testcase_file(str(f))
            testcases.append(tc)
        except Exception:
            pass

    graph = mapper.build_graph(testcases, persist=True)
    return {
        "status": "success",
        "project_id": project_id,
        "scanned_code_files": len(mapper.file_indices),
        "total_testcases": len(testcases),
        "total_mappings": len(graph.mappings),
    }


@router.get("/intelligence/mappings", response_model=list[dict[str, Any]])
async def get_test_code_mappings_endpoint(
    testcase_id: str | None = Query(None, description="Filter by testcase ID"),
    file_path: str | None = Query(None, description="Filter by application code file"),
    relation_type: str | None = Query(None, description="Filter by relation type"),
    project_id: str | None = Query("default_project", description="Project ID"),
) -> list[dict[str, Any]]:
    """Retrieve indexed test-to-code mappings from SQLite."""
    return get_test_code_mappings(
        testcase_id=testcase_id,
        file_path=file_path,
        relation_type=relation_type,
        project_id=project_id,
    )


@router.post("/intelligence/impact", response_model=CodeImpactReport)
async def analyze_code_impact_endpoint(
    repo_path: str = Query(".", description="Path to repository workspace"),
    base_ref: str | None = Query(None, description="Optional base git ref (e.g. main, HEAD~1)"),
    target_ref: str | None = Query(None, description="Optional target git ref (defaults to HEAD)"),
    staged_only: bool = Query(False, description="Whether to inspect only staged changes"),
    project_id: str = Query("default_project", description="Project ID"),
) -> CodeImpactReport:
    """Detect git changes and identify impacted regression tests with ranked confidence and evidence."""
    from tracecase.ui.service import find_testcase_files, resolve_testcase_file

    analyzer = GitChangeAnalyzer(repo_path)
    changeset = analyzer.analyze_repo(base_ref=base_ref, target_ref=target_ref, staged_only=staged_only)

    mapper = TestToCodeMapper(repo_path=repo_path, project_id=project_id)
    mapper.scan_codebase()

    tc_files = find_testcase_files()
    testcases: list[TestCase] = []
    test_names: dict[str, str] = {}
    for f in tc_files:
        try:
            _, tc = resolve_testcase_file(str(f))
            testcases.append(tc)
            test_names[tc.id] = tc.name
        except Exception:
            pass

    graph = mapper.build_graph(testcases, persist=False)
    impacted = graph.get_impacted_tests(changeset.files, all_tests=test_names)

    return CodeImpactReport(
        repo_path=str(Path(repo_path).resolve()),
        changeset_summary=changeset.summary,
        impacted_tests=impacted,
        total_impacted_tests=len(impacted),
        total_coverage_mappings=len(graph.mappings),
    )


class EvaluateRiskRequest(BaseModel):
    repo_path: str = "."
    base_ref: str | None = None
    target_ref: str | None = None
    staged_only: bool = False
    project_id: str = "default_project"
    persist: bool = True


@router.post("/intelligence/risk", response_model=PredictiveRiskReport)
async def evaluate_predictive_risk_endpoint(
    request: EvaluateRiskRequest | None = None,
    repo_path: str = Query(".", description="Path to repository workspace"),
    base_ref: str | None = Query(None, description="Optional base git ref (e.g. main, HEAD~1)"),
    target_ref: str | None = Query(None, description="Optional target git ref (defaults to HEAD)"),
    staged_only: bool = Query(False, description="Whether to inspect only staged changes"),
    project_id: str = Query("default_project", description="Project ID"),
    persist: bool = Query(True, description="Whether to persist snapshot to SQLite"),
) -> PredictiveRiskReport:
    """Calculate predictive failure risk scores across all regression tests for current code changes."""
    from tracecase.ui.service import find_testcase_files, resolve_testcase_file

    r_path = request.repo_path if request and request.repo_path != "." else repo_path
    b_ref = (request.base_ref if request else None) or base_ref
    t_ref = (request.target_ref if request else None) or target_ref
    s_only = request.staged_only if request else staged_only
    p_id = request.project_id if request and request.project_id != "default_project" else project_id
    p_persist = request.persist if request is not None else persist

    analyzer = GitChangeAnalyzer(r_path)
    changeset = analyzer.analyze_repo(base_ref=b_ref, target_ref=t_ref, staged_only=s_only)

    mapper = TestToCodeMapper(repo_path=r_path, project_id=p_id)
    mapper.scan_codebase()

    tc_files = find_testcase_files()
    testcases: list[TestCase] = []
    for f in tc_files:
        try:
            _, tc = resolve_testcase_file(str(f))
            testcases.append(tc)
        except Exception:
            pass

    graph = mapper.build_graph(testcases, persist=False)
    scorer = PredictiveRiskScorer(project_id=p_id)
    report = scorer.evaluate_suite_risk(testcases, graph, changeset, persist=p_persist)
    return report


@router.get("/intelligence/risk/snapshots", response_model=list[dict[str, Any]])
async def get_risk_snapshots_endpoint(
    commit_hash: str | None = Query(None, description="Filter by commit hash"),
    testcase_id: str | None = Query(None, description="Filter by testcase ID"),
    project_id: str = Query("default_project", description="Project ID"),
    limit: int = Query(50, ge=1, le=500, description="Maximum snapshots to retrieve"),
) -> list[dict[str, Any]]:
    """Retrieve historical predictive risk calculation snapshots."""
    return get_risk_scores_snapshots(
        commit_hash=commit_hash,
        testcase_id=testcase_id,
        project_id=project_id,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Intelligent Regression Selection Endpoints (Phase 7.5.4)
# ---------------------------------------------------------------------------

class SelectRegressionRequest(BaseModel):
    repo_path: str = "."
    base_ref: str | None = None
    target_ref: str | None = None
    staged_only: bool = False
    project_id: str = "default_project"
    strategy: SelectionStrategy = "time_budget"
    time_budget: str | float | None = "120s"
    min_risk_tier: str | None = None
    min_risk_score: float | None = None
    top_k: int | None = None
    include_critical_exceptions: bool = False
    fallback_duration_s: float = 15.0
    persist: bool = True


class ExecuteSelectionRequest(BaseModel):
    include_budget_exceptions: bool = False
    concurrency: int = 2
    browser: str = "chromium"
    headed: bool = False
    heal: bool = True
    assertions: bool = True
    visual_diff: bool = False
    retries: int = 1


@router.post("/intelligence/select", response_model=RegressionSelectionResult)
async def select_regression_endpoint(
    request: SelectRegressionRequest | None = None,
    repo_path: str = Query(".", description="Path to repository workspace"),
    base_ref: str | None = Query(None, description="Optional base git ref (e.g. main, HEAD~1)"),
    target_ref: str | None = Query(None, description="Optional target git ref (defaults to HEAD)"),
    staged_only: bool = Query(False, description="Whether to inspect only staged changes"),
    project_id: str = Query("default_project", description="Project ID"),
    strategy: SelectionStrategy = Query("time_budget", description="Selection strategy: time_budget, risk_threshold, top_k, combined"),
    time_budget: str | None = Query("120s", description="Time budget (e.g. 120s, 2m)"),
    min_risk_tier: str | None = Query(None, description="Minimum risk tier (critical, high, medium, low)"),
    min_risk_score: float | None = Query(None, description="Minimum raw risk score (0-100)"),
    top_k: int | None = Query(None, description="Maximum test count for top_k strategy"),
    include_critical_exceptions: bool = Query(False, description="Whether to include critical tests exceeding time budget"),
    fallback_duration_s: float = Query(15.0, description="Fallback execution duration in seconds"),
    persist: bool = Query(True, description="Whether to persist selection snapshot to SQLite"),
) -> RegressionSelectionResult:
    """Select the highest-value regression tests given git changes, risk scores, and duration constraints."""
    from tracecase.ui.service import find_testcase_files, resolve_testcase_file

    r_path = request.repo_path if request and request.repo_path != "." else repo_path
    b_ref = (request.base_ref if request else None) or base_ref
    t_ref = (request.target_ref if request else None) or target_ref
    s_only = request.staged_only if request else staged_only
    p_id = request.project_id if request and request.project_id != "default_project" else project_id
    strat = request.strategy if request and request.strategy != "time_budget" else strategy
    t_budget = request.time_budget if request and request.time_budget != "120s" else time_budget
    m_tier = (request.min_risk_tier if request else None) or min_risk_tier
    m_score = (request.min_risk_score if request else None) or min_risk_score
    t_k = (request.top_k if request else None) or top_k
    inc_crit = request.include_critical_exceptions if request else include_critical_exceptions
    fb_dur = request.fallback_duration_s if request and request.fallback_duration_s != 15.0 else fallback_duration_s
    p_persist = request.persist if request is not None else persist

    # 1. Analyze git changes
    analyzer = GitChangeAnalyzer(r_path)
    changeset = analyzer.analyze_repo(base_ref=b_ref, target_ref=t_ref, staged_only=s_only)

    # 2. Build code mapping graph
    mapper = TestToCodeMapper(repo_path=r_path, project_id=p_id)
    mapper.scan_codebase()

    tc_files = find_testcase_files()
    testcases: list[TestCase] = []
    for f in tc_files:
        try:
            _, tc = resolve_testcase_file(str(f))
            testcases.append(tc)
        except Exception:
            pass

    graph = mapper.build_graph(testcases, persist=False)

    # 3. Calculate predictive risk scores
    scorer = PredictiveRiskScorer(project_id=p_id)
    risk_report = scorer.evaluate_suite_risk(testcases, graph, changeset, persist=False)

    # 4. Run intelligent selection
    selector = IntelligentRegressionSelector(
        project_id=p_id,
        fallback_duration_s=fb_dur,
    )
    result = selector.select(
        testcases=testcases,
        risk_report=risk_report,
        strategy=strat,
        time_budget=t_budget,
        min_risk_tier=m_tier,
        min_risk_score=m_score,
        top_k=t_k,
        include_critical_exceptions=inc_crit,
        persist=p_persist,
    )
    if p_persist:
        try:
            explainer = PrioritizationExplainer(project_id=p_id)
            explainer.build_report(
                selection=result,
                risk_report=risk_report,
                changeset=changeset,
                graph=graph,
                persist=True,
            )
        except Exception as exc:
            logger.warning("Failed to auto-generate decision traces for selection %s: %s", result.id, exc)
    return result


@router.get("/intelligence/selections", response_model=list[dict[str, Any]])
async def get_regression_selections_endpoint(
    project_id: str = Query("default_project", description="Project ID"),
    commit_hash: str | None = Query(None, description="Filter by commit hash"),
    limit: int = Query(50, ge=1, le=500, description="Maximum snapshots to retrieve"),
) -> list[dict[str, Any]]:
    """Retrieve historical regression selection summaries."""
    return get_regression_selections(
        project_id=project_id,
        commit_hash=commit_hash,
        limit=limit,
    )


@router.get("/intelligence/selections/{selection_id}", response_model=dict[str, Any])
async def get_regression_selection_detail_endpoint(selection_id: str) -> dict[str, Any]:
    """Retrieve a complete regression selection snapshot including per-test decisions."""
    sel = get_regression_selection_by_id(selection_id)
    if not sel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regression selection '{selection_id}' not found.",
        )
    return sel


@router.post("/intelligence/selections/{selection_id}/execute")
async def execute_regression_selection_endpoint(
    selection_id: str,
    req: ExecuteSelectionRequest | None = None,
) -> dict[str, Any]:
    """Launch execution for test cases chosen by an intelligent regression selection snapshot."""
    sel = get_regression_selection_by_id(selection_id)
    if not sel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regression selection '{selection_id}' not found.",
        )

    options = req or ExecuteSelectionRequest()
    test_ids = list(sel.get("selected_test_ids") or [])

    if options.include_budget_exceptions:
        budget_exceptions = sel.get("budget_exceptions") or []
        for be in budget_exceptions:
            if be not in test_ids:
                test_ids.append(be)

    if not test_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No test cases to execute in this selection.",
        )

    try:
        batch = await orchestrator.start_batch_execution(
            testcase_ids=test_ids,
            concurrency=options.concurrency,
            project_id=sel.get("project_id", "default_project"),
            browser=options.browser,
            headed=options.headed,
            heal=options.heal,
            assertions=options.assertions,
            visual_diff=options.visual_diff,
            retries=options.retries,
        )
        return {
            "status": "launched",
            "selection_id": selection_id,
            "batch_id": batch.get("id"),
            "total_tests": len(test_ids),
            "testcase_ids": test_ids,
            "batch": batch,
        }
    except Exception as exc:
        logger.exception("Failed to launch batch execution for selection %s: %s", selection_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution launch failed: {exc}",
        ) from exc


class DecisionOverrideRequest(BaseModel):
    testcase_id: str
    override_decision: str  # "selected" or "excluded"
    override_reason: str
    project_id: str | None = None


def _reconstruct_selection_obj(sel: dict[str, Any]) -> RegressionSelectionResult:
    """Helper to convert stored selection dict into RegressionSelectionResult."""
    tests_data = sel.get("tests") or []
    items = [SelectedTestItem(**t) for t in tests_data]
    return RegressionSelectionResult(
        id=sel["id"],
        project_id=sel.get("project_id", "default_project"),
        commit_hash=sel.get("commit_hash"),
        branch=sel.get("branch"),
        created_at=sel.get("created_at", ""),
        strategy=sel.get("strategy", "time_budget"),
        strategy_params=sel.get("strategy_params") or {},
        time_budget_s=sel.get("time_budget_s"),
        total_tests_considered=sel.get("total_tests_considered", len(items)),
        selected_count=sel.get("selected_count", len(sel.get("selected_test_ids") or [])),
        excluded_count=sel.get("excluded_count", len(sel.get("excluded_test_ids") or [])),
        budget_exception_count=sel.get("budget_exception_count", len(sel.get("budget_exceptions") or [])),
        estimated_total_duration_s=sel.get("estimated_total_duration_s", 0.0),
        risk_coverage_pct=sel.get("risk_coverage_pct", 0.0),
        critical_coverage_pct=sel.get("critical_coverage_pct", 0.0),
        selected_test_ids=sel.get("selected_test_ids") or [],
        excluded_test_ids=sel.get("excluded_test_ids") or [],
        budget_exceptions=sel.get("budget_exceptions") or [],
        tests=items,
    )


@router.get("/intelligence/selections/{selection_id}/explanations", response_model=list[dict[str, Any]])
async def get_regression_selection_explanations_endpoint(selection_id: str) -> list[dict[str, Any]]:
    """Retrieve auditable decision traces and evidence categorization for a selection."""
    sel = get_regression_selection_by_id(selection_id)
    if not sel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regression selection '{selection_id}' not found.",
        )
    traces = get_decision_traces(selection_id)
    if traces:
        return traces
    # Fallback: if traces weren't precomputed, reconstruct explanations from stored selection tests
    selection_obj = _reconstruct_selection_obj(sel)
    explainer = PrioritizationExplainer(project_id=sel.get("project_id", "default_project"))
    explainer.build_report(selection_obj, persist=True)
    return get_decision_traces(selection_id)


@router.get("/intelligence/selections/{selection_id}/report")
async def get_regression_selection_report_endpoint(
    selection_id: str,
    format: str = Query("markdown", description="Report format: markdown or json"),
) -> Any:
    """Generate or retrieve a publication-ready regression prioritization report."""
    sel = get_regression_selection_by_id(selection_id)
    if not sel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regression selection '{selection_id}' not found.",
        )
    selection_obj = _reconstruct_selection_obj(sel)
    explainer = PrioritizationExplainer(project_id=sel.get("project_id", "default_project"))
    report = explainer.build_report(selection_obj, persist=False)
    if format.lower() == "markdown":
        return PlainTextResponse(content=report.markdown_report, media_type="text/markdown")
    return report.model_dump()


@router.get("/intelligence/selections/{selection_id}/manifest", response_model=dict[str, Any])
async def get_regression_selection_manifest_endpoint(selection_id: str) -> dict[str, Any]:
    """Generate machine-readable JSON manifest for CI/PR pull request automation."""
    sel = get_regression_selection_by_id(selection_id)
    if not sel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regression selection '{selection_id}' not found.",
        )
    selection_obj = _reconstruct_selection_obj(sel)
    explainer = PrioritizationExplainer(project_id=sel.get("project_id", "default_project"))
    report = explainer.build_report(selection_obj, persist=False)
    return explainer.generate_json_manifest(report)


@router.post("/intelligence/selections/{selection_id}/override")
async def override_selection_decision_endpoint(
    selection_id: str,
    req: DecisionOverrideRequest,
) -> dict[str, Any]:
    """Record explicit user approval or exclusion override for a test with audit rationale."""
    sel = get_regression_selection_by_id(selection_id)
    if not sel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regression selection '{selection_id}' not found.",
        )
    # Project isolation check
    if req.project_id and req.project_id != sel.get("project_id", "default_project"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Project ID mismatch. Cannot override selection belonging to another project.",
        )
    # Ensure testcase belongs to this selection candidates
    all_candidate_ids = set(
        (sel.get("selected_test_ids") or [])
        + (sel.get("excluded_test_ids") or [])
        + (sel.get("budget_exceptions") or [])
        + [t.get("testcase_id") for t in (sel.get("tests") or [])]
    )
    if all_candidate_ids and req.testcase_id not in all_candidate_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Testcase '{req.testcase_id}' does not belong to selection '{selection_id}'.",
        )
    if req.override_decision not in ("selected", "excluded", "user_excluded"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="override_decision must be 'selected' or 'excluded'",
        )
    if not req.override_reason or not req.override_reason.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="override_reason is required for auditability.",
        )
    res = record_user_decision_override(
        selection_id=selection_id,
        testcase_id=req.testcase_id,
        override_decision=req.override_decision,
        override_reason=req.override_reason.strip(),
    )
    return {"status": "ok", "override": res}



# ---------------------------------------------------------------------------
# Autonomous Exploration Endpoints
# ---------------------------------------------------------------------------

@router.post("/autonomous/explore")
async def start_autonomous_exploration(config: ExplorationConfig) -> dict[str, Any]:
    """Start a new background autonomous exploration run."""
    try:
        run_record = await exploration_controller.start_exploration(config)
        return run_record
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start exploration: {exc}",
        )


@router.get("/autonomous/runs")
async def list_exploration_runs_endpoint(
    project_id: str | None = Query(None, description="Optional project filter")
) -> list[dict[str, Any]]:
    """List historical and active autonomous exploration runs."""
    return exploration_controller.list_runs(project_id=project_id)


@router.get("/autonomous/runs/{exploration_id}")
async def get_exploration_run_endpoint(exploration_id: str) -> dict[str, Any]:
    """Get metadata and status of an exploration run."""
    run = exploration_controller.get_run(exploration_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exploration run '{exploration_id}' not found",
        )
    return run


@router.get("/autonomous/runs/{exploration_id}/graph")
async def get_exploration_graph_endpoint(exploration_id: str) -> dict[str, Any]:
    """Get full navigation graph (pages, transitions, forms) of an exploration run."""
    run = exploration_controller.get_run(exploration_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exploration run '{exploration_id}' not found",
        )
    return exploration_controller.get_graph(exploration_id)


@router.post("/autonomous/runs/{exploration_id}/cancel")
async def cancel_exploration_run_endpoint(exploration_id: str) -> dict[str, Any]:
    """Cancel a running autonomous exploration job."""
    success = await exploration_controller.cancel_exploration(exploration_id)
    return {"exploration_id": exploration_id, "cancelled": success}


@router.delete("/autonomous/runs/{exploration_id}")
async def delete_exploration_run_endpoint(exploration_id: str) -> dict[str, Any]:
    """Delete an exploration run and its persisted graph."""
    success = exploration_controller.delete_run(exploration_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exploration run '{exploration_id}' not found",
        )
    return {"exploration_id": exploration_id, "deleted": True}


class SynthesizeRequest(BaseModel):
    project_id: str = "default_project"
    max_journeys: int = Field(default=6, ge=1, le=20)


class DraftApproveRequest(BaseModel):
    custom_name: str | None = None
    modifications: dict[str, Any] | None = None


class DraftRejectRequest(BaseModel):
    reason: str | None = None


@router.post("/autonomous/runs/{exploration_id}/synthesize")
async def synthesize_journeys_endpoint(
    exploration_id: str, req: SynthesizeRequest | None = None
) -> list[dict[str, Any]]:
    """Synthesize test journey drafts from an exploration graph."""
    run = exploration_controller.get_run(exploration_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exploration run '{exploration_id}' not found",
        )

    graph_dict = exploration_controller.get_graph(exploration_id)
    if not graph_dict or not graph_dict.get("nodes"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot synthesize journeys: exploration graph has no discovered page nodes.",
        )

    # Convert graph dict into AppNavigationGraph model
    from tracecase.exploration.models import PageNode, PageTransition
    nodes = {url: PageNode(**n) for url, n in graph_dict.get("nodes", {}).items()}
    transitions = [PageTransition(**t) for t in graph_dict.get("transitions", [])]
    graph = AppNavigationGraph(
        exploration_id=exploration_id,
        start_url=graph_dict.get("start_url", run["start_url"]),
        nodes=nodes,
        transitions=transitions,
    )

    proj_id = req.project_id if req else "default_project"
    max_j = req.max_journeys if req else 6
    drafts = synthesize_test_journeys(graph=graph, project_id=proj_id, max_journeys=max_j)

    saved_drafts = []
    for d in drafts:
        saved = save_synthesized_draft(d.model_dump(mode="json"))
        saved_drafts.append(saved)

    return saved_drafts


@router.get("/autonomous/drafts")
async def list_drafts_endpoint(
    project_id: str | None = Query(None, description="Filter by project"),
    exploration_id: str | None = Query(None, description="Filter by exploration"),
    status: str | None = Query(None, description="Filter by status (pending, approved, rejected)"),
) -> list[dict[str, Any]]:
    """List synthesized test journey drafts."""
    return list_synthesized_drafts(
        project_id=project_id, exploration_id=exploration_id, status=status
    )


@router.get("/autonomous/drafts/{draft_id}")
async def get_draft_endpoint(draft_id: str) -> dict[str, Any]:
    """Get details of a synthesized test journey draft."""
    draft = get_synthesized_draft(draft_id)
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft '{draft_id}' not found",
        )
    return draft


@router.post("/autonomous/drafts/{draft_id}/approve")
async def approve_draft_endpoint(
    draft_id: str, req: DraftApproveRequest | None = None
) -> dict[str, Any]:
    """Approve a test journey draft and promote it into an executable TestCase."""
    try:
        custom_name = req.custom_name if req else None
        modifications = req.modifications if req else None
        result = approve_synthesized_draft(
            draft_id=draft_id,
            custom_name=custom_name,
            modifications=modifications,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed approving draft %s: %s", draft_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed approving draft: {exc}",
        ) from exc


@router.post("/autonomous/drafts/{draft_id}/reject")
async def reject_draft_endpoint(
    draft_id: str, req: DraftRejectRequest | None = None
) -> dict[str, Any]:
    """Reject a test journey draft with optional reason."""
    reason = req.reason if req else "Rejected by reviewer"
    success = reject_synthesized_draft(draft_id=draft_id, reason=reason)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft '{draft_id}' not found",
        )
    return {"draft_id": draft_id, "status": "rejected", "reason": reason}


class DraftUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[dict[str, Any]] | None = None


class RequirementsPlanRequest(BaseModel):
    requirement: str
    exploration_id: str
    project_id: str = "default_project"


class RegressionSelectRequest(BaseModel):
    changed_routes: list[str] = Field(default_factory=list)
    changed_selectors: list[str] = Field(default_factory=list)
    project_id: str = "default_project"
    max_recommendations: int = Field(default=15, ge=1, le=50)


@router.put("/autonomous/drafts/{draft_id}")
async def update_draft_endpoint(
    draft_id: str, req: DraftUpdateRequest
) -> dict[str, Any]:
    """
    Update a draft journey.
    
    Security Guardrail: If previously approved, content modifications reset
    approval status to 'pending' to prevent unreviewed test mutations.
    """
    updated = update_synthesized_draft(
        draft_id=draft_id,
        name=req.name,
        description=req.description,
        steps=req.steps,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft '{draft_id}' not found",
        )
    return updated


@router.post("/autonomous/requirements/plan")
async def plan_requirement_endpoint(req: RequirementsPlanRequest) -> dict[str, Any]:
    """
    Map natural language user stories/requirements against an exploration graph.
    Computes coverage gaps and synthesizes an evidence-backed test journey draft.
    """
    graph_dict = exploration_controller.get_graph(req.exploration_id)
    if not graph_dict or not graph_dict.get("nodes"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Exploration '{req.exploration_id}' has no navigation graph nodes.",
        )

    from tracecase.exploration.models import PageNode, PageTransition
    nodes = {url: PageNode(**n) for url, n in graph_dict.get("nodes", {}).items()}
    transitions = [PageTransition(**t) for t in graph_dict.get("transitions", [])]
    graph = AppNavigationGraph(
        exploration_id=req.exploration_id,
        start_url=graph_dict.get("start_url", ""),
        nodes=nodes,
        transitions=transitions,
    )

    plan_result = plan_requirement_against_graph(
        requirement=req.requirement,
        graph=graph,
        project_id=req.project_id,
    )

    # If draft was synthesized, persist it into synthesized_drafts as pending review
    if plan_result.get("synthesized_draft"):
        saved = save_synthesized_draft(plan_result["synthesized_draft"])
        plan_result["synthesized_draft"] = saved

    return plan_result


@router.post("/autonomous/regression/select")
async def select_regression_endpoint(req: RegressionSelectRequest) -> dict[str, Any]:
    """
    Analyze code/DOM change impact and select an intelligent regression test subset.
    """
    return select_intelligent_regression_suite(
        changed_routes=req.changed_routes,
        changed_selectors=req.changed_selectors,
        project_id=req.project_id,
        max_recommendations=req.max_recommendations,
    )


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


@router.websocket("/ws/explorations/{exploration_id}")
async def exploration_websocket(websocket: WebSocket, exploration_id: str) -> None:
    """Dedicated WebSocket stream for an autonomous exploration run."""
    channel = f"exploration:{exploration_id}"
    await manager.connect(websocket, channel=channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, channel=channel)


@router.websocket("/ws/batches/{batch_id}")
async def batch_websocket(websocket: WebSocket, batch_id: str) -> None:
    """Dedicated WebSocket stream for a batch execution run."""
    channel = f"batch:{batch_id}"
    await manager.connect(websocket, channel=channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, channel=channel)


@router.websocket("/ws/matrices/{matrix_id}")
async def matrix_websocket(websocket: WebSocket, matrix_id: str) -> None:
    """Dedicated WebSocket stream for a cross-browser matrix execution run."""
    channel = f"matrix:{matrix_id}"
    await manager.connect(websocket, channel=channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, channel=channel)
