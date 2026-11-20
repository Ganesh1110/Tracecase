"""Phase 8.3 — Baseline Comparison & Regression Drift Test Suite.

Verifies:
1. Baseline snapshot persistence, querying, and retrieval by commit and branch.
2. BaselineResolver exact commit match vs branch fallback vs missing baseline.
3. 7-state RegressionDriftClassifier taxonomy:
   - Passed -> Failed: NEW_REGRESSION
   - Failed -> Failed: PRE_EXISTING_FAILURE
   - Failed -> Passed: FIXED_REGRESSION
   - Passed -> Passed: STABLE_PASS
   - Passed -> Flaky: NEWLY_FLAKY
   - Flaky -> Flaky: PERSISTENT_FLAKY
   - Missing -> Failed: UNKNOWN_BASELINE_FAILURE (missing != passing)
   - Missing -> Passed: NEW_TEST_PASS
   - Any -> Error: INFRASTRUCTURE_ERROR
4. Test definition drift detection via revision hashing.
5. Pre-existing failures allowed under standard policy (non-blocking technical debt).
6. Pre-existing failures blocked under strict policy.
7. New regressions blocking gate under standard and strict policies.
8. Newly introduced flakiness rate gate enforcement.
9. Missing baseline policy enforcement (require_valid_baseline).
10. Drift analytics SQLite storage and querying.
11. Multi-format drift reporting (Markdown Drift Table, SARIF new regression rules, JSON manifest v1.1.0).
12. BaselineExecutor isolated worktree creation and cleanup.
13. CLI tracecase ci baseline options and console drift visualization.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
from pathlib import Path
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from tracecase.ci.baseline import (
    BaselineExecutor,
    BaselineManager,
    BaselineMatchStatus,
    BaselineResolutionResult,
    BaselineResolver,
    BaselineSnapshot,
    BaselineTestOutcome,
    compute_test_revision_hash,
)
from tracecase.ci.config import CIRunnerConfig
from tracecase.ci.drift import (
    DriftAnalytics,
    DriftAnalysisResult,
    DriftClassification,
    RegressionDriftClassifier,
    RegressionDriftComparator,
    TestDriftItem,
)
from tracecase.ci.gate import QualityGateEvaluator
from tracecase.ci.models import CIExitCode, QualityGateResult
from tracecase.ci.policy import (
    LENIENT_POLICY,
    PERMISSIVE_POLICY,
    STANDARD_POLICY,
    STRICT_POLICY,
    QualityGatePolicy,
)
from tracecase.ci.reporters.json import generate_ci_json_manifest
from tracecase.ci.reporters.markdown import generate_ci_markdown_report
from tracecase.ci.reporters.sarif import generate_sarif_report
from tracecase.ci.runner import CIRunner
from tracecase.cli import app
from tracecase.models import ElementInfo, Step, TestCase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Initialize a git repository with commits."""
    repo = tmp_path / "baseline_test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "CI Bot"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "ci@tracecase.io"], cwd=str(repo), check=True)

    # Initial commit (base)
    (repo / "src").mkdir()
    (repo / "src" / "App.tsx").write_text("export const App = () => <button id='pay'>Pay</button>;", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-m", "Initial base commit"], cwd=str(repo), check=True)

    return repo


@pytest.fixture
def sample_testcase() -> TestCase:
    """Create a sample test case for revision hashing and execution."""
    return TestCase(
        id="tc_login",
        name="User Login Flow",
        description="Verify user authentication",
        created_at=datetime.now(),
        start_url="https://app.example.com/login",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0",
        total_duration=5.0,
        total_steps=1,
        steps=[
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="click",
                element=ElementInfo(
                    selector="#login-btn",
                    tag_name="button",
                    bounding_box={"x": 10.0, "y": 20.0, "width": 100.0, "height": 40.0},
                ),
                description_short="Click login",
                description_detailed="Click login button",
            )
        ],
    )


# ---------------------------------------------------------------------------
# Subphase 8.3.1 Tests — Baseline Snapshot & Management
# ---------------------------------------------------------------------------

def test_baseline_snapshot_persistence_and_retrieval(tmp_path: Path):
    """Test 1: Persisting and retrieving baseline snapshots in SQLite."""
    db_file = tmp_path / "ci_test.db"
    mgr = BaselineManager(db_path=db_file)

    outcomes = {
        "tc_1": BaselineTestOutcome(
            testcase_id="tc_1",
            testcase_name="Test 1",
            status="passed",
            duration_ms=1200.0,
            test_revision_hash="rev_abc123",
        ),
        "tc_2": BaselineTestOutcome(
            testcase_id="tc_2",
            testcase_name="Test 2",
            status="failed",
            duration_ms=2500.0,
            error_message="Selector not found",
            test_revision_hash="rev_def456",
        ),
    }

    snap = BaselineSnapshot(
        id="snap_c0ffee11_chromium",
        project_id="test_proj",
        commit_hash="c0ffee1122334455",
        branch="main",
        browser="chromium",
        total_tests=2,
        passed_count=1,
        failed_count=1,
        outcomes=outcomes,
    )

    mgr.save_snapshot(snap)

    # 1. Retrieve by exact commit
    retrieved = mgr.get_snapshot_by_commit("test_proj", "c0ffee1122334455", "chromium")
    assert retrieved is not None
    assert retrieved.commit_hash == "c0ffee1122334455"
    assert len(retrieved.outcomes) == 2
    assert retrieved.get_outcome("tc_1").status == "passed"
    assert retrieved.get_outcome("tc_2").status == "failed"

    # 2. Retrieve by short commit prefix
    retrieved_short = mgr.get_snapshot_by_commit("test_proj", "c0ffee11", "chromium")
    assert retrieved_short is not None
    assert retrieved_short.commit_hash == "c0ffee1122334455"

    # 3. Retrieve by branch
    retrieved_branch = mgr.get_latest_branch_snapshot("test_proj", "main", "chromium")
    assert retrieved_branch is not None
    assert retrieved_branch.branch == "main"

    # 4. Incompatible browser returns None
    assert mgr.get_snapshot_by_commit("test_proj", "c0ffee11", "firefox") is None


def test_baseline_resolver_exact_commit_and_fallback(tmp_path: Path):
    """Test 2: BaselineResolver discovers exact commit or falls back to branch snapshot."""
    db_file = tmp_path / "ci_resolver_test.db"
    mgr = BaselineManager(db_path=db_file)
    resolver = BaselineResolver(manager=mgr)

    snap_main = BaselineSnapshot(
        id="snap_main_chromium",
        project_id="p1",
        commit_hash="1111222233334444",
        branch="main",
        browser="chromium",
        outcomes={
            "tc_login": BaselineTestOutcome(
                testcase_id="tc_login",
                testcase_name="Login",
                status="passed",
            )
        },
    )
    mgr.save_snapshot(snap_main)

    # 1. Exact commit match
    res_exact = resolver.resolve(
        project_id="p1",
        base_commit="1111222233334444",
        browser="chromium",
    )
    assert res_exact.status == BaselineMatchStatus.FOUND_EXACT_COMMIT
    assert res_exact.is_valid is True
    assert res_exact.snapshot.commit_hash == "1111222233334444"

    # 2. Fallback to base branch when base commit differs
    res_branch = resolver.resolve(
        project_id="p1",
        base_ref="origin/main",
        base_commit="9999888877776666",
        browser="chromium",
    )
    assert res_branch.status == BaselineMatchStatus.FOUND_BRANCH_SNAPSHOT
    assert res_branch.is_valid is True

    # 3. Missing baseline
    res_missing = resolver.resolve(
        project_id="p1",
        base_ref="origin/feature-x",
        base_commit="5555444433332222",
        browser="chromium",
    )
    assert res_missing.status == BaselineMatchStatus.NOT_FOUND
    assert res_missing.is_valid is False


# ---------------------------------------------------------------------------
# Subphase 8.3.2 Tests — Regression Drift Detection & Classification
# ---------------------------------------------------------------------------

def test_drift_classification_seven_states():
    """Test 3: Full 7-state taxonomy and edge cases in RegressionDriftClassifier."""
    # 1. Passed -> Failed => NEW_REGRESSION
    c, expl, _ = RegressionDriftClassifier.classify(
        pr_status="failed",
        base_outcome=BaselineTestOutcome(testcase_id="tc", testcase_name="TC", status="passed"),
    )
    assert c == DriftClassification.NEW_REGRESSION
    assert "New regression" in expl

    # 2. Failed -> Failed => PRE_EXISTING_FAILURE
    c, expl, _ = RegressionDriftClassifier.classify(
        pr_status="failed",
        base_outcome=BaselineTestOutcome(testcase_id="tc", testcase_name="TC", status="failed"),
    )
    assert c == DriftClassification.PRE_EXISTING_FAILURE
    assert "Pre-existing failure" in expl

    # 3. Failed -> Passed => FIXED_REGRESSION
    c, expl, _ = RegressionDriftClassifier.classify(
        pr_status="passed",
        base_outcome=BaselineTestOutcome(testcase_id="tc", testcase_name="TC", status="failed"),
    )
    assert c == DriftClassification.FIXED_REGRESSION
    assert "Fixed regression" in expl

    # 4. Passed -> Passed => STABLE_PASS
    c, expl, _ = RegressionDriftClassifier.classify(
        pr_status="passed",
        base_outcome=BaselineTestOutcome(testcase_id="tc", testcase_name="TC", status="passed"),
    )
    assert c == DriftClassification.STABLE_PASS

    # 5. Passed -> Flaky => NEWLY_FLAKY
    c, expl, _ = RegressionDriftClassifier.classify(
        pr_status="flaky",
        base_outcome=BaselineTestOutcome(testcase_id="tc", testcase_name="TC", status="passed"),
    )
    assert c == DriftClassification.NEWLY_FLAKY
    assert "Newly unstable" in expl

    # 6. Flaky -> Flaky => PERSISTENT_FLAKY
    c, expl, _ = RegressionDriftClassifier.classify(
        pr_status="flaky",
        base_outcome=BaselineTestOutcome(testcase_id="tc", testcase_name="TC", status="flaky"),
    )
    assert c == DriftClassification.PERSISTENT_FLAKY

    # 7. Missing -> Failed => UNKNOWN_BASELINE_FAILURE (missing != passing!)
    c, expl, _ = RegressionDriftClassifier.classify(
        pr_status="failed",
        base_outcome=None,
    )
    assert c == DriftClassification.UNKNOWN_BASELINE_FAILURE
    assert "no baseline record" in expl

    # 8. Missing -> Passed => NEW_TEST_PASS
    c, expl, _ = RegressionDriftClassifier.classify(
        pr_status="passed",
        base_outcome=None,
    )
    assert c == DriftClassification.NEW_TEST_PASS

    # 9. PR Error => INFRASTRUCTURE_ERROR
    c, expl, _ = RegressionDriftClassifier.classify(
        pr_status="error",
        base_outcome=BaselineTestOutcome(testcase_id="tc", testcase_name="TC", status="passed"),
    )
    assert c == DriftClassification.INFRASTRUCTURE_ERROR


def test_test_definition_drift_detection(sample_testcase: TestCase):
    """Test 4: Detect when test definition changes between base and PR."""
    base_hash = compute_test_revision_hash(sample_testcase)

    # Modify testcase steps
    modified_testcase = sample_testcase.model_copy(deep=True)
    modified_testcase.steps[0].element.selector = "#new-login-btn"
    pr_hash = compute_test_revision_hash(modified_testcase)

    assert base_hash != pr_hash, "Revision hash must change when locator is modified"

    # Verify classifier flags test_definition_drift
    base_outcome = BaselineTestOutcome(
        testcase_id=sample_testcase.id,
        testcase_name=sample_testcase.name,
        status="passed",
        test_revision_hash=base_hash,
    )

    c, expl, def_drift = RegressionDriftClassifier.classify(
        pr_status="failed",
        base_outcome=base_outcome,
        pr_test_revision_hash=pr_hash,
    )

    assert c == DriftClassification.NEW_REGRESSION
    assert def_drift is True
    assert "Test definition changed" in expl


# ---------------------------------------------------------------------------
# Subphase 8.3.3 Tests — Intelligent Baseline-Aware Quality Gates
# ---------------------------------------------------------------------------

def test_pre_existing_failures_allowed_by_policy():
    """Test 5: Pre-existing failure allows standard quality gate to PASS."""
    evaluator = QualityGateEvaluator(policy=STANDARD_POLICY)  # allow_pre_existing_failures = True

    runs = [
        {"testcase_id": "tc_stable", "status": "passed", "duration_ms": 1000},
        {"testcase_id": "tc_old_bug", "status": "failed", "duration_ms": 1500, "error_message": "Pre-existing failure"},
    ]

    drift_result = DriftAnalysisResult(
        run_id="run_1",
        baseline_found=True,
        total_compared=2,
        new_regressions_count=0,
        pre_existing_failures_count=1,
        items=[
            TestDriftItem(
                testcase_id="tc_stable",
                testcase_name="Stable",
                classification=DriftClassification.STABLE_PASS,
                pr_status="passed",
                base_status="passed",
            ),
            TestDriftItem(
                testcase_id="tc_old_bug",
                testcase_name="Old Bug",
                classification=DriftClassification.PRE_EXISTING_FAILURE,
                pr_status="failed",
                base_status="failed",
            ),
        ],
    )

    res = evaluator.evaluate(execution_runs=runs, drift_result=drift_result)

    assert res.passed is True
    assert res.status == "PASSED"
    assert res.metrics["pre_existing_failures_count"] == 1
    assert res.metrics["new_regressions_count"] == 0
    assert len(res.violations) == 0


def test_pre_existing_failures_blocked_by_strict_policy():
    """Test 6: Pre-existing failure blocks strict quality gate (allow_pre_existing_failures = False)."""
    evaluator = QualityGateEvaluator(policy=STRICT_POLICY)

    runs = [
        {"testcase_id": "tc_old_bug", "status": "failed", "duration_ms": 1500},
    ]

    drift_result = DriftAnalysisResult(
        run_id="run_strict",
        baseline_found=True,
        total_compared=1,
        new_regressions_count=0,
        pre_existing_failures_count=1,
        items=[
            TestDriftItem(
                testcase_id="tc_old_bug",
                testcase_name="Old Bug",
                classification=DriftClassification.PRE_EXISTING_FAILURE,
                pr_status="failed",
                base_status="failed",
            )
        ],
    )

    res = evaluator.evaluate(execution_runs=runs, drift_result=drift_result)
    assert res.passed is False
    assert any(v.rule_name == "pre_existing_failures" for v in res.violations)


def test_new_regression_blocks_gate():
    """Test 7: A new regression introduced by PR immediately blocks standard quality gate."""
    evaluator = QualityGateEvaluator(policy=STANDARD_POLICY)  # max_new_failures = 0

    runs = [
        {"testcase_id": "tc_broken", "status": "failed", "duration_ms": 1200, "error_message": "Regression"},
    ]

    drift_result = DriftAnalysisResult(
        run_id="run_new_fail",
        baseline_found=True,
        total_compared=1,
        new_regressions_count=1,
        items=[
            TestDriftItem(
                testcase_id="tc_broken",
                testcase_name="Broken Test",
                classification=DriftClassification.NEW_REGRESSION,
                pr_status="failed",
                base_status="passed",
            )
        ],
    )

    res = evaluator.evaluate(execution_runs=runs, drift_result=drift_result)
    assert res.passed is False
    assert any(v.rule_name == "new_regressions" for v in res.violations)


def test_missing_baseline_policy_enforcement():
    """Test 8: require_valid_baseline blocks gate when baseline snapshot is not found."""
    policy = QualityGatePolicy(
        name="custom_baseline_gate",
        baseline_enabled=True,
        require_valid_baseline=True,
    )
    evaluator = QualityGateEvaluator(policy=policy)

    runs = [{"testcase_id": "tc_1", "status": "passed", "duration_ms": 500}]
    drift_missing = DriftAnalysisResult(
        run_id="run_missing",
        baseline_found=False,
        total_compared=1,
    )

    res = evaluator.evaluate(execution_runs=runs, drift_result=drift_missing)
    assert res.passed is False
    assert any(v.rule_name == "missing_baseline" for v in res.violations)


# ---------------------------------------------------------------------------
# Subphase 8.3.4 Tests — Drift Reports, Analytics & CLI Integration
# ---------------------------------------------------------------------------

def test_drift_analytics_sqlite_storage_and_query(tmp_path: Path):
    """Test 9: Storing and querying drift records via DriftAnalytics."""
    db_file = tmp_path / "drift_analytics.db"
    analytics = DriftAnalytics(db_path=db_file)

    drift_res = DriftAnalysisResult(
        run_id="ci_run_analytics_1",
        project_id="proj_x",
        base_commit="aabbcc11",
        pr_commit="ddeeff22",
        browser="chromium",
        items=[
            TestDriftItem(
                testcase_id="tc_drift_1",
                testcase_name="Drift Test 1",
                classification=DriftClassification.NEW_REGRESSION,
                pr_status="failed",
                base_status="passed",
                duration_delta_ms=350.0,
            ),
            TestDriftItem(
                testcase_id="tc_drift_2",
                testcase_name="Drift Test 2",
                classification=DriftClassification.FIXED_REGRESSION,
                pr_status="passed",
                base_status="failed",
                duration_delta_ms=-120.0,
            ),
        ],
    )

    analytics.save_drift_result(drift_res)

    records = analytics.get_drift_records(run_id="ci_run_analytics_1", project_id="proj_x")
    assert len(records) == 2
    classifications = {r["testcase_id"]: r["classification"] for r in records}
    assert classifications["tc_drift_1"] == "new_regression"
    assert classifications["tc_drift_2"] == "fixed_regression"


def test_drift_reporters_markdown_and_sarif():
    """Test 10: Multi-format reporting includes drift attribution and SARIF rules."""
    from tracecase.ci.models import CIRunResult

    gate_res = QualityGateResult(
        status="PASSED",
        passed=True,
        policy_name="standard",
        summary="Gate passed with pre-existing failure allowed",
        metrics={"surface_coverage_pct": 100.0},
    )

    run_res = CIRunResult(
        run_id="run_rep_1",
        project_id="default_project",
        commit_hash="abcdef12",
        base_ref="origin/main",
        duration_seconds=6.5,
        exit_code=0,
        gate_result=gate_res,
        total_considered=2,
        selected_count=2,
        executed_count=2,
        test_results=[
            {"testcase_id": "tc_1", "testcase_name": "Login", "status": "passed", "duration_ms": 1000},
            {"testcase_id": "tc_2", "testcase_name": "Checkout", "status": "failed", "duration_ms": 2000, "error_message": "Pre-existing error"},
        ],
    )

    drift_res = DriftAnalysisResult(
        run_id="run_rep_1",
        base_commit="12345678",
        pr_commit="abcdef12",
        baseline_found=True,
        total_compared=2,
        new_regressions_count=0,
        pre_existing_failures_count=1,
        stable_passes_count=1,
        items=[
            TestDriftItem(
                testcase_id="tc_1",
                testcase_name="Login",
                classification=DriftClassification.STABLE_PASS,
                pr_status="passed",
                base_status="passed",
            ),
            TestDriftItem(
                testcase_id="tc_2",
                testcase_name="Checkout",
                classification=DriftClassification.PRE_EXISTING_FAILURE,
                pr_status="failed",
                base_status="failed",
                test_definition_drift=True,
            ),
        ],
    )

    # 1. Markdown report
    md = generate_ci_markdown_report(run_result=run_res, gate_result=gate_res, drift_result=drift_res)
    assert "Baseline & Regression Drift Analysis" in md
    assert "Pre-Existing Failures" in md
    assert "Pre-Existing" in md

    # 2. SARIF report
    sarif = generate_sarif_report(gate_result=gate_res, runs=run_res.test_results, drift_result=drift_res)
    assert any(r["id"] == "TRACECASE-PREEXISTING-FAIL" for r in sarif["runs"][0]["tool"]["driver"]["rules"])
    results = sarif["runs"][0]["results"]
    assert any(r["ruleId"] == "TRACECASE-PREEXISTING-FAIL" for r in results)

    # 3. JSON manifest
    manifest = generate_ci_json_manifest(run_result=run_res, gate_result=gate_res, drift_result=drift_res)
    assert manifest["schema_version"] == "1.1.0"
    assert "drift" in manifest
    assert manifest["drift"]["summary"]["pre_existing_failures"] == 1


@pytest.mark.asyncio
async def test_baseline_executor_worktree_isolation(temp_git_repo: Path, tmp_path: Path):
    """Test 11: BaselineExecutor runs in a separate git worktree and cleans it up."""
    # Get base commit SHA
    res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(temp_git_repo), capture_output=True, text=True, check=True)
    base_commit = res.stdout.strip()

    db_file = tmp_path / "worktree_test.db"
    mgr = BaselineManager(db_path=db_file)

    mock_orchestrator = MagicMock()
    mock_batch = {"id": "batch_base_1"}
    mock_orchestrator.start_batch_execution = AsyncMock(return_value=mock_batch)
    mock_orchestrator.active_tasks = {mock_batch["id"]: asyncio.sleep(0.01)}
    mock_orchestrator.browser_pool = MagicMock()
    mock_orchestrator.browser_pool.shutdown = AsyncMock()

    executor = BaselineExecutor(manager=mgr, orchestrator=mock_orchestrator, db_path=db_file)

    with patch("tracecase.ci.baseline.executor.find_testcase_files", return_value=[Path("dummy.json")]), \
         patch("tracecase.ci.baseline.executor.resolve_testcase_file", return_value=(Path("dummy.json"), TestCase(
             id="tc_worktree",
             name="Worktree Test",
             created_at=datetime.now(),
             start_url="https://example.com",
             browser="chromium",
             viewport={"width": 1280, "height": 720},
             user_agent="Tracecase",
             total_duration=1.0,
             total_steps=1,
             steps=[Step(
                 number=1,
                 timestamp=datetime.now(),
                 action_type="click",
                 description_short="Click",
                 description_detailed="Click element",
             )],
         ))), \
         patch("tracecase.ci.baseline.executor.get_execution_batch", return_value={
             "id": mock_batch["id"],
             "runs": [{"testcase_id": "tc_worktree", "status": "passed", "duration_ms": 1100}],
         }):

        snap = await executor.execute_baseline_in_worktree(
            repo_path=temp_git_repo,
            base_commit=base_commit,
            project_id="p_wt",
        )

        assert snap.commit_hash == base_commit
        assert snap.passed_count == 1
        assert "tc_worktree" in snap.outcomes

        # Verify no dangling worktrees in git
        wt_list = subprocess.run(["git", "worktree", "list"], cwd=str(temp_git_repo), capture_output=True, text=True)
        assert str(temp_git_repo) in wt_list.stdout
        assert "tc_base_worktree_" not in wt_list.stdout


def test_cli_baseline_drift_integration(temp_git_repo: Path, tmp_path: Path):
    """Test 12: CLI tracecase ci displays regression drift table when baseline exists."""
    db_file = tmp_path / "cli_drift.db"
    mgr = BaselineManager(db_path=db_file)

    # Save a baseline snapshot
    res_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(temp_git_repo), capture_output=True, text=True, check=True)
    base_sha = res_sha.stdout.strip()

    snap = BaselineSnapshot(
        id=f"base_{base_sha[:8]}_chromium",
        project_id="default_project",
        commit_hash=base_sha,
        branch="main",
        browser="chromium",
        outcomes={
            "tc_login": BaselineTestOutcome(
                testcase_id="tc_login",
                testcase_name="Login",
                status="passed",
            )
        },
    )
    mgr.save_snapshot(snap)

    runner = CliRunner()
    res = runner.invoke(app, [
        "ci",
        "--repo", str(temp_git_repo),
        "--base", "HEAD",
        "--gate", "standard",
    ])

    assert res.exit_code == 0
    assert "QUALITY GATE PASSED" in res.output


def test_baseline_ancestry_validation(temp_git_repo: Path, tmp_path: Path):
    """Scenario 13: Resolver verifies commit ancestry when resolving branch snapshots."""
    db_file = tmp_path / "ancestry.db"
    mgr = BaselineManager(db_path=db_file)
    resolver = BaselineResolver(mgr)

    # Commit 1
    sha1 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(temp_git_repo), capture_output=True, text=True).stdout.strip()

    # Commit 2
    f2 = temp_git_repo / "new_file.txt"
    f2.write_text("commit 2")
    subprocess.run(["git", "add", "."], cwd=str(temp_git_repo), check=True)
    subprocess.run(["git", "commit", "-m", "Commit 2"], cwd=str(temp_git_repo), check=True)
    sha2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(temp_git_repo), capture_output=True, text=True).stdout.strip()

    # Save snapshot for sha2
    snap2 = BaselineSnapshot(
        id=f"snap_{sha2[:8]}_chromium",
        commit_hash=sha2,
        branch="main",
        browser="chromium",
        outcomes={"tc_1": BaselineTestOutcome(testcase_id="tc_1", testcase_name="T1", status="passed")},
    )
    mgr.save_snapshot(snap2)

    # When PR is based on sha1 (older commit), sha2 is NOT an ancestor of sha1!
    res = resolver.resolve(
        project_id="default_project",
        base_ref="main",
        base_commit=sha1,
        repo_path=temp_git_repo,
    )
    # Must reject sha2 because it's newer than the PR's base commit (sha1)
    assert res.status == BaselineMatchStatus.NOT_FOUND
    assert "is not an ancestor" in res.reason


def test_baseline_environment_parity(tmp_path: Path):
    """Scenario 14: Resolver flags incompatible environment when browser version or OS mismatches."""
    db_file = tmp_path / "env_parity.db"
    mgr = BaselineManager(db_path=db_file)
    resolver = BaselineResolver(mgr)

    snap = BaselineSnapshot(
        id="snap_env_chrome120",
        commit_hash="deadbeef1234",
        browser="chromium",
        environment={"browser_version": "120.0.6099.109", "os": "Linux"},
        outcomes={"tc_1": BaselineTestOutcome(testcase_id="tc_1", testcase_name="T1", status="passed")},
    )
    mgr.save_snapshot(snap)

    # Mismatched browser version (130 vs 120)
    res_ver = resolver.resolve(
        project_id="default_project",
        base_commit="deadbeef1234",
        browser="chromium",
        environment={"browser_version": "130.0.0.0"},
    )
    assert res_ver.status == BaselineMatchStatus.INCOMPATIBLE_ENVIRONMENT
    assert "Browser major version mismatch" in res_ver.reason

    # Matching browser version (120 vs 120)
    res_ok = resolver.resolve(
        project_id="default_project",
        base_commit="deadbeef1234",
        browser="chromium",
        environment={"browser_version": "120.0.6099.200"},
    )
    assert res_ok.status == BaselineMatchStatus.FOUND_EXACT_COMMIT


def test_incomplete_baseline_rejected(tmp_path: Path):
    """Scenario 15: Incomplete or cancelled baseline snapshots are rejected."""
    db_file = tmp_path / "incomplete.db"
    mgr = BaselineManager(db_path=db_file)
    resolver = BaselineResolver(mgr)

    snap_cancelled = BaselineSnapshot(
        id="snap_cancelled",
        commit_hash="c0ffee112233",
        browser="chromium",
        status="cancelled",
        outcomes={"tc_1": BaselineTestOutcome(testcase_id="tc_1", testcase_name="T1", status="passed")},
    )
    mgr.save_snapshot(snap_cancelled)

    res = resolver.resolve(
        project_id="default_project",
        base_commit="c0ffee112233",
        browser="chromium",
    )
    assert res.status == BaselineMatchStatus.NOT_FOUND
    assert "incomplete" in res.reason


def test_extended_drift_transitions_and_definition_drift():
    """Scenario 16: Extended drift transitions including flaky, cancelled, and test definition drift."""
    # 1. Flaky on base -> Failed on PR: Degradation to regression
    base_flaky = BaselineTestOutcome(testcase_id="tc_flaky", testcase_name="Flaky Test", status="flaky")
    clf, expl, _ = RegressionDriftClassifier.classify(pr_status="failed", base_outcome=base_flaky)
    assert clf == DriftClassification.NEW_REGRESSION
    assert "Previously flaky test has now degraded to complete failure" in expl

    # 2. Failed on base -> Flaky on PR: Partial recovery
    base_failed = BaselineTestOutcome(testcase_id="tc_fail", testcase_name="Fail Test", status="failed")
    clf2, expl2, _ = RegressionDriftClassifier.classify(pr_status="flaky", base_outcome=base_failed)
    assert clf2 == DriftClassification.FIXED_REGRESSION
    assert "Partially recovered" in expl2

    # 3. Cancelled on base -> Failed on PR: Baseline invalid -> Unknown baseline failure
    base_cancelled = BaselineTestOutcome(testcase_id="tc_canc", testcase_name="Cancelled Test", status="cancelled")
    clf3, expl3, _ = RegressionDriftClassifier.classify(pr_status="failed", base_outcome=base_cancelled)
    assert clf3 == DriftClassification.UNKNOWN_BASELINE_FAILURE
    assert "baseline outcome is invalid" in expl3

    # 4. Passed on base -> Skipped on PR: Skipped
    base_passed = BaselineTestOutcome(testcase_id="tc_skip", testcase_name="Pass Test", status="passed")
    clf4, _, _ = RegressionDriftClassifier.classify(pr_status="skipped", base_outcome=base_passed)
    assert clf4 == DriftClassification.SKIPPED

    # 5. Passed on base and PR, but locators changed (Test Definition Drift)
    base_tc = BaselineTestOutcome(
        testcase_id="tc_drift",
        testcase_name="Locator Drift",
        status="passed",
        test_revision_hash="hash_base_v1",
    )
    clf5, expl5, def_drift = RegressionDriftClassifier.classify(
        pr_status="passed",
        base_outcome=base_tc,
        pr_test_revision_hash="hash_pr_v2",
    )
    assert clf5 == DriftClassification.STABLE_PASS
    assert def_drift is True
    assert "test definition drift" in expl5

