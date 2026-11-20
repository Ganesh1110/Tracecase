"""Integration and API test suite for Phase 8.4 — Studio CI Dashboard & PR Intelligence.

Validates:
1. Subphase 8.4.1: CI Runs Dashboard persistence, filtering, and retrieval.
2. Subphase 8.4.2: PR Regression Intelligence grouped drift items and breakdown.
3. Subphase 8.4.3: Visual evidence comparison and side-by-side artifact payloads.
4. Subphase 8.4.4: Historical CI analytics, daily trends, flakiness leaderboards.
5. CIRunner automatic persistence into SQLite ci_runs table.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from tracecase.ci.config import CIRunnerConfig
from tracecase.ci.drift.models import DriftClassification, DriftAnalysisResult, TestDriftItem
from tracecase.ci.gate import QualityGateResult
from tracecase.ci.models import CIExitCode, CIRunResult
from tracecase.ci.runner import CIRunner
from tracecase.ui.db import (
    get_ci_analytics,
    get_ci_drift_for_run,
    get_ci_run_by_id,
    get_ci_runs,
    init_studio_db,
    save_ci_run,
)
from tracecase.ui.server import create_app


@pytest.fixture
def test_db_path(tmp_path: Path) -> Path:
    """Fixture providing an isolated studio SQLite db path."""
    db_file = tmp_path / "test_ci_studio.db"
    init_studio_db(db_file)
    return db_file


@pytest.fixture
def api_client(test_db_path: Path, monkeypatch) -> TestClient:
    """FastAPI TestClient pointing to the isolated database."""
    from tracecase.ui import db
    monkeypatch.setattr(db, "DEFAULT_STUDIO_DB_PATH", test_db_path)
    return TestClient(create_app())


def test_ci_run_persistence_and_querying(test_db_path: Path):
    """Subphase 8.4.1: Validate persisting and querying CI quality gate runs in SQLite."""
    gate_res = QualityGateResult(
        status="PASSED",
        passed=True,
        policy_name="standard",
        summary="All standard policy gates satisfied",
        metrics={
            "completed_runs": 10,
            "passed_count": 9,
            "failed_count": 1,
            "flaky_count": 1,
            "surface_coverage_pct": 94.5,
        },
    )

    drift_summary = {
        "new_regressions_count": 0,
        "pre_existing_failures_count": 1,
        "fixed_regressions_count": 2,
        "newly_flaky_count": 1,
    }

    run = CIRunResult(
        run_id="ci_run_test_001",
        project_id="proj_ecommerce",
        commit_hash="a1b2c3d4e5",
        branch="feature/checkout",
        base_ref="origin/main",
        duration_seconds=14.2,
        exit_code=0,
        gate_result=gate_res,
        total_considered=15,
        selected_count=10,
        executed_count=10,
        drift_summary=drift_summary,
        test_results=[
            {
                "testcase_id": "tc_cart",
                "name": "Cart Checkout",
                "status": "passed",
                "duration_ms": 1200.0,
            },
            {
                "testcase_id": "tc_legacy_auth",
                "name": "Legacy Auth",
                "status": "failed",
                "duration_ms": 800.0,
                "error_message": "Old token expired",
            },
        ],
    )

    # Persist
    save_ci_run(run, db_path=test_db_path)

    # Retrieve by ID
    retrieved = get_ci_run_by_id("ci_run_test_001", db_path=test_db_path)
    assert retrieved is not None
    assert retrieved["id"] == "ci_run_test_001"
    assert retrieved["project_id"] == "proj_ecommerce"
    assert retrieved["branch"] == "feature/checkout"
    assert retrieved["base_ref"] == "origin/main"
    assert retrieved["gate_passed"] == 1
    assert retrieved["status"] == "PASSED"
    assert retrieved["duration_seconds"] == 14.2
    assert retrieved["metrics"]["surface_coverage_pct"] == 94.5
    assert retrieved["drift_summary"]["pre_existing_failures_count"] == 1
    assert len(retrieved["test_results"]) == 2

    # Query list
    all_runs = get_ci_runs(db_path=test_db_path)
    assert len(all_runs) == 1
    assert all_runs[0]["id"] == "ci_run_test_001"

    # Filter by status
    passed_runs = get_ci_runs(status="PASSED", db_path=test_db_path)
    assert len(passed_runs) == 1

    failed_runs = get_ci_runs(status="FAILED", db_path=test_db_path)
    assert len(failed_runs) == 0


def test_api_ci_runs_endpoints(api_client: TestClient, test_db_path: Path):
    """Subphase 8.4.1: Validate REST API endpoints GET /api/ci/runs and GET /api/ci/runs/{id}."""
    # Seed two runs
    run1 = {
        "run_id": "ci_api_run_1",
        "project_id": "default_project",
        "commit_hash": "1111aaaa",
        "branch": "main",
        "exit_code": 0,
        "duration_seconds": 9.5,
        "gate_result": {"passed": True, "policy_name": "strict", "summary": "Strict pass"},
        "drift_summary": {"new_regressions_count": 0, "pre_existing_failures_count": 0},
    }
    run2 = {
        "run_id": "ci_api_run_2",
        "project_id": "default_project",
        "commit_hash": "2222bbbb",
        "branch": "feat/payment",
        "exit_code": 1,
        "duration_seconds": 18.0,
        "gate_result": {"passed": False, "policy_name": "standard", "summary": "1 new regression introduced"},
        "drift_summary": {"new_regressions_count": 1, "pre_existing_failures_count": 0},
    }
    save_ci_run(run1, db_path=test_db_path)
    save_ci_run(run2, db_path=test_db_path)

    # 1. List runs
    res_list = api_client.get("/api/ci/runs")
    assert res_list.status_code == 200
    runs = res_list.json()
    assert len(runs) == 2

    # 2. Filter by status=FAILED
    res_failed = api_client.get("/api/ci/runs?status=FAILED")
    assert res_failed.status_code == 200
    failed_runs = res_failed.json()
    assert len(failed_runs) == 1
    assert failed_runs[0]["id"] == "ci_api_run_2"

    # 3. Get single run
    res_single = api_client.get("/api/ci/runs/ci_api_run_1")
    assert res_single.status_code == 200
    data = res_single.json()
    assert data["id"] == "ci_api_run_1"
    assert data["gate_passed"] == 1

    # 4. Get missing run 404
    res_404 = api_client.get("/api/ci/runs/non_existent_run")
    assert res_404.status_code == 404


def test_api_ci_pr_regression_drift(api_client: TestClient, test_db_path: Path):
    """Subphase 8.4.2: Validate PR Regression Intelligence endpoint GET /api/ci/runs/{id}/drift."""
    from tracecase.ci.drift.analytics import DriftAnalytics

    # Seed run
    run = {
        "run_id": "ci_drift_run_1",
        "project_id": "proj_drift",
        "commit_hash": "3333cccc",
        "base_ref": "origin/main",
        "branch": "fix/order-flow",
        "exit_code": 1,
        "gate_result": {"passed": False, "policy_name": "standard", "summary": "Blocked by new regression"},
        "drift_summary": {
            "new_regressions_count": 1,
            "pre_existing_failures_count": 1,
            "fixed_regressions_count": 1,
            "newly_flaky_count": 1,
        },
    }
    save_ci_run(run, db_path=test_db_path)

    # Seed drift items into ci_drift_records
    analytics = DriftAnalytics(db_path=test_db_path)
    drift_result = DriftAnalysisResult(
        run_id="ci_drift_run_1",
        project_id="proj_drift",
        base_commit="base_sha_123",
        pr_commit="3333cccc",
        browser="chromium",
        items=[
            TestDriftItem(
                testcase_id="tc_broken_reg",
                testcase_name="Broken Regression Test",
                classification=DriftClassification.NEW_REGRESSION,
                pr_status="failed",
                base_status="passed",
                duration_delta_ms=250.0,
                explanation="Passed on base, failed on PR",
            ),
            TestDriftItem(
                testcase_id="tc_pre_existing",
                testcase_name="Old Broken Test",
                classification=DriftClassification.PRE_EXISTING_FAILURE,
                pr_status="failed",
                base_status="failed",
                duration_delta_ms=-10.0,
                explanation="Failed on both base and PR",
            ),
            TestDriftItem(
                testcase_id="tc_fixed",
                testcase_name="Fixed Bug Test",
                classification=DriftClassification.FIXED_REGRESSION,
                pr_status="passed",
                base_status="failed",
                duration_delta_ms=-80.0,
                explanation="Failed on base, passing on PR",
            ),
            TestDriftItem(
                testcase_id="tc_def_drift",
                testcase_name="Changed Step Test",
                classification=DriftClassification.STABLE_PASS,
                pr_status="passed",
                base_status="passed",
                test_definition_drift=True,
                explanation="Passed with locators modified",
            ),
        ],
    )
    analytics.save_drift_result(drift_result)

    # Call endpoint
    res = api_client.get("/api/ci/runs/ci_drift_run_1/drift")
    assert res.status_code == 200
    data = res.json()

    assert data["run_id"] == "ci_drift_run_1"
    assert data["total_items"] == 4

    grouped = data["grouped"]
    assert len(grouped["new_regressions"]) == 1
    assert grouped["new_regressions"][0]["testcase_id"] == "tc_broken_reg"

    assert len(grouped["pre_existing_failures"]) == 1
    assert grouped["pre_existing_failures"][0]["testcase_id"] == "tc_pre_existing"

    assert len(grouped["fixed_regressions"]) == 1
    assert grouped["fixed_regressions"][0]["testcase_id"] == "tc_fixed"

    assert len(grouped["definition_drift"]) == 1
    assert grouped["definition_drift"][0]["testcase_id"] == "tc_def_drift"


def test_api_ci_visual_diff_evidence(api_client: TestClient, test_db_path: Path):
    """Subphase 8.4.3: Validate visual diff side-by-side evidence endpoint."""
    from tracecase.ci.drift.analytics import DriftAnalytics

    run = {
        "run_id": "ci_vis_run",
        "project_id": "default_project",
        "commit_hash": "4444dddd",
        "base_ref": "origin/main",
        "branch": "feat/ui",
        "exit_code": 1,
        "gate_result": {"passed": False, "policy_name": "standard", "summary": "Failed"},
        "test_results": [
            {
                "testcase_id": "tc_ui_button",
                "name": "Submit Button Test",
                "status": "failed",
                "duration_ms": 720.0,
                "error_message": "Timeout 5000ms waiting for locator('#submit-btn')",
                "failed_step": {"order": 3, "action": "click", "selector": "#submit-btn"},
            }
        ],
    }
    save_ci_run(run, db_path=test_db_path)

    analytics = DriftAnalytics(db_path=test_db_path)
    drift_result = DriftAnalysisResult(
        run_id="ci_vis_run",
        items=[
            TestDriftItem(
                testcase_id="tc_ui_button",
                testcase_name="Submit Button Test",
                classification=DriftClassification.NEW_REGRESSION,
                pr_status="failed",
                base_status="passed",
                base_duration_ms=450.0,
                pr_duration_ms=720.0,
                duration_delta_ms=270.0,
                test_definition_drift=True,
                explanation="New regression introduced by button selector change",
            )
        ],
    )
    analytics.save_drift_result(drift_result)

    # Call endpoint
    res = api_client.get("/api/ci/runs/ci_vis_run/visual-diff/tc_ui_button")
    assert res.status_code == 200
    data = res.json()

    assert data["testcase_id"] == "tc_ui_button"
    assert data["testcase_name"] == "Submit Button Test"
    assert data["classification"] == "new_regression"
    assert data["test_definition_drift"] is True
    assert data["duration_delta_ms"] == 270.0

    # Verify side-by-side payloads
    pr_ev = data["pr_evidence"]
    assert pr_ev["status"] == "failed"
    assert pr_ev["duration_ms"] == 720.0
    assert "Timeout 5000ms" in pr_ev["error_message"]

    base_ev = data["base_evidence"]
    assert base_ev["status"] == "passed"
    assert base_ev["duration_ms"] == 450.0


def test_api_ci_historical_analytics(api_client: TestClient, test_db_path: Path):
    """Subphase 8.4.4: Validate historical CI analytics and flakiness leaderboards."""
    from tracecase.ci.drift.analytics import DriftAnalytics

    # Seed 3 runs on different branches
    runs = [
        {
            "run_id": f"run_hist_{i}",
            "project_id": "default_project",
            "commit_hash": f"sha_{i}",
            "branch": "main" if i % 2 == 0 else "feat/payments",
            "exit_code": 0 if i == 0 else 1,
            "duration_seconds": 10.0 + i * 5,
            "gate_result": {"passed": i == 0, "policy_name": "standard", "summary": "test"},
            "drift_summary": {"new_regressions_count": 0 if i == 0 else 1, "pre_existing_failures_count": 1},
        }
        for i in range(3)
    ]
    for r in runs:
        save_ci_run(r, db_path=test_db_path)

    # Seed flaky records
    analytics = DriftAnalytics(db_path=test_db_path)
    res_flaky = DriftAnalysisResult(
        run_id="run_hist_1",
        items=[
            TestDriftItem(
                testcase_id="tc_flake_master",
                testcase_name="Flaky Modal Test",
                classification=DriftClassification.NEWLY_FLAKY,
                pr_status="flaky",
                base_status="passed",
            )
        ],
    )
    analytics.save_drift_result(res_flaky)

    # Call analytics endpoint
    res = api_client.get("/api/ci/analytics?days=30")
    assert res.status_code == 200
    data = res.json()

    overview = data["overview"]
    assert overview["total_runs"] == 3
    assert overview["passed_runs"] == 1
    assert overview["failed_runs"] == 2
    assert overview["pass_rate_pct"] == 33.3
    assert overview["total_new_regressions"] == 2

    # Verify daily trends & branch breakdown
    assert len(data["runs_by_day"]) >= 1
    assert len(data["branch_breakdown"]) >= 2
    branches = {b["branch_name"] for b in data["branch_breakdown"]}
    assert "main" in branches
    assert "feat/payments" in branches

    # Verify flaky leaderboard
    assert len(data["top_flaky_tests"]) >= 1
    assert data["top_flaky_tests"][0]["testcase_id"] == "tc_flake_master"
    assert data["top_flaky_tests"][0]["flaky_occurrences"] >= 1


def test_cirunner_automatic_sqlite_persistence(tmp_path: Path):
    """End-to-End: CIRunner automatically persists run records and drift into SQLite."""
    import subprocess
    repo = tmp_path / "repo_ci_db"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)

    file_a = repo / "app.py"
    file_a.write_text("print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo), check=True)

    db_path = tmp_path / "ci_runner_auto.db"
    config = CIRunnerConfig(
        repo_path=str(repo),
        base_ref="HEAD",
        policy="standard",
    )

    runner = CIRunner(config=config, db_path=db_path)
    import asyncio
    run_res = asyncio.run(runner.run())

    assert run_res.exit_code == 0
    assert run_res.gate_result.passed is True

    # Verify automatically persisted in SQLite
    saved = get_ci_run_by_id(run_res.run_id, db_path=db_path)
    assert saved is not None
    assert saved["id"] == run_res.run_id
    assert saved["status"] == "PASSED"
    assert saved["gate_passed"] == 1
    assert saved["policy_name"] == "standard"
