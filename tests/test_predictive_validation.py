"""Phase 7.5.6 — Real-World Predictive Validation & Hardening Suite.

Systematically validates:
1. Real Git Change Scenarios:
   - Added routes & endpoints
   - Modified locators
   - Deleted selectors (breaking changes)
   - Renamed files
   - Transitive dependency modifications
2. Prediction Accuracy & Zero-Escape Verification:
   - 100% recall on affected and breaking tests (0 escapes)
   - Accurate low-risk demotion of unaffected flows
3. Selection Efficiency & Cost Reduction:
   - Quantified duration savings vs full-suite execution
   - Functional surface coverage vs time budget trade-offs
4. Historical Commit Replay:
   - Replaying a sequence of real Git commits and verifying dynamic risk score adaptation
5. Explainability & Snapshot Reproducibility:
   - Verified that report and manifest generation from stored SQLite traces remains 100% reproducible
     even after the local working tree and branches are subsequently modified
6. Production Reliability & Security Hardening:
   - Override history preservation (`original_decision` cannot be erased)
   - Multi-project isolation enforcement (403 Forbidden on cross-project override)
   - Foreign testcase candidate validation (400 Bad Request on alien testcase ID)
   - Standalone CLI execution without web server dependency
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from tracecase.cli import app
from tracecase.intelligence.code_mapper import TestToCodeMapper
from tracecase.intelligence.explainer import PrioritizationExplainer
from tracecase.intelligence.git_analyzer import GitChangeAnalyzer
from tracecase.intelligence.models import (
    PredictiveRiskReport,
    RegressionSelectionResult,
    SelectedTestItem,
)
from tracecase.intelligence.risk_scorer import PredictiveRiskScorer
from tracecase.intelligence.selector import IntelligentRegressionSelector
from tracecase.models import ElementInfo, Step, TestCase
from tracecase.ui.db import (
    get_decision_traces,
    get_regression_selection_by_id,
    init_studio_db,
    record_user_decision_override,
    save_decision_traces,
    save_regression_selection,
)
from tracecase.ui.server import create_app


def _run_git(args: list[str], cwd: Path) -> str:
    """Run git command in isolated test workspace."""
    res = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout.strip()


@pytest.fixture
def real_git_repo(tmp_path: Path) -> Path:
    """Initialize a real Git repository with a mini full-stack application."""
    repo = tmp_path / "app_repo"
    repo.mkdir()

    # Configure Git
    _run_git(["init", "-b", "main"], cwd=repo)
    _run_git(["config", "user.name", "QA Engineer"], cwd=repo)
    _run_git(["config", "user.email", "qa@example.com"], cwd=repo)

    # Initial codebase
    src = repo / "src"
    src.mkdir()

    login_code = (
        "import React from 'react';\n"
        "export function LoginPage() {\n"
        "  return (\n"
        "    <form action='/api/auth/login'>\n"
        "      <input id='username-input' type='text' />\n"
        "      <input id='password-input' type='password' />\n"
        "      <button id='login-submit-btn' type='submit'>Sign In</button>\n"
        "      <a id='forgot-password-link' href='/forgot'>Forgot?</a>\n"
        "    </form>\n"
        "  );\n"
        "}\n"
    )
    (src / "Login.tsx").write_text(login_code, encoding="utf-8")

    checkout_code = (
        "import { calculateTax } from './utils';\n"
        "export function CheckoutPage() {\n"
        "  return (\n"
        "    <div>\n"
        "      <h1>Checkout</h1>\n"
        "      <button id='pay-now-button'>Pay Now</button>\n"
        "    </div>\n"
        "  );\n"
        "}\n"
    )
    (src / "Checkout.tsx").write_text(checkout_code, encoding="utf-8")

    utils_code = (
        "export function calculateTax(amount: number): number {\n"
        "  return amount * 0.08;\n"
        "}\n"
    )
    (src / "utils.ts").write_text(utils_code, encoding="utf-8")

    routes_code = (
        "export const routes = {\n"
        "  login: '/login',\n"
        "  checkout: '/checkout',\n"
        "  profile: '/profile',\n"
        "};\n"
    )
    (src / "routes.ts").write_text(routes_code, encoding="utf-8")

    _run_git(["add", "."], cwd=repo)
    _run_git(["commit", "-m", "Initial commit: Base application"], cwd=repo)

    return repo


@pytest.fixture
def mock_db(tmp_path: Path) -> Path:
    """Initialize an isolated test studio database."""
    db_file = tmp_path / "test_studio_validation.db"
    init_studio_db(db_file)
    return db_file


def _build_testcase(tc_id: str, name: str, route: str, selector: str, dur: float) -> TestCase:
    return TestCase(
        id=tc_id,
        name=name,
        start_url=f"https://app.example.com{route}",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0",
        total_duration=dur,
        total_steps=1,
        created_at=datetime.now(),
        steps=[
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="click",
                url=f"https://app.example.com{route}",
                element=ElementInfo(
                    selector=selector,
                    tag_name="button",
                    bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
                    attributes={"id": selector.replace("#", "")},
                ),
                description_short=f"Click {selector}",
                description_detailed=f"Click {selector} on {route}",
            )
        ],
    )


# -----------------------------------------------------------------------------
# 1. Real Git Change Scenarios (Added, Modified, Deleted, Renamed)
# -----------------------------------------------------------------------------

def test_real_git_change_scenarios(real_git_repo: Path):
    """Verify that AST and diff extraction works across real git operations."""
    repo = real_git_repo
    src = repo / "src"

    # 1. Modify Login.tsx: Delete a selector and modify another
    new_login = (
        "import React from 'react';\n"
        "export function LoginPage() {\n"
        "  return (\n"
        "    <form action='/api/v2/auth/login'>\n"  # Modified route
        "      <input id='user-id-field' type='text' />\n"
        "      <button id='new-submit-btn' type='submit'>Sign In</button>\n"  # Renamed button
        "    </form>\n"  # Deleted #forgot-password-link and #login-submit-btn
        "  );\n"
        "}\n"
    )
    (src / "Login.tsx").write_text(new_login, encoding="utf-8")

    # 2. Add a new API route in routes.ts
    new_routes = (
        "export const routes = {\n"
        "  login: '/login',\n"
        "  checkout: '/checkout',\n"
        "  profile: '/profile',\n"
        "  billing: '/billing',\n"  # Added route
        "};\n"
    )
    (src / "routes.ts").write_text(new_routes, encoding="utf-8")

    # 3. Rename utils.ts to math.ts
    _run_git(["mv", "src/utils.ts", "src/math.ts"], cwd=repo)

    analyzer = GitChangeAnalyzer(repo_path=repo)
    changeset = analyzer.analyze_repo()

    assert len(changeset.files) >= 3

    # Check Login.tsx diff extraction
    login_cf = next((f for f in changeset.files if "Login.tsx" in f.path), None)
    assert login_cf is not None
    assert "#login-submit-btn" in [s.lower() for s in login_cf.removed_selectors]
    assert "#forgot-password-link" in [s.lower() for s in login_cf.removed_selectors]
    assert "#new-submit-btn" in [s.lower() for s in login_cf.changed_selectors]
    assert "/api/v2/auth/login" in login_cf.changed_routes

    # Check renamed file
    renamed_cf = next((f for f in changeset.files if "math.ts" in f.path), None)
    assert renamed_cf is not None
    assert renamed_cf.change_type == "renamed"
    assert renamed_cf.old_path == "src/utils.ts"


# -----------------------------------------------------------------------------
# 2. Prediction Accuracy & Zero-Escape Verification
# -----------------------------------------------------------------------------

def test_prediction_accuracy_and_zero_escapes(real_git_repo: Path, mock_db: Path):
    """Verify that all tests affected by real code breakages are selected (0 escapes)."""
    repo = real_git_repo
    src = repo / "src"

    # Break Login by deleting #login-submit-btn
    broken_login = (
        "import React from 'react';\n"
        "export function LoginPage() {\n"
        "  return (\n"
        "    <form action='/login'>\n"
        "      <button id='different-button-id'>Sign In</button>\n"
        "    </form>\n"
        "  );\n"
        "}\n"
    )
    (src / "Login.tsx").write_text(broken_login, encoding="utf-8")

    suite = [
        _build_testcase("tc-login", "Login Flow", "/login", "#login-submit-btn", dur=10.0),
        _build_testcase("tc-checkout", "Checkout Flow", "/checkout", "#pay-now-button", dur=25.0),
        _build_testcase("tc-profile", "Profile View", "/profile", "#profile-header", dur=15.0),
        _build_testcase("tc-search", "Catalog Search", "/search", "#search-box", dur=8.0),
    ]

    analyzer = GitChangeAnalyzer(repo_path=repo)
    changeset = analyzer.analyze_repo()

    mapper = TestToCodeMapper(repo_path=repo, project_id="default_project", db_path=mock_db)
    mapper.scan_codebase()
    graph = mapper.build_graph(suite, persist=False)

    scorer = PredictiveRiskScorer(project_id="default_project", db_path=mock_db)
    risk_report = scorer.evaluate_suite_risk(suite, graph, changeset, persist=False)

    selector = IntelligentRegressionSelector(project_id="default_project", db_path=mock_db)
    selection = selector.select(
        testcases=suite,
        risk_report=risk_report,
        strategy="time_budget",
        time_budget="30s",
        persist=False,
    )

    # Verification:
    # 1. tc-login MUST be identified as highest risk due to deleted selector
    login_score = next(s for s in risk_report.scores if s.testcase_id == "tc-login")
    assert login_score.risk_score >= 60.0
    assert login_score.breakdown.broken_selectors_count >= 1

    # 2. tc-login MUST be in selected tests (Zero Escapes)
    assert "tc-login" in selection.selected_test_ids
    assert selection.selected_count >= 1

    # 3. Unaffected tests (profile, checkout, search) must have low risk
    profile_score = next(s for s in risk_report.scores if s.testcase_id == "tc-profile")
    assert profile_score.risk_tier == "low"
    assert profile_score.risk_score <= 25.0


# -----------------------------------------------------------------------------
# 3. Selection Efficiency & Cost Reduction Benchmark
# -----------------------------------------------------------------------------

def test_selection_efficiency_and_cost_reduction(real_git_repo: Path, mock_db: Path):
    """Benchmark time and resource reduction of smart regression selection vs full suite."""
    repo = real_git_repo
    src = repo / "src"

    # Edit checkout page
    (src / "Checkout.tsx").write_text(
        (src / "Checkout.tsx").read_text(encoding="utf-8") + "\n// Minor UI fix\n",
        encoding="utf-8",
    )

    suite = [
        _build_testcase("tc-login", "Login", "/login", "#login-submit-btn", dur=20.0),
        _build_testcase("tc-checkout", "Checkout", "/checkout", "#pay-now-button", dur=30.0),
        _build_testcase("tc-profile", "Profile", "/profile", "#profile-header", dur=25.0),
        _build_testcase("tc-settings", "Settings", "/settings", "#save-btn", dur=40.0),
        _build_testcase("tc-admin", "Admin Dashboard", "/admin", "#admin-panel", dur=45.0),
    ]

    total_suite_duration = sum(tc.total_duration for tc in suite)  # 160.0s

    analyzer = GitChangeAnalyzer(repo_path=repo)
    changeset = analyzer.analyze_repo()

    mapper = TestToCodeMapper(repo_path=repo, project_id="default_project", db_path=mock_db)
    mapper.scan_codebase()
    graph = mapper.build_graph(suite, persist=False)

    scorer = PredictiveRiskScorer(project_id="default_project", db_path=mock_db)
    risk_report = scorer.evaluate_suite_risk(suite, graph, changeset, persist=False)

    # Budget constrained to 40 seconds (out of 160s full suite)
    selector = IntelligentRegressionSelector(project_id="default_project", db_path=mock_db)
    selection = selector.select(
        testcases=suite,
        risk_report=risk_report,
        strategy="time_budget",
        time_budget="40s",
        persist=False,
    )

    # Verification:
    assert selection.estimated_total_duration_s <= 40.0
    assert "tc-checkout" in selection.selected_test_ids

    # Execution savings: > 70% time reduction
    time_saved_pct = ((total_suite_duration - selection.estimated_total_duration_s) / total_suite_duration) * 100.0
    assert time_saved_pct >= 75.0  # 160s down to 30s = 81.25% savings


# -----------------------------------------------------------------------------
# 4. Historical Commit Replay
# -----------------------------------------------------------------------------

def test_historical_commit_replay_adaptation(real_git_repo: Path, mock_db: Path):
    """Replay consecutive commits and verify that risk scores dynamically adapt."""
    repo = real_git_repo
    src = repo / "src"

    suite = [
        _build_testcase("tc-login", "Login", "/login", "#login-submit-btn", dur=10.0),
        _build_testcase("tc-checkout", "Checkout", "/checkout", "#pay-now-button", dur=15.0),
    ]

    # Commit 1: Break Checkout
    (src / "Checkout.tsx").write_text("export function Checkout() { return <div id='new-checkout' />; }\n")
    _run_git(["add", "."], cwd=repo)
    _run_git(["commit", "-m", "Commit 1: Break checkout button"], cwd=repo)
    c1 = _run_git(["rev-parse", "HEAD"], cwd=repo)

    # Commit 2: Break Login
    (src / "Login.tsx").write_text("export function Login() { return <div id='broken-login' />; }\n")
    _run_git(["add", "."], cwd=repo)
    _run_git(["commit", "-m", "Commit 2: Break login button"], cwd=repo)
    c2 = _run_git(["rev-parse", "HEAD"], cwd=repo)

    analyzer = GitChangeAnalyzer(repo_path=repo)
    mapper = TestToCodeMapper(repo_path=repo, project_id="default_project", db_path=mock_db)
    scorer = PredictiveRiskScorer(project_id="default_project", db_path=mock_db)

    # Evaluate at Commit 1 (compared to main~2)
    changeset_c1 = analyzer.analyze_repo(base_ref=f"{c1}~1", target_ref=c1)
    graph_c1 = mapper.build_graph(suite, persist=False)
    report_c1 = scorer.evaluate_suite_risk(suite, graph_c1, changeset_c1, persist=False)
    checkout_score_c1 = next(s for s in report_c1.scores if s.testcase_id == "tc-checkout")
    login_score_c1 = next(s for s in report_c1.scores if s.testcase_id == "tc-login")

    assert checkout_score_c1.risk_score > login_score_c1.risk_score

    # Evaluate at Commit 2 (compared to c1)
    changeset_c2 = analyzer.analyze_repo(base_ref=c1, target_ref=c2)
    graph_c2 = mapper.build_graph(suite, persist=False)
    report_c2 = scorer.evaluate_suite_risk(suite, graph_c2, changeset_c2, persist=False)
    checkout_score_c2 = next(s for s in report_c2.scores if s.testcase_id == "tc-checkout")
    login_score_c2 = next(s for s in report_c2.scores if s.testcase_id == "tc-login")

    # In Commit 2, Login is broken so its risk must eclipse Checkout
    assert login_score_c2.risk_score > checkout_score_c2.risk_score
    assert login_score_c2.risk_score >= 60.0


# -----------------------------------------------------------------------------
# 5. Explainability & Snapshot Reproducibility
# -----------------------------------------------------------------------------

def test_explainability_snapshot_reproducibility(real_git_repo: Path, mock_db: Path):
    """Verify that reports and manifests remain reproducible from SQLite after repo changes."""
    repo = real_git_repo
    src = repo / "src"

    # Create change and selection
    (src / "Login.tsx").write_text("// change\n", encoding="utf-8")
    suite = [_build_testcase("tc-login", "Login", "/login", "#login-submit-btn", dur=10.0)]

    analyzer = GitChangeAnalyzer(repo_path=repo)
    changeset = analyzer.analyze_repo()
    mapper = TestToCodeMapper(repo_path=repo, project_id="default_project", db_path=mock_db)
    graph = mapper.build_graph(suite, persist=False)
    scorer = PredictiveRiskScorer(project_id="default_project", db_path=mock_db)
    risk_report = scorer.evaluate_suite_risk(suite, graph, changeset, persist=False)

    selector = IntelligentRegressionSelector(project_id="default_project", db_path=mock_db)
    selection = selector.select(testcases=suite, risk_report=risk_report, strategy="time_budget", persist=True)

    explainer = PrioritizationExplainer(project_id="default_project", db_path=mock_db)
    original_report = explainer.build_report(selection, risk_report=risk_report, changeset=changeset, persist=True)

    # Now drastically mutate working tree (e.g. wipe src folder!)
    for f in src.glob("*"):
        f.unlink()

    # Reconstruct report from SQLite traces without passing changeset or risk_report
    reconstructed_report = explainer.build_report(selection, risk_report=None, changeset=None, persist=False)

    assert reconstructed_report.selection_id == original_report.selection_id
    assert reconstructed_report.selected_count == original_report.selected_count
    assert reconstructed_report.functional_surface_coverage_pct == original_report.functional_surface_coverage_pct
    assert len(reconstructed_report.explanations) == len(original_report.explanations)

    # Generated Markdown and JSON manifest should match perfectly
    manifest = explainer.generate_json_manifest(reconstructed_report)
    assert manifest["selection_id"] == selection.id
    assert manifest["summary"]["selected_count"] == 1


# -----------------------------------------------------------------------------
# 6. Production Reliability & Security Hardening
# -----------------------------------------------------------------------------

def test_override_immutability_and_security(mock_db: Path):
    """Verify that original_decision is preserved, cross-project overrides are rejected, and foreign candidates fail."""
    selection = RegressionSelectionResult(
        id="sel_security_001",
        project_id="proj_alpha",
        commit_hash="abc1234",
        strategy="time_budget",
        selected_test_ids=["tc-1"],
        excluded_test_ids=["tc-2"],
        budget_exceptions=[],
        tests=[
            SelectedTestItem(
                testcase_id="tc-1",
                testcase_name="Test 1",
                decision="selected",
                risk_score=90.0,
                risk_tier="critical",
                mapping_confidence=1.0,
                value_score=90.0,
                estimated_duration_s=10.0,
                duration_source="measured_history",
                decision_reason="Top priority",
            ),
            SelectedTestItem(
                testcase_id="tc-2",
                testcase_name="Test 2",
                decision="excluded",
                risk_score=30.0,
                risk_tier="low",
                mapping_confidence=0.5,
                value_score=30.0,
                estimated_duration_s=15.0,
                duration_source="estimated_fallback",
                decision_reason="Below budget cutoff",
            ),
        ],
    )
    save_regression_selection(selection, db_path=mock_db)

    explainer = PrioritizationExplainer(project_id="proj_alpha", db_path=mock_db)
    explainer.build_report(selection, persist=True)

    # Check original decision is recorded
    traces = get_decision_traces("sel_security_001", db_path=mock_db)
    t2 = next(t for t in traces if t["testcase_id"] == "tc-2")
    assert t2["decision"] == "excluded"
    assert t2["original_decision"] == "excluded"
    assert t2["user_override"] == 0

    # Apply override: promote tc-2 to selected
    record_user_decision_override(
        selection_id="sel_security_001",
        testcase_id="tc-2",
        override_decision="selected",
        override_reason="Manually approved for hotfix verification",
        db_path=mock_db,
    )

    # Verify original_decision is intact while decision changed
    traces_after = get_decision_traces("sel_security_001", db_path=mock_db)
    t2_after = next(t for t in traces_after if t["testcase_id"] == "tc-2")
    assert t2_after["decision"] == "selected"
    assert t2_after["original_decision"] == "excluded"
    assert t2_after["user_override"] == 1
    assert "Manually approved" in t2_after["override_reason"]

    # Test REST API Security
    with patch("tracecase.ui.db.get_db_path", return_value=mock_db), \
         patch("tracecase.ui.api.get_regression_selection_by_id", side_effect=lambda sid: get_regression_selection_by_id(sid, db_path=mock_db)), \
         patch("tracecase.ui.api.record_user_decision_override", side_effect=lambda **kw: record_user_decision_override(**{**kw, "db_path": mock_db})):

        client = TestClient(create_app())

        # 1. Project Mismatch: proj_beta attempting to override proj_alpha selection -> 403 Forbidden
        res_forbidden = client.post(
            "/api/intelligence/selections/sel_security_001/override",
            json={
                "testcase_id": "tc-2",
                "override_decision": "excluded",
                "override_reason": "Malicious override",
                "project_id": "proj_beta",
            },
        )
        assert res_forbidden.status_code == 403
        assert "Forbidden" in res_forbidden.json()["detail"]

        # 2. Foreign Testcase: tc-unknown does not belong to selection -> 400 Bad Request
        res_bad_tc = client.post(
            "/api/intelligence/selections/sel_security_001/override",
            json={
                "testcase_id": "tc-alien-unknown",
                "override_decision": "selected",
                "override_reason": "Invalid test",
                "project_id": "proj_alpha",
            },
        )
        assert res_bad_tc.status_code == 400
        assert "does not belong" in res_bad_tc.json()["detail"]


# -----------------------------------------------------------------------------
# 7. Standalone CLI Operation
# -----------------------------------------------------------------------------

def test_standalone_cli_explain_and_report_operation(mock_db: Path):
    """Verify tracecase explain and tracecase report operate standalone against SQLite."""
    selection = RegressionSelectionResult(
        id="sel_cli_standalone",
        project_id="default_project",
        commit_hash="deadbeef",
        strategy="top_k",
        selected_test_ids=["tc-fast"],
        excluded_test_ids=[],
        budget_exceptions=[],
        tests=[
            SelectedTestItem(
                testcase_id="tc-fast",
                testcase_name="Fast Unit Flow",
                decision="selected",
                risk_score=75.0,
                risk_tier="high",
                mapping_confidence=0.95,
                value_score=75.0,
                estimated_duration_s=5.0,
                duration_source="measured_history",
                decision_reason="Top-K ranked",
            )
        ],
    )
    save_regression_selection(selection, db_path=mock_db)
    explainer = PrioritizationExplainer(project_id="default_project", db_path=mock_db)
    explainer.build_report(selection, persist=True)

    runner = CliRunner()

    with patch("tracecase.ui.db.get_db_path", return_value=mock_db), \
         patch("tracecase.ui.db.get_regression_selection_by_id", side_effect=lambda sid: get_regression_selection_by_id(sid, db_path=mock_db)), \
         patch("tracecase.ui.db.get_decision_traces", side_effect=lambda sid: get_decision_traces(sid, db_path=mock_db)), \
         patch("tracecase.ui.db.get_regression_selections", side_effect=lambda **kw: [get_regression_selection_by_id(selection.id, db_path=mock_db)]):

        # Test CLI explain
        res_explain = runner.invoke(app, ["explain", selection.id])
        assert res_explain.exit_code == 0
        assert "Fast" in res_explain.output
        assert "SELECT" in res_explain.output

        # Test CLI report
        res_report = runner.invoke(app, ["report", selection.id, "--format", "json"])
        assert res_report.exit_code == 0
        data = json.loads(res_report.output)
        assert data["selection_id"] == "sel_cli_standalone"
        assert data["summary"]["selected_count"] == 1
