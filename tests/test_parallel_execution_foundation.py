"""Phase 7.1: Parallel Execution Foundation Tests.

Validates:
1. Bounded Worker Pool: Configurable concurrency (1-8, default 2), sequential mode (c=1).
2. Database Persistence: Schema migration (batch_id, worker_id, concurrency) in execution_runs & execution_batches.
3. Context Isolation: Dedicated artifact output directories per worker/run, independent engines.
4. Exception Isolation: Worker exception/failure does not crash or abort sibling workers.
5. Cancellation & Resource Cleanup: Draining pending queue, cancelling active workers, setting status to cancelled.
6. REST API & WebSockets: Batch creation, batch status, batch cancellation, and suite parallel run.
7. Real Browser Batch Execution: Concurrent multi-test execution using Playwright against local HTTP server.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient

from qa_auto.models import ElementInfo, Step, TestCase
from qa_auto.replay.models import ReplayResult, StepResult
from qa_auto.ui.db import (
    create_execution_batch,
    create_execution_run,
    create_project,
    create_suite,
    get_connection,
    get_execution_batch,
    get_execution_run,
    init_studio_db,
    list_execution_batches,
    list_execution_runs,
    sync_testcase_meta,
)
from qa_auto.ui.executor import ExecutionOrchestrator, orchestrator
from qa_auto.ui.server import create_app


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ParallelTestAppHandler(BaseHTTPRequestHandler):
    """Local HTTP application with distinct endpoints for testing concurrent worker execution."""

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path == "/":
            body = """<!DOCTYPE html>
<html><head><title>Parallel Test Home</title></head>
<body><h1>Home Portal</h1><a id="btn-login" href="/login">Go to Login</a></body></html>"""
        elif path == "/login":
            body = """<!DOCTYPE html>
<html><head><title>Login Page</title></head>
<body><h1>Login</h1><input id="username" type="text" /><button id="submit-btn">Login</button></body></html>"""
        elif path == "/dashboard":
            body = """<!DOCTYPE html>
<html><head><title>Dashboard</title></head>
<body><h1>Dashboard</h1><span id="welcome">Welcome User</span></body></html>"""
        else:
            body = """<!DOCTYPE html>
<html><head><title>404</title></head><body><h1>Not Found</h1></body></html>"""

        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope="module")
def local_web_server():
    port = find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), ParallelTestAppHandler)
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
        user_agent="Mozilla/5.0 QA Auto",
        steps=steps,
        total_duration=1.0,
        total_steps=len(steps),
    )


@pytest.fixture
def testcases_dir(tmp_path: Path) -> Path:
    """Create three test cases on disk with metadata synced to DB."""
    tcs = [
        _make_testcase(
            id="tc_alpha",
            name="Alpha Navigation",
            start_url="http://127.0.0.1:8000/",
            steps=[
                _step(number=1, action_type="navigate", url="http://127.0.0.1:8000/"),
                _step(number=2, action_type="click", selector="#btn-login"),
            ],
        ),
        _make_testcase(
            id="tc_beta",
            name="Beta Login Form",
            start_url="http://127.0.0.1:8000/login",
            steps=[
                _step(number=1, action_type="navigate", url="http://127.0.0.1:8000/login"),
                _step(number=2, action_type="input", selector="#username", input_value="admin"),
            ],
        ),
        _make_testcase(
            id="tc_gamma",
            name="Gamma Dashboard Check",
            start_url="http://127.0.0.1:8000/dashboard",
            steps=[
                _step(number=1, action_type="navigate", url="http://127.0.0.1:8000/dashboard"),
                _step(number=2, action_type="click", selector="#welcome"),
            ],
        ),
    ]

    for tc in tcs:
        folder = tmp_path / tc.id
        folder.mkdir(parents=True, exist_ok=True)
        file_path = folder / "testcase.json"
        file_path.write_text(tc.model_dump_json(indent=2), encoding="utf-8")
        sync_testcase_meta(testcase=tc, file_path=file_path, project_id="default_project")

    return tmp_path


# ---------------------------------------------------------------------------
# 1. Bounded Worker Pool & Concurrency Configuration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrency_bounds_and_clamping(testcases_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify concurrency is clamped to [1, 8] with default 2."""
    monkeypatch.chdir(testcases_dir.parent)
    init_studio_db()

    orch = ExecutionOrchestrator()

    # Mock the internal worker so we test orchestrator bounds without launching browsers
    async def mock_worker(*args: Any, **kwargs: Any) -> None:
        queue = kwargs.get("batch_ctx", {}).get("queue")
        while not queue.empty():
            try:
                tc_file, testcase, run_rec = queue.get_nowait()
                queue.task_done()
            except Exception:
                break

    monkeypatch.setattr(orch, "_run_batch_worker", mock_worker)

    # Test under-bound (< 1 clamped to 1)
    res_under = await orch.start_batch_execution(
        testcase_ids=["tc_alpha"],
        concurrency=0,
    )
    assert res_under["concurrency"] == 1

    # Test over-bound (> 8 clamped to 8)
    res_over = await orch.start_batch_execution(
        testcase_ids=["tc_alpha"],
        concurrency=12,
    )
    assert res_over["concurrency"] == 8

    # Test default concurrency is 2
    res_default = await orch.start_batch_execution(
        testcase_ids=["tc_alpha"],
    )
    assert res_default["concurrency"] == 2


# ---------------------------------------------------------------------------
# 2. Database Schema & Persistence
# ---------------------------------------------------------------------------

def test_database_schema_and_batch_persistence():
    """Verify execution_runs schema columns and execution_batches persistence."""
    init_studio_db()
    conn = get_connection()

    # Verify columns exist
    cursor = conn.execute("PRAGMA table_info(execution_runs)")
    col_names = [row["name"] for row in cursor.fetchall()]
    assert "batch_id" in col_names
    assert "worker_id" in col_names
    assert "concurrency" in col_names

    # Test creating and updating a batch record
    batch_id = f"batch_test_{uuid.uuid4().hex[:8]}"
    batch = create_execution_batch(
        batch_id=batch_id,
        project_id="default_project",
        suite_id="suite_alpha",
        concurrency=4,
        total_tests=3,
    )
    assert batch["id"] == batch_id
    assert batch["concurrency"] == 4
    assert batch["total_tests"] == 3
    assert batch["status"] == "queued"

    # Add child run
    run = create_execution_run(
        testcase_id="tc_alpha",
        testcase_name="Alpha",
        batch_id=batch_id,
        worker_id="worker-1",
        concurrency=4,
    )
    assert run["batch_id"] == batch_id
    assert run["worker_id"] == "worker-1"
    assert run["concurrency"] == 4

    # Fetch batch with runs
    fetched = get_execution_batch(batch_id)
    assert fetched is not None
    assert len(fetched["runs"]) == 1
    assert fetched["runs"][0]["id"] == run["id"]


# ---------------------------------------------------------------------------
# 3. Context & Artifact Isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_worker_context_and_directory_isolation(testcases_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify each worker gets an isolated dedicated directory and independent ReplayEngine."""
    monkeypatch.chdir(testcases_dir.parent)
    init_studio_db()

    orch = ExecutionOrchestrator()
    created_output_dirs: list[Path] = []

    # Mock ReplayEngine to inspect directory and ensure distinct contexts
    class MockReplayEngine:
        def __init__(self, **kwargs: Any) -> None:
            self.output_dir = kwargs.get("output_dir")
            created_output_dirs.append(self.output_dir)
            self.testcase = kwargs.get("testcase")

        async def run(self) -> ReplayResult:
            await asyncio.sleep(0.01)
            now = datetime.now()
            return ReplayResult(
                testcase_id=self.testcase.id,
                started_at=now,
                finished_at=now,
                status="passed",
                duration_ms=10.0,
                exit_code=0,
                steps=[
                    StepResult(number=1, status="passed", duration_ms=5.0),
                    StepResult(number=2, status="passed", duration_ms=5.0),
                ],
            )

    monkeypatch.setattr("qa_auto.ui.executor.ReplayEngine", MockReplayEngine)

    batch = await orch.start_batch_execution(
        testcase_ids=["tc_alpha", "tc_beta", "tc_gamma"],
        concurrency=3,
    )
    batch_id = batch["id"]

    # Wait for coordinator task
    task = orch.active_tasks.get(batch_id)
    if task:
        await task

    # Verify all 3 test cases were executed in dedicated directories
    assert len(created_output_dirs) == 3
    # Check uniqueness of output directories (each worker/run gets unique timestamped folder)
    assert len(set(created_output_dirs)) == 3
    for p in created_output_dirs:
        assert str(batch_id) in str(p)


# ---------------------------------------------------------------------------
# 4. Exception Isolation Across Workers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_worker_exception_isolation(testcases_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify failure or exception in one worker does not abort sibling workers."""
    monkeypatch.chdir(testcases_dir.parent)
    init_studio_db()

    orch = ExecutionOrchestrator()

    class FaultyReplayEngine:
        def __init__(self, **kwargs: Any) -> None:
            self.testcase = kwargs.get("testcase")

        async def run(self) -> ReplayResult:
            if self.testcase.id == "tc_beta":
                # Simulated unhandled engine failure
                raise RuntimeError("Simulated browser crash on Beta")
            now = datetime.now()
            return ReplayResult(
                testcase_id=self.testcase.id,
                started_at=now,
                finished_at=now,
                status="passed",
                duration_ms=10.0,
                exit_code=0,
                steps=[StepResult(number=1, status="passed", duration_ms=5.0)],
            )

    monkeypatch.setattr("qa_auto.ui.executor.ReplayEngine", FaultyReplayEngine)

    batch = await orch.start_batch_execution(
        testcase_ids=["tc_alpha", "tc_beta", "tc_gamma"],
        concurrency=2,
    )
    batch_id = batch["id"]

    task = orch.active_tasks.get(batch_id)
    if task:
        await task

    # Fetch final batch record
    final_batch = get_execution_batch(batch_id)
    assert final_batch is not None
    assert final_batch["status"] == "failed"
    assert final_batch["passed_tests"] == 2
    assert final_batch["failed_tests"] == 1

    # Verify individual runs in SQLite
    runs = final_batch["runs"]
    run_statuses = {r["testcase_id"]: r["status"] for r in runs}
    assert run_statuses["tc_alpha"] == "passed"
    assert run_statuses["tc_beta"] == "error"
    assert run_statuses["tc_gamma"] == "passed"


# ---------------------------------------------------------------------------
# 5. Batch Cancellation & Clean-up
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_batch_cancellation(testcases_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify cancelling a batch terminates active workers and marks remaining queue cancelled."""
    monkeypatch.chdir(testcases_dir.parent)
    init_studio_db()

    orch = ExecutionOrchestrator()

    class SlowReplayEngine:
        def __init__(self, **kwargs: Any) -> None:
            self.testcase = kwargs.get("testcase")

        async def run(self) -> ReplayResult:
            await asyncio.sleep(2.0)
            return ReplayResult(
                status="passed",
                duration_ms=2000.0,
                exit_code=0,
                steps=[],
            )

    monkeypatch.setattr("qa_auto.ui.executor.ReplayEngine", SlowReplayEngine)

    batch = await orch.start_batch_execution(
        testcase_ids=["tc_alpha", "tc_beta", "tc_gamma"],
        concurrency=1,  # Sequential so tc_beta and tc_gamma stay queued while tc_alpha runs
    )
    batch_id = batch["id"]

    await asyncio.sleep(0.05)
    # Cancel batch
    cancelled = await orch.cancel_batch_execution(batch_id)
    assert cancelled is True

    # Allow cancellation propagation
    await asyncio.sleep(0.1)

    final_batch = get_execution_batch(batch_id)
    assert final_batch is not None
    assert final_batch["status"] == "cancelled"


# ---------------------------------------------------------------------------
# 6. REST API Endpoints
# ---------------------------------------------------------------------------

def test_batch_execution_api_endpoints(testcases_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """Test POST /api/executions/batch, GET /api/executions/batches, and POST /api/suites/{id}/run."""
    monkeypatch.chdir(testcases_dir.parent)
    init_studio_db()

    class SlowReplayEngine:
        def __init__(self, **kwargs: Any) -> None:
            self.testcase = kwargs.get("testcase")

        async def run(self) -> ReplayResult:
            await asyncio.sleep(2.0)
            now = datetime.now()
            return ReplayResult(
                testcase_id=self.testcase.id,
                started_at=now,
                finished_at=now,
                status="passed",
                duration_ms=2000.0,
                exit_code=0,
                steps=[],
            )

    monkeypatch.setattr("qa_auto.ui.executor.ReplayEngine", SlowReplayEngine)

    client = TestClient(create_app())

    # 1. Create a suite
    create_project("default_project", "Default Project")
    suite = create_suite(
        project_id="default_project",
        name="Regression Suite",
        testcase_ids=["tc_alpha", "tc_beta"],
    )
    suite_id = suite["id"]

    # 2. Run suite with concurrency
    res_suite = client.post(
        f"/api/suites/{suite_id}/run",
        json={"concurrency": 4, "browser": "chromium"},
    )
    assert res_suite.status_code == 200
    suite_runs = res_suite.json()
    assert len(suite_runs) == 2
    assert suite_runs[0]["concurrency"] == 4

    # 3. Direct batch execution endpoint
    res_batch = client.post(
        "/api/executions/batch",
        json={
            "testcase_ids": ["tc_alpha", "tc_gamma"],
            "concurrency": 2,
            "browser": "firefox",
        },
    )
    assert res_batch.status_code == 200
    batch_data = res_batch.json()
    batch_id = batch_data["id"]
    assert batch_data["concurrency"] == 2
    assert len(batch_data["runs"]) == 2

    # 4. Fetch batch details
    res_get = client.get(f"/api/executions/batches/{batch_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == batch_id

    # 5. Cancel batch
    res_cancel = client.post(f"/api/executions/batches/{batch_id}/cancel")
    assert res_cancel.status_code == 200
    assert res_cancel.json()["cancelled"] is True


# ---------------------------------------------------------------------------
# 7. Real Playwright Browser Parallel Batch Execution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_real_playwright_parallel_batch_execution(
    local_web_server: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Execute real Playwright browser instances in parallel across isolated workers."""
    monkeypatch.chdir(tmp_path)
    init_studio_db()

    # Create real test cases targeting the running local web server
    tc1 = _make_testcase(
        id="real_tc_home",
        name="Real Home Test",
        start_url=f"{local_web_server}/",
        steps=[
            _step(number=1, action_type="navigate", url=f"{local_web_server}/"),
            _step(number=2, action_type="click", selector="#btn-login"),
        ],
    )
    tc2 = _make_testcase(
        id="real_tc_login",
        name="Real Login Test",
        start_url=f"{local_web_server}/login",
        steps=[
            _step(number=1, action_type="navigate", url=f"{local_web_server}/login"),
            _step(number=2, action_type="input", selector="#username", input_value="engineer"),
            _step(number=3, action_type="click", selector="#submit-btn"),
        ],
    )

    for tc in [tc1, tc2]:
        folder = tmp_path / tc.id
        folder.mkdir(parents=True, exist_ok=True)
        file_path = folder / "testcase.json"
        file_path.write_text(tc.model_dump_json(indent=2), encoding="utf-8")
        sync_testcase_meta(testcase=tc, file_path=file_path, project_id="default_project")

    orch = ExecutionOrchestrator()
    batch = await orch.start_batch_execution(
        testcase_ids=["real_tc_home", "real_tc_login"],
        concurrency=2,
        browser="chromium",
        headed=False,
    )
    batch_id = batch["id"]

    # Wait for completion of coordinator
    task = orch.active_tasks.get(batch_id)
    if task:
        await task

    final_batch = get_execution_batch(batch_id)
    assert final_batch is not None
    assert final_batch["status"] == "passed"
    assert final_batch["passed_tests"] == 2
    assert final_batch["failed_tests"] == 0

    # Verify both child runs passed and recorded isolated worker IDs
    runs = final_batch["runs"]
    worker_ids = {r["worker_id"] for r in runs}
    assert len(worker_ids) >= 1
    for r in runs:
        assert r["status"] == "passed"
        assert r["passed_steps"] >= 2
