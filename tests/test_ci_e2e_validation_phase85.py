"""Comprehensive validation and end-to-end integration tests for Phase 8.5:
Production Hardening & CI Validation.

Validates:
1. Subphase 8.5.1: Hosted CI Ingestion Engine, token authentication, and CLI upload.
2. Subphase 8.5.2: Complete 5-scenario regression validation (New, Pre-existing, Fixed, Newly Flaky, Incompatible/Missing Baseline).
3. Subphase 8.5.3: Visual evidence security, path traversal prevention, project isolation, and status differentiation.
4. Subphase 8.5.4: SQLite WAL concurrency, write contention safety, and reliability.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from tracecase.ci.config import CIRunnerConfig
from tracecase.ci.drift.classifier import RegressionDriftClassifier
from tracecase.ci.drift.models import DriftClassification, DriftAnalysisResult, TestDriftItem
from tracecase.ci.gate import QualityGateEvaluator, QualityGatePolicy
from tracecase.ci.models import CIExitCode, CIRunResult
from tracecase.ci.policy import STANDARD_POLICY, STRICT_POLICY
from tracecase.ci.runner import CIRunner
from tracecase.cli import app
from tracecase.ui.db import (
    get_ci_drift_for_run,
    get_ci_run_by_id,
    get_ci_runs,
    get_connection,
    init_studio_db,
    save_ci_run,
)
from tracecase.ui.server import create_app


@pytest.fixture
def phase85_db_path(tmp_path: Path) -> Path:
    """Fixture providing an isolated studio SQLite db path."""
    db_file = tmp_path / "studio_phase85.db"
    init_studio_db(db_file)
    return db_file


@pytest.fixture
def client(phase85_db_path: Path, monkeypatch) -> TestClient:
    """FastAPI TestClient with monkeypatched database."""
    from tracecase.ui import db
    monkeypatch.setattr(db, "DEFAULT_STUDIO_DB_PATH", phase85_db_path)
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# 8.5.1 Hosted CI Ingestion Engine Tests
# ---------------------------------------------------------------------------

def test_hosted_ci_manifest_ingestion(client: TestClient, phase85_db_path: Path):
    """Subphase 8.5.1: Ingest complete CI manifest from hosted CI runner into Studio."""
    manifest_payload = {
        "manifest": {
            "schema_version": "1.1.0",
            "generator": "Tracecase CI Execution Engine & Quality Gate",
            "run_id": "ci_hosted_run_999",
            "project_id": "proj_hosted",
            "commit": "fedcba9876",
            "branch": "feat/hosted-ci",
            "base_ref": "origin/main",
            "duration_seconds": 16.4,
            "exit_code": 1,
            "gate": {
                "status": "FAILED",
                "passed": False,
                "policy": "standard",
                "summary": "1 new regression introduced by PR",
                "metrics": {
                    "completed_runs": 8,
                    "passed_count": 7,
                    "failed_count": 1,
                    "surface_coverage_pct": 100.0,
                },
            },
            "drift": {
                "baseline_found": True,
                "baseline_commit": "0123456789",
                "new_regressions_count": 1,
                "pre_existing_failures_count": 0,
                "fixed_regressions_count": 1,
                "newly_flaky_count": 0,
                "items": [
                    {
                        "testcase_id": "tc_hosted_reg",
                        "testcase_name": "Hosted Regression Test",
                        "classification": "new_regression",
                        "pr_status": "failed",
                        "base_status": "passed",
                        "duration_delta_ms": 320.0,
                        "explanation": "Passed on base commit, failed on PR",
                    },
                    {
                        "testcase_id": "tc_hosted_fix",
                        "testcase_name": "Hosted Fixed Test",
                        "classification": "fixed_regression",
                        "pr_status": "passed",
                        "base_status": "failed",
                        "duration_delta_ms": -50.0,
                        "explanation": "Failed on base commit, resolved on PR",
                    },
                ],
            },
            "tests": [
                {
                    "testcase_id": "tc_hosted_reg",
                    "name": "Hosted Regression Test",
                    "status": "failed",
                    "duration_ms": 950.0,
                    "error_message": "AssertionError: expected 200 got 500",
                }
            ],
        }
    }

    # Post manifest to ingestion endpoint
    resp = client.post("/api/ci/ingest", json=manifest_payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "ingested"
    assert res_data["run_id"] == "ci_hosted_run_999"
    assert res_data["gate_status"] == "FAILED"
    assert res_data["drift_items_count"] == 2

    # Verify run record in Studio database
    saved_run = get_ci_run_by_id("ci_hosted_run_999", db_path=phase85_db_path)
    assert saved_run is not None
    assert saved_run["commit_hash"] == "fedcba9876"
    assert saved_run["status"] == "FAILED"
    assert saved_run["new_regressions_count"] == 1
    assert saved_run["fixed_regressions_count"] == 1

    # Verify drift records in Studio database
    drift_items = get_ci_drift_for_run("ci_hosted_run_999", db_path=phase85_db_path)
    assert len(drift_items) == 2
    classifications = {d["classification"] for d in drift_items}
    assert "new_regression" in classifications
    assert "fixed_regression" in classifications


def test_hosted_ci_ingestion_token_auth(client: TestClient, phase85_db_path: Path, monkeypatch):
    """Subphase 8.5.1: Validate ingestion token authentication when configured in settings."""
    from tracecase.ui.db import update_settings

    # Configure a secret CI ingestion token in settings
    update_settings({"ci_api_token": "super_secret_token_123"}, db_path=phase85_db_path)

    payload = {
        "manifest": {
            "run_id": "ci_auth_test_run",
            "commit": "abcdef12",
            "gate": {"passed": True, "status": "PASSED"},
        }
    }

    # 1. Reject without token
    resp_no_token = client.post("/api/ci/ingest", json=payload)
    assert resp_no_token.status_code == 401

    # 2. Reject with invalid token
    resp_bad_token = client.post(
        "/api/ci/ingest",
        json=payload,
        headers={"Authorization": "Bearer wrong_token"},
    )
    assert resp_bad_token.status_code == 401

    # 3. Accept with valid Bearer token
    resp_good_bearer = client.post(
        "/api/ci/ingest",
        json=payload,
        headers={"Authorization": "Bearer super_secret_token_123"},
    )
    assert resp_good_bearer.status_code == 200

    # 4. Accept with valid X-Tracecase-Token header
    payload["manifest"]["run_id"] = "ci_auth_test_run_2"
    resp_good_header = client.post(
        "/api/ci/ingest",
        json=payload,
        headers={"X-Tracecase-Token": "super_secret_token_123"},
    )
    assert resp_good_header.status_code == 200


def test_cli_ci_upload_command(tmp_path: Path, monkeypatch):
    """Subphase 8.5.1: CLI tracecase ci-upload command reads manifest and posts to server."""
    manifest_file = tmp_path / "test-manifest.json"
    manifest_file.write_text(
        json.dumps({
            "schema_version": "1.1.0",
            "run_id": "ci_cli_uploaded_run",
            "commit": "1234abcd",
            "gate": {"passed": True, "status": "PASSED"},
        }),
        encoding="utf-8",
    )

    # Mock urllib.request.urlopen
    class MockResponse:
        def read(self):
            return json.dumps({"status": "ingested", "run_id": "ci_cli_uploaded_run", "gate_status": "PASSED"}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=15: MockResponse())

    runner = CliRunner()
    res = runner.invoke(app, [
        "ci-upload",
        str(manifest_file),
        "--url", "https://studio.example.com",
        "--token", "secret_tok",
    ])
    assert res.exit_code == 0
    assert "Ingested run ci_cli_uploaded_run into Studio" in res.output


# ---------------------------------------------------------------------------
# 8.5.2 Complete 5-Scenario Regression Validation
# ---------------------------------------------------------------------------

def test_regression_scenarios_comprehensive():
    """Subphase 8.5.2: Rigorously validate all 5 regression scenarios and edge classifications."""
    from tracecase.ci.baseline.models import BaselineTestOutcome

    # Scenario 1: New Regression (Passed on base, failed on PR)
    b_pass = BaselineTestOutcome(testcase_id="tc_1", testcase_name="T1", status="passed")
    c1, expl1, _ = RegressionDriftClassifier.classify(pr_status="failed", base_outcome=b_pass)
    assert c1 == DriftClassification.NEW_REGRESSION
    assert "New regression introduced" in expl1

    # Scenario 2: Pre-Existing Failure (Failed on base, failed on PR)
    b_fail = BaselineTestOutcome(testcase_id="tc_2", testcase_name="T2", status="failed")
    c2, expl2, _ = RegressionDriftClassifier.classify(pr_status="failed", base_outcome=b_fail)
    assert c2 == DriftClassification.PRE_EXISTING_FAILURE
    assert "Pre-existing failure" in expl2

    # Scenario 3: Fixed Regression (Failed on base, passed on PR)
    c3, expl3, _ = RegressionDriftClassifier.classify(pr_status="passed", base_outcome=b_fail)
    assert c3 == DriftClassification.FIXED_REGRESSION
    assert "Fixed regression" in expl3

    # Scenario 4: Partial Recovery vs Newly Flaky
    # 4a: Failed on base, Flaky on PR -> Partial recovery (not fully fixed!)
    c4a, expl4a, _ = RegressionDriftClassifier.classify(pr_status="flaky", base_outcome=b_fail)
    assert c4a == DriftClassification.PARTIAL_RECOVERY
    assert "Partially recovered" in expl4a

    # 4b: Passed on base, Flaky on PR -> Newly Flaky
    c4b, expl4b, _ = RegressionDriftClassifier.classify(pr_status="flaky", base_outcome=b_pass)
    assert c4b == DriftClassification.NEWLY_FLAKY
    assert "Newly unstable" in expl4b

    # Scenario 5: Missing / Incompatible Baseline
    # 5a: Missing baseline, Failed on PR -> Unknown Baseline Failure (never assume pass!)
    c5a, expl5a, _ = RegressionDriftClassifier.classify(pr_status="failed", base_outcome=None)
    assert c5a == DriftClassification.UNKNOWN_BASELINE_FAILURE
    assert "no baseline record available" in expl5a

    # 5b: Base Infrastructure Error, Passed on PR -> Unknown baseline (not a false fixed regression!)
    b_infra = BaselineTestOutcome(testcase_id="tc_3", testcase_name="T3", status="error")
    c5b, expl5b, _ = RegressionDriftClassifier.classify(pr_status="passed", base_outcome=b_infra)
    assert c5b == DriftClassification.NEW_TEST_PASS
    assert "baseline test outcome is unknown" in expl5b


# ---------------------------------------------------------------------------
# 8.5.3 Evidence Access & Security Validation
# ---------------------------------------------------------------------------

def test_visual_evidence_security_and_traversal_protection(client: TestClient, phase85_db_path: Path):
    """Subphase 8.5.3: Verify visual diff endpoint prevents path traversal and verifies project ownership."""
    # Seed run in project 'finance_core'
    run = {
        "run_id": "ci_sec_run_1",
        "project_id": "finance_core",
        "commit_hash": "sec12345",
        "gate_result": {"passed": True},
        "test_results": [
            {
                "testcase_id": "tc_traversal",
                "name": "Traversal Test",
                "status": "passed",
                "screenshot_path": "../../../../../etc/passwd",
            }
        ],
    }
    save_ci_run(run, db_path=phase85_db_path)

    # 1. Attempt path traversal in screenshot path -> sanitized
    res = client.get("/api/ci/runs/ci_sec_run_1/visual-diff/tc_traversal")
    assert res.status_code == 200
    data = res.json()
    assert data["pr_evidence"]["screenshot_path"] is None  # Path traversal rejected
    assert data["pr_evidence"]["has_screenshot"] is False
    assert data["visual_diff_status"] == "unavailable"

    # 2. Project ownership validation -> mismatch returns 403 Forbidden
    res_forbidden = client.get(
        "/api/ci/runs/ci_sec_run_1/visual-diff/tc_traversal?project_id=wrong_project"
    )
    assert res_forbidden.status_code == 403
    assert "Run does not belong to requested project" in res_forbidden.json()["detail"]


# ---------------------------------------------------------------------------
# 8.5.4 SQLite Concurrency & Reliability
# ---------------------------------------------------------------------------

def test_sqlite_concurrent_ci_writes(phase85_db_path: Path):
    """Subphase 8.5.4: Verify concurrent CI run persistence under simulated parallel writers."""
    import concurrent.futures

    def writer(run_idx: int):
        run = {
            "run_id": f"conc_run_{run_idx}",
            "project_id": "default_project",
            "commit_hash": f"sha_{run_idx:04d}",
            "duration_seconds": 5.0,
            "gate_result": {"passed": True, "policy_name": "standard"},
            "drift_summary": {"new_regressions_count": 0},
        }
        save_ci_run(run, db_path=phase85_db_path)
        return run_idx

    # 15 concurrent threads writing runs
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(writer, i) for i in range(15)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 15
    stored_runs = get_ci_runs(db_path=phase85_db_path, limit=50)
    assert len(stored_runs) == 15
