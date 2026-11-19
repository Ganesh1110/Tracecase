"""Comprehensive tests for Tracecase Phase 3: Dashboard & Project Management."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tracecase.models import TestCase
from tracecase.ui.db import (
    add_testcase_to_suite,
    create_execution_run,
    create_project,
    create_suite,
    delete_project,
    delete_suite,
    get_dashboard_metrics,
    get_project,
    get_suite,
    init_studio_db,
    remove_testcase_from_suite,
    sync_testcase_meta,
    update_execution_run_status,
    update_project,
)
from tracecase.ui.server import create_app

app = create_app()
client = TestClient(app)


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        db_p = Path(f.name)
        init_studio_db(db_p)
        yield db_p


def test_empty_database_behavior(temp_db):
    metrics = get_dashboard_metrics(db_path=temp_db)
    assert metrics["total_projects"] == 1  # default_project auto-initialized
    assert metrics["total_suites"] == 0
    assert metrics["total_executions"] == 0
    assert metrics["passed_executions"] == 0
    assert metrics["failed_executions"] == 0
    assert metrics["success_rate"] == 100.0
    assert metrics["failure_rate"] == 0.0
    assert metrics["avg_duration_sec"] == 0.0
    assert len(metrics["recent_executions"]) == 0
    assert len(metrics["failed_tests"]) == 0
    assert len(metrics["execution_trends"]) == 7


def test_project_crud_and_safety_checks(temp_db):
    # 1. Disallow deleting default_project
    assert not delete_project("default_project", db_path=temp_db)

    # 2. Create Project
    proj = create_project("Commerce App", "Checkout & Cart", db_path=temp_db)
    pid = proj["id"]
    assert proj["name"] == "Commerce App"

    # 3. Read Project
    fetched = get_project(pid, db_path=temp_db)
    assert fetched is not None
    assert fetched["name"] == "Commerce App"

    # 4. Update Project
    updated = update_project(pid, name="Commerce App v2", description="Updated Cart", db_path=temp_db)
    assert updated["name"] == "Commerce App v2"
    assert updated["description"] == "Updated Cart"

    # 5. Attach testcase to project to test deletion protection
    from datetime import datetime
    tc = TestCase(
        id=f"tc_{uuid.uuid4().hex[:8]}",
        name="Cart Flow",
        start_url="https://example.com",
        browser="chromium",
        user_agent="Tracecase Studio",
        viewport={"width": 1280, "height": 720},
        steps=[],
        created_at=datetime.now(),
        total_duration=0.0,
        total_steps=0,
    )
    sync_testcase_meta(tc, Path("/tmp/fake/testcase.json"), project_id=pid, db_path=temp_db)

    # Deleting without force must raise ValueError because project has testcases
    with pytest.raises(ValueError, match="force=true"):
        delete_project(pid, force=False, db_path=temp_db)

    # Deleting with force must succeed
    assert delete_project(pid, force=True, db_path=temp_db) is True
    assert get_project(pid, db_path=temp_db) is None


def test_suite_crud_and_deduplication(temp_db):
    proj = create_project("Suite Workspace", db_path=temp_db)
    pid = proj["id"]

    # 1. Create suite with duplicates in testcase_ids
    suite = create_suite(
        name="Smoke Tests",
        project_id=pid,
        description="Daily smoke suite",
        testcase_ids=["tc_login", "tc_checkout", "tc_login"],
        db_path=temp_db,
    )
    sid = suite["id"]
    # Check deduplication
    assert suite["testcase_ids"] == ["tc_login", "tc_checkout"]
    assert suite["total_cases"] == 2

    # 2. Add testcase to suite (new case)
    updated1 = add_testcase_to_suite(sid, "tc_profile", db_path=temp_db)
    assert "tc_profile" in updated1["testcase_ids"]
    assert updated1["total_cases"] == 3

    # Add duplicate case to suite (should not duplicate)
    updated_dup = add_testcase_to_suite(sid, "tc_login", db_path=temp_db)
    assert updated_dup["testcase_ids"].count("tc_login") == 1

    # 3. Remove testcase from suite
    updated2 = remove_testcase_from_suite(sid, "tc_checkout", db_path=temp_db)
    assert "tc_checkout" not in updated2["testcase_ids"]
    assert updated2["total_cases"] == 2

    # 4. Delete suite
    assert delete_suite(sid, db_path=temp_db)
    assert get_suite(sid, db_path=temp_db) is None


def test_dashboard_calculations_against_known_records(temp_db):
    proj_a = create_project("Project Alpha", db_path=temp_db)
    proj_b = create_project("Project Beta", db_path=temp_db)

    # Register executions in Project Alpha
    e1 = create_execution_run(
        testcase_id="tc_1",
        testcase_name="Login Test",
        project_id=proj_a["id"],
        db_path=temp_db,
    )
    update_execution_run_status(e1["id"], status="passed", duration_ms=4000.0, db_path=temp_db)

    e2 = create_execution_run(
        testcase_id="tc_2",
        testcase_name="Cart Test",
        project_id=proj_a["id"],
        db_path=temp_db,
    )
    update_execution_run_status(
        e2["id"],
        status="failed",
        duration_ms=6000.0,
        error_message="Selector not found",
        db_path=temp_db,
    )

    # Register execution in Project Beta
    e3 = create_execution_run(
        testcase_id="tc_3",
        testcase_name="Payment Test",
        project_id=proj_b["id"],
        db_path=temp_db,
    )
    update_execution_run_status(e3["id"], status="passed", duration_ms=2000.0, db_path=temp_db)

    # 1. Global Metrics (no project filter)
    global_m = get_dashboard_metrics(project_id=None, days=7, db_path=temp_db)
    assert global_m["total_projects"] == 3  # default + alpha + beta
    assert global_m["total_executions"] == 3
    assert global_m["passed_executions"] == 2
    assert global_m["failed_executions"] == 1
    assert global_m["success_rate"] == 66.7
    assert global_m["failure_rate"] == 33.3
    assert global_m["avg_duration_sec"] == 4.0  # (4000 + 6000 + 2000)/3000 = 4.0s
    assert len(global_m["failed_tests"]) == 1
    assert global_m["failed_tests"][0]["error_message"] == "Selector not found"

    # 2. Project-Level Data Isolation (Project Alpha only)
    alpha_m = get_dashboard_metrics(project_id=proj_a["id"], days=7, db_path=temp_db)
    assert alpha_m["total_executions"] == 2
    assert alpha_m["passed_executions"] == 1
    assert alpha_m["failed_executions"] == 1
    assert alpha_m["success_rate"] == 50.0
    assert alpha_m["failure_rate"] == 50.0
    assert alpha_m["avg_duration_sec"] == 5.0  # (4000 + 6000)/2000 = 5.0s

    # 3. Project-Level Data Isolation (Project Beta only)
    beta_m = get_dashboard_metrics(project_id=proj_b["id"], days=7, db_path=temp_db)
    assert beta_m["total_executions"] == 1
    assert beta_m["passed_executions"] == 1
    assert beta_m["failed_executions"] == 0
    assert beta_m["success_rate"] == 100.0
    assert beta_m["failure_rate"] == 0.0
    assert beta_m["avg_duration_sec"] == 2.0


def test_api_project_and_suite_endpoints():
    # 1. Create Project via API
    p_res = client.post("/api/projects", json={
        "name": "Phase 3 API Workspace",
        "description": "API verification workspace"
    })
    assert p_res.status_code == 200
    p_data = p_res.json()
    pid = p_data["id"]

    # 2. Update Project via API
    up_res = client.put(f"/api/projects/{pid}", json={
        "name": "Phase 3 Renamed Workspace",
        "description": "Renamed description"
    })
    assert up_res.status_code == 200
    assert up_res.json()["name"] == "Phase 3 Renamed Workspace"

    # 3. Create Suite via API
    s_res = client.post("/api/suites", json={
        "name": "Phase 3 Regression",
        "project_id": pid,
        "description": "Regression tests",
        "testcase_ids": ["tc_sample_1"]
    })
    assert s_res.status_code == 200
    sid = s_res.json()["id"]

    # 4. Add case to suite via API
    add_c = client.post(f"/api/suites/{sid}/testcases/tc_sample_2")
    assert add_c.status_code == 200
    assert "tc_sample_2" in add_c.json()["testcase_ids"]

    # 5. Remove case from suite via API
    rem_c = client.delete(f"/api/suites/{sid}/testcases/tc_sample_1")
    assert rem_c.status_code == 200
    assert "tc_sample_1" not in rem_c.json()["testcase_ids"]

    # 6. Query Suite Executions via API
    exec_res = client.get(f"/api/suites/{sid}/executions")
    assert exec_res.status_code == 200
    assert isinstance(exec_res.json(), list)

    # 7. Query Metrics with days selector
    m_res = client.get(f"/api/dashboard/metrics?project_id={pid}&days=14")
    assert m_res.status_code == 200
    m_data = m_res.json()
    assert len(m_data["execution_trends"]) == 14

    # 8. Clean up Suite
    del_s = client.delete(f"/api/suites/{sid}")
    assert del_s.status_code == 200

    # 9. Clean up Project
    del_p = client.delete(f"/api/projects/{pid}")
    assert del_p.status_code == 200
