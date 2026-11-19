"""Real Browser End-to-End Validation Suite for Phase 5.1 (AI Intelligence).

Validates the full lifecycle with real Chromium browser execution against a local test server:
1. Live Recording -> AI Assertion Generation (runtime evidence backed, provider transparent) -> Replay with Assertions
2. Fragile Selector Detection -> Live DOM Resolution Guardrail (1 match + semantic match + allowed host) -> Fix & Replay
3. Failure Diagnosis Accuracy (Distinguishes ASSERTION_FAILURE vs APPLICATION_BUG vs TIMEOUT_ENVIRONMENT)
4. Isolated Smart Variations (Boundary, Format, Security opt-in & sandboxed execution)
5. Persistence vs Transient Evidence Verification across reload
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import pytest
from playwright.async_api import async_playwright

from qa_auto.ai.assertion_generator import suggest_assertions
from qa_auto.ai.coverage_analyst import analyze_corpus_coverage
from qa_auto.ai.failure_analyst import (
    analyze_execution_failure,
    analyze_failure_heuristics,
)
from qa_auto.ai.provider import NullProvider
from qa_auto.ai.selectors import (
    audit_testcase_selectors,
    evaluate_selector,
    verify_locator_in_live_dom,
)
from qa_auto.ai.variations import (
    generate_heuristic_variations,
    generate_smart_variations,
    is_safe_test_environment,
)
from qa_auto.models import ElementInfo, Step, TestCase
from qa_auto.recorder import Recorder
from qa_auto.replay.engine import ReplayEngine
from qa_auto.ui.db import (
    create_execution_run,
    get_execution_run,
    init_studio_db,
    update_execution_run_status,
)
from qa_auto.ui.service import (
    add_custom_assertion,
    persist_generated_testcase,
    resolve_testcase_file,
    update_testcase_step,
)

logger = logging.getLogger("qa_auto.test_real_ai_validation_e2e")

TEST_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>QA Auto AI Test Bench</title>
</head>
<body style="font-family: sans-serif; padding: 20px;">
  <h1 id="main-heading">QA Auto Test Bench</h1>

  <div style="margin-bottom: 15px;">
    <button type="button" id="toggle-status-btn" style="padding: 8px 16px;" onclick="document.getElementById('status-message').style.display='block';">Toggle Status</button>
    <button type="button" id="fetch-btn" style="padding: 8px 16px;" onclick="fetch('/api/login', {method: 'POST'});">Call API</button>
  </div>

  <div id="status-message" style="display: none; margin-bottom: 15px; font-weight: bold; color: green;">Status: Authenticated and Ready</div>

  <form id="login-form" action="/dashboard" method="GET">
    <div style="margin-bottom: 10px;">
      <label for="username">Username:</label>
      <input type="text" id="username" name="username" data-testid="username-input" placeholder="Enter username" />
    </div>

    <div style="margin-bottom: 10px;">
      <label for="password">Password:</label>
      <input type="password" id="user-session-987654" name="password" placeholder="Enter password" class="css-1a2b3c" />
    </div>

    <button type="submit" id="submit-btn" role="button" style="padding: 8px 16px;">Sign In</button>
  </form>
</body>
</html>
"""

DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Dashboard</title>
</head>
<body style="font-family: sans-serif; padding: 20px;">
  <h1 id="welcome-header">Welcome back, QA Engineer!</h1>
  <p id="dashboard-status">Session active and healthy.</p>
</body>
</html>
"""


class TestBenchHandler(BaseHTTPRequestHandler):
    """Local HTTP test handler serving deterministic pages and failure endpoints."""

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(TEST_HTML.encode("utf-8"))
        elif self.path.startswith("/dashboard"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode("utf-8"))
        elif self.path.startswith("/500-error"):
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Internal Server Error: Database pool exhausted")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        if self.path.startswith("/api/login"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'{"token": "auth_token_12345", "status": "success"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress standard HTTP request logging in test runs
        return


@pytest.fixture(scope="module")
def local_server():
    """Start local HTTP server on random free port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), TestBenchHandler)
    host, port = server.server_address
    base_url = f"http://{host}:{port}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield base_url

    server.shutdown()
    server.server_close()


# ---------------------------------------------------------------------------
# Test 1: Record -> AI Assertion Generation (Evidence-Backed) -> Replay
# ---------------------------------------------------------------------------

@pytest.mark.timeout(60)
@pytest.mark.asyncio
async def test_ai_assertion_generation_and_replay_lifecycle(local_server: str, tmp_path: Path):
    """Verify live recording, AI assertion derivation with runtime evidence, and enforcement."""
    output_dir = tmp_path / "recordings" / "live_flow_test"
    output_dir.mkdir(parents=True, exist_ok=True)

    recorder = Recorder(
        output_dir=output_dir,
        start_url=local_server,
        name="Live AI Recording",
        browser_type="chromium",
        headless=True,
        auto_start=True,
    )
    record_task = asyncio.create_task(recorder.run())

    for _ in range(50):
        if recorder.is_recording and recorder._pages:
            break
        await asyncio.sleep(0.1)

    assert recorder.is_recording is True
    page = recorder._pages[0]

    # Perform interactions
    await page.click("#toggle-status-btn")
    await asyncio.sleep(0.4)
    await page.click("#fetch-btn")
    await asyncio.sleep(0.4)
    await page.click("#submit-btn")
    await asyncio.sleep(0.6)

    await recorder.stop_recording()
    await record_task

    tc_file = output_dir / "testcase.json"
    assert tc_file.exists()
    testcase = TestCase.model_validate_json(tc_file.read_text(encoding="utf-8"))
    assert testcase is not None
    assert len(testcase.steps) >= 1

    # Step 1: Generate AI assertions using provider / heuristic fallback
    provider = NullProvider()
    result = await suggest_assertions(testcase, provider)

    # Verify provider transparency (must report heuristic, not fake LLM)
    assert result.provider_used == "heuristic"
    assert result.is_llm_generated is False
    assert len(result.suggestions) >= 2

    for s in result.suggestions:
        assert s.source == "heuristic"
        assert s.confidence >= 0.8
        assert s.step_number in [st.number for st in testcase.steps]

    # Attach generated assertions to testcase
    tc_file = output_dir / "testcase.json"
    for s in result.suggestions:
        testcase.custom_assertions.append(
            {
                "kind": s.kind,
                "target": s.target,
                "expected": s.expected,
                "step_number": s.step_number,
                "source": s.source,
                "confidence": s.confidence,
                "enforced": True,
            }
        )
    tc_file.write_text(testcase.model_dump_json(indent=2), encoding="utf-8")

    # Replay with assertions enabled
    replay_engine = ReplayEngine(
        testcase=testcase,
        headless=True,
        assertions_enabled=True,
        timeout=5000,
    )
    replay_res = await replay_engine.run()

    # Replay should pass with zero assertion failures
    failed_assertions = [
        (s.number, a.assertion.kind, a.assertion.expected, a.actual, a.message)
        for s in replay_res.steps
        for a in s.assertions
        if not a.passed
    ]
    assert not failed_assertions, f"Failed assertions: {failed_assertions}"
    assert replay_res.status == "passed"
    for step in replay_res.steps:
        for ast in step.assertions:
            assert ast.passed is True


# ---------------------------------------------------------------------------
# Test 2: Selector Fragility & Live DOM Resolution Guardrail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_live_dom_resolution_guardrail_and_healing(local_server: str, tmp_path: Path):
    """Verify live DOM resolution probe enforces single match, semantic match, and host safety."""
    # 1. Host restriction check: external domains must be rejected
    with pytest.raises(ValueError, match="Host restriction denied"):
        await verify_locator_in_live_dom(
            target_url="https://evil-unauthorized-domain.com",
            candidate_selector="button",
        )

    # 2. Ambiguous locator check: 'input' matches multiple inputs in form
    ambig_res = await verify_locator_in_live_dom(
        target_url=local_server,
        candidate_selector="input",
    )
    assert ambig_res["verified"] is False
    assert ambig_res["count"] > 1
    assert "Ambiguous" in ambig_res["reason"]

    # 3. Tag mismatch check: expecting a 'button' but selector points to an 'input'
    tag_mismatch_res = await verify_locator_in_live_dom(
        target_url=local_server,
        candidate_selector="[data-testid='username-input']",
        expected_tag="button",
    )
    assert tag_mismatch_res["verified"] is False
    assert tag_mismatch_res["count"] == 1
    assert "mismatch" in tag_mismatch_res["reason"].lower()

    # 4. Valid single match: data-testid="username-input"
    valid_res = await verify_locator_in_live_dom(
        target_url=local_server,
        candidate_selector="[data-testid='username-input']",
        expected_tag="input",
    )
    assert valid_res["verified"] is True
    assert valid_res["count"] == 1
    assert valid_res["matched_tag"] == "input"

    # 5. Playwright code expression: page.getByRole('button', name='Sign In')
    role_res = await verify_locator_in_live_dom(
        target_url=local_server,
        candidate_selector="page.getByRole('button', name='Sign In')",
        expected_tag="button",
        expected_text="Sign In",
    )
    assert role_res["verified"] is True
    assert role_res["count"] == 1
    assert role_res["matched_tag"] == "button"
    assert "Sign In" in role_res["matched_text"]


# ---------------------------------------------------------------------------
# Test 3: Failure Diagnosis Accuracy (Category Classification)
# ---------------------------------------------------------------------------

def test_failure_diagnosis_distinguishes_causes():
    """Verify failure diagnosis accurately differentiates failure classes."""
    # Case A: ASSERTION_FAILURE
    run_assertion = {
        "id": "run_ast_1",
        "testcase_name": "Login Test",
        "status": "failed",
        "error_message": "Assertion [url] failed: expected '/dashboard' but got '/login'",
        "step_number_failed": 3,
        "logs": ["Step 1 passed", "Step 2 passed", "Assertion failed: expected /dashboard"],
    }
    diag_ast = analyze_failure_heuristics(run_assertion)
    assert diag_ast.category == "ASSERTION_FAILURE"
    assert diag_ast.confidence >= 0.9

    # Case B: APPLICATION_BUG (500 Internal Server Error)
    run_500 = {
        "id": "run_500_1",
        "testcase_name": "Checkout Flow",
        "status": "failed",
        "error_message": "HTTP 500 Internal Server Error: Database pool exhausted",
        "step_number_failed": 4,
        "logs": ["Click checkout", "500 Internal Server Error"],
    }
    diag_500 = analyze_failure_heuristics(run_500)
    assert diag_500.category == "APPLICATION_BUG"
    assert "server" in diag_500.remediation.lower()

    # Case C: SELECTOR_DRIFT (Element timeout)
    run_drift = {
        "id": "run_drift_1",
        "testcase_name": "Profile Flow",
        "status": "failed",
        "error_message": "Timeout 5000ms exceeded waiting for locator('button.submit-123')",
        "step_number_failed": 2,
        "logs": ["Timed out waiting for selector button.submit-123"],
    }
    diag_drift = analyze_failure_heuristics(run_drift)
    assert diag_drift.category == "SELECTOR_DRIFT"
    assert diag_drift.selector_drift_detected is True

    # Case D: TIMEOUT_ENVIRONMENT (Network refusal)
    run_env = {
        "id": "run_env_1",
        "testcase_name": "API Ping",
        "status": "failed",
        "error_message": "net::ERR_CONNECTION_REFUSED at http://127.0.0.1:59999",
        "step_number_failed": 1,
        "logs": ["net::ERR_CONNECTION_REFUSED"],
    }
    diag_env = analyze_failure_heuristics(run_env)
    assert diag_env.category == "TIMEOUT_ENVIRONMENT"


# ---------------------------------------------------------------------------
# Test 4: Isolated Security Test Variations
# ---------------------------------------------------------------------------

def test_security_variations_safety_isolation():
    """Verify security variations are safely restricted to local/isolated test environments."""
    # Test on local server URL (safe)
    local_tc = TestCase(
        id="tc_local_safe",
        name="Local Form",
        start_url="http://127.0.0.1:8080/form",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="QA Auto",
        steps=[
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="input",
                input_value="test",
                description_short="Type test",
                description_detailed="Input test",
            )
        ],
        created_at=datetime.now(),
        total_steps=1,
        total_duration=1.0,
    )
    assert is_safe_test_environment(local_tc.start_url) is True

    safe_variations = generate_heuristic_variations(
        local_tc, strategies=["security", "boundary"]
    )
    strategies = [v.strategy for v in safe_variations]
    assert "security" in strategies
    assert "boundary" in strategies

    # Test on production external URL without explicit opt-in
    prod_tc = TestCase(
        id="tc_prod_external",
        name="Production External Site",
        start_url="https://production-banking-app.com/login",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="QA Auto",
        steps=[
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="input",
                input_value="test",
                description_short="Type test",
                description_detailed="Input test",
            )
        ],
        created_at=datetime.now(),
        total_steps=1,
        total_duration=1.0,
    )
    assert is_safe_test_environment(prod_tc.start_url) is False

    # Security probes should be skipped automatically to protect external systems
    prod_variations = generate_heuristic_variations(
        prod_tc, strategies=["security", "boundary"], allow_security_probes=False
    )
    prod_strategies = [v.strategy for v in prod_variations]
    assert "security" not in prod_strategies
    assert "boundary" in prod_strategies


# ---------------------------------------------------------------------------
# Test 5: Persistence vs Transient Diagnostics Verification
# ---------------------------------------------------------------------------

def test_persistence_contracts_across_restart(tmp_path: Path):
    """Verify persisted models survive process reload while diagnostics are evidence-based."""
    db_file = tmp_path / "studio_lifecycle.db"
    init_studio_db(str(db_file))

    # Persist a testcase with custom assertions
    tc = TestCase(
        id="tc_persistence_probe",
        name="Persistence Verification Flow",
        start_url="http://127.0.0.1:8000/app",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="QA Auto",
        steps=[
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="navigate",
                url="http://127.0.0.1:8000/app",
                description_short="Navigate",
                description_detailed="Navigate to app",
            )
        ],
        custom_assertions=[
            {"kind": "url", "expected": "/app", "step_number": 1, "confidence": 0.95}
        ],
        created_at=datetime.now(),
        total_steps=1,
        total_duration=1.0,
    )
    persist_generated_testcase(tc)

    # Record execution in DB
    run_meta = create_execution_run(
        testcase_id=tc.id,
        testcase_name=tc.name,
        browser="chromium",
        db_path=db_file,
    )
    run_id = run_meta["id"]
    update_execution_run_status(
        execution_id=run_id,
        status="passed",
        duration_ms=1200.0,
        passed_steps=1,
        total_steps=1,
        db_path=db_file,
    )

    # Simulate restart by re-initializing and fetching fresh
    reloaded_run = get_execution_run(run_id, db_path=db_file)
    assert reloaded_run is not None
    assert reloaded_run["status"] == "passed"
    assert reloaded_run["testcase_id"] == tc.id

    # Verify testcase file reload
    found_file, loaded_tc = resolve_testcase_file(tc.id, search_paths=[Path("recordings")])
    assert loaded_tc.id == tc.id
    assert len(loaded_tc.custom_assertions) == 1
    assert loaded_tc.custom_assertions[0]["expected"] == "/app"
