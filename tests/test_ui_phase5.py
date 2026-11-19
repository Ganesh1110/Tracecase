"""Comprehensive tests for Phase 5: AI-Powered QA Intelligence.

Validates:
1. AI Test Case Analysis & Intent classification
2. Automatic Assertion Generation (heuristic + provider fallback)
3. Smart Test Generation (Boundary, Security, Invalid Format)
4. Selector Intelligence & Fragility Scoring
5. Execution Failure Analysis & Root Cause Diagnosis
6. Resilient Locator Derivation (getByRole, getByTestId, getByLabel)
7. Corpus Coverage Intelligence & Test Gap Analysis
8. UI REST API Endpoints for all AI Intelligence features
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
import pytest
from fastapi.testclient import TestClient

from qa_auto.ai.assertion_generator import (
    generate_heuristic_assertions,
    suggest_assertions,
)
from qa_auto.ai.coverage_analyst import analyze_corpus_coverage
from qa_auto.ai.failure_analyst import (
    FailureCategory,
    analyze_execution_failure,
    analyze_failure_heuristics,
)
from qa_auto.ai.provider import NullProvider
from qa_auto.ai.selectors import (
    audit_testcase_selectors,
    evaluate_selector,
)
from qa_auto.ai.variations import (
    generate_heuristic_variations,
    generate_smart_variations,
)
from qa_auto.models import ElementInfo, NetworkRequest, Step, TestCase
from qa_auto.ui.db import (
    create_execution_run,
    init_studio_db,
    update_execution_run_status,
)
from qa_auto.ui.server import create_app
from qa_auto.ui.service import create_manual_testcase, persist_generated_testcase


@pytest.fixture
def sample_testcase() -> TestCase:
    """Create a multi-step test case with various selectors and inputs."""
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url="https://example.com/login",
            description_short="Navigate to login page",
            description_detailed="Open login page",
        ),
        Step(
            number=2,
            timestamp=datetime.now(),
            action_type="input",
            element=ElementInfo(
                selector="input#session-123456",  # dynamic ID
                tag_name="input",
                placeholder="Enter email",
                attributes={"data-testid": "email-input", "type": "email", "name": "email"},
                bounding_box={"x": 10, "y": 20, "width": 200, "height": 30},
            ),
            input_value="user@example.com",
            description_short="Enter user email",
            description_detailed="Type user@example.com into email input",
        ),
        Step(
            number=3,
            timestamp=datetime.now(),
            action_type="input",
            element=ElementInfo(
                selector="input.css-1a2b3c",  # hashed class
                tag_name="input",
                placeholder="Enter password",
                attributes={"type": "password", "name": "password", "aria-label": "Password"},
                bounding_box={"x": 10, "y": 60, "width": 200, "height": 30},
            ),
            input_value="secret123",
            description_short="Enter password",
            description_detailed="Type secret123 into password input",
        ),
        Step(
            number=4,
            timestamp=datetime.now(),
            action_type="click",
            element=ElementInfo(
                selector="/html/body/div[2]/form/div[3]/button",  # absolute xpath
                xpath="/html/body/div[2]/form/div[3]/button",
                tag_name="button",
                text="Sign In",
                attributes={"role": "button", "type": "submit"},
                bounding_box={"x": 10, "y": 100, "width": 100, "height": 40},
            ),
            network_requests=[
                NetworkRequest(
                    method="POST",
                    url="https://example.com/api/login",
                    status=200,
                    resource_type="xhr",
                    response_body='{"token": "xyz123", "success": true}',
                )
            ],
            description_short="Click Sign In button",
            description_detailed="Submit login form",
        ),
    ]

    return TestCase(
        id="tc_sample_phase5",
        name="User Authentication Flow",
        description="Verify user can login successfully with credentials",
        start_url="https://example.com/login",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="QA Auto Studio",
        steps=steps,
        custom_assertions=[],
        created_at=datetime.now(),
        total_steps=len(steps),
        total_duration=3.5,
    )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Configure isolated FastAPI test client."""
    db_file = tmp_path / "studio_phase5.db"
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("QA_AUTO_STUDIO_DB", str(db_file))
    monkeypatch.chdir(tmp_path)
    init_studio_db(str(db_file))

    app = create_app()
    return TestClient(app)


# ---------------------------------------------------------------------------
# Unit Tests: Assertion Generator
# ---------------------------------------------------------------------------

def test_heuristic_assertion_generation(sample_testcase: TestCase):
    """Verify heuristic assertion generator produces URL, visibility, and API response assertions."""
    suggestions = generate_heuristic_assertions(sample_testcase)
    assert len(suggestions) >= 3

    kinds = [s.kind for s in suggestions]
    assert "url" in kinds
    assert "visible" in kinds or "status" in kinds

    # Verify high confidence scores and rationales
    for s in suggestions:
        assert 0.0 <= s.confidence <= 1.0
        assert len(s.rationale) > 5
        assert s.step_number in [step.number for step in sample_testcase.steps]


@pytest.mark.asyncio
async def test_suggest_assertions_provider_fallback(sample_testcase: TestCase):
    """Verify suggest_assertions falls back cleanly to heuristics when provider is NullProvider."""
    provider = NullProvider()
    result = await suggest_assertions(sample_testcase, provider)
    assert result.total_suggestions >= 3
    assert len(result.suggestions) == result.total_suggestions


# ---------------------------------------------------------------------------
# Unit Tests: Selector Intelligence & Fragility
# ---------------------------------------------------------------------------

def test_selector_fragility_evaluation():
    """Verify selector evaluation catches dynamic IDs, hashed classes, and absolute XPaths."""
    # 1. Dynamic ID
    res1 = evaluate_selector("button#btn_173200112233")
    assert res1.is_fragile is True
    assert "Dynamic" in res1.issues[0]

    # 2. Hashed Class
    res2 = evaluate_selector("div.css-1y829ab")
    assert res2.is_fragile is True
    assert "Hashed" in res2.issues[0]

    # 3. Absolute XPath
    res3 = evaluate_selector("/html/body/div[1]/form/input")
    assert res3.is_fragile is True
    assert "XPath" in res3.issues[0]

    # 4. Safe data-testid
    res4 = evaluate_selector("[data-testid='submit-btn']")
    assert res4.is_fragile is False
    assert res4.fragility_score <= 15


def test_testcase_selector_audit(sample_testcase: TestCase):
    """Verify audit_testcase_selectors identifies fragile locators and recommends Playwright locators."""
    report = audit_testcase_selectors(sample_testcase)
    assert report.total_evaluated == 3  # Steps 2, 3, 4 have elements
    assert report.fragile_count >= 2

    # Step 2 has data-testid="email-input", should recommend getByTestId
    step2_audit = next(s for s in report.selectors if s.step_number == 2)
    assert step2_audit.is_fragile is True
    assert "getByTestId('email-input')" in step2_audit.recommended_locator

    # Step 4 has role="button" and text="Sign In", should recommend getByRole
    step4_audit = next(s for s in report.selectors if s.step_number == 4)
    assert step4_audit.is_fragile is True
    assert "getByRole('button'" in (step4_audit.recommended_locator or "")


# ---------------------------------------------------------------------------
# Unit Tests: Failure Analyst
# ---------------------------------------------------------------------------

def test_analyze_failure_heuristics_selector_drift():
    """Verify selector drift is properly identified from timeout logs."""
    run = {
        "id": "run_failed_1",
        "status": "failed",
        "error_message": "Timeout 5000ms exceeded waiting for locator('button#submit')",
        "step_number_failed": 3,
        "logs": ["Clicking step 3", "Timeout 5000ms exceeded waiting for locator('button#submit')"],
        "steps": [
            {"step_number": 1, "status": "passed"},
            {"step_number": 2, "status": "passed"},
            {
                "step_number": 3,
                "status": "failed",
                "action_type": "click",
                "selector": "button#submit",
                "error": "Timeout 5000ms exceeded waiting for locator('button#submit')",
            },
        ],
    }

    res = analyze_failure_heuristics(run)
    assert res.category == "SELECTOR_DRIFT"
    assert res.step_number_failed == 3
    assert res.selector_drift_detected is True
    assert "selector" in res.remediation.lower() or "locator" in res.remediation.lower()


def test_analyze_failure_heuristics_assertion_failure():
    """Verify assertion failures are diagnosed with expected vs actual discrepancies."""
    run = {
        "id": "run_failed_2",
        "status": "failed",
        "error_message": "AssertionError: expected URL to contain '/dashboard' but got '/login'",
        "step_number_failed": 2,
        "logs": ["Assertion failed: expected /dashboard but got /login"],
        "steps": [
            {"step_number": 1, "status": "passed"},
            {
                "step_number": 2,
                "status": "failed",
                "error": "AssertionError: expected URL to contain '/dashboard' but got '/login'",
            },
        ],
    }

    res = analyze_failure_heuristics(run)
    assert res.category == "ASSERTION_FAILURE"
    assert "assertion" in res.root_cause.lower()


# ---------------------------------------------------------------------------
# Unit Tests: Smart Variations Generator
# ---------------------------------------------------------------------------

def test_smart_variations_generator(sample_testcase: TestCase):
    """Verify synthesis of boundary, security, and format test variations."""
    variations = generate_heuristic_variations(
        sample_testcase,
        strategies=["boundary", "security", "invalid_format"],
        allow_security_probes=True,
    )
    assert len(variations) >= 5

    # Check that input steps were mutated
    for v in variations:
        assert v.variation_id != sample_testcase.id
        assert len(v.mutations) == 2  # Steps 2 and 3 are input steps
        assert v.test_case.steps[1].input_value != "user@example.com"
        assert v.test_case.steps[2].input_value != "secret123"


# ---------------------------------------------------------------------------
# Unit Tests: Corpus Coverage Intelligence
# ---------------------------------------------------------------------------

def test_corpus_coverage_intelligence(sample_testcase: TestCase):
    """Verify coverage report computes route coverage, assertion density, and recommendations."""
    res = analyze_corpus_coverage([sample_testcase])
    assert res.total_testcases == 1
    assert res.total_steps == 4
    assert res.unique_routes_count >= 1
    assert len(res.testcases_without_assertions) == 1
    assert res.assertion_density == 0.0
    assert len(res.recommendations) >= 1
    assert res.coverage_score < 100


# ---------------------------------------------------------------------------
# Integration Tests: UI REST API Endpoints
# ---------------------------------------------------------------------------

def test_api_ai_suggest_and_apply_assertions(client: TestClient, sample_testcase: TestCase):
    """Verify POST /api/ai/suggest-assertions and batch apply."""
    # Persist sample testcase
    persist_generated_testcase(sample_testcase)

    # 1. Suggest assertions
    resp = client.post(
        "/api/ai/suggest-assertions", json={"testcase_id": sample_testcase.id}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_suggestions"] >= 3
    suggestions = data["suggestions"]

    # 2. Apply suggestions
    apply_resp = client.post(
        f"/api/testcases/{sample_testcase.id}/assertions/apply-suggestions",
        json={"suggestions": suggestions},
    )
    assert apply_resp.status_code == 200
    updated_tc = apply_resp.json()
    assert len(updated_tc["custom_assertions"]) == len(suggestions)


def test_api_selector_audit_and_fix(client: TestClient, sample_testcase: TestCase):
    """Verify GET /api/testcases/{id}/selectors/audit and POST /apply-fix."""
    persist_generated_testcase(sample_testcase)

    # 1. Audit selectors
    audit_resp = client.get(f"/api/testcases/{sample_testcase.id}/selectors/audit")
    assert audit_resp.status_code == 200
    report = audit_resp.json()
    assert report["fragile_count"] >= 2

    # 2. Apply selector fix to step 2
    step2_audit = next(s for s in report["selectors"] if s["step_number"] == 2)
    new_locator = step2_audit["recommended_locator"]

    fix_resp = client.post(
        f"/api/testcases/{sample_testcase.id}/selectors/apply-fix",
        json={"step_number": 2, "selector": new_locator},
    )
    assert fix_resp.status_code == 200
    updated = fix_resp.json()
    step2 = next(s for s in updated["steps"] if s["number"] == 2)
    assert step2["element"]["selector"] == new_locator


def test_api_failure_analysis(client: TestClient):
    """Verify POST /api/ai/failure-analysis."""
    # Record a failed execution run in DB
    run_meta = create_execution_run(
        testcase_id="tc_dummy",
        testcase_name="Dummy Case",
        browser="chromium",
    )
    run_id = run_meta["id"]
    update_execution_run_status(
        execution_id=run_id,
        status="failed",
        error_message="Timed out waiting for selector .loading-spinner",
        duration_ms=5000.0,
        failed_steps=1,
        total_steps=3,
        logs=["Step 1 passed", "Timed out waiting for selector .loading-spinner"],
    )

    resp = client.post("/api/ai/failure-analysis", json={"execution_id": run_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] in ["SELECTOR_DRIFT", "TIMEOUT_ENVIRONMENT"]
    assert len(data["remediation"]) > 0


def test_api_generate_variations(client: TestClient, sample_testcase: TestCase):
    """Verify POST /api/ai/generate-variations with auto_save."""
    persist_generated_testcase(sample_testcase)

    resp = client.post(
        "/api/ai/generate-variations",
        json={
            "testcase_id": sample_testcase.id,
            "strategies": ["boundary", "security"],
            "allow_security_probes": True,
            "auto_save": True,
        },
    )
    assert resp.status_code == 200
    variations = resp.json()
    assert len(variations) >= 3

    # Check that variations exist in testcase listings
    tc_resp = client.get("/api/testcases")
    assert tc_resp.status_code == 200
    all_cases = tc_resp.json()
    all_ids = [c["id"] for c in all_cases]
    for v in variations:
        assert v["variation_id"] in all_ids


def test_api_coverage_insights(client: TestClient, sample_testcase: TestCase):
    """Verify GET /api/ai/coverage-insights."""
    persist_generated_testcase(sample_testcase)

    resp = client.get("/api/ai/coverage-insights")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_testcases"] >= 1
    assert data["total_steps"] >= 4
    assert "coverage_score" in data
    assert "risk_level" in data
    assert len(data["recommendations"]) >= 1
