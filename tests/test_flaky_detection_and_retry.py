"""Phase 7.3: Flaky Test Detection & Intelligent Retry Tests.

Validates:
1. Database Schema & Persistence for Retries & Attempts:
   - Columns: retries, attempt_count, retry_history_json, failure_step, failure_selector in execution_runs.
   - execution_attempts table: record_execution_attempt, get_execution_attempts.
   - Permanent preservation of all attempts without overwriting initial failure data.
2. Configurable Retry Engine:
   - Retry failed tests 0-3 times (default: 2 retries).
   - ReplayRequest, BatchExecutionRequest, MatrixExecutionRequest accept retries.
3. Flaky Test Classification & Status Design:
   - Attempt 1 passes -> "passed".
   - Attempt 1 fails, Attempt 2 or 3 passes -> "flaky".
   - All attempts fail -> "failed".
   - Cancelled -> "cancelled".
   - Browser environment error (missing browser binary) -> "error" (no retries).
4. Failure Intelligence:
   - Capture failed step, failed selector, error message, execution duration, and attempt history.
5. Historical Flakiness Analysis:
   - get_testcase_flakiness_stats calculates flakiness_score, reliability_score, rating (stable/low/moderate/high),
     and flakiness_by_browser breakdown.
6. Batch & Matrix Parallel Integration:
   - Flaky tests and retry attempts tracked in parallel batch and matrix coordinators.
7. REST API Endpoints:
   - GET /api/executions/{execution_id}/attempts
   - GET /api/testcases/{testcase_id}/flakiness
8. Real Browser Execution with Playwright:
   - Real browser run validating end-to-end replay engine execution.
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
    create_execution_batch,
    create_execution_matrix,
    create_execution_run,
    get_execution_attempts,
    get_execution_batch,
    get_execution_matrix,
    get_execution_run,
    get_testcase_flakiness_stats,
    init_studio_db,
    record_execution_attempt,
    sync_testcase_meta,
    update_execution_batch,
    update_execution_matrix,
    update_execution_run_status,
)
from tracecase.ui.executor import ExecutionOrchestrator, is_browser_env_error
from tracecase.ui.server import create_app


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FlakyAppHandler(BaseHTTPRequestHandler):
    """Local HTTP app for testing real browser runs."""
    fail_then_pass_requests = 0

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path == "/fail-then-pass":
            FlakyAppHandler.fail_then_pass_requests += 1
            if FlakyAppHandler.fail_then_pass_requests == 1:
                # First attempt: element is missing so click times out
                body = """<!DOCTYPE html>
<html><head><title>Flaky Page</title></head>
<body><h1>Transient State</h1><p id="loading">Components loading...</p></body></html>"""
            else:
                # Subsequent attempts (retry): element is present and clickable
                body = """<!DOCTYPE html>
<html><head><title>Flaky Page</title></head>
<body><h1>Ready</h1><button id="btn-action">Click Me</button></body></html>"""
        elif path == "/":
            body = """<!DOCTYPE html>
<html><head><title>Flaky Test Page</title></head>
<body><h1>Flaky App Portal</h1><button id="btn-action">Click Me</button></body></html>"""
        else:
            body = "<html><body>404 Not Found</body></html>"

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


@pytest.fixture(scope="module")
def local_app_server():
    port = find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), FlakyAppHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()
    server.server_close()


@pytest.fixture
def testcase_dir(tmp_path: Path) -> Path:
    tc_dir = tmp_path / "testcases" / "test_flaky_login"
    tc_dir.mkdir(parents=True, exist_ok=True)
    return tc_dir


def _make_element(selector: str, tag_name: str = "button", text: str = "Action") -> ElementInfo:
    return ElementInfo(
        selector=selector,
        xpath=f"//*[@id='{selector.lstrip('#')}']",
        tag_name=tag_name,
        text=text,
        attributes={"id": selector.lstrip("#")},
        bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
    )


def _make_testcase(id: str, name: str, start_url: str, steps: list[Step], browser: str = "chromium") -> TestCase:
    return TestCase(
        id=id,
        name=name,
        created_at=datetime.now().isoformat(),
        start_url=start_url,
        browser=browser,
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0 Tracecase",
        steps=steps,
        total_duration=1.0,
        total_steps=len(steps),
    )


def _make_replay_res(
    status: str,
    exit_code: int = 0,
    steps: list[StepResult] | None = None,
    testcase_id: str = "test_flaky_case_1",
) -> ReplayResult:
    now = datetime.now()
    return ReplayResult(
        testcase_id=testcase_id,
        started_at=now,
        finished_at=now,
        status=status,
        exit_code=exit_code,
        steps=steps or [],
    )


@pytest.fixture
def sample_testcase(testcase_dir: Path) -> TestCase:
    tc = _make_testcase(
        id="test_flaky_case_1",
        name="Flaky Login Test Case",
        start_url="http://127.0.0.1:8000/",
        steps=[
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="click",
                element=_make_element("#btn-action"),
                description_short="Click action button",
                description_detailed="Click action button with id btn-action",
            )
        ],
    )
    tc_file = testcase_dir / "testcase.json"
    tc_file.write_text(tc.model_dump_json(indent=2), encoding="utf-8")
    return tc


# ===========================================================================
# 1. Database Schema & Attempt Persistence Tests
# ===========================================================================

def test_db_schema_and_attempt_recording(tmp_path: Path):
    db_file = tmp_path / "studio_flaky_test.db"
    init_studio_db(db_file)

    # 1. Create run with retries=2
    run = create_execution_run(
        testcase_id="tc_flaky_01",
        testcase_name="Flaky Case 01",
        retries=2,
        db_path=db_file,
    )
    assert run["id"] is not None
    assert run["retries"] == 2
    assert run["attempt_count"] == 1
    assert run["status"] == "queued"

    # 2. Record Attempt 1 (Failure)
    att1 = record_execution_attempt(
        execution_id=run["id"],
        attempt_number=1,
        status="failed",
        duration_ms=1250.0,
        error_message="Timeout waiting for selector '#btn-action'",
        failed_step=1,
        failed_selector="#btn-action",
        report_path="/tmp/run1",
        db_path=db_file,
    )
    assert att1["id"].startswith("att_")
    assert att1["attempt_number"] == 1
    assert att1["status"] == "failed"

    # 3. Record Attempt 2 (Success on Retry)
    att2 = record_execution_attempt(
        execution_id=run["id"],
        attempt_number=2,
        status="passed",
        duration_ms=850.0,
        error_message=None,
        report_path="/tmp/run2",
        db_path=db_file,
    )
    assert att2["attempt_number"] == 2
    assert att2["status"] == "passed"

    # 4. Update run status to 'flaky' with retry_history
    history = [att1, att2]
    update_execution_run_status(
        execution_id=run["id"],
        status="flaky",
        attempt_count=2,
        retry_history=history,
        failure_step=1,
        failure_selector="#btn-action",
        error_message="Timeout waiting for selector '#btn-action'",
        db_path=db_file,
    )

    # 5. Fetch execution run and verify attempt preservation
    fetched = get_execution_run(run["id"], db_path=db_file)
    assert fetched["status"] == "flaky"
    assert fetched["attempt_count"] == 2
    assert fetched["retries"] == 2
    assert fetched["failure_step"] == 1
    assert fetched["failure_selector"] == "#btn-action"
    assert len(fetched["attempts"]) == 2
    assert fetched["attempts"][0]["status"] == "failed"
    assert fetched["attempts"][0]["error_message"] == "Timeout waiting for selector '#btn-action'"
    assert fetched["attempts"][1]["status"] == "passed"


# ===========================================================================
# 2. Intelligent Retry & Status Classification Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_flaky_test_classification_fail_then_pass(tmp_path: Path, sample_testcase: TestCase, monkeypatch: pytest.MonkeyPatch):
    """Attempt 1 fails -> Attempt 2 passes -> final status must be 'flaky'."""
    monkeypatch.chdir(tmp_path)
    init_studio_db()
    sync_testcase_meta(testcase=sample_testcase, file_path=tmp_path / "testcase.json", approval_status="approved")

    orchestrator = ExecutionOrchestrator()
    calls = 0

    class MockFlakyEngine:
        def __init__(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            self.call_num = calls

        async def run(self):
            if self.call_num == 1:
                return _make_replay_res(
                    status="failed",
                    exit_code=1,
                    steps=[
                        StepResult(
                            number=1,
                            status="failed",
                            duration_ms=400.0,
                            error="Element #btn-action not clickable",
                            selector_used="#btn-action",
                        )
                    ],
                )
            else:
                return _make_replay_res(
                    status="passed",
                    exit_code=0,
                    steps=[
                        StepResult(
                            number=1,
                            status="passed",
                            duration_ms=300.0,
                            selector_used="#btn-action",
                        )
                    ],
                )

    with patch("tracecase.ui.executor.ReplayEngine", MockFlakyEngine), \
         patch("tracecase.ui.executor.resolve_testcase_file", return_value=(tmp_path / "testcase.json", sample_testcase)), \
         patch("tracecase.ui.db.get_testcase_meta", return_value={"approval_status": "approved"}):

        run = await orchestrator.start_execution(
            testcase_id=sample_testcase.id,
            retries=2,
        )
        task = orchestrator.active_tasks.get(run["id"])
        if task:
            await task

        final_run = get_execution_run(run["id"])
        assert final_run["status"] == "flaky"
        assert final_run["attempt_count"] == 2
        assert final_run["failure_step"] == 1
        assert final_run["failure_selector"] == "#btn-action"
        assert len(final_run["attempts"]) == 2
        assert final_run["attempts"][0]["status"] == "failed"
        assert final_run["attempts"][1]["status"] == "passed"


@pytest.mark.asyncio
async def test_failed_test_classification_all_attempts_fail(tmp_path: Path, sample_testcase: TestCase, monkeypatch: pytest.MonkeyPatch):
    """All attempts fail -> final status must be 'failed' and attempt_count = 1 + retries."""
    monkeypatch.chdir(tmp_path)
    init_studio_db()
    sync_testcase_meta(testcase=sample_testcase, file_path=tmp_path / "testcase.json", approval_status="approved")

    orchestrator = ExecutionOrchestrator()
    calls = 0

    class MockFailingEngine:
        def __init__(self, *args, **kwargs):
            nonlocal calls
            calls += 1

        async def run(self):
            return _make_replay_res(
                status="failed",
                exit_code=1,
                steps=[
                    StepResult(
                        number=1,
                        status="failed",
                        duration_ms=250.0,
                        error="Assertion failed: expected 'Welcome' but got 'Error'",
                    )
                ],
            )

    with patch("tracecase.ui.executor.ReplayEngine", MockFailingEngine), \
         patch("tracecase.ui.executor.resolve_testcase_file", return_value=(tmp_path / "testcase.json", sample_testcase)), \
         patch("tracecase.ui.db.get_testcase_meta", return_value={"approval_status": "approved"}):

        run = await orchestrator.start_execution(
            testcase_id=sample_testcase.id,
            retries=2,
        )
        task = orchestrator.active_tasks.get(run["id"])
        if task:
            await task

        final_run = get_execution_run(run["id"])
        assert final_run["status"] == "failed"
        assert final_run["attempt_count"] == 3  # 1 initial + 2 retries
        assert calls == 3
        assert len(final_run["attempts"]) == 3
        for att in final_run["attempts"]:
            assert att["status"] == "failed"


# ===========================================================================
# 3. Non-Retriable Browser Environment Error Distinction
# ===========================================================================

@pytest.mark.asyncio
async def test_browser_environment_error_not_retried(tmp_path: Path, sample_testcase: TestCase, monkeypatch: pytest.MonkeyPatch):
    """Missing browser binary errors must be classified as 'error' and NOT retried."""
    monkeypatch.chdir(tmp_path)
    init_studio_db()
    sync_testcase_meta(testcase=sample_testcase, file_path=tmp_path / "testcase.json", approval_status="approved")

    orchestrator = ExecutionOrchestrator()
    calls = 0

    class MockMissingBinaryEngine:
        def __init__(self, *args, **kwargs):
            nonlocal calls
            calls += 1

        async def run(self):
            return _make_replay_res(
                status="error",
                exit_code=1,
                steps=[
                    StepResult(
                        number=0,
                        status="error",
                        error="Executable doesn't exist at /path/to/firefox. Please run 'playwright install firefox'",
                    )
                ],
            )

    with patch("tracecase.ui.executor.ReplayEngine", MockMissingBinaryEngine), \
         patch("tracecase.ui.executor.resolve_testcase_file", return_value=(tmp_path / "testcase.json", sample_testcase)), \
         patch("tracecase.ui.db.get_testcase_meta", return_value={"approval_status": "approved"}):

        run = await orchestrator.start_execution(
            testcase_id=sample_testcase.id,
            browser="firefox",
            retries=3,
        )
        task = orchestrator.active_tasks.get(run["id"])
        if task:
            await task

        final_run = get_execution_run(run["id"])
        assert final_run["status"] == "error"
        assert final_run["attempt_count"] == 1  # Crucial: did NOT retry missing browser binary
        assert calls == 1
        assert "Browser binary missing" in final_run["error_message"]
        assert len(final_run["attempts"]) == 1
        assert final_run["attempts"][0]["status"] == "error"


# ===========================================================================
# 4. Historical Flakiness Analysis & Browser Breakdown Tests
# ===========================================================================

def test_historical_flakiness_and_per_browser_stats(tmp_path: Path):
    db_file = tmp_path / "studio_history.db"
    init_studio_db(db_file)
    tc_id = "tc_auth_checkout"

    # Simulate 10 runs for this test case:
    # Chromium: 4 passed, 1 flaky (attempt_count=2)
    # Firefox: 2 passed, 1 flaky (attempt_count=2)
    # WebKit: 1 failed, 1 flaky
    history_data = [
        # Chromium (5 runs: 4 passed, 1 flaky)
        ("passed", "chromium", 1),
        ("passed", "chromium", 1),
        ("passed", "chromium", 1),
        ("flaky", "chromium", 2),
        ("passed", "chromium", 1),
        # Firefox (3 runs: 2 passed, 1 flaky)
        ("passed", "firefox", 1),
        ("flaky", "firefox", 2),
        ("passed", "firefox", 1),
        # WebKit (2 runs: 1 failed, 1 flaky)
        ("failed", "webkit", 3),
        ("flaky", "webkit", 2),
    ]

    for status, browser, att_count in history_data:
        run = create_execution_run(
            testcase_id=tc_id,
            testcase_name="Auth Checkout",
            browser=browser,
            db_path=db_file,
        )
        update_execution_run_status(
            execution_id=run["id"],
            status=status,
            attempt_count=att_count,
            db_path=db_file,
        )

    stats = get_testcase_flakiness_stats(tc_id, limit=20, db_path=db_file)
    assert stats["total_runs"] == 10
    assert stats["flaky_runs"] == 3
    assert stats["passed_runs"] == 6
    assert stats["failed_runs"] == 1
    assert stats["error_runs"] == 0

    # Separated metrics:
    # 1. Flakiness rate: 3/10 = 30.0%
    assert stats["flakiness_rate"] == 30.0
    assert stats["flakiness_score"] == 30.0
    # 2. First-attempt pass rate: 6/10 = 60.0%
    assert stats["first_attempt_pass_rate"] == 60.0
    # 3. Final pass rate: (6 + 3)/10 = 90.0%
    assert stats["final_pass_rate"] == 90.0
    # 4. Failure rate: 1/10 = 10.0%
    assert stats["failure_rate"] == 10.0
    # 5. Stability score: modal outcome (passed = 6) / 10 = 60.0%
    assert stats["stability_score"] == 60.0
    # Reliability score: first attempt pass rate = 60.0% (NOT 100 - flakiness_score = 70.0%)
    assert stats["reliability_score"] == 60.0
    # Rating: 30% flakiness is moderate (<= 40.0)
    assert stats["rating"] == "moderate"

    # Per-browser breakdown
    by_browser = stats["flakiness_by_browser"]
    assert "chromium" in by_browser
    assert by_browser["chromium"]["total"] == 5
    assert by_browser["chromium"]["flaky"] == 1
    assert by_browser["chromium"]["passed"] == 4
    assert by_browser["chromium"]["flakiness_rate"] == 20.0
    assert by_browser["chromium"]["first_attempt_pass_rate"] == 80.0
    assert by_browser["chromium"]["final_pass_rate"] == 100.0

    assert "firefox" in by_browser
    assert by_browser["firefox"]["total"] == 3
    assert by_browser["firefox"]["flaky"] == 1
    assert by_browser["firefox"]["passed"] == 2
    assert by_browser["firefox"]["flakiness_rate"] == 33.3
    assert by_browser["firefox"]["first_attempt_pass_rate"] == 66.7
    assert by_browser["firefox"]["final_pass_rate"] == 100.0

    assert "webkit" in by_browser
    assert by_browser["webkit"]["total"] == 2
    assert by_browser["webkit"]["flaky"] == 1
    assert by_browser["webkit"]["failed"] == 1
    assert by_browser["webkit"]["flakiness_rate"] == 50.0
    assert by_browser["webkit"]["first_attempt_pass_rate"] == 0.0
    assert by_browser["webkit"]["final_pass_rate"] == 50.0
    assert by_browser["webkit"]["failure_rate"] == 50.0


def test_consistently_failing_test_metrics_not_reliable(tmp_path: Path):
    """A test that fails every time has 0% flakiness, 100% stability, but 0% reliability and 'failing' rating."""
    db_file = tmp_path / "studio_failing.db"
    init_studio_db(db_file)
    tc_id = "tc_broken_checkout"

    # 30 runs, all failed
    for _ in range(30):
        run = create_execution_run(
            testcase_id=tc_id,
            testcase_name="Broken Checkout",
            browser="chromium",
            db_path=db_file,
        )
        update_execution_run_status(
            execution_id=run["id"],
            status="failed",
            attempt_count=3,
            db_path=db_file,
        )

    stats = get_testcase_flakiness_stats(tc_id, limit=30, db_path=db_file)
    assert stats["total_runs"] == 30
    assert stats["flaky_runs"] == 0
    assert stats["passed_runs"] == 0
    assert stats["failed_runs"] == 30
    assert stats["error_runs"] == 0

    # Explicit metrics verification:
    assert stats["flakiness_rate"] == 0.0
    assert stats["flakiness_score"] == 0.0
    assert stats["first_attempt_pass_rate"] == 0.0
    assert stats["final_pass_rate"] == 0.0
    assert stats["failure_rate"] == 100.0
    # Stability score is 100% because outcome is 100% consistently failing
    assert stats["stability_score"] == 100.0
    # CRITICAL: Reliability score must NOT be (100 - flakiness) = 100%. It is 0.0%.
    assert stats["reliability_score"] == 0.0
    # Rating must NOT be 'stable'
    assert stats["rating"] == "failing"


# ===========================================================================
# 5. Batch & Matrix Parallel Execution with Retries
# ===========================================================================

@pytest.mark.asyncio
async def test_batch_execution_with_intelligent_retry(tmp_path: Path, sample_testcase: TestCase, monkeypatch: pytest.MonkeyPatch):
    """Batch coordinator tracks flaky_tests count when workers recover on retry."""
    monkeypatch.chdir(tmp_path)
    init_studio_db()
    sync_testcase_meta(testcase=sample_testcase, file_path=tmp_path / "testcase.json", approval_status="approved")

    orchestrator = ExecutionOrchestrator()
    calls = 0

    class MockBatchFlakyEngine:
        def __init__(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            self.call_num = calls

        async def run(self):
            # First attempt fails, second attempt passes
            if self.call_num == 1:
                return _make_replay_res(
                    status="failed",
                    exit_code=1,
                    steps=[StepResult(number=1, status="failed", error="Transient network hiccup")],
                )
            return _make_replay_res(
                status="passed",
                exit_code=0,
                steps=[StepResult(number=1, status="passed")],
            )

    with patch("tracecase.ui.executor.ReplayEngine", MockBatchFlakyEngine), \
         patch("tracecase.ui.executor.resolve_testcase_file", return_value=(tmp_path / "testcase.json", sample_testcase)), \
         patch("tracecase.ui.db.get_testcase_meta", return_value={"approval_status": "approved"}):

        batch = await orchestrator.start_batch_execution(
            testcase_ids=[sample_testcase.id],
            concurrency=2,
            retries=2,
        )
        task = orchestrator.active_tasks.get(batch["id"])
        if task:
            await task

        final_batch = get_execution_batch(batch["id"])
        assert final_batch["status"] == "passed"
        assert final_batch["passed_tests"] == 1
        assert final_batch["flaky_tests"] == 1
        assert final_batch["failed_tests"] == 0

        runs = final_batch["runs"]
        assert len(runs) == 1
        assert runs[0]["status"] == "flaky"
        assert runs[0]["attempt_count"] == 2


@pytest.mark.asyncio
async def test_matrix_execution_with_intelligent_retry(tmp_path: Path, sample_testcase: TestCase, monkeypatch: pytest.MonkeyPatch):
    """Matrix execution recovers flaky runs and tracks flaky_executions."""
    monkeypatch.chdir(tmp_path)
    init_studio_db()
    sync_testcase_meta(testcase=sample_testcase, file_path=tmp_path / "testcase.json", approval_status="approved")

    orchestrator = ExecutionOrchestrator()
    calls = 0

    class MockMatrixEngine:
        def __init__(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            self.call_num = calls

        async def run(self):
            # Recover on attempt 2
            if self.call_num == 1:
                return _make_replay_res(
                    status="failed",
                    exit_code=1,
                    steps=[StepResult(number=1, status="failed", error="DOM race condition")],
                )
            return _make_replay_res(
                status="passed",
                exit_code=0,
                steps=[StepResult(number=1, status="passed")],
            )

    with patch("tracecase.ui.executor.ReplayEngine", MockMatrixEngine), \
         patch("tracecase.ui.executor.resolve_testcase_file", return_value=(tmp_path / "testcase.json", sample_testcase)), \
         patch("tracecase.ui.db.get_testcase_meta", return_value={"approval_status": "approved"}):

        matrix = await orchestrator.start_matrix_execution(
            testcase_ids=[sample_testcase.id],
            browsers=["chromium"],
            concurrency=2,
            retries=2,
        )
        task = orchestrator.active_tasks.get(matrix["id"])
        if task:
            await task

        final_matrix = get_execution_matrix(matrix["id"])
        assert final_matrix["status"] == "passed"
        assert final_matrix["passed_executions"] == 1
        assert final_matrix["flaky_executions"] == 1

        grid = final_matrix["grid"]
        assert len(grid) == 1
        assert grid[0]["browsers"]["chromium"]["status"] == "flaky"
        assert grid[0]["browsers"]["chromium"]["attempt_count"] == 2


@pytest.mark.asyncio
async def test_cross_browser_divergence_with_flaky_and_mixed_outcomes(
    tmp_path: Path, sample_testcase: TestCase, monkeypatch: pytest.MonkeyPatch
):
    """Verify cross-browser divergence properly exposes flaky outcomes alongside clean passes and failures.
    
    Matrix scenario:
    - Chromium: Passed (clean on attempt 1)
    - Firefox: Flaky (failed attempt 1, passed attempt 2)
    - WebKit: Failed (all attempts failed)

    Divergence must NOT hide Firefox's inconsistency as a generic pass.
    """
    monkeypatch.chdir(tmp_path)
    init_studio_db()
    sync_testcase_meta(testcase=sample_testcase, file_path=tmp_path / "testcase.json", approval_status="approved")

    orchestrator = ExecutionOrchestrator()
    calls_per_browser: dict[str, int] = {"chromium": 0, "firefox": 0, "webkit": 0}

    class MockCrossBrowserMatrixEngine:
        def __init__(self, browser_type: str = "chromium", *args, **kwargs):
            self.browser = browser_type
            calls_per_browser[self.browser] = calls_per_browser.get(self.browser, 0) + 1
            self.call_num = calls_per_browser[self.browser]

        async def run(self):
            if self.browser == "chromium":
                # Clean pass
                return _make_replay_res(status="passed", exit_code=0, steps=[StepResult(number=1, status="passed")])
            elif self.browser == "firefox":
                # Attempt 1 fails, Attempt 2 passes (flaky)
                if self.call_num == 1:
                    return _make_replay_res(
                        status="failed",
                        exit_code=1,
                        steps=[StepResult(number=1, status="failed", error="Firefox layout reflow race")],
                    )
                return _make_replay_res(status="passed", exit_code=0, steps=[StepResult(number=1, status="passed")])
            else:  # webkit
                # Fails all attempts
                return _make_replay_res(
                    status="failed",
                    exit_code=1,
                    steps=[StepResult(number=1, status="failed", error="WebKit SVG rendering crash")],
                )

    with patch("tracecase.ui.executor.ReplayEngine", MockCrossBrowserMatrixEngine), \
         patch("tracecase.ui.executor.resolve_testcase_file", return_value=(tmp_path / "testcase.json", sample_testcase)), \
         patch("tracecase.ui.db.get_testcase_meta", return_value={"approval_status": "approved"}):

        matrix = await orchestrator.start_matrix_execution(
            testcase_ids=[sample_testcase.id],
            browsers=["chromium", "firefox", "webkit"],
            concurrency=3,
            retries=2,
        )
        task = orchestrator.active_tasks.get(matrix["id"])
        if task:
            await task

        final_matrix = get_execution_matrix(matrix["id"])
        # Overall matrix status is failed because webkit failed
        assert final_matrix["status"] == "failed"
        assert final_matrix["total_executions"] == 3
        # 2 passed eventually (chromium clean + firefox recovered)
        assert final_matrix["passed_executions"] == 2
        assert final_matrix["flaky_executions"] == 1
        assert final_matrix["failed_executions"] == 1
        assert final_matrix["divergence_count"] == 1

        grid = final_matrix["grid"]
        assert len(grid) == 1
        row = grid[0]

        # 1. Distinct final outcomes preserved per browser
        assert row["browsers"]["chromium"]["status"] == "passed"
        assert row["browsers"]["chromium"]["attempt_count"] == 1

        assert row["browsers"]["firefox"]["status"] == "flaky"
        assert row["browsers"]["firefox"]["attempt_count"] == 2

        assert row["browsers"]["webkit"]["status"] == "failed"
        assert row["browsers"]["webkit"]["attempt_count"] == 3

        # 2. Cross-browser consistency flags divergence
        assert row["is_divergent"] is True
        assert "chromium: passed" in row["divergence_notes"]
        assert "firefox: flaky" in row["divergence_notes"]
        assert "webkit: failed" in row["divergence_notes"]

        # 3. Rates per browser accurately reflect clean vs flaky vs failed
        assert final_matrix["browser_first_attempt_pass_rates"]["chromium"] == 100.0
        assert final_matrix["browser_flakiness_rates"]["chromium"] == 0.0

        assert final_matrix["browser_first_attempt_pass_rates"]["firefox"] == 0.0
        assert final_matrix["browser_flakiness_rates"]["firefox"] == 100.0
        assert final_matrix["browser_final_pass_rates"]["firefox"] == 100.0

        assert final_matrix["browser_first_attempt_pass_rates"]["webkit"] == 0.0
        assert final_matrix["browser_final_pass_rates"]["webkit"] == 0.0


@pytest.mark.asyncio
async def test_concurrent_retries_do_not_exceed_concurrency(
    tmp_path: Path, sample_testcase: TestCase, monkeypatch: pytest.MonkeyPatch
):
    """Verify that retries executing inside existing worker pool do not exceed configured concurrency."""
    monkeypatch.chdir(tmp_path)
    init_studio_db()

    # Create 4 test cases
    tc_ids = []
    tc_files = {}
    for i in range(1, 5):
        t_id = f"tc_conc_{i}"
        tc_ids.append(t_id)
        tc_obj = _make_testcase(id=t_id, name=f"Case {i}", start_url="http://test/", steps=[
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="click",
                element=_make_element("#btn"),
                description_short="Click button",
                description_detailed="Click action button",
            )
        ])
        f_path = tmp_path / f"{t_id}.json"
        f_path.write_text(tc_obj.model_dump_json(), encoding="utf-8")
        sync_testcase_meta(testcase=tc_obj, file_path=f_path, approval_status="approved")
        tc_files[t_id] = (f_path, tc_obj)

    orchestrator = ExecutionOrchestrator()

    # Track concurrent execution
    active_concurrent = 0
    max_observed_concurrent = 0
    lock = asyncio.Lock()
    call_counts: dict[str, int] = {}

    class MockWorkerBoundRetryEngine:
        def __init__(self, testcase: TestCase, *args, **kwargs):
            self.tc_id = testcase.id

        async def run(self):
            nonlocal active_concurrent, max_observed_concurrent
            async with lock:
                active_concurrent += 1
                if active_concurrent > max_observed_concurrent:
                    max_observed_concurrent = active_concurrent
                call_counts[self.tc_id] = call_counts.get(self.tc_id, 0) + 1
                current_call = call_counts[self.tc_id]

            # Concurrency limit check: must never exceed 2 workers at any time
            assert active_concurrent <= 2

            # Simulate execution duration
            await asyncio.sleep(0.05)

            async with lock:
                active_concurrent -= 1

            # Fail attempt 1, pass attempt 2 (retry)
            if current_call == 1:
                return _make_replay_res(status="failed", exit_code=1, steps=[StepResult(number=1, status="failed", error="Retry me")])
            return _make_replay_res(status="passed", exit_code=0, steps=[StepResult(number=1, status="passed")])

    with patch("tracecase.ui.executor.ReplayEngine", MockWorkerBoundRetryEngine), \
         patch("tracecase.ui.executor.resolve_testcase_file", side_effect=lambda tid: tc_files[tid]), \
         patch("tracecase.ui.db.get_testcase_meta", return_value={"approval_status": "approved"}):

        batch = await orchestrator.start_batch_execution(
            testcase_ids=tc_ids,
            concurrency=2,
            retries=1,
        )
        task = orchestrator.active_tasks.get(batch["id"])
        if task:
            await task

        final_batch = get_execution_batch(batch["id"])
        assert final_batch["status"] == "passed"
        assert final_batch["total_tests"] == 4
        assert final_batch["flaky_tests"] == 4

        # Verify concurrency was strictly bounded at <= 2
        assert max_observed_concurrent <= 2
        assert max_observed_concurrent >= 1


# ===========================================================================
# 6. Cancellation During Retries
# ===========================================================================

@pytest.mark.asyncio
async def test_cancellation_during_retry_preserves_all_attempts(tmp_path: Path, sample_testcase: TestCase, monkeypatch: pytest.MonkeyPatch):
    """Cancelling a test during retry attempts terminates cleanly and permanently preserves all attempt records."""
    monkeypatch.chdir(tmp_path)
    init_studio_db()
    sync_testcase_meta(testcase=sample_testcase, file_path=tmp_path / "testcase.json", approval_status="approved")

    orchestrator = ExecutionOrchestrator()
    attempt = 0

    class MockSlowRetryEngine:
        def __init__(self, *args, **kwargs):
            nonlocal attempt
            attempt += 1

        async def run(self):
            if attempt == 1:
                return _make_replay_res(
                    status="failed",
                    exit_code=1,
                    steps=[StepResult(number=1, status="failed", error="Transient error")],
                )
            # Attempt 2 takes a while so cancellation hits mid-attempt
            await asyncio.sleep(2.0)
            return _make_replay_res(status="passed", exit_code=0, steps=[])

    with patch("tracecase.ui.executor.ReplayEngine", MockSlowRetryEngine), \
         patch("tracecase.ui.executor.resolve_testcase_file", return_value=(tmp_path / "testcase.json", sample_testcase)), \
         patch("tracecase.ui.db.get_testcase_meta", return_value={"approval_status": "approved"}):

        run = await orchestrator.start_execution(
            testcase_id=sample_testcase.id,
            retries=3,
        )

        # Allow attempt 1 to finish and attempt 2 to start
        await asyncio.sleep(0.3)
        cancelled = await orchestrator.cancel_execution(run["id"])
        assert cancelled is True

        await asyncio.sleep(0.1)
        final_run = get_execution_run(run["id"])
        assert final_run["status"] == "cancelled"

        # Permanent attempt preservation verification:
        attempts = get_execution_attempts(run["id"])
        assert len(attempts) == 2
        # Attempt 1 must be preserved as failed with initial error details
        assert attempts[0]["attempt_number"] == 1
        assert attempts[0]["status"] == "failed"
        assert attempts[0]["error_message"] == "Transient error"
        # Attempt 2 must be preserved as cancelled
        assert attempts[1]["attempt_number"] == 2
        assert attempts[1]["status"] == "cancelled"

        # Also verified in final_run["attempts"]
        assert len(final_run["attempts"]) == 2
        assert final_run["attempts"][0]["status"] == "failed"
        assert final_run["attempts"][1]["status"] == "cancelled"


# ===========================================================================
# 7. REST API Endpoints Tests
# ===========================================================================

def test_api_attempts_and_flakiness_endpoints(tmp_path: Path):
    db_file = tmp_path / "api_flaky.db"
    init_studio_db(db_file)
    app = create_app()

    with patch("tracecase.ui.api.get_execution_run") as mock_get_run, \
         patch("tracecase.ui.api.get_execution_attempts") as mock_get_attempts, \
         patch("tracecase.ui.api.get_testcase_flakiness_stats") as mock_get_stats:

        mock_get_run.return_value = {"id": "exec_123", "status": "flaky"}
        mock_get_attempts.return_value = [
            {"attempt_number": 1, "status": "failed", "error_message": "Timeout"},
            {"attempt_number": 2, "status": "passed", "error_message": None},
        ]
        mock_get_stats.return_value = {
            "testcase_id": "tc_login",
            "total_runs": 10,
            "flaky_runs": 2,
            "passed_runs": 7,
            "failed_runs": 1,
            "error_runs": 0,
            "flakiness_rate": 20.0,
            "flakiness_score": 20.0,
            "first_attempt_pass_rate": 70.0,
            "final_pass_rate": 90.0,
            "failure_rate": 10.0,
            "stability_score": 70.0,
            "reliability_score": 70.0,
            "rating": "low",
            "flakiness_by_browser": {
                "chromium": {
                    "total": 5,
                    "flaky": 1,
                    "passed": 4,
                    "failed": 0,
                    "error": 0,
                    "flakiness_rate": 20.0,
                    "flakiness_score": 20.0,
                    "first_attempt_pass_rate": 80.0,
                    "final_pass_rate": 100.0,
                    "failure_rate": 0.0,
                    "stability_score": 80.0,
                    "reliability_score": 80.0,
                }
            },
        }

        client = TestClient(app)

        # 1. GET /api/executions/{id}/attempts
        res1 = client.get("/api/executions/exec_123/attempts")
        assert res1.status_code == 200
        attempts = res1.json()
        assert len(attempts) == 2
        assert attempts[0]["status"] == "failed"
        assert attempts[1]["status"] == "passed"

        # 2. GET /api/testcases/{id}/flakiness
        res2 = client.get("/api/testcases/tc_login/flakiness?limit=25")
        assert res2.status_code == 200
        flakiness = res2.json()
        assert flakiness["flakiness_rate"] == 20.0
        assert flakiness["flakiness_score"] == 20.0
        assert flakiness["first_attempt_pass_rate"] == 70.0
        assert flakiness["final_pass_rate"] == 90.0
        assert flakiness["failure_rate"] == 10.0
        assert flakiness["stability_score"] == 70.0
        assert flakiness["reliability_score"] == 70.0
        assert flakiness["rating"] == "low"
        assert "chromium" in flakiness["flakiness_by_browser"]


# ===========================================================================
# 8. Real Browser Execution (Playwright)
# ===========================================================================

@pytest.mark.asyncio
async def test_real_browser_clean_pass_no_flakiness(
    tmp_path: Path, local_app_server: str, sample_testcase: TestCase, monkeypatch: pytest.MonkeyPatch
):
    """Verify real Playwright browser execution passes cleanly with attempt_count=1."""
    monkeypatch.chdir(tmp_path)
    init_studio_db()
    sync_testcase_meta(testcase=sample_testcase, file_path=tmp_path / "testcase.json", approval_status="approved")

    sample_testcase.start_url = local_app_server
    sample_testcase.steps[0].element.selector = "#btn-action"

    orchestrator = ExecutionOrchestrator()
    with patch("tracecase.ui.executor.resolve_testcase_file", return_value=(tmp_path / "testcase.json", sample_testcase)), \
         patch("tracecase.ui.db.get_testcase_meta", return_value={"approval_status": "approved"}):

        run = await orchestrator.start_execution(
            testcase_id=sample_testcase.id,
            browser="chromium",
            retries=2,
        )
        task = orchestrator.active_tasks.get(run["id"])
        if task:
            await task

        final_run = get_execution_run(run["id"])
        assert final_run["status"] == "passed"
        assert final_run["attempt_count"] == 1
        assert len(final_run["attempts"]) == 1
        assert final_run["attempts"][0]["status"] == "passed"


@pytest.mark.asyncio
async def test_real_browser_fail_then_pass_retry(
    tmp_path: Path, local_app_server: str, sample_testcase: TestCase, monkeypatch: pytest.MonkeyPatch
):
    """Verify real Playwright browser execution recovers from an intermittent DOM condition and is classified as flaky."""
    monkeypatch.chdir(tmp_path)
    init_studio_db()
    sync_testcase_meta(testcase=sample_testcase, file_path=tmp_path / "testcase.json", approval_status="approved")

    # Reset server request counter: Request 1 misses button, Request 2 has button
    FlakyAppHandler.fail_then_pass_requests = 0

    sample_testcase.start_url = f"{local_app_server}/fail-then-pass"
    sample_testcase.steps[0].element.selector = "#btn-action"

    orchestrator = ExecutionOrchestrator()
    with patch("tracecase.ui.executor.resolve_testcase_file", return_value=(tmp_path / "testcase.json", sample_testcase)), \
         patch("tracecase.ui.db.get_testcase_meta", return_value={"approval_status": "approved"}):

        run = await orchestrator.start_execution(
            testcase_id=sample_testcase.id,
            browser="chromium",
            retries=2,
        )
        task = orchestrator.active_tasks.get(run["id"])
        if task:
            await task

        final_run = get_execution_run(run["id"])
        assert final_run["status"] == "flaky"
        assert final_run["attempt_count"] == 2
        assert len(final_run["attempts"]) == 2

        # Attempt 1: Failed on Playwright click timeout because #btn-action was absent
        assert final_run["attempts"][0]["status"] == "failed"
        assert final_run["attempts"][0]["attempt_number"] == 1
        assert final_run["attempts"][0]["failed_step"] == 1
        assert final_run["attempts"][0]["failed_selector"] == "#btn-action"

        # Attempt 2: Recovered on retry and passed cleanly
        assert final_run["attempts"][1]["status"] == "passed"
        assert final_run["attempts"][1]["attempt_number"] == 2
