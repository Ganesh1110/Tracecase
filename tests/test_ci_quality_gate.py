"""Phase 8.1 — Continuous Quality Gates & CI Execution Engine Test Suite.

Verifies:
1. No changed files (sensible pass, 0 cost).
2. Changed selector with failing test (gate fails, exit code 1).
3. Critical test excluded by budget (gate follows block_on_budget_exceptions policy).
4. Flaky test that passes on retry (flakiness policy applied against max_flakiness_pct, not counted as failure).
5. Browser / infrastructure error (classified as infrastructure error, exit code 3).
6. Missing Git base ref (classified as config/environment error, exit code 2).
7. Non-git repository directory (classified as config/environment error, exit code 2).
8. JUnit XML schema & XML structure validation.
9. SARIF 2.1.0 schema compliance & rule definitions.
10. Markdown report generation (GitHub Step Summary & PR comments table).
11. JSON manifest validation (schema_version 1.0.0).
12. YAML configuration file loading and custom policy overrides.
13. Standalone CLI invocation `tracecase ci` without FastAPI / web server running.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch
import xml.etree.ElementTree as ET

import pytest
from typer.testing import CliRunner

from tracecase.ci.config import CIRunnerConfig
from tracecase.ci.gate import QualityGateEvaluator
from tracecase.ci.models import CIExitCode, QualityGateResult
from tracecase.ci.policy import (
    LENIENT_POLICY,
    PERMISSIVE_POLICY,
    STANDARD_POLICY,
    STRICT_POLICY,
    QualityGatePolicy,
    get_policy,
)
from tracecase.ci.reporters.json import generate_ci_json_manifest
from tracecase.ci.reporters.junit import generate_junit_xml
from tracecase.ci.reporters.markdown import generate_ci_markdown_report
from tracecase.ci.reporters.sarif import generate_sarif_report
from tracecase.ci.runner import CIRunner
from tracecase.cli import app
from tracecase.intelligence.models import (
    ChangedFile,
    GitChangeSet,
    PredictiveRiskReport,
    PrioritizationReport,
    RegressionSelectionResult,
    SelectedTestItem,
)
from tracecase.models import ActionType, Step, TestCase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Initialize a genuine git repository with commits."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "CI Bot"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "ci@tracecase.io"], cwd=str(repo), check=True)

    # Base commit
    (repo / "src").mkdir()
    (repo / "src" / "index.html").write_text("<button id='checkout-btn'>Pay</button>", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo), check=True)

    return repo


@pytest.fixture
def mock_testcase() -> TestCase:
    """Create a sample test case for testing."""
    from datetime import datetime
    from tracecase.models import ElementInfo

    return TestCase(
        id="tc_checkout_flow",
        name="Checkout Flow",
        description="Verify checkout flow",
        created_at=datetime.now(),
        start_url="https://shop.example.com/checkout",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0",
        total_duration=10.0,
        total_steps=1,
        steps=[
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="click",
                element=ElementInfo(
                    selector="#checkout-btn",
                    tag_name="button",
                    bounding_box={"x": 10.0, "y": 20.0, "width": 100.0, "height": 30.0},
                ),
                description_short="Click checkout button",
                description_detailed="Click checkout button",
            )
        ],
    )


# ---------------------------------------------------------------------------
# Policy Tests
# ---------------------------------------------------------------------------

def test_named_policy_profiles():
    """Verify built-in named quality gate policy profiles."""
    strict = get_policy("strict")
    assert strict.name == "strict"
    assert strict.fail_on_critical_breakage is True
    assert strict.max_failure_rate_pct == 0.0
    assert strict.max_flakiness_pct == 0.0
    assert strict.block_on_budget_exceptions is True

    standard = get_policy("standard")
    assert standard.name == "standard"
    assert standard.max_failure_rate_pct == 0.0
    assert standard.max_flakiness_pct == 15.0

    lenient = get_policy("lenient")
    assert lenient.max_failure_rate_pct == 10.0
    assert lenient.max_flakiness_pct == 30.0
    assert lenient.block_on_budget_exceptions is False

    permissive = get_policy("permissive")
    assert permissive.fail_on_critical_breakage is False
    assert permissive.max_failure_rate_pct == 100.0


# ---------------------------------------------------------------------------
# CI Runner & Quality Gate Unit & Integration Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ci_no_changed_files_sensible_pass(temp_git_repo: Path):
    """Scenario 1: No changed files should pass the quality gate immediately with 0 runs."""
    config = CIRunnerConfig(
        repo_path=str(temp_git_repo),
        project_id="test_proj",
        gate_policy=STANDARD_POLICY,
    )
    runner = CIRunner(config=config)
    res = await runner.run()

    assert res.exit_code == int(CIExitCode.PASSED)
    assert res.gate_result.status == "PASSED"
    assert res.gate_result.passed is True
    assert res.executed_count == 0
    assert res.selected_count == 0
    assert "No changes detected" in res.gate_result.summary


@pytest.mark.asyncio
async def test_ci_failing_test_fails_gate(temp_git_repo: Path, mock_testcase: TestCase):
    """Scenario 2: Changed selector with failing test fails the gate with exit code 1."""
    # Modify code in repo
    (temp_git_repo / "src" / "index.html").write_text("<button id='pay-now'>Pay</button>", encoding="utf-8")

    config = CIRunnerConfig(
        repo_path=str(temp_git_repo),
        project_id="test_proj",
        gate_policy=STANDARD_POLICY,
    )

    # Mock batch execution returning a failing run
    mock_batch = {"id": "batch_fail_1"}
    mock_runs = [
        {
            "id": "run_1",
            "testcase_id": mock_testcase.id,
            "testcase_name": mock_testcase.name,
            "status": "failed",
            "duration_ms": 2500,
            "error_message": "Selector #checkout-btn not found",
        }
    ]

    mock_orchestrator = MagicMock()
    mock_orchestrator.start_batch_execution = AsyncMock(return_value=mock_batch)
    mock_orchestrator.active_tasks = {mock_batch["id"]: asyncio.sleep(0.01)}

    with patch("tracecase.ci.runner.find_testcase_files", return_value=[Path("dummy.json")]), \
         patch("tracecase.ci.runner.resolve_testcase_file", return_value=(Path("dummy.json"), mock_testcase)), \
         patch("tracecase.ci.runner.get_execution_batch", return_value={"id": mock_batch["id"], "runs": mock_runs}):

        runner = CIRunner(config=config, orchestrator=mock_orchestrator)
        res = await runner.run()

        assert res.exit_code == int(CIExitCode.GATE_FAILED)
        assert res.gate_result.status == "FAILED"
        assert res.gate_result.passed is False
        assert len(res.gate_result.violations) >= 1
        assert any(v.rule_name in ("critical_breakage", "max_failure_rate") for v in res.gate_result.violations)


@pytest.mark.asyncio
async def test_ci_critical_test_excluded_by_budget(temp_git_repo: Path, mock_testcase: TestCase):
    """Scenario 3: Critical test excluded by budget follows block_on_budget_exceptions policy."""
    # 1. Under STRICT or STANDARD policy (block_on_budget_exceptions = True)
    evaluator_standard = QualityGateEvaluator(policy=STANDARD_POLICY)

    selection = RegressionSelectionResult(
        id="sel_budget_test",
        strategy="time_budget",
        time_budget_s=10.0,
        total_tests_considered=5,
        selected_test_ids=[],
        budget_exception_test_ids=["tc_critical_skipped"],
        budget_exception_count=1,
        tests=[],
    )

    gate_res_standard = evaluator_standard.evaluate(selection=selection, execution_runs=[])
    assert gate_res_standard.passed is False
    assert any(v.rule_name == "budget_exceptions" for v in gate_res_standard.violations)

    # 2. Under LENIENT policy (block_on_budget_exceptions = False)
    evaluator_lenient = QualityGateEvaluator(policy=LENIENT_POLICY)
    gate_res_lenient = evaluator_lenient.evaluate(selection=selection, execution_runs=[])
    assert gate_res_lenient.passed is True
    assert not any(v.rule_name == "budget_exceptions" for v in gate_res_lenient.violations)


@pytest.mark.asyncio
async def test_ci_flaky_test_passes_on_retry():
    """Scenario 4: Flaky test that passes on retry is evaluated against max_flakiness_pct, not marked failed."""
    evaluator = QualityGateEvaluator(policy=STANDARD_POLICY)  # max_flakiness_pct = 15.0

    # 10 completed runs: 9 passed, 1 flaky (10% flakiness <= 15.0%)
    runs = [
        {"testcase_id": f"tc_{i}", "status": "passed", "duration_ms": 1000} for i in range(9)
    ]
    runs.append({
        "testcase_id": "tc_flaky",
        "status": "flaky",
        "duration_ms": 3200,
        "retry_history": [{"attempt": 1, "status": "failed"}, {"attempt": 2, "status": "passed"}],
    })

    gate_res = evaluator.evaluate(execution_runs=runs)
    assert gate_res.passed is True
    assert gate_res.metrics["flaky_count"] == 1
    assert gate_res.metrics["failed_count"] == 0
    assert gate_res.metrics["flakiness_rate_pct"] == 10.0
    assert gate_res.metrics["failure_rate_pct"] == 0.0

    # If flakiness exceeds policy limit (e.g., STRICT policy with max_flakiness_pct = 0.0)
    strict_evaluator = QualityGateEvaluator(policy=STRICT_POLICY)
    strict_res = strict_evaluator.evaluate(execution_runs=runs)
    assert strict_res.passed is False
    assert any(v.rule_name == "max_flakiness" for v in strict_res.violations)


@pytest.mark.asyncio
async def test_ci_infrastructure_browser_error_exit_3(temp_git_repo: Path, mock_testcase: TestCase):
    """Scenario 5: Infrastructure / browser crash returns exit code 3."""
    (temp_git_repo / "src" / "index.html").write_text("<button>New</button>", encoding="utf-8")

    config = CIRunnerConfig(
        repo_path=str(temp_git_repo),
        project_id="test_proj",
        gate_policy=STANDARD_POLICY,
    )

    mock_batch = {"id": "batch_crash_1"}
    mock_runs = [
        {
            "id": "run_crash",
            "testcase_id": mock_testcase.id,
            "status": "error",
            "duration_ms": 500,
            "error_message": "BrowserProcessCrash: Browser closed unexpectedly",
        }
    ]

    mock_orchestrator = MagicMock()
    mock_orchestrator.start_batch_execution = AsyncMock(return_value=mock_batch)
    mock_orchestrator.active_tasks = {mock_batch["id"]: asyncio.sleep(0.01)}

    with patch("tracecase.ci.runner.find_testcase_files", return_value=[Path("dummy.json")]), \
         patch("tracecase.ci.runner.resolve_testcase_file", return_value=(Path("dummy.json"), mock_testcase)), \
         patch("tracecase.ci.runner.get_execution_batch", return_value={"id": mock_batch["id"], "runs": mock_runs}):

        runner = CIRunner(config=config, orchestrator=mock_orchestrator)
        res = await runner.run()

        assert res.exit_code == int(CIExitCode.INFRASTRUCTURE_ERROR)
        assert res.error_category == "infrastructure"


@pytest.mark.asyncio
async def test_ci_missing_git_base_ref_exit_2(temp_git_repo: Path):
    """Scenario 6: Missing or invalid Git base ref is classified as config error (exit 2)."""
    config = CIRunnerConfig(
        repo_path=str(temp_git_repo),
        base_ref="origin/non_existent_branch_xyz_123",
        gate_policy=STANDARD_POLICY,
    )
    runner = CIRunner(config=config)
    res = await runner.run()

    assert res.exit_code == int(CIExitCode.CONFIG_ERROR)
    assert res.error_category == "config"
    assert "Invalid or missing git base ref" in (res.error_detail or "")


@pytest.mark.asyncio
async def test_ci_invalid_repo_path_exit_2(tmp_path: Path):
    """Scenario 7: Non-git repository directory is classified as config error (exit 2)."""
    non_git = tmp_path / "empty_dir"
    non_git.mkdir()

    config = CIRunnerConfig(
        repo_path=str(non_git),
        gate_policy=STANDARD_POLICY,
    )
    runner = CIRunner(config=config)
    res = await runner.run()

    assert res.exit_code == int(CIExitCode.CONFIG_ERROR)
    assert res.error_category == "config"


# ---------------------------------------------------------------------------
# Reporting Format Tests
# ---------------------------------------------------------------------------

def test_ci_junit_xml_generation_and_schema():
    """Scenario 8: JUnit XML reporter produces standard schema XML."""
    runs = [
        {"testcase_id": "tc_1", "testcase_name": "Login Flow", "status": "passed", "duration_ms": 1200},
        {"testcase_id": "tc_2", "testcase_name": "Checkout Flow", "status": "failed", "duration_ms": 2500, "error_message": "Timeout waiting for button"},
        {"testcase_id": "tc_3", "testcase_name": "Profile Flow", "status": "error", "duration_ms": 300, "error_message": "Browser crash"},
        {"testcase_id": "tc_4", "testcase_name": "Search Flow", "status": "flaky", "duration_ms": 1800, "retry_history": [{"attempt": 1, "status": "failed"}]},
    ]

    xml_text = generate_junit_xml(runs, suite_name="Tracecase Unit Test Suite")
    root = ET.fromstring(xml_text)

    assert root.tag == "testsuites"
    assert root.attrib["tests"] == "4"
    assert root.attrib["failures"] == "1"
    assert root.attrib["errors"] == "1"

    suite = root.find("testsuite")
    assert suite is not None
    assert suite.attrib["name"] == "Tracecase Unit Test Suite"

    testcases = suite.findall("testcase")
    assert len(testcases) == 4

    # Verify failure element
    tc_fail = [tc for tc in testcases if tc.attrib["id"] == "tc_2"][0]
    fail_el = tc_fail.find("failure")
    assert fail_el is not None
    assert "Timeout waiting for button" in fail_el.attrib["message"]

    # Verify flaky property
    tc_flaky = [tc for tc in testcases if tc.attrib["id"] == "tc_4"][0]
    prop = tc_flaky.find(".//property[@name='flaky']")
    assert prop is not None
    assert prop.attrib["value"] == "true"


def test_ci_sarif_210_generation_and_schema():
    """Scenario 9: SARIF reporter outputs SARIF 2.1.0 compliant structure."""
    gate_res = QualityGateResult(
        status="FAILED",
        passed=False,
        policy_name="standard",
        summary="1 critical breakage detected",
    )

    runs = [
        {
            "testcase_id": "tc_broken",
            "testcase_name": "Broken Locator Test",
            "status": "failed",
            "error_message": "Selector not found",
        }
    ]

    selection = RegressionSelectionResult(
        id="sel_test_sarif",
        strategy="time_budget",
        total_tests_considered=1,
        selected_test_ids=["tc_broken"],
        budget_exception_test_ids=["tc_skipped_crit"],
        budget_exception_count=1,
        tests=[
            SelectedTestItem(
                testcase_id="tc_broken",
                testcase_name="Broken Locator Test",
                risk_tier="critical",
                risk_score=95.0,
                mapping_confidence=1.0,
                estimated_duration_s=5.0,
                duration_source="estimated_fallback",
                decision="selected",
                decision_reason="Critical locator modified",
                affected_files=["src/components/Checkout.tsx"],
            )
        ],
    )

    sarif = generate_sarif_report(gate_result=gate_res, runs=runs, selection=selection)

    assert sarif["version"] == "2.1.0"
    assert "sarif-schema-2.1.0.json" in sarif["$schema"]
    assert len(sarif["runs"]) == 1

    driver = sarif["runs"][0]["tool"]["driver"]
    assert driver["name"] == "Tracecase Continuous Quality Gate"
    assert len(driver["rules"]) == 4

    results = sarif["runs"][0]["results"]
    assert len(results) >= 2  # 1 critical test fail + 1 budget exception

    crit_res = [r for r in results if r["ruleId"] == "TRACECASE-CRITICAL-FAIL"][0]
    assert crit_res["level"] == "error"
    loc = crit_res["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "src/components/Checkout.tsx"


def test_ci_markdown_report_formatting():
    """Scenario 10: Markdown summary report generates GitHub Step Summary formatted table."""
    from tracecase.ci.models import CIRunResult

    gate_res = QualityGateResult(
        status="PASSED",
        passed=True,
        policy_name="standard",
        summary="All quality checks passed",
        metrics={
            "completed_runs": 5,
            "passed_count": 5,
            "failed_count": 0,
            "critical_failures_count": 0,
            "flaky_count": 0,
            "surface_coverage_pct": 100.0,
            "budget_exceptions_count": 0,
        },
    )

    run_res = CIRunResult(
        run_id="ci_run_test1",
        project_id="test_project",
        commit_hash="a1b2c3d",
        base_ref="origin/main",
        duration_seconds=12.4,
        exit_code=0,
        gate_result=gate_res,
        total_considered=5,
        selected_count=5,
        executed_count=5,
    )

    md = generate_ci_markdown_report(run_result=run_res, gate_result=gate_res)
    assert "QUALITY GATE PASSED" in md
    assert "Executive Summary" in md
    assert "100.0%" in md
    assert "origin/main" in md


def test_ci_json_manifest_generation():
    """Scenario 11: JSON manifest generates schema 1.0.0."""
    from tracecase.ci.models import CIRunResult

    gate_res = QualityGateResult(
        status="PASSED",
        passed=True,
        policy_name="strict",
        summary="Strict checks satisfied",
    )

    run_res = CIRunResult(
        run_id="ci_run_json",
        project_id="sample_proj",
        commit_hash="c0ffee1",
        base_ref="HEAD~1",
        duration_seconds=8.5,
        exit_code=0,
        gate_result=gate_res,
        total_considered=3,
        selected_count=3,
        executed_count=3,
    )

    manifest = generate_ci_json_manifest(run_result=run_res, gate_result=gate_res)
    assert manifest["schema_version"] == "1.0.0"
    assert manifest["generator"] == "Tracecase CI Execution Engine & Quality Gate"
    assert manifest["run_id"] == "ci_run_json"
    assert manifest["exit_code"] == 0
    assert manifest["gate"]["passed"] is True


def test_ci_yaml_config_loading_and_override(tmp_path: Path):
    """Scenario 12: CIRunnerConfig loads from YAML with customized policy thresholds."""
    yaml_content = """
ci:
  base_branch: "origin/release-v2"
  budget: "240s"
  concurrency: 4
  browser: "firefox"
  retries: 2
quality_gate:
  policy: "strict"
  max_flakiness_pct: 5.0
  block_on_budget_exceptions: false
reports:
  junit: "reports/junit.xml"
  sarif: "reports/sarif.json"
  markdown: "reports/summary.md"
  manifest: "reports/manifest.json"
"""
    cfg_file = tmp_path / "ci_config.yaml"
    cfg_file.write_text(yaml_content, encoding="utf-8")

    cfg = CIRunnerConfig.load_from_file(cfg_file)
    assert cfg.base_ref == "origin/release-v2"
    assert cfg.time_budget == "240s"
    assert cfg.concurrency == 4
    assert cfg.browser == "firefox"
    assert cfg.retries == 2
    assert cfg.gate_policy.name == "strict"
    assert cfg.gate_policy.max_flakiness_pct == 5.0
    assert cfg.gate_policy.block_on_budget_exceptions is False
    assert cfg.junit_path == "reports/junit.xml"
    assert cfg.sarif_path == "reports/sarif.json"


# ---------------------------------------------------------------------------
# Standalone CLI Invocation Tests
# ---------------------------------------------------------------------------

def test_cli_tracecase_ci_standalone(temp_git_repo: Path):
    """Scenario 13: tracecase ci executes standalone via CLI with clean exit."""
    runner = CliRunner()

    # Clean repo (0 changes) should exit with code 0
    res = runner.invoke(app, ["ci", "--repo", str(temp_git_repo), "--gate", "standard"])
    assert res.exit_code == 0
    assert "QUALITY GATE PASSED" in res.output
    assert "Quality Gate Results Summary" in res.output

    # Invocation with invalid base ref should exit with code 2
    res_bad = runner.invoke(app, [
        "ci",
        "--repo", str(temp_git_repo),
        "--base", "origin/missing_branch_999",
    ])
    assert res_bad.exit_code == 2
    assert "CONFIGURATION / ENVIRONMENT ERROR" in res_bad.output

    # Invocation with JSON output flag
    res_json = runner.invoke(app, [
        "ci",
        "--repo", str(temp_git_repo),
        "--gate", "standard",
        "--json",
    ])
    assert res_json.exit_code == 0
    parsed = json.loads(res_json.output)
    assert parsed["exit_code"] == 0
    assert parsed["gate_result"]["passed"] is True
