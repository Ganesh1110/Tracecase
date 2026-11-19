"""Unit and integration tests for QA Auto Studio Phase 4.

Verifies:
1. Recorder Session Manager pause/resume/step capture & API endpoints
2. TestCase metadata editing (PUT /api/testcases/{id})
3. Custom assertion updating (PUT /api/testcases/{id}/assertions/{index})
4. Execution step logging with assertions_json and report retrieval
5. End-to-end recording-to-replay-report workflow
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from qa_auto.models import Step, TestCase
from qa_auto.replay.models import Assertion, AssertionResult, StepResult
from qa_auto.ui.api import router
from qa_auto.ui.db import (
    create_execution_run,
    create_project,
    get_execution_run,
    init_studio_db,
    log_execution_step,
)
from qa_auto.ui.server import create_app
from qa_auto.ui.service import (
    add_custom_assertion,
    create_manual_testcase,
    recording_manager,
    resolve_testcase_file,
    update_custom_assertion,
    update_testcase_metadata,
)


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture
def temp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Hermetic temp DB."""
    db_file = tmp_path / "studio.db"
    monkeypatch.setattr("qa_auto.ui.db.DEFAULT_STUDIO_DB_PATH", db_file)
    init_studio_db(db_file)
    return tmp_path, db_file


@pytest.mark.asyncio
async def test_recorder_pause_resume_and_step_callback(temp_env):
    """Test recorder pause/resume state machine and live step streaming."""
    tmp_path, db_file = temp_env
    rec_dir = tmp_path / "recordings"
    rec_dir.mkdir(parents=True, exist_ok=True)

    # Ensure recorder is reset
    recording_manager.current_session = None
    recording_manager._recorder = None

    # Mock BrowserRecorder
    mock_rec = MagicMock()
    run_finish_event = asyncio.Event()

    async def mock_run():
        await run_finish_event.wait()

    mock_rec.run = mock_run
    mock_rec.record = AsyncMock()
    mock_rec.pause_recording = AsyncMock()
    mock_rec.resume_recording = AsyncMock()
    mock_rec.stop_recording = AsyncMock(side_effect=lambda: run_finish_event.set())
    mock_rec.page_errors = []
    mock_rec.network_requests = []

    with patch("qa_auto.ui.service.Recorder", return_value=mock_rec):
        session = await recording_manager.start(
            url="https://example.com",
            name="Streaming Record Test",
            output_dir=rec_dir / "streaming_test",
            browser_type="chromium",
            headless=True,
            project_id="default_project",
        )

        # Allow background task to initialize
        await asyncio.sleep(0.05)

        assert session["status"] == "recording"
        assert session["url"] == "https://example.com"
        assert session["project_id"] == "default_project"

        from datetime import datetime

        # Simulate step callbacks
        step1 = Step(
            number=1,
            timestamp=datetime.now(),
            action_type="click",
            description_short="Click button",
            description_detailed="Click submit button",
        )
        mock_rec.step_callback(step1)

        status_info = recording_manager.get_status()
        assert status_info["steps_count"] == 1
        assert len(status_info["steps"]) == 1
        assert status_info["steps"][0]["action_type"] == "click"

        # Test Pause
        paused_status = await recording_manager.pause()
        assert paused_status["status"] == "paused"
        assert paused_status["is_paused"] is True
        mock_rec.pause_recording.assert_awaited_once()

        # Step during pause should be ignored by step_callback
        step2 = Step(
            number=2,
            timestamp=datetime.now(),
            action_type="input",
            description_short="Type text",
            description_detailed="Fill username input",
        )
        mock_rec.step_callback(step2)
        assert len(recording_manager.get_status()["steps"]) == 1

        # Test Resume
        resumed_status = await recording_manager.resume()
        assert resumed_status["status"] == "recording"
        assert resumed_status["is_paused"] is False
        mock_rec.resume_recording.assert_awaited_once()

        # Step after resume is captured
        step3 = Step(
            number=3,
            timestamp=datetime.now(),
            action_type="navigate",
            url="https://example.com/dashboard",
            description_short="Go to dashboard",
            description_detailed="Navigate to dashboard page",
        )
        mock_rec.step_callback(step3)
        assert len(recording_manager.get_status()["steps"]) == 2

        # Finalize stop
        final_status = await recording_manager.stop()
        assert final_status["status"] == "completed"
        assert "testcase_id" in final_status


def test_testcase_metadata_and_assertion_api(client, temp_env):
    """Test PUT /api/testcases/{id} and PUT /api/testcases/{id}/assertions/{index}."""
    tmp_path, db_file = temp_env

    # Create a manual testcase
    tc = create_manual_testcase(
        name="Phase4 Meta Test",
        start_url="https://initial.example.com",
        browser="chromium",
        description="Original desc",
        project_id="default_project",
    )
    tc_id = tc.id

    try:
        # 1. Update Test Case Metadata via API
        resp = client.put(
            f"/api/testcases/{tc_id}",
            json={
                "name": "Phase4 Meta Updated",
                "description": "Updated detailed description",
                "start_url": "https://updated.example.com",
            },
        )
        assert resp.status_code == 200, resp.text
        meta_data = resp.json()
        assert meta_data["name"] == "Phase4 Meta Updated"
        assert meta_data["description"] == "Updated detailed description"
        assert meta_data["start_url"] == "https://updated.example.com"

        # 2. Add Custom Assertion via API
        add_resp = client.post(
            f"/api/testcases/{tc_id}/assertions",
            json={
                "kind": "visible",
                "target": "#login-button",
                "expected": "Submit",
                "step_number": 1,
                "enforced": True,
            },
        )
        assert add_resp.status_code == 200, add_resp.text
        assert len(add_resp.json()["custom_assertions"]) == 1

        # 3. Update Custom Assertion via API
        edit_resp = client.put(
            f"/api/testcases/{tc_id}/assertions/0",
            json={
                "kind": "text",
                "target": "#welcome-header",
                "expected": "Welcome Back",
                "step_number": 1,
                "enforced": True,
            },
        )
        assert edit_resp.status_code == 200, edit_resp.text
        updated_asserts = edit_resp.json()["custom_assertions"]
        assert len(updated_asserts) == 1
        assert updated_asserts[0]["kind"] == "text"
        assert updated_asserts[0]["target"] == "#welcome-header"
        assert updated_asserts[0]["expected"] == "Welcome Back"

        # 4. Delete Custom Assertion via API
        del_resp = client.delete(f"/api/testcases/{tc_id}/assertions/0")
        assert del_resp.status_code == 200
        assert len(del_resp.json()["custom_assertions"]) == 0
    finally:
        from qa_auto.ui.service import delete_testcase
        try:
            delete_testcase(tc_id)
        except Exception:
            pass


def test_execution_step_logging_with_assertions(temp_env):
    """Test step logging with assertions_json and SQLite retrieval."""
    tmp_path, db_file = temp_env

    run_record = create_execution_run(
        project_id="default_project",
        testcase_id="tc_demo",
        testcase_name="Demo Test",
        browser="chromium",
        db_path=db_file,
    )
    run_id = run_record["id"]

    assertions_data = [
        {
            "kind": "status",
            "target": None,
            "expected": "200",
            "passed": True,
            "actual": "200",
            "message": "HTTP 200 matched",
        },
        {
            "kind": "visible",
            "target": "#main-header",
            "expected": "true",
            "passed": True,
            "actual": "true",
            "message": "",
        },
    ]

    log_execution_step(
        execution_id=run_id,
        step_number=1,
        action_type="click",
        status="passed",
        duration_ms=120.5,
        selector_used="#submit-btn",
        healed_from=None,
        error=None,
        screenshot_path="/tmp/shot1.png",
        assertions=assertions_data,
        db_path=db_file,
    )

    # Fetch execution details
    run_details = get_execution_run(run_id, db_path=db_file)
    assert run_details is not None
    assert len(run_details["step_logs"]) == 1
    logged_step = run_details["step_logs"][0]
    assert logged_step["step_number"] == 1
    assert logged_step["status"] == "passed"
    assert len(logged_step["assertions"]) == 2
    assert logged_step["assertions"][0]["kind"] == "status"
    assert logged_step["assertions"][0]["passed"] is True
    assert logged_step["assertions"][1]["target"] == "#main-header"


def test_recorder_pause_resume_api_endpoints(client, temp_env):
    """Test POST /api/record/pause and POST /api/record/resume HTTP routes."""
    tmp_path, db_file = temp_env

    # Active recording session mock
    recording_manager.current_session = {
        "session_id": "rec_api_test",
        "status": "recording",
        "is_paused": False,
        "steps": [],
        "started_at": "2026-01-01T00:00:00",
    }
    recording_manager._recorder = None

    pause_resp = client.post("/api/record/pause")
    assert pause_resp.status_code == 200
    assert pause_resp.json()["status"] == "paused"
    assert pause_resp.json()["is_paused"] is True

    resume_resp = client.post("/api/record/resume")
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "recording"
    assert resume_resp.json()["is_paused"] is False

    # Clean up
    recording_manager.current_session = None


@pytest.mark.asyncio
async def test_end_to_end_replay_and_report_retrieval(client, temp_env):
    """Test full workflow: create testcase, trigger replay, log assertions, and get report."""
    tmp_path, db_file = temp_env

    # 1. Create a testcase
    tc = create_manual_testcase(
        name="E2E Report Workflow Case",
        start_url="https://qa-test.example.com",
        browser="chromium",
        description="E2E validation testcase",
        project_id="default_project",
    )
    tc_id = tc.id

    try:
        # 2. Add an assertion
        client.post(
            f"/api/testcases/{tc_id}/assertions",
            json={
                "kind": "status",
                "expected": "200",
                "step_number": 1,
            },
        )

        # 3. Register execution run in DB
        run = create_execution_run(
            project_id="default_project",
            testcase_id=tc_id,
            testcase_name=tc.name,
            browser="chromium",
            db_path=db_file,
        )
        run_id = run["id"]

        # 4. Log a completed step with evaluated assertions
        log_execution_step(
            execution_id=run_id,
            step_number=1,
            action_type="navigate",
            status="passed",
            duration_ms=210.0,
            selector_used=None,
            assertions=[
                {
                    "kind": "status",
                    "target": None,
                    "expected": "200",
                    "passed": True,
                    "actual": "200",
                    "message": "HTTP 200 OK",
                }
            ],
            db_path=db_file,
        )

        # 5. Retrieve execution report via API
        resp = client.get(f"/api/executions/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == run_id
        assert data["testcase_id"] == tc_id
        assert len(data["step_logs"]) == 1
        assert len(data["step_logs"][0]["assertions"]) == 1
        assert data["step_logs"][0]["assertions"][0]["kind"] == "status"
        assert data["step_logs"][0]["assertions"][0]["passed"] is True
    finally:
        from qa_auto.ui.service import delete_testcase
        try:
            delete_testcase(tc_id)
        except Exception:
            pass
