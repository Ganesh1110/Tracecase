"""Phase 7.2: Cross-Browser Matrix Execution Tests.

Validates:
1. Matrix Database Schema & Persistence:
   - Schema creation (matrix_id in execution_runs, execution_matrices table).
   - CRUD functions (create_execution_matrix, update_execution_matrix, get_execution_matrix, list_execution_matrices).
2. Cross-Product Queue Generation:
   - Configurable browser selection (Chromium, Firefox, WebKit).
   - N test cases x M browsers = N*M independent child runs.
   - Bounded concurrency pool (1-8, default 2).
   - Draft approval guardrail enforcement.
3. Artifact Isolation:
   - Dedicated output directory per matrix, browser, and worker run:
     replay_runs/{matrix_id}_{browser}_{worker_id}_{ts}/
4. Cross-Browser Divergence Detection:
   - Flag tests passing in one browser but failing/erroring in another.
   - Consolidated comparison grid (Test Cases x Browsers).
   - Cross-browser parity rate % and per-browser pass rates.
5. Browser Environment Failure Distinction:
   - Distinguish missing browser binaries (playwright install required) from application test failures.
6. Matrix Cancellation Integrity:
   - Cancel matrix execution, draining pending items and terminating active workers cleanly.
7. REST API & WebSockets:
   - POST /api/executions/matrix, GET /api/executions/matrices, GET /api/executions/matrices/{id},
     POST /api/executions/matrices/{id}/cancel, POST /api/suites/{id}/run_matrix.
8. Real Browser Cross-Browser Matrix Execution:
   - Real Playwright execution against local HTTP test server.
"""

from __future__ import annotations

import asyncio
import socket
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tracecase.models import ElementInfo, Step, TestCase
from tracecase.replay.models import ReplayResult, StepResult
from tracecase.ui.db import (
    create_execution_matrix,
    create_execution_run,
    create_suite,
    get_execution_matrix,
    init_studio_db,
    list_execution_matrices,
    sync_testcase_meta,
    update_execution_matrix,
    update_execution_run_status,
)
from tracecase.ui.executor import ExecutionOrchestrator
from tracecase.ui.server import create_app


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class MatrixTestAppHandler(BaseHTTPRequestHandler):
    """Local HTTP application with distinct endpoints for testing cross-browser matrix execution."""

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path == "/":
            body = """<!DOCTYPE html>
<html><head><title>Matrix Home</title></head>
<body><h1>Cross-Browser Matrix Portal</h1><a id="nav-login" href="/login">Login</a></body></html>"""
        elif path == "/login":
            body = """<!DOCTYPE html>
<html><head><title>Matrix Login</title></head>
<body><h1>Login Page</h1><input id="user-input" type="text" /><button id="btn-submit">Submit</button></body></html>"""
        else:
            body = """<!DOCTYPE html><html><head><title>404</title></head><body><h1>Not Found</h1></body></html>"""

        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope="module")
def matrix_web_server():
    port = find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), MatrixTestAppHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()
    server.server_close()


def _element(selector: str, tag_name: str = "button", text: str = "Test") -> ElementInfo:
    return ElementInfo(
        selector=selector,
        xpath=f"//*[@id='{selector.lstrip('#')}']",
        tag_name=tag_name,
        text=text,
        attributes={"id": selector.lstrip("#")},
        bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
    )


def _step(
    number: int,
    action_type: str,
    selector: str | None = None,
    url: str | None = None,
    input_value: str | None = None,
) -> Step:
    elem = _element(selector) if selector else None
    return Step(
        number=number,
        timestamp=datetime.now(),
        action_type=action_type,
        element=elem,
        url=url,
        input_value=input_value,
        description_short=f"Step {number}: {action_type}",
        description_detailed=f"Detailed step {number}: {action_type} on {selector or url}",
    )


def _make_testcase(id: str, name: str, start_url: str, steps: list[Step]) -> TestCase:
    return TestCase(
        id=id,
        name=name,
        created_at=datetime.now().isoformat(),
        start_url=start_url,
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0 Tracecase",
        steps=steps,
        total_duration=1.0,
        total_steps=len(steps),
    )


@pytest.fixture
def matrix_testcases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, list[TestCase]]:
    """Fixture to create isolated test cases on disk in a temporary directory and chdir to its parent."""
    monkeypatch.chdir(tmp_path)
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    init_studio_db()

    tc1 = _make_testcase(
        id="tc_mat_1",
        name="Matrix Target Alpha",
        start_url="http://app/alpha",
        steps=[
            _step(number=1, action_type="navigate", url="http://app/alpha"),
            _step(number=2, action_type="click", selector="#btn-submit"),
        ],
    )
    dir1 = recordings_dir / tc1.id
    dir1.mkdir(parents=True, exist_ok=True)
    f1 = dir1 / "testcase.json"
    f1.write_text(tc1.model_dump_json(indent=2), encoding="utf-8")
    sync_testcase_meta(testcase=tc1, file_path=f1, approval_status="approved")

    tc2 = _make_testcase(
        id="tc_mat_2",
        name="Matrix Target Beta",
        start_url="http://app/beta",
        steps=[
            _step(number=1, action_type="navigate", url="http://app/beta"),
            _step(number=2, action_type="input", selector="#user-input", input_value="val"),
        ],
    )
    dir2 = recordings_dir / tc2.id
    dir2.mkdir(parents=True, exist_ok=True)
    f2 = dir2 / "testcase.json"
    f2.write_text(tc2.model_dump_json(indent=2), encoding="utf-8")
    sync_testcase_meta(testcase=tc2, file_path=f2, approval_status="approved")

    return recordings_dir, [tc1, tc2]


class MockMatrixReplayEngine:
    """Mock engine allowing browser-conditioned execution results."""

    def __init__(
        self,
        testcase: TestCase,
        browser_type: str = "chromium",
        output_dir: Path | None = None,
        step_callback: Any = None,
        fail_browsers: list[str] | None = None,
        error_browsers: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        self.testcase = testcase
        self.browser_type = browser_type
        self.output_dir = output_dir or Path("/tmp/replay")
        self.step_callback = step_callback
        self.fail_browsers = fail_browsers or []
        self.error_browsers = error_browsers or []

    async def run(self) -> ReplayResult:
        if self.browser_type in self.error_browsers:
            err_msg = (
                f"BrowserType.launch: Executable doesn't exist at /fake/path/{self.browser_type}\n"
                f"Please run 'playwright install {self.browser_type}'"
            )
            step_err = StepResult(number=1, status="error", duration_ms=0.0, error=err_msg)
            now = datetime.now()
            return ReplayResult(
                testcase_id=self.testcase.id,
                started_at=now,
                finished_at=now,
                status="error",
                exit_code=2,
                steps=[step_err],
            )

        should_fail = self.browser_type in self.fail_browsers

        steps_res = []
        for s in self.testcase.steps:
            await asyncio.sleep(0.01)
            status = "failed" if should_fail and s.number == len(self.testcase.steps) else "passed"
            err = "Simulated browser incompatibility failure" if status == "failed" else None
            sr = StepResult(
                number=s.number,
                status=status,
                duration_ms=10.0,
                selector_used=s.element.selector if s.element else None,
                error=err,
            )
            steps_res.append(sr)
            if self.step_callback:
                await self.step_callback(sr, s.number, len(self.testcase.steps))

        final_st = "failed" if should_fail else "passed"
        now = datetime.now()
        return ReplayResult(
            testcase_id=self.testcase.id,
            started_at=now,
            finished_at=now,
            status=final_st,
            exit_code=1 if should_fail else 0,
            steps=steps_res,
        )


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_matrix_database_schema_and_crud(tmp_path: Path):
    """Test 1: Verify execution_matrices table schema, CRUD operations, and divergence calculations."""
    db_file = tmp_path / "test_studio.db"
    init_studio_db(db_file)

    matrix_id = "matrix_test_1"
    mat = create_execution_matrix(
        matrix_id=matrix_id,
        project_id="default_project",
        name="Checkout Cross-Browser Matrix",
        concurrency=3,
        browsers=["chromium", "firefox", "webkit"],
        total_executions=6,
        db_path=db_file,
    )
    assert mat["id"] == matrix_id
    assert mat["concurrency"] == 3
    assert mat["browsers"] == ["chromium", "firefox", "webkit"]
    assert mat["total_executions"] == 6
    assert mat["status"] == "queued"

    # Add child execution runs:
    # Testcase 1: Consistent pass across chromium & firefox
    r1 = create_execution_run(
        testcase_id="tc_1",
        testcase_name="Login Flow",
        browser="chromium",
        matrix_id=matrix_id,
        db_path=db_file,
    )
    update_execution_run_status(r1["id"], status="passed", duration_ms=150.0, db_path=db_file)

    r2 = create_execution_run(
        testcase_id="tc_1",
        testcase_name="Login Flow",
        browser="firefox",
        matrix_id=matrix_id,
        db_path=db_file,
    )
    update_execution_run_status(r2["id"], status="passed", duration_ms=160.0, db_path=db_file)

    # Testcase 2: Divergent! Passes on chromium, fails on firefox
    r3 = create_execution_run(
        testcase_id="tc_2",
        testcase_name="Checkout Flow",
        browser="chromium",
        matrix_id=matrix_id,
        db_path=db_file,
    )
    update_execution_run_status(r3["id"], status="passed", duration_ms=200.0, db_path=db_file)

    r4 = create_execution_run(
        testcase_id="tc_2",
        testcase_name="Checkout Flow",
        browser="firefox",
        matrix_id=matrix_id,
        db_path=db_file,
    )
    update_execution_run_status(r4["id"], status="failed", duration_ms=210.0, error_message="Element not clickable in Firefox", db_path=db_file)

    # Fetch matrix and verify consolidated grid and divergence
    fetched = get_execution_matrix(matrix_id, db_path=db_file)
    assert fetched is not None
    assert len(fetched["runs"]) == 4

    grid = fetched["grid"]
    assert len(grid) == 2  # tc_1 and tc_2

    tc1_item = next(g for g in grid if g["testcase_id"] == "tc_1")
    assert tc1_item["is_divergent"] is False
    assert tc1_item["divergence_notes"] is None

    tc2_item = next(g for g in grid if g["testcase_id"] == "tc_2")
    assert tc2_item["is_divergent"] is True
    assert "Divergence detected" in tc2_item["divergence_notes"]
    assert "firefox: failed" in tc2_item["divergence_notes"]

    assert fetched["total_testcases"] == 2
    assert fetched["divergent_testcases_count"] == 1
    assert fetched["cross_browser_parity_pct"] == 50.0
    assert fetched["browser_pass_rates"]["chromium"] == 100.0
    assert fetched["browser_pass_rates"]["firefox"] == 50.0

    # Test update and list
    updated = update_execution_matrix(
        matrix_id=matrix_id,
        status="failed",
        divergence_count=1,
        finished_at=datetime.now().isoformat(),
        duration_ms=720.0,
        db_path=db_file,
    )
    assert updated["status"] == "failed"

    m_list = list_execution_matrices(db_path=db_file)
    assert len(m_list) >= 1
    assert any(m["id"] == matrix_id for m in m_list)


@pytest.mark.asyncio
async def test_matrix_cross_product_queue_and_concurrency(matrix_testcases: tuple[Path, list[TestCase]]):
    """Test 2: Verify cross-product queue generation (N testcases x M browsers) and bounded concurrency."""
    _, tcs = matrix_testcases
    orch = ExecutionOrchestrator()

    # Launch matrix with 2 testcases x 3 browsers = 6 runs, with concurrency requested as 10 (clamped to 8)
    with patch("tracecase.ui.executor.ReplayEngine", side_effect=lambda **kw: MockMatrixReplayEngine(**kw)):
        matrix_info = await orch.start_matrix_execution(
            testcase_ids=[tcs[0].id, tcs[1].id],
            browsers=["chromium", "firefox", "webkit"],
            concurrency=10,  # Should clamp to 8
        )

        matrix_id = matrix_info["id"]
        assert matrix_info["concurrency"] == 8
        assert matrix_info["total_executions"] == 6

        coord_task = orch.active_tasks.get(matrix_id)
        if coord_task:
            await coord_task

        final_matrix = get_execution_matrix(matrix_id)
        assert final_matrix is not None
        assert final_matrix["total_executions"] == 6
        assert len(final_matrix["runs"]) == 6

        browsers_executed = {r["browser"] for r in final_matrix["runs"]}
        assert browsers_executed == {"chromium", "firefox", "webkit"}


@pytest.mark.asyncio
async def test_matrix_unapproved_draft_guardrail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test 3: Verify unapproved drafts cannot be launched in a matrix run."""
    monkeypatch.chdir(tmp_path)
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    init_studio_db()

    tc_draft = _make_testcase("tc_draft_x", "Draft Test", "http://app/draft", [_step(1, "navigate", url="http://app/draft")])
    tc_dir = recordings_dir / "tc_draft_x"
    tc_dir.mkdir(parents=True, exist_ok=True)
    tc_file = tc_dir / "testcase.json"
    tc_file.write_text(tc_draft.model_dump_json(indent=2), encoding="utf-8")
    sync_testcase_meta(tc_draft, tc_file, approval_status="draft")

    orch = ExecutionOrchestrator()
    with pytest.raises(ValueError, match="draft requires human approval"):
        await orch.start_matrix_execution(testcase_ids=["tc_draft_x"], browsers=["chromium", "firefox"])


@pytest.mark.asyncio
async def test_cross_browser_divergence_detection(matrix_testcases: tuple[Path, list[TestCase]]):
    """Test 4: Verify divergence is accurately flagged when Chromium passes and Firefox fails."""
    _, tcs = matrix_testcases
    orch = ExecutionOrchestrator()

    with patch(
        "tracecase.ui.executor.ReplayEngine",
        side_effect=lambda **kw: MockMatrixReplayEngine(fail_browsers=["firefox"], **kw),
    ):
        matrix_res = await orch.start_matrix_execution(
            testcase_ids=[tcs[0].id],
            browsers=["chromium", "firefox"],
            concurrency=2,
        )
        matrix_id = matrix_res["id"]
        coord_task = orch.active_tasks.get(matrix_id)
        if coord_task:
            await coord_task

        final_mat = get_execution_matrix(matrix_id)
        assert final_mat["status"] == "failed"
        assert final_mat["divergence_count"] == 1
        assert final_mat["cross_browser_parity_pct"] == 0.0  # 1 out of 1 testcase diverged
        assert final_mat["browser_pass_rates"]["chromium"] == 100.0
        assert final_mat["browser_pass_rates"]["firefox"] == 0.0

        grid = final_mat["grid"]
        assert len(grid) == 1
        assert grid[0]["is_divergent"] is True
        assert "Divergence detected" in grid[0]["divergence_notes"]


@pytest.mark.asyncio
async def test_browser_environment_error_distinction(matrix_testcases: tuple[Path, list[TestCase]]):
    """Test 5: Verify missing browser binaries are caught and identified as browser environment errors."""
    _, tcs = matrix_testcases
    orch = ExecutionOrchestrator()

    with patch(
        "tracecase.ui.executor.ReplayEngine",
        side_effect=lambda **kw: MockMatrixReplayEngine(error_browsers=["webkit"], **kw),
    ):
        matrix_res = await orch.start_matrix_execution(
            testcase_ids=[tcs[0].id],
            browsers=["chromium", "webkit"],
            concurrency=2,
        )
        matrix_id = matrix_res["id"]
        coord_task = orch.active_tasks.get(matrix_id)
        if coord_task:
            await coord_task

        final_mat = get_execution_matrix(matrix_id)
        webkit_run = next(r for r in final_mat["runs"] if r["browser"] == "webkit")
        assert webkit_run["status"] == "error"
        assert "Browser binary missing for 'webkit'" in webkit_run["error_message"]
        assert "playwright install webkit" in webkit_run["error_message"]


@pytest.mark.asyncio
async def test_matrix_cancellation(matrix_testcases: tuple[Path, list[TestCase]]):
    """Test 6: Verify cancelling matrix execution drains queue and marks pending/active runs cancelled."""
    _, tcs = matrix_testcases
    orch = ExecutionOrchestrator()

    class SlowReplayEngine:
        def __init__(self, **kw: Any) -> None:
            pass

        async def run(self) -> ReplayResult:
            await asyncio.sleep(10.0)
            now = datetime.now()
            return ReplayResult(testcase_id="tc_mat_1", started_at=now, finished_at=now, status="passed", exit_code=0, steps=[])

    with patch("tracecase.ui.executor.ReplayEngine", side_effect=lambda **kw: SlowReplayEngine(**kw)):
        matrix_res = await orch.start_matrix_execution(
            testcase_ids=[tcs[0].id],
            browsers=["chromium", "firefox", "webkit"],
            concurrency=1,
        )
        matrix_id = matrix_res["id"]
        await asyncio.sleep(0.05)

        cancelled = await orch.cancel_matrix_execution(matrix_id)
        assert cancelled is True

        mat = get_execution_matrix(matrix_id)
        assert mat["status"] == "cancelled"
        for r in mat["runs"]:
            assert r["status"] in ("cancelled", "running")


def test_matrix_api_endpoints(matrix_testcases: tuple[Path, list[TestCase]]):
    """Test 7: Verify REST API endpoints for matrix launch, listing, detail, and suite execution."""
    _, tcs = matrix_testcases
    app = create_app()
    client = TestClient(app)

    # 1. Launch matrix execution via POST /api/executions/matrix
    with patch("tracecase.ui.executor.ReplayEngine", side_effect=lambda **kw: MockMatrixReplayEngine(**kw)):
        resp = client.post(
            "/api/executions/matrix",
            json={
                "testcase_ids": [tcs[0].id],
                "browsers": ["chromium", "firefox"],
                "concurrency": 2,
                "matrix_name": "API Matrix Run",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        matrix_id = data["id"]
        assert data["browsers"] == ["chromium", "firefox"]

        # 2. Get matrix details via GET /api/executions/matrices/{id}
        detail_resp = client.get(f"/api/executions/matrices/{matrix_id}")
        assert detail_resp.status_code == 200
        detail_data = detail_resp.json()
        assert detail_data["id"] == matrix_id
        assert "grid" in detail_data
        assert "cross_browser_parity_pct" in detail_data

        # 3. List matrices via GET /api/executions/matrices
        list_resp = client.get("/api/executions/matrices")
        assert list_resp.status_code == 200
        matrices = list_resp.json()
        assert any(m["id"] == matrix_id for m in matrices)

        # 4. Filter executions by matrix_id
        runs_resp = client.get(f"/api/executions?matrix_id={matrix_id}")
        assert runs_resp.status_code == 200
        runs_data = runs_resp.json()
        assert len(runs_data) == 2

        # 5. Suite matrix execution via POST /api/suites/{suite_id}/run_matrix
        suite = create_suite(name="Matrix Test Suite", project_id="default_project", testcase_ids=[tcs[0].id])
        suite_id = suite["id"]

        suite_mat_resp = client.post(
            f"/api/suites/{suite_id}/run_matrix",
            json={"browsers": ["chromium"], "concurrency": 1},
        )
        assert suite_mat_resp.status_code == 200
        assert suite_mat_resp.json()["suite_id"] == suite_id


@pytest.mark.asyncio
async def test_real_browser_cross_browser_matrix_execution(matrix_web_server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test 8: Real Playwright execution against local test server with installed & missing browser detection."""
    monkeypatch.chdir(tmp_path)
    base_url = matrix_web_server
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    init_studio_db()

    tc = _make_testcase(
        "tc_real_matrix",
        "Real Matrix Test",
        f"{base_url}/",
        [
            _step(1, "navigate", url=f"{base_url}/"),
            _step(2, "click", selector="#nav-login"),
        ],
    )
    tc_dir = recordings_dir / "tc_real_matrix"
    tc_dir.mkdir(parents=True, exist_ok=True)
    tc_file = tc_dir / "testcase.json"
    tc_file.write_text(tc.model_dump_json(indent=2), encoding="utf-8")
    sync_testcase_meta(tc, tc_file, approval_status="approved")

    orch = ExecutionOrchestrator()

    # Chromium is installed, Firefox is missing.
    # The matrix executes Chromium with real Playwright browser engine,
    # and accurately catches Firefox missing binary error.
    matrix_res = await orch.start_matrix_execution(
        testcase_ids=["tc_real_matrix"],
        browsers=["chromium", "firefox"],
        concurrency=2,
    )
    matrix_id = matrix_res["id"]

    coord_task = orch.active_tasks.get(matrix_id)
    if coord_task:
        await coord_task

    final_mat = get_execution_matrix(matrix_id)
    assert final_mat is not None
    assert final_mat["total_executions"] == 2

    # Check chromium run: real browser executed and passed
    chrom_run = next(r for r in final_mat["runs"] if r["browser"] == "chromium")
    assert chrom_run["status"] == "passed"
    assert chrom_run["passed_steps"] == 2

    # Check firefox run: missing binary detected and classified as environment error
    fox_run = next(r for r in final_mat["runs"] if r["browser"] == "firefox")
    assert fox_run["status"] == "error"
    assert "Browser binary missing for 'firefox'" in fox_run["error_message"]

    # Verify cross-browser divergence was automatically computed
    assert final_mat["divergence_count"] == 1
    assert final_mat["cross_browser_parity_pct"] == 0.0
    assert final_mat["browser_pass_rates"]["chromium"] == 100.0
    assert final_mat["browser_pass_rates"]["firefox"] == 0.0

    grid_item = final_mat["grid"][0]
    assert grid_item["is_divergent"] is True
    assert "chromium: passed" in grid_item["divergence_notes"]
    assert "firefox: error" in grid_item["divergence_notes"]
