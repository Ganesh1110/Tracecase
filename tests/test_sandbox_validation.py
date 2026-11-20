"""Tests for Phase 9.1.3: Isolated Playwright Sandbox Validation."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tracecase.browser_pool import BrowserPool
from tracecase.exploration.models import (
    SynthesizedAssertion,
    SynthesizedStep,
    TestJourneyDraft,
)
from tracecase.requirements.validation import (
    DraftValidationReport,
    SandboxExecutor,
    SandboxSafetyPolicy,
    ValidationOrchestrator,
    get_validation_orchestrator,
)
from tracecase.ui.db import (
    create_exploration_run,
    get_draft_validation,
    get_latest_draft_validation,
    get_synthesized_draft,
    init_studio_db,
    list_draft_validations,
    save_draft_validation,
    save_synthesized_draft,
    update_synthesized_draft,
)
from tracecase.ui.server import create_app

HTML_TEST_BENCH = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Sandbox Test Application</title>
</head>
<body style="font-family: sans-serif; padding: 20px;">
  <h1>Tracecase Sandbox Portal</h1>
  
  <form id="user-form" onsubmit="event.preventDefault(); document.getElementById('confirmation').innerText = 'Profile Updated: ' + document.getElementById('input-username').value;">
    <div>
      <label for="input-username">Username</label>
      <input id="input-username" name="username" type="text" placeholder="Enter username" />
    </div>
    
    <div>
      <button id="btn-submit" type="submit">Submit Form</button>
      <button id="btn-disabled" type="button" disabled>Disabled Action</button>
      <button id="btn-delete" type="button">Delete User Data</button>
      <button id="btn-error" type="button" onclick="throw new Error('Uncaught runtime exception');">Trigger Error</button>
    </div>
  </form>

  <div id="elem-hidden" style="display: none;">This content is hidden</div>

  <div class="duplicate-group">
    <button class="dup-btn" id="btn-dup-1">Save Choice A</button>
    <button class="dup-btn" id="btn-dup-2">Save Choice B</button>
  </div>

  <div id="confirmation" style="margin-top: 20px; font-weight: bold;">Initial State</div>
</body>
</html>
"""


@pytest.fixture
def local_test_page() -> str:
    """Create a temporary static HTML bench file and return its file:// URL."""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(HTML_TEST_BENCH)
        temp_path = f.name
    return f"file://{temp_path}"


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    """Initialize a dedicated SQLite DB path for isolation."""
    db_file = tmp_path / "test_studio.db"
    init_studio_db(db_file)
    return db_file


@pytest.mark.asyncio
async def test_valid_evidence_backed_journey_passes(local_test_page: str, tmp_path: Path):
    """Test 1: Valid evidence-backed journey executes in sandbox and produces VERIFIED status."""
    draft = TestJourneyDraft(
        id="draft_valid_01",
        exploration_id="exp_test",
        name="Update Username Journey",
        start_url=local_test_page,
        steps=[
            SynthesizedStep(
                number=1,
                action_type="navigate",
                url=local_test_page,
                description_short="Open Sandbox App",
                description_detailed="Navigate to local test application",
                assertions=[
                    SynthesizedAssertion(
                        assertion_type="title_matches",
                        expected_value="Sandbox Test Application",
                    ),
                    SynthesizedAssertion(
                        assertion_type="no_page_error",
                    ),
                ],
            ),
            SynthesizedStep(
                number=2,
                action_type="input",
                selector="#input-username",
                input_value="Grace Hopper",
                description_short="Fill Username",
                description_detailed="Input name into #input-username",
                target_status="resolved",
                selector_confidence=0.95,
            ),
            SynthesizedStep(
                number=3,
                action_type="click",
                selector="#btn-submit",
                description_short="Click Submit",
                description_detailed="Submit form",
                target_status="resolved",
                selector_confidence=0.95,
                assertions=[
                    SynthesizedAssertion(
                        assertion_type="element_visible",
                        target_selector="#confirmation",
                    ),
                    SynthesizedAssertion(
                        assertion_type="text_matches",
                        target_selector="#confirmation",
                        expected_value="Profile Updated: Grace Hopper",
                    ),
                ],
            ),
        ],
    )

    executor = SandboxExecutor(base_artifacts_dir=tmp_path / "artifacts")
    report = await executor.execute_validation(draft, headless=True)

    assert report.overall_status == "VERIFIED"
    assert report.passed_steps_count == 3
    assert report.failed_steps_count == 0
    assert report.blocked_steps_count == 0
    assert report.artifacts["trace_path"] is not None
    assert report.artifacts["total_screenshots"] >= 2


@pytest.mark.asyncio
async def test_missing_evidence_blocks_step(local_test_page: str, tmp_path: Path):
    """Test 2: Missing evidence produces unresolved status and BLOCKS execution."""
    draft = TestJourneyDraft(
        id="draft_unresolved",
        exploration_id="exp_test",
        name="Unresolved Step Draft",
        start_url=local_test_page,
        steps=[
            SynthesizedStep(
                number=1,
                action_type="click",
                selector=None,
                description_short="Click Phantom Control",
                description_detailed="Target missing from catalog",
                target_status="unresolved",
                selector_confidence=0.0,
            )
        ],
    )

    executor = SandboxExecutor(base_artifacts_dir=tmp_path / "artifacts")
    report = await executor.execute_validation(draft, headless=True)

    assert report.overall_status == "BLOCKED"
    assert report.step_results[0].status == "BLOCKED"
    assert "missing exploration evidence" in (report.step_results[0].error_message or "").lower()


@pytest.mark.asyncio
async def test_ambiguous_selectors_not_executed(local_test_page: str, tmp_path: Path):
    """Test 3: Ambiguous selectors are prevented from execution and marked BLOCKED."""
    draft = TestJourneyDraft(
        id="draft_ambiguous",
        exploration_id="exp_test",
        name="Ambiguous Target Draft",
        start_url=local_test_page,
        steps=[
            SynthesizedStep(
                number=1,
                action_type="click",
                selector="#ambiguous-btn",
                description_short="Click Ambiguous Button",
                description_detailed="Target matched multiple elements",
                target_status="ambiguous",
                selector_confidence=0.5,
            )
        ],
    )

    executor = SandboxExecutor(base_artifacts_dir=tmp_path / "artifacts")
    report = await executor.execute_validation(draft, headless=True)

    assert report.overall_status == "BLOCKED"
    assert report.step_results[0].status == "BLOCKED"
    assert "ambiguous" in (report.step_results[0].error_message or "").lower()


@pytest.mark.asyncio
async def test_non_unique_selectors_rejected(local_test_page: str, tmp_path: Path):
    """Test 4: Selectors matching multiple elements in live DOM fail uniqueness check."""
    draft = TestJourneyDraft(
        id="draft_non_unique",
        exploration_id="exp_test",
        name="Non-Unique Selector Draft",
        start_url=local_test_page,
        steps=[
            SynthesizedStep(
                number=1,
                action_type="navigate",
                url=local_test_page,
                description_short="Open Page",
                description_detailed="Navigate to bench",
            ),
            SynthesizedStep(
                number=2,
                action_type="click",
                selector=".dup-btn",
                description_short="Click Duplicate Button",
                description_detailed="Selector matches two buttons",
                target_status="resolved",
            ),
        ],
    )

    executor = SandboxExecutor(base_artifacts_dir=tmp_path / "artifacts")
    report = await executor.execute_validation(draft, headless=True)

    assert report.overall_status == "FAILED"
    step2 = report.step_results[1]
    assert step2.status == "FAILED"
    assert "matched 2 elements" in (step2.error_message or "")


@pytest.mark.asyncio
async def test_hidden_and_disabled_elements_handled(local_test_page: str, tmp_path: Path):
    """Test 5: Hidden or disabled elements fail pre-execution checks."""
    executor = SandboxExecutor(base_artifacts_dir=tmp_path / "artifacts")

    # 1. Hidden element check
    draft_hidden = TestJourneyDraft(
        id="draft_hidden",
        exploration_id="exp_test",
        name="Hidden Element Draft",
        start_url=local_test_page,
        steps=[
            SynthesizedStep(number=1, action_type="navigate", url=local_test_page, description_short="Nav", description_detailed="Nav"),
            SynthesizedStep(
                number=2,
                action_type="click",
                selector="#elem-hidden",
                description_short="Click Hidden",
                description_detailed="Click display:none div",
                target_status="resolved",
            ),
        ],
    )
    report_hidden = await executor.execute_validation(draft_hidden, headless=True)
    assert report_hidden.overall_status == "FAILED"
    assert "hidden or not visible" in (report_hidden.step_results[1].error_message or "")

    # 2. Disabled button check
    draft_disabled = TestJourneyDraft(
        id="draft_disabled",
        exploration_id="exp_test",
        name="Disabled Button Draft",
        start_url=local_test_page,
        steps=[
            SynthesizedStep(number=1, action_type="navigate", url=local_test_page, description_short="Nav", description_detailed="Nav"),
            SynthesizedStep(
                number=2,
                action_type="click",
                selector="#btn-disabled",
                description_short="Click Disabled",
                description_detailed="Click button with disabled attribute",
                target_status="resolved",
            ),
        ],
    )
    report_disabled = await executor.execute_validation(draft_disabled, headless=True)
    assert report_disabled.overall_status == "FAILED"
    assert "disabled" in (report_disabled.step_results[1].error_message or "")


@pytest.mark.asyncio
async def test_stale_selector_detected(local_test_page: str, tmp_path: Path):
    """Test 6: Missing/stale locator in live DOM reports count 0 and fails pre-check."""
    draft = TestJourneyDraft(
        id="draft_stale",
        exploration_id="exp_test",
        name="Stale Selector Draft",
        start_url=local_test_page,
        steps=[
            SynthesizedStep(number=1, action_type="navigate", url=local_test_page, description_short="Nav", description_detailed="Nav"),
            SynthesizedStep(
                number=2,
                action_type="click",
                selector="#stale-element-xyz",
                description_short="Click Stale",
                description_detailed="Element removed from DOM",
                target_status="resolved",
            ),
        ],
    )

    executor = SandboxExecutor(base_artifacts_dir=tmp_path / "artifacts")
    report = await executor.execute_validation(draft, headless=True)

    assert report.overall_status == "FAILED"
    assert "stale selector" in (report.step_results[1].error_message or "").lower()


@pytest.mark.asyncio
async def test_successful_assertions_persisted(local_test_page: str, tmp_path: Path):
    """Test 7: Passing deterministic assertions are stored in validation reports."""
    draft = TestJourneyDraft(
        id="draft_assertions_pass",
        exploration_id="exp_test",
        name="Passing Assertions",
        start_url=local_test_page,
        steps=[
            SynthesizedStep(
                number=1,
                action_type="navigate",
                url=local_test_page,
                description_short="Nav",
                description_detailed="Nav",
                assertions=[
                    SynthesizedAssertion(assertion_type="title_matches", expected_value="Sandbox Test Application"),
                    SynthesizedAssertion(assertion_type="element_visible", target_selector="#btn-submit"),
                    SynthesizedAssertion(assertion_type="no_page_error"),
                ],
            )
        ],
    )

    executor = SandboxExecutor(base_artifacts_dir=tmp_path / "artifacts")
    report = await executor.execute_validation(draft, headless=True)

    assert report.overall_status == "VERIFIED"
    assert len(report.assertion_results) == 3
    assert all(a.passed for a in report.assertion_results)


@pytest.mark.asyncio
async def test_failed_assertions_preserve_diagnostic_evidence(local_test_page: str, tmp_path: Path):
    """Test 8: Failed assertions record failure reason and preserve diagnostic artifacts."""
    draft = TestJourneyDraft(
        id="draft_assertion_fail",
        exploration_id="exp_test",
        name="Failing Assertion Draft",
        start_url=local_test_page,
        steps=[
            SynthesizedStep(
                number=1,
                action_type="navigate",
                url=local_test_page,
                description_short="Nav",
                description_detailed="Nav",
                assertions=[
                    SynthesizedAssertion(
                        assertion_type="text_matches",
                        target_selector="#confirmation",
                        expected_value="Expected Secret Token 12345",
                    )
                ],
            )
        ],
    )

    executor = SandboxExecutor(base_artifacts_dir=tmp_path / "artifacts")
    report = await executor.execute_validation(draft, headless=True)

    assert report.overall_status == "FAILED"
    failed_assert = next(a for a in report.assertion_results if not a.passed)
    assert failed_assert.failure_reason is not None
    assert "Expected Secret Token 12345" in failed_assert.failure_reason


@pytest.mark.asyncio
async def test_destructive_operations_blocked_by_policy(local_test_page: str, tmp_path: Path):
    """Test 9: Destructive action is blocked when allow_destructive is False."""
    draft = TestJourneyDraft(
        id="draft_destructive",
        exploration_id="exp_test",
        name="Destructive Operation Draft",
        start_url=local_test_page,
        steps=[
            SynthesizedStep(number=1, action_type="navigate", url=local_test_page, description_short="Nav", description_detailed="Nav"),
            SynthesizedStep(
                number=2,
                action_type="click",
                selector="#btn-delete",
                description_short="Delete user profile data",
                description_detailed="Irreversible deletion operation",
                target_status="resolved",
            ),
        ],
    )

    executor = SandboxExecutor(base_artifacts_dir=tmp_path / "artifacts")
    # Default policy blocks destructive operations
    report = await executor.execute_validation(draft, policy=SandboxSafetyPolicy(allow_destructive=False), headless=True)

    assert report.overall_status == "BLOCKED"
    assert report.step_results[1].status == "BLOCKED"
    assert "destructive operation blocked" in (report.step_results[1].error_message or "").lower()


@pytest.mark.asyncio
async def test_browser_page_errors_distinguished_from_assertion_failures(local_test_page: str, tmp_path: Path):
    """Test 10: Uncaught JavaScript page errors are captured and fail no_page_error assertion."""
    draft = TestJourneyDraft(
        id="draft_page_error",
        exploration_id="exp_test",
        name="Page Error Trigger Draft",
        start_url=local_test_page,
        steps=[
            SynthesizedStep(number=1, action_type="navigate", url=local_test_page, description_short="Nav", description_detailed="Nav"),
            SynthesizedStep(
                number=2,
                action_type="click",
                selector="#btn-error",
                description_short="Click trigger error",
                description_detailed="Triggers runtime throw",
                target_status="resolved",
                assertions=[SynthesizedAssertion(assertion_type="no_page_error")],
            ),
        ],
    )

    executor = SandboxExecutor(base_artifacts_dir=tmp_path / "artifacts")
    report = await executor.execute_validation(draft, headless=True)

    assert report.overall_status == "FAILED"
    assert len(report.artifacts.get("page_errors", [])) >= 1
    assert "Uncaught runtime exception" in str(report.artifacts.get("page_errors", []))


@pytest.mark.asyncio
async def test_cancellation_closes_contexts_and_releases_resources(local_test_page: str, tmp_path: Path):
    """Test 11: Cancelling an in-flight validation task cleanly releases browser context."""
    orchestrator = ValidationOrchestrator()
    draft = TestJourneyDraft(
        id="draft_cancel",
        exploration_id="exp_test",
        name="Long Draft for Cancellation",
        start_url=local_test_page,
        steps=[
            SynthesizedStep(number=1, action_type="navigate", url=local_test_page, description_short="Nav", description_detailed="Nav"),
            SynthesizedStep(number=2, action_type="wait", description_short="Wait", description_detailed="Wait"),
            SynthesizedStep(number=3, action_type="wait", description_short="Wait", description_detailed="Wait"),
        ],
    )

    # Launch background validation
    orchestrator.start_background_validation(draft, headless=True)
    assert orchestrator.is_validating(draft.id) is True

    # Cancel task
    cancelled = orchestrator.cancel_validation(draft.id)
    assert cancelled is True
    assert orchestrator.is_validating(draft.id) is False


@pytest.mark.asyncio
async def test_concurrent_validations_use_isolated_contexts(local_test_page: str, tmp_path: Path):
    """Test 12: Concurrent validations execute simultaneously with isolated contexts."""
    executor = SandboxExecutor(base_artifacts_dir=tmp_path / "artifacts")

    draft1 = TestJourneyDraft(
        id="draft_conc_1",
        exploration_id="exp_test",
        name="Concurrent Run 1",
        start_url=local_test_page,
        steps=[
            SynthesizedStep(number=1, action_type="navigate", url=local_test_page, description_short="Nav 1", description_detailed="Nav 1"),
        ],
    )
    draft2 = TestJourneyDraft(
        id="draft_conc_2",
        exploration_id="exp_test",
        name="Concurrent Run 2",
        start_url=local_test_page,
        steps=[
            SynthesizedStep(number=1, action_type="navigate", url=local_test_page, description_short="Nav 2", description_detailed="Nav 2"),
        ],
    )

    report1, report2 = await asyncio.gather(
        executor.execute_validation(draft1, headless=True),
        executor.execute_validation(draft2, headless=True),
    )

    assert report1.overall_status == "VERIFIED"
    assert report2.overall_status == "VERIFIED"
    assert report1.validation_id != report2.validation_id
    assert report1.artifacts["artifact_dir"] != report2.artifacts["artifact_dir"]


def test_draft_version_change_invalidates_prior_validation(test_db: Path):
    """Test 13: Draft edits increment version and invalidate previous validation status."""
    create_exploration_run(
        exploration_id="exp_v1",
        project_id="default_project",
        start_url="http://127.0.0.1:8000/",
        config={},
        db_path=test_db,
    )
    # 1. Save draft version 1
    draft_dict = {
        "id": "draft_ver_test",
        "exploration_id": "exp_v1",
        "name": "Version Test Draft",
        "start_url": "http://127.0.0.1:8000/",
        "steps": [{"number": 1, "action_type": "navigate", "url": "http://127.0.0.1:8000/"}],
    }
    saved = save_synthesized_draft(draft_dict, db_path=test_db)
    assert saved.get("version", 1) == 1

    # 2. Persist validation for version 1
    val_report = {
        "validation_id": "val_v1_001",
        "draft_id": "draft_ver_test",
        "draft_version": 1,
        "browser": "chromium",
        "headless": True,
        "overall_status": "VERIFIED",
        "started_at": "2026-11-20T10:00:00",
        "completed_at": "2026-11-20T10:00:05",
        "step_results": [{"step_number": 1, "status": "PASSED"}],
        "assertion_results": [],
        "artifacts": {},
    }
    save_draft_validation(val_report, db_path=test_db)

    # Latest validation is current
    latest = get_latest_draft_validation("draft_ver_test", db_path=test_db)
    assert latest is not None
    assert latest["is_current_version"] is True

    # 3. User edits draft (changes steps/name) -> increments version to 2
    updated = update_synthesized_draft(
        draft_id="draft_ver_test",
        name="Version Test Draft v2 (Edited)",
        steps=[{"number": 1, "action_type": "navigate", "url": "http://127.0.0.1:8000/new"}],
        db_path=test_db,
    )
    assert updated["version"] == 2

    # Prior validation record still exists in history, but is_current_version is now False!
    latest_after_edit = get_latest_draft_validation("draft_ver_test", db_path=test_db)
    assert latest_after_edit is not None
    assert latest_after_edit["is_current_version"] is False


def test_api_endpoints_for_validation(local_test_page: str, monkeypatch, tmp_path: Path):
    """Test 14: REST API endpoints for starting, querying, and cancelling validations."""
    db_file = tmp_path / "api_test_studio.db"
    init_studio_db(db_file)

    create_exploration_run(
        exploration_id="exp_api",
        project_id="default_project",
        start_url=local_test_page,
        config={},
        db_path=db_file,
    )

    # Save draft into test DB
    draft_dict = {
        "id": "draft_api_test",
        "exploration_id": "exp_api",
        "name": "API Test Draft",
        "start_url": local_test_page,
        "steps": [{"number": 1, "action_type": "navigate", "url": local_test_page, "description_short": "Nav", "description_detailed": "Nav"}],
    }
    save_synthesized_draft(draft_dict, db_path=db_file)

    from tracecase.ui import db
    monkeypatch.setattr(db, "DEFAULT_STUDIO_DB_PATH", db_file)

    app = create_app()
    client = TestClient(app)

    # 1. Start validation via POST
    resp_post = client.post(
        "/api/autonomous/drafts/draft_api_test/validate",
        json={"browser": "chromium", "headless": True},
    )
    assert resp_post.status_code == 200
    report_data = resp_post.json()
    assert report_data["overall_status"] == "VERIFIED"
    assert report_data["draft_id"] == "draft_api_test"

    # 2. Query latest validation via GET
    resp_get = client.get("/api/autonomous/drafts/draft_api_test/validation")
    assert resp_get.status_code == 200
    assert resp_get.json()["validation_id"] == report_data["validation_id"]
    assert resp_get.json()["is_current_version"] is True

    # 3. Query all validations via GET
    resp_list = client.get("/api/autonomous/drafts/draft_api_test/validations")
    assert resp_list.status_code == 200
    assert len(resp_list.json()) >= 1

    # 4. Cancel endpoint
    resp_cancel = client.post("/api/autonomous/drafts/draft_api_test/validation/cancel")
    assert resp_cancel.status_code == 200
    assert "cancelled" in resp_cancel.json()
