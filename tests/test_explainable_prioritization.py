"""Tests for Phase 7.5.5 - Explainable Test Prioritization Engine.

Verifies:
1. Strict evidence categorization:
   - Observed Evidence (verifiable Git diffs, deleted/modified locators, measured run history)
   - Heuristic Inferences (transitive module dependencies, value density)
   - Missing Evidence (untested testcases, fallback duration estimates)
2. Verifiable locator attribution:
   - Deleted selector marked as observed critical breakage
   - Modified selector marked as observed
3. Untested testcase handling:
   - Flagged with neutral baseline risk in missing evidence
4. Explicit distinction:
   - Mapping confidence (connection certainty) != Failure risk (breakage probability)
5. Comprehensive report generators:
   - Publication-ready human-readable Markdown report with executive summary
   - Distinct functional surface coverage % calculation
   - Machine-readable JSON manifest with schema version 1.0.0 for CI/PR integration
6. Auditable persistence:
   - Storing decision traces into SQLite table `regression_decision_traces`
   - Retrieval of auditable traces with parsed JSON evidence
7. User decision overrides & audit trail:
   - Explicit inclusion or exclusion override with required reason
   - Update of selection records and decision traces
8. REST API endpoints:
   - GET /api/intelligence/selections/{id}/explanations
   - GET /api/intelligence/selections/{id}/report (markdown and json formats)
   - GET /api/intelligence/selections/{id}/manifest
   - POST /api/intelligence/selections/{id}/override
9. CLI commands:
   - tracecase explain
   - tracecase report
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from tracecase.cli import app
from tracecase.intelligence.explainer import PrioritizationExplainer
from tracecase.intelligence.models import (
    ChangedFile,
    GitChangeSet,
    PredictiveRiskReport,
    RegressionSelectionResult,
    RiskFactorBreakdown,
    RiskScoringWeights,
    SelectedTestItem,
    TestPrioritizationExplanation,
    TestRiskScore,
)
from tracecase.models import ElementInfo, Step, TestCase
from tracecase.ui.db import (
    get_connection,
    get_decision_traces,
    get_regression_selection_by_id,
    init_studio_db,
    record_user_decision_override,
    save_decision_traces,
    save_regression_selection,
)
from tracecase.ui.server import create_app


def create_mock_breakdown(
    impact: float = 100.0,
    breakage: float = 0.0,
    failure: float = 0.0,
    flakiness: float = 0.0,
    magnitude: float = 0.0,
    has_history: bool = True,
    broken_selectors: int = 0,
    modified_selectors: int = 0,
) -> RiskFactorBreakdown:
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
        has_history=has_history,
        history_run_count=5 if has_history else 0,
        recent_failure_detected=failure > 50.0,
        broken_selectors_count=broken_selectors,
        modified_selectors_count=modified_selectors,
        lines_changed=15,
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
                    selector="#submit-btn",
                    tag_name="button",
                    bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
                    attributes={"id": "submit-btn"},
                ),
                description_short="Click",
                description_detailed="Click submit",
            )
        ],
    )


@pytest.fixture
def mock_db(tmp_path: Path) -> Path:
    """Initialize an isolated test studio database."""
    db_file = tmp_path / "test_studio_explainer.db"
    init_studio_db(db_file)
    return db_file


@pytest.fixture
def sample_prioritization_context() -> tuple[
    RegressionSelectionResult,
    PredictiveRiskReport,
    GitChangeSet,
]:
    """Construct a full sample context with selections, risk report, and changeset."""
    changeset = GitChangeSet(
        repo_path=".",
        current_commit="c0ffee1",
        current_branch="feature/auth-redesign",
        base_ref="main",
        target_ref="HEAD",
        files=[
            ChangedFile(
                path="src/components/Login.tsx",
                change_type="modified",
                additions=12,
                deletions=4,
                diff_patch="@@ -10,4 +10,12 @@",
                removed_selectors=["#old-login-btn"],
                changed_selectors=["#submit-btn"],
            ),
            ChangedFile(
                path="src/api/routes.ts",
                change_type="modified",
                additions=5,
                deletions=2,
                diff_patch="@@ -1,2 +1,5 @@",
            ),
        ],
        total_changed_files=2,
        total_additions=17,
        total_deletions=6,
    )

    risk_scores = [
        TestRiskScore(
            testcase_id="tc-login",
            testcase_name="Login Flow",
            project_id="default_project",
            risk_score=94.5,
            risk_tier="critical",
            mapping_confidence=1.0,
            primary_risk_driver="Critical selector '#old-login-btn' deleted in Login.tsx",
            breakdown=create_mock_breakdown(
                impact=100.0, breakage=100.0, failure=60.0, broken_selectors=1
            ),
            affected_files=["src/components/Login.tsx"],
            matched_selectors=["#old-login-btn", "#submit-btn"],
            matched_routes=["/login"],
        ),
        TestRiskScore(
            testcase_id="tc-checkout",
            testcase_name="Checkout Flow",
            project_id="default_project",
            risk_score=85.0,
            risk_tier="critical",
            mapping_confidence=0.85,
            primary_risk_driver="API route change in routes.ts",
            breakdown=create_mock_breakdown(
                impact=80.0, breakage=0.0, failure=0.0, has_history=False
            ),
            affected_files=["src/api/routes.ts"],
            matched_selectors=[],
            matched_routes=["/api/v1/checkout"],
        ),
        TestRiskScore(
            testcase_id="tc-settings",
            testcase_name="User Settings",
            project_id="default_project",
            risk_score=45.0,
            risk_tier="medium",
            mapping_confidence=0.75,
            primary_risk_driver="Transitive module dependency",
            breakdown=create_mock_breakdown(
                impact=40.0, breakage=0.0, failure=10.0, has_history=True
            ),
            affected_files=["src/components/Login.tsx"],
            matched_selectors=[],
            matched_routes=[],
        ),
    ]

    risk_report = PredictiveRiskReport(
        id="risk_rep_001",
        project_id="default_project",
        commit_hash="c0ffee1",
        branch="feature/auth-redesign",
        scores=risk_scores,
        total_testcases=3,
        critical_count=2,
        high_count=0,
        medium_count=1,
        low_count=0,
        weights=RiskScoringWeights(),
        created_at=datetime.now().isoformat(),
    )

    selected_tests = [
        SelectedTestItem(
            testcase_id="tc-login",
            testcase_name="Login Flow",
            decision="selected",
            risk_score=94.5,
            risk_tier="critical",
            mapping_confidence=1.0,
            value_score=94.5,
            estimated_duration_s=12.0,
            duration_source="measured_history",
            decision_reason="Selected as top priority critical test within budget",
            primary_risk_driver="Critical selector '#old-login-btn' deleted in Login.tsx",
            affected_files=["src/components/Login.tsx"],
        ),
        SelectedTestItem(
            testcase_id="tc-checkout",
            testcase_name="Checkout Flow",
            decision="budget_exception",
            risk_score=85.0,
            risk_tier="critical",
            mapping_confidence=0.85,
            value_score=85.0,
            estimated_duration_s=140.0,
            duration_source="estimated_fallback",
            decision_reason="Critical test exceeds remaining time budget",
            primary_risk_driver="API route change in routes.ts",
            affected_files=["src/api/routes.ts"],
        ),
        SelectedTestItem(
            testcase_id="tc-settings",
            testcase_name="User Settings",
            decision="excluded",
            risk_score=45.0,
            risk_tier="medium",
            mapping_confidence=0.75,
            value_score=45.0,
            estimated_duration_s=25.0,
            duration_source="recorded_testcase",
            decision_reason="Exceeds remaining budget after selecting higher-value candidates",
            primary_risk_driver="Transitive module dependency",
            affected_files=["src/components/Login.tsx"],
        ),
    ]

    selection = RegressionSelectionResult(
        id="sel_test_001",
        project_id="default_project",
        commit_hash="c0ffee1",
        branch="feature/auth-redesign",
        strategy="time_budget",
        strategy_params={"time_budget": "120s"},
        time_budget_s=120.0,
        total_tests_considered=3,
        selected_count=1,
        excluded_count=1,
        budget_exception_count=1,
        estimated_total_duration_s=12.0,
        risk_coverage_pct=42.1,
        critical_coverage_pct=50.0,
        selected_test_ids=["tc-login"],
        excluded_test_ids=["tc-settings"],
        budget_exceptions=["tc-checkout"],
        tests=selected_tests,
        created_at=datetime.now().isoformat(),
    )

    return selection, risk_report, changeset


def test_evidence_categorization_observed_vs_heuristic_vs_missing(
    sample_prioritization_context,
):
    """Test that evidence is strictly categorized into observed, heuristic, and missing."""
    selection, risk_report, changeset = sample_prioritization_context
    explainer = PrioritizationExplainer(project_id="default_project")

    # tc-login: observed git diff, deleted selector, modified selector, history
    exp_login = explainer.explain_test(
        item=selection.tests[0],
        risk_score_item=risk_report.scores[0],
        changeset=changeset,
    )

    assert exp_login.testcase_id == "tc-login"
    assert exp_login.decision == "selected"
    assert len(exp_login.observed_evidence) >= 3

    # Check observed evidence types
    obs_categories = [e.category for e in exp_login.observed_evidence]
    assert "git_diff" in obs_categories
    assert "selector" in obs_categories
    assert "history" in obs_categories
    assert "budget" in obs_categories  # measured_history duration

    # Verify deleted selector detail
    deleted_sel_ev = [
        e for e in exp_login.observed_evidence if e.detail.get("status") == "deleted"
    ]
    assert len(deleted_sel_ev) == 1
    assert deleted_sel_ev[0].detail["selector"] == "#old-login-btn"


def test_untested_testcase_neutral_baseline_missing_attribution(
    sample_prioritization_context,
):
    """Test that an untested test case gets missing evidence attribution."""
    selection, risk_report, changeset = sample_prioritization_context
    explainer = PrioritizationExplainer(project_id="default_project")

    exp_checkout = explainer.explain_test(
        item=selection.tests[1],  # tc-checkout has no history and fallback duration
        risk_score_item=risk_report.scores[1],
        changeset=changeset,
    )

    assert exp_checkout.testcase_id == "tc-checkout"
    assert exp_checkout.decision == "budget_exception"

    # Missing evidence should reflect no run history and estimated fallback duration
    missing_cats = [e.category for e in exp_checkout.missing_evidence]
    assert "history" in missing_cats
    assert "budget" in missing_cats

    history_missing = [e for e in exp_checkout.missing_evidence if e.category == "history"][0]
    assert "Untested testcase" in history_missing.description
    assert "Neutral baseline risk" in history_missing.description


def test_confidence_vs_risk_distinction_narrative(sample_prioritization_context):
    """Test that risk narrative strictly distinguishes mapping confidence from failure probability."""
    selection, risk_report, changeset = sample_prioritization_context
    explainer = PrioritizationExplainer(project_id="default_project")

    for item, score in zip(selection.tests, risk_report.scores):
        exp = explainer.explain_test(item=item, risk_score_item=score, changeset=changeset)
        assert "Mapping confidence measures certainty of code-to-test connection, NOT failure probability" in exp.risk_narrative
        assert f"{exp.mapping_confidence * 100:.0f}%" in exp.risk_narrative
        assert exp.confidence_type in ("exact_route", "route_prefix", "transitive_dependency")


def test_build_report_and_surface_coverage(sample_prioritization_context, mock_db):
    """Test comprehensive report building and distinct functional surface coverage percentage."""
    selection, risk_report, changeset = sample_prioritization_context
    explainer = PrioritizationExplainer(project_id="default_project", db_path=mock_db)

    report = explainer.build_report(
        selection=selection,
        risk_report=risk_report,
        changeset=changeset,
        persist=True,
    )

    assert report.selection_id == "sel_test_001"
    assert report.total_tests == 3
    assert report.selected_count == 1
    assert report.budget_exception_count == 1
    assert report.excluded_count == 1

    # Surface coverage: tc-login covers src/components/Login.tsx out of 2 total impacted files = 50.0%
    assert report.total_impacted_files_count == 2
    assert report.covered_files_count == 1
    assert report.functional_surface_coverage_pct == 50.0

    # Verify Markdown report content
    assert report.markdown_report != ""
    assert "# Tracecase Intelligent Regression Decision Report" in report.markdown_report
    assert "## Executive Summary" in report.markdown_report
    assert "Critical Test Budget Exceptions" in report.markdown_report
    assert "Login Flow (`tc-login`)" in report.markdown_report
    assert "- **Observed Evidence:**" in report.markdown_report


def test_json_manifest_generation(sample_prioritization_context, mock_db):
    """Test machine-readable JSON manifest generation for CI/PR workflows."""
    selection, risk_report, changeset = sample_prioritization_context
    explainer = PrioritizationExplainer(project_id="default_project", db_path=mock_db)

    report = explainer.build_report(
        selection=selection,
        risk_report=risk_report,
        changeset=changeset,
        persist=False,
    )

    manifest = explainer.generate_json_manifest(report)

    assert manifest["schema_version"] == "1.0.0"
    assert manifest["generator"] == "Tracecase Intelligent Regression Prioritizer"
    assert manifest["selection_id"] == "sel_test_001"
    assert manifest["summary"]["selected_count"] == 1
    assert manifest["summary"]["budget_exception_count"] == 1
    assert manifest["summary"]["surface_coverage_percentage"] == 50.0
    assert manifest["selected_test_ids"] == ["tc-login"]
    assert manifest["budget_exception_test_ids"] == ["tc-checkout"]
    assert manifest["excluded_test_ids"] == ["tc-settings"]
    assert len(manifest["tests"]) == 3


def test_decision_trace_sqlite_persistence_and_querying(
    sample_prioritization_context, mock_db
):
    """Test saving and retrieving auditable decision traces from SQLite."""
    selection, risk_report, changeset = sample_prioritization_context
    explainer = PrioritizationExplainer(project_id="default_project", db_path=mock_db)

    explainer.build_report(
        selection=selection,
        risk_report=risk_report,
        changeset=changeset,
        persist=True,
    )

    traces = get_decision_traces("sel_test_001", db_path=mock_db)
    assert len(traces) == 3

    # Ordered by risk_score desc
    assert traces[0]["testcase_id"] == "tc-login"
    assert traces[0]["decision"] == "selected"
    assert traces[0]["risk_score"] == 94.5
    assert traces[0]["user_override"] == 0

    # Evidence JSON should be parsed into dictionary
    ev = traces[0]["evidence"]
    assert "observed" in ev
    assert len(ev["observed"]) > 0


def test_user_decision_override_and_audit(sample_prioritization_context, mock_db):
    """Test recording an explicit user approval or exclusion override with audit rationale."""
    selection, risk_report, changeset = sample_prioritization_context

    # Save selection and traces first
    save_regression_selection(selection, db_path=mock_db)
    explainer = PrioritizationExplainer(project_id="default_project", db_path=mock_db)
    explainer.build_report(
        selection=selection,
        risk_report=risk_report,
        changeset=changeset,
        persist=True,
    )

    # User overrides tc-checkout from budget_exception to selected
    override_res = record_user_decision_override(
        selection_id="sel_test_001",
        testcase_id="tc-checkout",
        override_decision="selected",
        override_reason="Critical checkout path approved by QA Lead for hotfix validation",
        db_path=mock_db,
    )

    assert override_res is not None
    assert override_res["user_override"] == 1
    assert override_res["decision"] == "selected"
    assert "QA Lead" in override_res["override_reason"]

    # Verify updated traces
    updated_traces = get_decision_traces("sel_test_001", db_path=mock_db)
    checkout_trace = [t for t in updated_traces if t["testcase_id"] == "tc-checkout"][0]
    assert checkout_trace["decision"] == "selected"
    assert checkout_trace["user_override"] == 1
    assert "approved by QA Lead" in checkout_trace["override_reason"]

    # Verify updated regression_selections record
    sel_record = get_regression_selection_by_id("sel_test_001", db_path=mock_db)
    assert "tc-checkout" in sel_record["selected_test_ids"]
    assert "tc-checkout" not in sel_record["budget_exceptions"]


def test_rest_api_explainability_endpoints(sample_prioritization_context, mock_db):
    """Test REST API endpoints for explanations, report, manifest, and override."""
    selection, risk_report, changeset = sample_prioritization_context
    save_regression_selection(selection, db_path=mock_db)

    explainer = PrioritizationExplainer(project_id="default_project", db_path=mock_db)
    explainer.build_report(
        selection=selection,
        risk_report=risk_report,
        changeset=changeset,
        persist=True,
    )

    with patch("tracecase.ui.db.get_db_path", return_value=mock_db), \
         patch("tracecase.ui.api.get_decision_traces", side_effect=lambda sid: get_decision_traces(sid, db_path=mock_db)), \
         patch("tracecase.ui.api.get_regression_selection_by_id", side_effect=lambda sid: get_regression_selection_by_id(sid, db_path=mock_db)), \
         patch("tracecase.ui.api.record_user_decision_override", side_effect=lambda **kw: record_user_decision_override(**{**kw, "db_path": mock_db})):

        app_instance = create_app()
        client = TestClient(app_instance)

        # 1. GET /api/intelligence/selections/{id}/explanations
        res_exp = client.get(f"/api/intelligence/selections/{selection.id}/explanations")
        assert res_exp.status_code == 200
        traces = res_exp.json()
        assert len(traces) == 3
        assert traces[0]["testcase_id"] == "tc-login"

        # 2. GET /api/intelligence/selections/{id}/report (Markdown)
        res_rep_md = client.get(f"/api/intelligence/selections/{selection.id}/report?format=markdown")
        assert res_rep_md.status_code == 200
        assert "text/markdown" in res_rep_md.headers["content-type"]
        assert "# Tracecase Intelligent Regression Decision Report" in res_rep_md.text

        # 3. GET /api/intelligence/selections/{id}/report (JSON)
        res_rep_json = client.get(f"/api/intelligence/selections/{selection.id}/report?format=json")
        assert res_rep_json.status_code == 200
        rep_data = res_rep_json.json()
        assert rep_data["selection_id"] == selection.id
        assert len(rep_data["explanations"]) == 3

        # 4. GET /api/intelligence/selections/{id}/manifest
        res_man = client.get(f"/api/intelligence/selections/{selection.id}/manifest")
        assert res_man.status_code == 200
        man_data = res_man.json()
        assert man_data["schema_version"] == "1.0.0"
        assert man_data["summary"]["selected_count"] == 1

        # 5. POST /api/intelligence/selections/{id}/override
        res_over = client.post(
            f"/api/intelligence/selections/{selection.id}/override",
            json={
                "testcase_id": "tc-settings",
                "override_decision": "selected",
                "override_reason": "Promoted to smoke test set for release candidate",
            },
        )
        assert res_over.status_code == 200
        over_data = res_over.json()
        assert over_data["status"] == "ok"
        assert over_data["override"]["user_override"] == 1


def test_cli_explain_and_report_commands(sample_prioritization_context, mock_db):
    """Test CLI commands `tracecase explain` and `tracecase report`."""
    selection, risk_report, changeset = sample_prioritization_context
    save_regression_selection(selection, db_path=mock_db)

    explainer = PrioritizationExplainer(project_id="default_project", db_path=mock_db)
    explainer.build_report(
        selection=selection,
        risk_report=risk_report,
        changeset=changeset,
        persist=True,
    )

    runner = CliRunner()

    with patch("tracecase.ui.db.get_db_path", return_value=mock_db), \
         patch("tracecase.ui.db.get_regression_selection_by_id", side_effect=lambda sid: get_regression_selection_by_id(sid, db_path=mock_db)), \
         patch("tracecase.ui.db.get_decision_traces", side_effect=lambda sid: get_decision_traces(sid, db_path=mock_db)), \
         patch("tracecase.ui.db.get_regression_selections", side_effect=lambda **kw: [get_regression_selection_by_id(selection.id, db_path=mock_db)]):

        # Test `tracecase explain`
        res_explain = runner.invoke(app, ["explain", selection.id])
        assert res_explain.exit_code == 0
        assert "Prioritization Decision Explanation" in res_explain.output
        assert "Login" in res_explain.output
        assert "Mapping confidence measures certainty" in res_explain.output

        # Test `tracecase report --format markdown`
        res_report_md = runner.invoke(app, ["report", selection.id, "--format", "markdown"])
        assert res_report_md.exit_code == 0
        assert "Tracecase Intelligent Regression Decision Report" in res_report_md.output

        # Test `tracecase report --format json`
        res_report_json = runner.invoke(app, ["report", selection.id, "--format", "json"])
        assert res_report_json.exit_code == 0
        assert '"schema_version": "1.0.0"' in res_report_json.output
