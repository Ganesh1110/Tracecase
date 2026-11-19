"""Tests for Phase 7.5.3 - Predictive Risk Scoring Engine.

Verifies:
1. Signal I: Change Impact score calculation and confidence tracking.
2. Signal B: Selector and route breakage detection (deleted vs modified).
3. Signal F: Historical failure rate calculation with neutral baseline for untested tests.
4. Signal H: Flakiness rate and recent failure penalty calculations.
5. Signal C: Change magnitude scaling based on code lines modified.
6. Multi-factor composite weighted risk calculation and customizable weights.
7. Risk tier classification: Critical (85-100), High (70-84), Medium (40-69), Low (0-39).
8. Strict decoupling between mapping confidence and failure risk.
9. Safety safeguard: Untested tests never receive 0 risk.
10. SQLite persistence of risk score snapshots by git commit hash.
11. REST API endpoints:
    - POST /api/intelligence/risk
    - GET /api/intelligence/risk/snapshots
12. CLI command:
    - tracecase risk
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
from tracecase.intelligence.code_mapper import (
    TestReferenceExtractor,
    TestToCodeGraph,
)
from tracecase.intelligence.models import (
    ChangedFile,
    DiffHunk,
    RiskFactorBreakdown,
    RiskScoringWeights,
    TestCodeMapping,
    TestCoverageProfile,
    TestRiskScore,
)
from tracecase.intelligence.risk_scorer import PredictiveRiskScorer
from tracecase.models import ElementInfo, NetworkRequest, Step, TestCase
from tracecase.ui.db import (
    get_risk_scores_snapshots,
    init_studio_db,
    save_risk_scores_snapshot,
)
from tracecase.ui.server import create_app


@pytest.fixture
def sample_test_case() -> TestCase:
    """Construct a mock TestCase instance with rich step metadata."""
    return TestCase(
        id="tc-login-01",
        name="User Login Flow",
        description="Verifies authentication flow",
        start_url="https://app.example.com/login",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0",
        total_duration=1.5,
        total_steps=2,
        created_at=datetime.now(),
        steps=[
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="input",
                url="https://app.example.com/login",
                element=ElementInfo(
                    selector="#email-input",
                    tag_name="input",
                    bounding_box={"x": 10, "y": 20, "width": 100, "height": 30},
                    attributes={"id": "email-input", "data-testid": "auth-email-field"},
                ),
                input_value="user@example.com",
                description_short="Type email",
                description_detailed="Enter email address into login input field",
            ),
            Step(
                number=2,
                timestamp=datetime.now(),
                action_type="click",
                url="https://app.example.com/login",
                element=ElementInfo(
                    selector="button#submit-btn",
                    tag_name="button",
                    bounding_box={"x": 10, "y": 60, "width": 80, "height": 30},
                    attributes={"id": "submit-btn", "data-testid": "login-button"},
                ),
                description_short="Click submit button",
                description_detailed="Click submit button to submit credentials",
            ),
        ],
    )


@pytest.fixture
def mock_db(tmp_path: Path) -> Path:
    """Initialize an isolated test studio database."""
    db_file = tmp_path / "test_studio.db"
    init_studio_db(db_file)
    return db_file


def test_factor_change_impact():
    """Verify Signal I (Change Impact) calculates correctly based on relation type."""
    scorer = PredictiveRiskScorer()
    mappings = [
        TestCodeMapping(
            id="m-1",
            testcase_id="tc-01",
            testcase_name="Login Test",
            file_path="src/pages/Login.tsx",
            relation_type="exact_route",
            confidence=1.0,
            matched_entity="/login",
        ),
        TestCodeMapping(
            id="m-2",
            testcase_id="tc-02",
            testcase_name="Button Test",
            file_path="src/components/Button.tsx",
            relation_type="exact_selector",
            confidence=0.95,
            matched_entity="#submit-btn",
        ),
        TestCodeMapping(
            id="m-3",
            testcase_id="tc-03",
            testcase_name="Auth API Test",
            file_path="src/api/auth.ts",
            relation_type="api_endpoint",
            confidence=0.90,
            matched_entity="/api/login",
        ),
        TestCodeMapping(
            id="m-4",
            testcase_id="tc-04",
            testcase_name="Helper Test",
            file_path="src/utils/helpers.ts",
            relation_type="dependency_import",
            confidence=0.70,
            matched_entity="helpers",
        ),
    ]
    graph = TestToCodeGraph()
    for m in mappings:
        graph.add_mapping(m)

    # File changed: Login.tsx
    changed = [
        ChangedFile(
            path="src/pages/Login.tsx",
            change_type="modified",
            additions=10,
            deletions=2,
        )
    ]

    # tc-01 should have impact score 100.0, max_conf 1.0
    score, conf, expl = scorer.compute_change_impact("tc-01", graph, changed)
    assert score == 100.0
    assert conf == 1.0
    assert any("Direct route match" in e for e in expl)

    # tc-02 (unrelated file) should have impact score 0.0
    score2, conf2, expl2 = scorer.compute_change_impact("tc-02", graph, changed)
    assert score2 == 0.0
    assert conf2 == 0.0

    # If Button.tsx changes, tc-02 gets 95.0
    changed_btn = [
        ChangedFile(
            path="src/components/Button.tsx",
            change_type="modified",
            additions=5,
            deletions=1,
        )
    ]
    score_btn, conf_btn, _ = scorer.compute_change_impact("tc-02", graph, changed_btn)
    assert score_btn == 95.0
    assert conf_btn == 0.95


def test_factor_selector_breakage():
    """Verify Signal B detects deleted and modified selectors with elevated risk."""
    scorer = PredictiveRiskScorer()
    profile = TestCoverageProfile(
        testcase_id="tc-01",
        testcase_name="Login Test",
        start_url="https://app.example.com/login",
        selectors_used=["button#submit-btn", "[data-testid='login-button']"],
        page_routes=["/login"],
    )

    # 1. Deleted selector in diff
    changed_del = [
        ChangedFile(
            path="src/components/Button.tsx",
            change_type="modified",
            additions=0,
            deletions=10,
            removed_selectors=["button#submit-btn"],
        )
    ]
    score_del, broken_cnt, mod_cnt, expl_del = scorer.compute_selector_breakage(
        profile, changed_del
    )
    assert score_del == 100.0
    assert broken_cnt == 1
    assert mod_cnt == 0
    assert any("CRITICAL: Interacted selector 'button#submit-btn' was deleted" in e for e in expl_del)

    # 2. Modified selector
    changed_mod = [
        ChangedFile(
            path="src/components/Button.tsx",
            change_type="modified",
            additions=5,
            deletions=5,
            changed_selectors=["button#submit-btn"],
        )
    ]
    score_mod, broken_cnt_m, mod_cnt_m, expl_mod = scorer.compute_selector_breakage(
        profile, changed_mod
    )
    assert score_mod == 60.0
    assert broken_cnt_m == 0
    assert mod_cnt_m == 1
    assert any("Selector 'button#submit-btn' was modified" in e for e in expl_mod)

    # 3. No overlap
    changed_none = [
        ChangedFile(
            path="src/pages/Dashboard.tsx",
            change_type="modified",
            additions=5,
            deletions=2,
            changed_selectors=["#sidebar"],
        )
    ]
    score_none, b_c, m_c, _ = scorer.compute_selector_breakage(profile, changed_none)
    assert score_none == 0.0
    assert b_c == 0
    assert m_c == 0


def test_factor_historical_failure_and_untested_baseline(mock_db: Path):
    """Verify Signal F uses SQLite history or neutral 40.0 baseline for untested tests."""
    scorer = PredictiveRiskScorer(db_path=mock_db)

    # Untested test: must yield 40.0 baseline (NOT 0.0 false safety)
    score_untested, has_hist, run_cnt, expl_un = scorer.compute_historical_failure(
        {"total_runs": 0}
    )
    assert score_untested == 40.0
    assert has_hist is False
    assert run_cnt == 0
    assert any("baseline failure risk 40.0 applied" in e for e in expl_un)

    # Test with history: 2 failures out of 10 runs = 20%
    tested_stats = {
        "total_runs": 10,
        "failed_runs": 2,
        "failure_rate": 20.0,
    }
    score_tested, has_h, runs, expl_t = scorer.compute_historical_failure(tested_stats)
    assert score_tested == 20.0
    assert has_h is True
    assert runs == 10
    assert any("20.0%" in e for e in expl_t)


def test_factor_flakiness_and_recency(mock_db: Path):
    """Verify Signal H penalizes recent failure and incorporates flakiness."""
    scorer = PredictiveRiskScorer(db_path=mock_db)

    # 1. Recent failure detected (+30.0 boost)
    mock_recent_fail = {
        "total_runs": 5,
        "flakiness_rate": 25.0,
        "runs": [{"status": "failed"}],
    }
    score, rec_fail, expl = scorer.compute_flakiness_and_recency(mock_recent_fail)
    assert rec_fail is True
    # flakiness_rate (25.0) + 30.0 = 55.0
    assert score == 55.0
    assert any("The most recent execution of this test failed" in e for e in expl)

    # 2. Untested test: baseline 30.0
    score_untested, rec_un, _ = scorer.compute_flakiness_and_recency({"total_runs": 0})
    assert score_untested == 30.0
    assert rec_un is False


def test_factor_change_magnitude():
    """Verify Signal C scales with lines changed in mapped files."""
    scorer = PredictiveRiskScorer()
    mappings = [
        TestCodeMapping(
            id="m-1",
            testcase_id="tc-01",
            testcase_name="Login Test",
            file_path="src/pages/Login.tsx",
            relation_type="exact_route",
            confidence=1.0,
            matched_entity="/login",
        )
    ]
    graph = TestToCodeGraph()
    for m in mappings:
        graph.add_mapping(m)

    # 50 lines changed -> score = 75.0 (50 * 1.5)
    changed_50 = [
        ChangedFile(
            path="src/pages/Login.tsx",
            change_type="modified",
            additions=30,
            deletions=20,
        )
    ]
    score_50, lines_50, _ = scorer.compute_change_magnitude("tc-01", graph, changed_50)
    assert lines_50 == 50
    assert score_50 == 75.0

    # 300 lines changed -> clamped at 100.0
    changed_300 = [
        ChangedFile(
            path="src/pages/Login.tsx",
            change_type="modified",
            additions=200,
            deletions=100,
        )
    ]
    score_300, lines_300, _ = scorer.compute_change_magnitude("tc-01", graph, changed_300)
    assert lines_300 == 300
    assert score_300 == 100.0


def test_composite_scoring_and_weights(sample_test_case: TestCase, mock_db: Path):
    """Verify the weighted multi-factor calculation matches the mathematical model."""
    weights = RiskScoringWeights(
        weight_impact=0.30,
        weight_breakage=0.25,
        weight_failure_rate=0.20,
        weight_flakiness_recency=0.15,
        weight_change_magnitude=0.10,
    )
    scorer = PredictiveRiskScorer(weights=weights, db_path=mock_db)

    mappings = [
        TestCodeMapping(
            id="m-1",
            testcase_id=sample_test_case.id,
            testcase_name=sample_test_case.name,
            file_path="src/pages/Login.tsx",
            relation_type="exact_route",
            confidence=1.0,
            matched_entity="/login",
        )
    ]
    graph = TestToCodeGraph()
    for m in mappings:
        graph.add_mapping(m)
    profile = TestReferenceExtractor.extract_profile(sample_test_case)

    # Mock signals:
    # I = 100.0 (exact route match)
    # B = 100.0 (deleted selector)
    # F = 50.0
    # H = 40.0
    # C = 50 * 1.5 = 75.0
    changed_files = [
        ChangedFile(
            path="src/pages/Login.tsx",
            change_type="modified",
            additions=30,
            deletions=20,
            removed_selectors=["button#submit-btn"],
        )
    ]

    mock_stats = {
        "total_runs": 10,
        "failed_runs": 5,
        "failure_rate": 50.0,
        "flakiness_rate": 40.0,
        "runs": [{"status": "passed"}],
    }
    with patch(
        "tracecase.intelligence.risk_scorer.get_testcase_flakiness_stats",
        return_value=mock_stats,
    ):
        risk_result = scorer.score_test(
            sample_test_case, profile, graph, changed_files
        )

    # Expected: 0.30*100 + 0.25*100 + 0.20*50 + 0.15*40 + 0.10*75
    # = 30 + 25 + 10 + 6 + 7.5 = 78.5
    assert round(risk_result.risk_score, 1) == 78.5
    assert risk_result.risk_tier == "high"
    assert risk_result.breakdown.broken_selectors_count == 1
    assert "Critical DOM selector or route breakage" in risk_result.primary_risk_driver


def test_confidence_vs_risk_decoupling(sample_test_case: TestCase, mock_db: Path):
    """Demonstrate that Mapping Confidence != Failure Risk.
    
    A testcase with 1.0 mapping confidence can have a low failure risk if no
    selectors broke and the test has a pristine pass history.
    """
    scorer = PredictiveRiskScorer(db_path=mock_db)

    mappings = [
        TestCodeMapping(
            id="m-1",
            testcase_id=sample_test_case.id,
            testcase_name=sample_test_case.name,
            file_path="src/pages/Login.tsx",
            relation_type="exact_route",
            confidence=1.0,  # MAXIMUM CONFIDENCE
            matched_entity="/login",
        )
    ]
    graph = TestToCodeGraph()
    for m in mappings:
        graph.add_mapping(m)
    profile = TestReferenceExtractor.extract_profile(sample_test_case)

    # Code modified with 0 deleted selectors, 1 line comment changed
    changed_files = [
        ChangedFile(
            path="src/pages/Login.tsx",
            change_type="modified",
            additions=1,
            deletions=0,
        )
    ]

    mock_pristine_stats = {
        "total_runs": 50,
        "failed_runs": 0,
        "failure_rate": 0.0,
        "flakiness_rate": 0.0,
        "runs": [{"status": "passed"}],
    }
    with patch(
        "tracecase.intelligence.risk_scorer.get_testcase_flakiness_stats",
        return_value=mock_pristine_stats,
    ):
        risk_result = scorer.score_test(
            sample_test_case, profile, graph, changed_files
        )

    # Confidence is 1.0 (certain relationship)
    assert risk_result.mapping_confidence == 1.0
    # But Risk Score is low (only impact: 0.30*100 + 0.10*1.5 = 30.15 -> 30.2)
    assert risk_result.risk_score <= 35.0
    assert risk_result.risk_tier == "low"


def test_risk_snapshot_persistence(mock_db: Path):
    """Verify risk scores can be snapshotted and queried from SQLite."""
    breakdown = RiskFactorBreakdown(
        change_impact_score=100.0,
        selector_breakage_score=100.0,
        historical_failure_score=50.0,
        flakiness_recency_score=20.0,
        change_magnitude_score=30.0,
        weighted_impact=30.0,
        weighted_breakage=25.0,
        weighted_failure=10.0,
        weighted_flakiness=3.0,
        weighted_magnitude=3.0,
        has_history=True,
        history_run_count=10,
        recent_failure_detected=False,
        broken_selectors_count=1,
        modified_selectors_count=0,
        lines_changed=30,
    )

    scores = [
        TestRiskScore(
            testcase_id="tc-01",
            testcase_name="Checkout Test",
            project_id="test_proj",
            risk_score=92.5,
            risk_tier="critical",
            mapping_confidence=1.0,
            primary_risk_driver="Critical selector breakage",
            explanation=["Deleted checkout button"],
            breakdown=breakdown,
            affected_files=["src/pages/Checkout.tsx"],
            matched_selectors=["#pay-btn"],
            matched_routes=["/checkout"],
        )
    ]

    save_risk_scores_snapshot(
        scores=scores,
        commit_hash="a1b2c3d4",
        branch="feature/checkout",
        project_id="test_proj",
        db_path=mock_db,
    )

    snapshots = get_risk_scores_snapshots(
        commit_hash="a1b2c3d4",
        project_id="test_proj",
        db_path=mock_db,
    )
    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap["testcase_id"] == "tc-01"
    assert snap["risk_score"] == 92.5
    assert snap["risk_tier"] == "critical"
    assert snap["commit_hash"] == "a1b2c3d4"
    assert snap["branch"] == "feature/checkout"


def test_api_risk_and_snapshots(mock_db: Path, sample_test_case: TestCase):
    """Verify REST API endpoints POST /api/intelligence/risk and GET /api/intelligence/risk/snapshots."""
    with patch("tracecase.ui.db.DEFAULT_STUDIO_DB_PATH", mock_db):
        app_instance = create_app()
        client = TestClient(app_instance)

        with patch(
            "tracecase.ui.service.find_testcase_files",
            return_value=[Path("/fake/tc-login.json")],
        ), patch(
            "tracecase.ui.service.resolve_testcase_file",
            return_value=(Path("/fake/tc-login.json"), sample_test_case),
        ):
            res = client.post(
                "/api/intelligence/risk",
                json={
                    "project_id": "test_proj",
                    "repo_path": ".",
                    "persist_snapshot": True,
                },
            )
            assert res.status_code == 200
            data = res.json()
            assert "total_tests_evaluated" in data
            assert "scores" in data
            assert data["total_tests_evaluated"] == 1

            # Check snapshots query
            res_snap = client.get(
                "/api/intelligence/risk/snapshots",
                params={"project_id": "test_proj"},
            )
            assert res_snap.status_code == 200
            snap_data = res_snap.json()
            assert isinstance(snap_data, list)
            assert len(snap_data) >= 1
            assert snap_data[0]["testcase_id"] == sample_test_case.id


def test_cli_risk_command(sample_test_case: TestCase):
    """Verify the tracecase risk CLI command runs and outputs valid JSON."""
    runner = CliRunner()

    with patch(
        "tracecase.ui.service.find_testcase_files",
        return_value=[Path("/fake/tc.json")],
    ), patch(
        "tracecase.ui.service.resolve_testcase_file",
        return_value=(Path("/fake/tc.json"), sample_test_case),
    ):
        result = runner.invoke(app, ["risk", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total_tests_evaluated" in data
        assert "scores" in data
        assert "critical_count" in data
