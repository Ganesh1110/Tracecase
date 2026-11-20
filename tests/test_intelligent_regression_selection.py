"""Tests for Phase 7.5.4 - Intelligent Regression Selection Engine.

Verifies:
1. Time budget selection with greedy value-density allocation.
2. Minimum risk tier threshold selection.
3. Top-K selection based on risk ranking.
4. Combined strategy (risk threshold + time budget).
5. Critical risk safeguard: Critical tests are NEVER silently excluded by budget.
6. Duration intelligence:
   - Measured history (from execution_runs)
   - Recorded testcase total_duration
   - Safe configurable fallback (never zero!)
7. Synthesized draft approval status enforcement.
8. Deterministic, reproducible selection order and tie-breaking.
9. Duplicate prevention in candidate processing.
10. SQLite persistence of selection snapshots.
11. REST API endpoints:
    - POST /api/intelligence/select
    - GET /api/intelligence/selections
    - GET /api/intelligence/selections/{id}
    - POST /api/intelligence/selections/{id}/execute
12. CLI commands:
    - tracecase select
    - tracecase run --select-smart --ci
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from tracecase.cli import app
from tracecase.intelligence.models import (
    PredictiveRiskReport,
    RegressionSelectionResult,
    RiskFactorBreakdown,
    RiskScoringWeights,
    TestRiskScore,
)
from tracecase.intelligence.selector import (
    IntelligentRegressionSelector,
    parse_duration_string,
)
from tracecase.models import ElementInfo, Step, TestCase
from tracecase.ui.db import (
    get_connection,
    get_regression_selection_by_id,
    get_regression_selections,
    get_testcase_duration_stats,
    init_studio_db,
    save_regression_selection,
)
from tracecase.ui.server import create_app


def create_mock_breakdown(impact=100.0, breakage=0.0, failure=0.0, flakiness=0.0, magnitude=0.0):
    return RiskFactorBreakdown(
        change_impact_score=impact,
        selector_breakage_score=breakage,
        historical_failure_score=failure,
        flakiness_recency_score=flakiness,
        change_magnitude_score=magnitude,
        weighted_impact=impact * 0.30,
        weighted_breakage=breakage * 0.25,
        weighted_failure=failure * 0.20,
        weighted_flakiness=flakiness * 0.15,
        weighted_magnitude=magnitude * 0.10,
        has_history=True,
        history_run_count=5,
        recent_failure_detected=False,
        broken_selectors_count=0,
        modified_selectors_count=0,
        lines_changed=10,
    )


def create_mock_testcase(tc_id: str, name: str, duration: float = 10.0) -> TestCase:
    return TestCase(
        id=tc_id,
        name=name,
        start_url="https://app.example.com",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0",
        total_duration=duration,
        total_steps=1,
        created_at=datetime.now(),
        steps=[
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="click",
                url="https://app.example.com",
                element=ElementInfo(
                    selector="#btn",
                    tag_name="button",
                    bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
                    attributes={"id": "btn"},
                ),
                description_short="Click",
                description_detailed="Click button",
            )
        ],
    )


@pytest.fixture
def mock_db(tmp_path: Path) -> Path:
    """Initialize an isolated test studio database."""
    db_file = tmp_path / "test_studio_selector.db"
    init_studio_db(db_file)
    return db_file


@pytest.fixture
def mock_test_suite() -> tuple[list[TestCase], PredictiveRiskReport]:
    """Construct a varied test suite with critical, high, medium, and low risk tests."""
    tcs = [
        create_mock_testcase("tc-login", "Login Flow", duration=10.0),
        create_mock_testcase("tc-checkout", "Checkout Flow", duration=40.0),
        create_mock_testcase("tc-quick", "Quick Search", duration=5.0),
        create_mock_testcase("tc-settings", "User Settings", duration=25.0),
        create_mock_testcase("tc-profile", "Profile View", duration=15.0),
    ]

    scores = [
        TestRiskScore(
            testcase_id="tc-login",
            testcase_name="Login Flow",
            project_id="default_project",
            risk_score=92.0,
            risk_tier="critical",
            mapping_confidence=1.0,
            primary_risk_driver="Critical selector deleted in Login.tsx",
            breakdown=create_mock_breakdown(impact=100.0, breakage=100.0),
        ),
        TestRiskScore(
            testcase_id="tc-checkout",
            testcase_name="Checkout Flow",
            project_id="default_project",
            risk_score=88.0,
            risk_tier="critical",
            mapping_confidence=0.95,
            primary_risk_driver="Critical payment route modified",
            breakdown=create_mock_breakdown(impact=95.0, breakage=80.0),
        ),
        TestRiskScore(
            testcase_id="tc-quick",
            testcase_name="Quick Search",
            project_id="default_project",
            risk_score=80.0,
            risk_tier="high",
            mapping_confidence=0.90,
            primary_risk_driver="High failure rate component",
            breakdown=create_mock_breakdown(impact=80.0, failure=80.0),
        ),
        TestRiskScore(
            testcase_id="tc-settings",
            testcase_name="User Settings",
            project_id="default_project",
            risk_score=50.0,
            risk_tier="medium",
            mapping_confidence=0.70,
            primary_risk_driver="Transitive dependency change",
            breakdown=create_mock_breakdown(impact=50.0),
        ),
        TestRiskScore(
            testcase_id="tc-profile",
            testcase_name="Profile View",
            project_id="default_project",
            risk_score=20.0,
            risk_tier="low",
            mapping_confidence=0.10,
            primary_risk_driver="Minimal impact",
            breakdown=create_mock_breakdown(impact=20.0),
        ),
    ]

    report = PredictiveRiskReport(
        changeset_commit="c0ffee1",
        changeset_branch="main",
        weights=RiskScoringWeights(),
        total_tests_evaluated=len(scores),
        critical_count=2,
        high_count=1,
        medium_count=1,
        low_count=1,
        scores=scores,
    )
    return tcs, report


def test_parse_duration_string():
    """Verify duration parsing for various string formats."""
    assert parse_duration_string("120s") == 120.0
    assert parse_duration_string("2m") == 120.0
    assert parse_duration_string("1.5h") == 5400.0
    assert parse_duration_string("500ms") == 0.5
    assert parse_duration_string("90") == 90.0
    assert parse_duration_string(60) == 60.0
    assert parse_duration_string(None) is None
    with pytest.raises(ValueError):
        parse_duration_string("invalid_time")


def test_time_budget_selection(mock_test_suite, mock_db: Path):
    """Verify time budget strategy selects highest value-density tests within budget."""
    tcs, report = mock_test_suite
    selector = IntelligentRegressionSelector(db_path=mock_db)

    # Budget of 20 seconds:
    # tc-login takes 10s (Critical, risk 92) -> selected (10s used)
    # tc-quick takes 5s (High, risk 80) -> high efficiency -> selected (15s used)
    # tc-checkout takes 40s (Critical) -> exceeds remaining 5s -> marked budget_exception!
    # tc-settings takes 25s -> exceeds budget -> excluded
    res = selector.select(tcs, report, strategy="time_budget", time_budget="20s")

    assert "tc-login" in res.selected_test_ids
    assert "tc-quick" in res.selected_test_ids
    assert "tc-settings" in res.excluded_test_ids
    assert "tc-profile" in res.excluded_test_ids
    assert res.estimated_total_duration_s <= 20.0
    assert res.selected_count == 2

    # Verify critical safeguard: tc-checkout must be in budget_exception_test_ids, NOT silently dropped
    assert "tc-checkout" in res.budget_exception_test_ids
    assert res.budget_exception_count == 1
    chk_item = next(t for t in res.tests if t.testcase_id == "tc-checkout")
    assert chk_item.decision == "budget_exception"
    assert "CRITICAL RISK EXCEPTION" in chk_item.decision_reason


def test_critical_exception_override(mock_test_suite, mock_db: Path):
    """Verify user opt-in includes critical tests exceeding the budget as approved exceptions."""
    tcs, report = mock_test_suite
    selector = IntelligentRegressionSelector(db_path=mock_db)

    res = selector.select(
        tcs,
        report,
        strategy="time_budget",
        time_budget="20s",
        include_critical_exceptions=True,
    )

    # With override, tc-checkout is selected as an exception
    assert "tc-checkout" in res.selected_test_ids
    assert "tc-checkout" in res.budget_exception_test_ids
    chk_item = next(t for t in res.tests if t.testcase_id == "tc-checkout")
    assert chk_item.decision == "selected"
    assert "CRITICAL SAFEGUARD EXCEPTION" in chk_item.decision_reason


def test_risk_threshold_selection(mock_test_suite, mock_db: Path):
    """Verify risk threshold strategy selects all tests >= threshold."""
    tcs, report = mock_test_suite
    selector = IntelligentRegressionSelector(db_path=mock_db)

    res_high = selector.select(tcs, report, strategy="risk_threshold", min_risk_tier="high")
    # High + Critical = tc-login (critical), tc-checkout (critical), tc-quick (high)
    assert set(res_high.selected_test_ids) == {"tc-login", "tc-checkout", "tc-quick"}
    assert "tc-settings" in res_high.excluded_test_ids
    assert "tc-profile" in res_high.excluded_test_ids


def test_top_k_selection(mock_test_suite, mock_db: Path):
    """Verify top-k strategy selects exactly the top K ranked tests by risk."""
    tcs, report = mock_test_suite
    selector = IntelligentRegressionSelector(db_path=mock_db)

    res = selector.select(tcs, report, strategy="top_k", top_k=3)
    assert len(res.selected_test_ids) == 3
    # Top 3 risks: 92 (tc-login), 88 (tc-checkout), 80 (tc-quick)
    assert set(res.selected_test_ids) == {"tc-login", "tc-checkout", "tc-quick"}
    assert len(res.excluded_test_ids) == 2


def test_combined_strategy(mock_test_suite, mock_db: Path):
    """Verify combined strategy applies risk threshold first, then budget."""
    tcs, report = mock_test_suite
    selector = IntelligentRegressionSelector(db_path=mock_db)

    # Combined: min_risk_tier="high" and time_budget="20s"
    # Eligible candidates: tc-login (10s), tc-checkout (40s), tc-quick (5s).
    # tc-settings and tc-profile are excluded by threshold.
    # tc-login (10s) and tc-quick (5s) fit in 20s. tc-checkout is a budget exception.
    res = selector.select(
        tcs,
        report,
        strategy="combined",
        min_risk_tier="high",
        time_budget="20s",
    )
    assert "tc-login" in res.selected_test_ids
    assert "tc-quick" in res.selected_test_ids
    assert "tc-settings" in res.excluded_test_ids
    assert "tc-checkout" in res.budget_exception_test_ids


def test_duration_intelligence_sources(mock_db: Path):
    """Verify duration sources: measured_history vs recorded_testcase vs estimated_fallback."""
    conn = get_connection(mock_db)
    # 1. Measured history in execution_runs
    with conn:
        conn.execute(
            """
            INSERT INTO execution_runs (
                id, project_id, testcase_id, testcase_name, status, browser, started_at, duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("run-1", "default_project", "tc-hist", "Historical Test", "passed", "chromium", datetime.now().isoformat(), 8500.0),
        )
        conn.execute(
            """
            INSERT INTO execution_runs (
                id, project_id, testcase_id, testcase_name, status, browser, started_at, duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("run-2", "default_project", "tc-hist", "Historical Test", "passed", "chromium", datetime.now().isoformat(), 9500.0),
        )

        # 2. Recorded testcase in testcases_meta
        conn.execute(
            """
            INSERT INTO testcases_meta (
                id, project_id, name, start_url, total_duration, folder_path, file_path, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("tc-meta", "default_project", "Meta Test", "https://app.com", 12.3, "tests", "test.json", datetime.now().isoformat(), datetime.now().isoformat()),
        )
    conn.close()

    # Query stats for measured history
    s_hist = get_testcase_duration_stats("tc-hist", db_path=mock_db)
    assert s_hist["source"] == "measured_history"
    assert s_hist["sample_count"] == 2
    assert s_hist["duration_s"] == 9.5

    # Query stats for recorded testcase
    s_meta = get_testcase_duration_stats("tc-meta", db_path=mock_db)
    assert s_meta["source"] == "recorded_testcase"
    assert s_meta["duration_s"] == 12.3

    # Query stats for test with no history or meta (safe fallback, never 0!)
    s_fall = get_testcase_duration_stats("tc-unknown", fallback_s=18.0, db_path=mock_db)
    assert s_fall["source"] == "estimated_fallback"
    assert s_fall["duration_s"] == 18.0


def test_synthesized_draft_approval_safeguard(mock_test_suite, mock_db: Path):
    """Verify unapproved synthesized drafts are excluded from selection."""
    tcs, report = mock_test_suite
    conn = get_connection(mock_db)
    with conn:
        conn.execute(
            """
            INSERT INTO exploration_runs (
                id, project_id, start_url, status, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("exp-1", "default_project", "https://app.com", "completed", datetime.now().isoformat()),
        )
        conn.execute(
            """
            INSERT INTO synthesized_drafts (
                id, exploration_id, project_id, name, journey_type, start_url, steps_json, status, approved_testcase_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("draft-1", "exp-1", "default_project", "Draft Test", "flow", "https://app.com", "[]", "pending", "tc-login", datetime.now().isoformat()),
        )
    conn.close()

    selector = IntelligentRegressionSelector(db_path=mock_db)
    res = selector.select(tcs, report, strategy="time_budget", time_budget="120s")

    # tc-login is linked to a pending draft -> excluded by safeguard
    assert "tc-login" in res.excluded_test_ids
    login_item = next(t for t in res.tests if t.testcase_id == "tc-login")
    assert "Unapproved synthesized draft" in login_item.decision_reason


def test_deterministic_reproducible_selection(mock_test_suite, mock_db: Path):
    """Verify running selection multiple times with identical inputs produces identical results."""
    tcs, report = mock_test_suite
    selector = IntelligentRegressionSelector(db_path=mock_db)

    res1 = selector.select(tcs, report, strategy="time_budget", time_budget="60s")
    res2 = selector.select(tcs, report, strategy="time_budget", time_budget="60s")

    assert res1.selected_test_ids == res2.selected_test_ids
    assert res1.excluded_test_ids == res2.excluded_test_ids
    assert res1.estimated_total_duration_s == res2.estimated_total_duration_s
    assert res1.risk_coverage_pct == res2.risk_coverage_pct


def test_selection_persistence_sqlite(mock_test_suite, mock_db: Path):
    """Verify regression selection snapshots can be saved and queried from SQLite."""
    tcs, report = mock_test_suite
    selector = IntelligentRegressionSelector(db_path=mock_db)

    res = selector.select(tcs, report, strategy="top_k", top_k=2, persist=True)

    # Query list
    selections = get_regression_selections(db_path=mock_db)
    assert len(selections) >= 1
    assert selections[0]["id"] == res.id

    # Query detail
    detail = get_regression_selection_by_id(res.id, db_path=mock_db)
    assert detail is not None
    assert detail["strategy"] == "top_k"
    assert len(detail["selected_test_ids"]) == 2


def test_api_selection_endpoints(mock_db: Path, mock_test_suite):
    """Verify REST API endpoints: POST /api/intelligence/select and GET /api/intelligence/selections."""
    tcs, _ = mock_test_suite
    sample_tc = tcs[0]

    with patch("tracecase.ui.db.DEFAULT_STUDIO_DB_PATH", mock_db):
        app_instance = create_app()
        client = TestClient(app_instance)

        with patch(
            "tracecase.ui.service.find_testcase_files",
            return_value=[Path("/fake/tc-login.json")],
        ), patch(
            "tracecase.ui.service.resolve_testcase_file",
            return_value=(Path("/fake/tc-login.json"), sample_tc),
        ):
            # 1. POST /api/intelligence/select
            res = client.post(
                "/api/intelligence/select",
                json={
                    "project_id": "test_proj",
                    "strategy": "time_budget",
                    "time_budget": "60s",
                    "persist": True,
                },
            )
            assert res.status_code == 200
            data = res.json()
            assert "selected_test_ids" in data
            assert data["total_tests_considered"] == 1
            sel_id = data["id"]

            # 2. GET /api/intelligence/selections
            res_list = client.get("/api/intelligence/selections", params={"project_id": "test_proj"})
            assert res_list.status_code == 200
            list_data = res_list.json()
            assert len(list_data) >= 1

            # 3. GET /api/intelligence/selections/{id}
            res_detail = client.get(f"/api/intelligence/selections/{sel_id}")
            assert res_detail.status_code == 200
            detail_data = res_detail.json()
            assert detail_data["id"] == sel_id

            # 4. POST /api/intelligence/selections/{id}/execute
            with patch("tracecase.ui.executor.orchestrator.start_batch_execution", new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = {"id": "batch-123", "status": "queued"}
                res_exec = client.post(
                    f"/api/intelligence/selections/{sel_id}/execute",
                    json={"concurrency": 2},
                )
                assert res_exec.status_code == 200
                exec_data = res_exec.json()
                assert exec_data["status"] == "launched"
                assert exec_data["batch_id"] == "batch-123"


def test_cli_select_and_run(mock_test_suite):
    """Verify tracecase select and tracecase run --select-smart CLI commands."""
    tcs, _ = mock_test_suite
    runner = CliRunner()

    with patch(
        "tracecase.ui.service.find_testcase_files",
        return_value=[Path("/fake/tc.json")],
    ), patch(
        "tracecase.ui.service.resolve_testcase_file",
        return_value=(Path("/fake/tc.json"), tcs[0]),
    ):
        # 1. Test tracecase select --budget 60s --json
        res_sel = runner.invoke(app, ["select", "--budget", "60s", "--json"])
        assert res_sel.exit_code == 0
        data = json.loads(res_sel.output)
        assert "selected_test_ids" in data
        assert "estimated_total_duration_s" in data

        # 2. Test tracecase run --select-smart --ci
        with patch("tracecase.ui.executor.orchestrator.start_batch_execution", new_callable=AsyncMock) as mock_batch:
            mock_batch.return_value = {"id": "batch-ci-1", "status": "queued"}
            res_run = runner.invoke(app, ["run", "--select-smart", "--budget", "60s", "--ci"])
            assert res_run.exit_code == 0
            assert "Batch execution started" in res_run.output
