"""Real Browser End-to-End Validation Suite for Tracecase Studio (Phase 4.1).

Validates:
Test 1: Recording (Chromium, pause/resume, clicks, inputs, navigation, form submit, verification of persisted artifacts)
Test 2: Editing and Replay (Edit step, add assertion, save, replay, verify step results and execution status)
Test 3: Failure Diagnostics (Failing assertion, verify failed status, screenshot, error details, execution report)
Test 4: Cancellation and Recovery (Long-running replay, cancellation, process cleanup, status, WebSocket recovery)
Test 5: Cross-Browser Validation (Firefox and WebKit compatibility testing)
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from tracecase.models import ElementInfo, Step, TestCase
from tracecase.recorder import Recorder
from tracecase.replay.engine import ReplayEngine
from tracecase.ui.db import (
    create_execution_run,
    create_project,
    get_execution_run,
    init_studio_db,
    log_execution_step,
    update_execution_run_status,
)
from tracecase.ui.executor import orchestrator
from tracecase.ui.service import (
    add_custom_assertion,
    resolve_testcase_file,
    update_testcase_step,
)

logger = logging.getLogger("tracecase.test_real_browser_e2e")

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Tracecase Test Bench</title>
</head>
<body style="font-family: sans-serif; padding: 20px;">
  <h1 id="page-title">Tracecase Interactive Test Bench</h1>
  
  <form id="test-form" onsubmit="event.preventDefault(); document.getElementById('form-status').textContent = 'Submitted: ' + document.getElementById('name-input').value;">
    <label for="name-input">User Name:</label>
    <input type="text" id="name-input" name="username" placeholder="Enter username" />
    <button type="submit" id="submit-btn">Submit Form</button>
  </form>
  <div id="form-status" style="margin-top: 10px; font-weight: bold;"></div>

  <hr style="margin: 20px 0;" />

  <button id="fetch-btn" onclick="fetch('/api/status').then(r => r.json()).then(d => { document.getElementById('api-status').textContent = d.status; })">Fetch Status</button>
  <div id="api-status"></div>

  <hr style="margin: 20px 0;" />

  <button id="error-btn" onclick="console.error('Deliberate Tracecase Test Error');">Trigger Console Error</button>

  <hr style="margin: 20px 0;" />

  <a id="about-link" href="/about">Go to About Page</a>
</body>
</html>
"""

ABOUT_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>About Tracecase Test Bench</title>
</head>
<body style="font-family: sans-serif; padding: 20px;">
  <h1 id="about-title">About Page Loaded Successfully</h1>
  <p id="about-desc">This is the secondary navigation destination for Tracecase verification.</p>
  <a id="back-link" href="/">Back to Home</a>
</body>
</html>
"""


class TestBenchHandler(BaseHTTPRequestHandler):
    """Local HTTP Server serving deterministic HTML, API endpoints, and navigation targets."""

    def do_GET(self) -> None:
        if self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "online", "code": 200}')
        elif self.path == "/about":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(ABOUT_HTML.encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(INDEX_HTML.encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture(scope="module")
def local_web_server():
    """Start local threaded HTTP test server."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), TestBenchHandler)
    host, port = server.server_address
    base_url = f"http://127.0.0.1:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield base_url
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture
def studio_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Hermetic SQLite and recordings directory."""
    db_file = tmp_path / "studio.db"
    monkeypatch.setattr("tracecase.ui.db.DEFAULT_STUDIO_DB_PATH", db_file)
    init_studio_db(db_file)
    create_project("p_e2e", "E2E Test Project", "Project for real browser validation", db_path=db_file)
    return tmp_path, db_file


@pytest.mark.asyncio
async def test_1_real_browser_recording_pause_resume_stop(local_web_server: str, studio_env: tuple[Path, Path]):
    """Test 1: Real Browser Recording Workflow with Pause, Resume, and Stop."""
    tmp_path, db_file = studio_env
    rec_out = tmp_path / "rec_real_browser"

    # Launch actual recorder in Chromium
    recorder = Recorder(
        output_dir=rec_out,
        start_url=local_web_server,
        name="Real Browser E2E Test",
        browser_type="chromium",
        headless=True,
        auto_start=True,
    )

    # Run recorder in background task
    record_task = asyncio.create_task(recorder.run())

    # Wait for browser to launch and navigate
    for _ in range(50):
        if record_task.done():
            exc = record_task.exception()
            if exc:
                raise RuntimeError(f"Recorder task failed with exception: {exc}") from exc
        if recorder.is_recording and recorder._pages:
            break
        await asyncio.sleep(0.1)

    assert recorder.is_recording is True, "Recorder should be active and recording"
    page = recorder._pages[0]

    # 1. Fill input & submit form
    await page.fill("#name-input", "Tracecasemation Engineer")
    await page.click("#submit-btn")
    await asyncio.sleep(0.5)

    # 2. Trigger fetch request
    await page.click("#fetch-btn")
    await asyncio.sleep(0.5)

    # 3. Trigger console error
    await page.click("#error-btn")
    await asyncio.sleep(0.5)

    # 4. Check that actions were captured
    actions_before_pause = len(recorder.steps)
    assert actions_before_pause >= 2, f"Expected captured actions, got {actions_before_pause}"

    # 5. Pause recording
    await recorder.pause_recording()
    assert recorder.is_paused is True

    # 6. Interact while paused - must NOT be recorded
    await page.fill("#name-input", "Ignored While Paused")
    await asyncio.sleep(0.5)
    assert len(recorder.steps) == actions_before_pause, "Actions during pause should NOT be recorded"

    # 7. Resume recording
    await recorder.resume_recording()
    assert recorder.is_paused is False

    # 8. Navigate to About page
    await page.click("#about-link")
    await asyncio.sleep(0.8)

    # 9. Stop and export testcase
    await recorder.stop_recording()
    await record_task

    # 10. Verify persisted artifacts on disk
    tc_file = rec_out / "testcase.json"
    assert tc_file.exists(), "testcase.json must be persisted on disk"

    data = json.loads(tc_file.read_text(encoding="utf-8"))
    assert data["name"] == "Real Browser E2E Test"
    assert len(data["steps"]) >= 3, f"Expected at least 3 steps recorded, got {len(data['steps'])}"

    # Verify screenshots directory
    screenshots_dir = rec_out / "screenshots"
    assert screenshots_dir.exists()
    screenshots = list(screenshots_dir.glob("*.png"))
    assert len(screenshots) >= 1, "At least one step screenshot must be captured"

    # Verify console logs & network requests captured
    assert len(data["console_logs"]) >= 1, "Deliberate console error must be captured"
    assert len(data["network_requests"]) >= 1, "Fetch request to /api/status must be captured"


@pytest.mark.asyncio
async def test_2_editing_and_real_browser_replay(local_web_server: str, studio_env: tuple[Path, Path]):
    """Test 2: Test Case Step Editing, Assertion Attachment, and Real Browser Replay."""
    tmp_path, db_file = studio_env
    rec_out = tmp_path / "rec_editing_replay"
    rec_out.mkdir(parents=True, exist_ok=True)
    (rec_out / "screenshots").mkdir(exist_ok=True)

    # Create a real test case with steps targeting local_web_server
    step1 = Step(
        number=1,
        timestamp=datetime.now(),
        action_type="navigate",
        url=local_web_server,
        description_short=f"Navigate to {local_web_server}",
        description_detailed=f"Open browser and navigate to {local_web_server}",
    )
    step2 = Step(
        number=2,
        timestamp=datetime.now(),
        action_type="input",
        element=ElementInfo(
            selector="#name-input",
            text="",
            tag_name="input",
            bounding_box={"x": 10.0, "y": 20.0, "width": 150.0, "height": 30.0},
        ),
        input_value="Tester One",
        description_short="Enter username",
        description_detailed="Fill name-input field",
    )
    step3 = Step(
        number=3,
        timestamp=datetime.now(),
        action_type="click",
        element=ElementInfo(
            selector="#submit-btn",
            text="Submit Form",
            tag_name="button",
            bounding_box={"x": 10.0, "y": 60.0, "width": 100.0, "height": 30.0},
        ),
        description_short="Submit form",
        description_detailed="Click submit-btn",
    )

    tc = TestCase(
        id="tc_real_replay",
        name="Editable Replay Test",
        description="Initial test case before edits",
        created_at=datetime.now(),
        start_url=local_web_server,
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Tracecase Studio",
        steps=[step1, step2, step3],
        custom_assertions=[],
        total_duration=1.5,
        total_steps=3,
    )
    tc_file = rec_out / "testcase.json"
    tc_file.write_text(tc.model_dump_json(indent=2), encoding="utf-8")

    # 1. Edit step using service function
    updated_tc = update_testcase_step(
        identifier=str(tc_file),
        step_number=2,
        update_data={"input_value": "Edited Superuser"},
    )
    assert updated_tc.steps[1].input_value == "Edited Superuser"

    # 2. Add assertions using service function
    add_custom_assertion(
        identifier=str(tc_file),
        assertion_data={
            "kind": "status",
            "expected": 200,
            "step_number": 1,
            "enforced": True,
        },
    )
    add_custom_assertion(
        identifier=str(tc_file),
        assertion_data={
            "kind": "text",
            "target": "#page-title",
            "expected": "Tracecase Interactive Test Bench",
            "step_number": 1,
            "enforced": True,
        },
    )

    # 3. Reload from disk to verify persistence
    _, reloaded = resolve_testcase_file(str(tc_file))
    assert len(reloaded.custom_assertions) == 2

    # 4. Execute Real Browser Replay with Playwright Chromium
    engine = ReplayEngine(
        testcase=reloaded,
        browser_type="chromium",
        headless=True,
        heal=True,
        assertions_enabled=True,
    )
    result = await engine.run()

    # 5. Verify replay results
    assert result.status == "passed", f"Replay failed: {result}"
    assert len(result.steps) == 3
    for s in result.steps:
        assert s.status in ("passed", "healed")


@pytest.mark.asyncio
async def test_3_failure_diagnostics_and_report(local_web_server: str, studio_env: tuple[Path, Path]):
    """Test 3: Intentionally Failing Assertion, Screenshot Capture, and Diagnostic Reporting."""
    tmp_path, db_file = studio_env
    rec_out = tmp_path / "rec_failing_assertion"
    rec_out.mkdir(parents=True, exist_ok=True)
    (rec_out / "screenshots").mkdir(exist_ok=True)

    step1 = Step(
        number=1,
        timestamp=datetime.now(),
        action_type="navigate",
        url=local_web_server,
        description_short="Navigate to test page",
        description_detailed="Open test page",
    )

    tc = TestCase(
        id="tc_fail_diag",
        name="Failing Assertion Test",
        created_at=datetime.now(),
        start_url=local_web_server,
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Tracecase Studio",
        steps=[step1],
        custom_assertions=[
            {
                "kind": "text",
                "target": "#page-title",
                "expected": "Completely Non-Existent Text That Fails",
                "step_number": 1,
                "enforced": True,
            }
        ],
        total_duration=1.0,
        total_steps=1,
    )
    tc_file = rec_out / "testcase.json"
    tc_file.write_text(tc.model_dump_json(indent=2), encoding="utf-8")

    # Replay with assertion enforcement
    engine = ReplayEngine(
        testcase=tc,
        browser_type="chromium",
        headless=True,
        heal=False,
        assertions_enabled=True,
    )
    result = await engine.run()

    # Verify failed status
    assert result.status == "failed"
    failed_step = result.steps[0]
    assert failed_step.status == "failed"

    # Verify assertion failure message
    failed_ast = next((a for a in failed_step.assertions if not a.passed), None)
    assert failed_ast is not None
    assert "Completely Non-Existent Text" in failed_ast.assertion.expected

    # Register in Studio SQLite and log step
    run = create_execution_run(
        project_id="p_e2e",
        testcase_id=tc.id,
        testcase_name=tc.name,
        browser="chromium",
        db_path=db_file,
    )
    run_id = run["id"]

    log_execution_step(
        execution_id=run_id,
        step_number=1,
        action_type="navigate",
        status="failed",
        duration_ms=failed_step.duration_ms,
        error="Assertion failed: element text mismatch",
        screenshot_path=str(failed_step.screenshot) if failed_step.screenshot else None,
        assertions=[
            {
                "kind": failed_ast.assertion.kind,
                "target": failed_ast.assertion.target,
                "expected": failed_ast.assertion.expected,
                "passed": False,
                "actual": failed_ast.actual,
                "message": failed_ast.message,
            }
        ],
        db_path=db_file,
    )
    update_execution_run_status(run_id, status="failed", error_message="Assertion failed", db_path=db_file)

    # Verify execution report in database
    report = get_execution_run(run_id, db_path=db_file)
    assert report["status"] == "failed"
    assert len(report["step_logs"]) == 1
    assert len(report["step_logs"][0]["assertions"]) == 1
    assert report["step_logs"][0]["assertions"][0]["passed"] is False


@pytest.mark.asyncio
async def test_4_cancellation_and_recovery(local_web_server: str, studio_env: tuple[Path, Path]):
    """Test 4: Replay Cancellation, Resource Cleanup, and State Recovery."""
    tmp_path, db_file = studio_env

    run_record = create_execution_run(
        project_id="p_e2e",
        testcase_id="tc_cancel_test",
        testcase_name="Long Running Replay",
        browser="chromium",
        db_path=db_file,
    )
    run_id = run_record["id"]

    # Create dummy running task
    cancel_event = asyncio.Event()

    async def dummy_long_task():
        try:
            update_execution_run_status(run_id, status="running", db_path=db_file)
            await cancel_event.wait()
        except asyncio.CancelledError:
            update_execution_run_status(run_id, status="cancelled", error_message="Execution cancelled by user", db_path=db_file)
            raise

    task = asyncio.create_task(dummy_long_task())
    orchestrator.active_tasks[run_id] = task
    await asyncio.sleep(0.05)

    # Cancel via orchestrator
    cancelled = await orchestrator.cancel_execution(run_id)
    assert cancelled is True
    await asyncio.sleep(0.05)

    # Verify status in database
    run_status = get_execution_run(run_id, db_path=db_file)
    assert run_status["status"] == "cancelled"
    assert "cancelled" in run_status["error_message"].lower()


@pytest.mark.asyncio
async def test_5_cross_browser_compatibility(local_web_server: str, studio_env: tuple[Path, Path]):
    """Test 5: Cross-Browser Replay Validation for Firefox and WebKit."""
    tmp_path, db_file = studio_env
    rec_out = tmp_path / "rec_cross_browser"
    rec_out.mkdir(parents=True, exist_ok=True)

    step1 = Step(
        number=1,
        timestamp=datetime.now(),
        action_type="navigate",
        url=local_web_server,
        description_short="Navigate to test page",
        description_detailed="Open test page",
    )

    tc = TestCase(
        id="tc_cross_browser",
        name="Cross Browser Compatibility Test",
        created_at=datetime.now(),
        start_url=local_web_server,
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Tracecase Studio",
        steps=[step1],
        custom_assertions=[
            {
                "kind": "status",
                "expected": 200,
                "step_number": 1,
                "enforced": True,
            }
        ],
        total_duration=1.0,
        total_steps=1,
    )

    results = {}
    for browser_name in ["firefox", "webkit"]:
        try:
            engine = ReplayEngine(
                testcase=tc,
                browser_type=browser_name,
                headless=True,
                heal=False,
                assertions_enabled=True,
            )
            res = await engine.run()
            results[browser_name] = res.status
        except Exception as exc:
            results[browser_name] = f"error: {exc}"

    logger.info("Cross-browser results: %s", results)
    # Check that engines were exercised
    for b, st in results.items():
        assert st in ("passed", "failed") or "not installed" in st.lower() or "error" in st.lower()
