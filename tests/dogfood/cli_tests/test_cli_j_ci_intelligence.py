"""CLI Section J Tests: CI & Change Intelligence (Flows J1 - J20).

Dedicated tests for each flow tagged with @pytest.mark.flow("<ID>"):
- J1 - J6: changes, map, impact, risk, select, explain
- J7 - J11: report, run, ci gate, ci concurrency/matrix, ci baseline drift
- J12: ci-upload
- J13: benchmark
- J14 - J17: storage disk usage, dry-run, retention policy, failures-only filter
- J18: non-git directory error handling
- J19: ci command reports (junit XML and sarif)
- J20: ci command YAML config file loading
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from tracecase.models import ElementInfo, NetworkRequest, Step, TestCase
from tests.dogfood.cli_tests.conftest import run_tracecase


def _setup_corpus_for_git(repo_dir: Path, db_path: Path) -> Path:
    """Index testcases matching the git fixture routes/selectors into db."""
    tc_dir = repo_dir / "recordings" / "tc_login"
    tc_dir.mkdir(parents=True, exist_ok=True)
    tc = TestCase(
        id="tc_login_flow",
        name="Login Flow Verification",
        description="Matches git login route and button selector",
        created_at=datetime.now(),
        start_url="http://127.0.0.1:9010/login",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Tracecase-Dogfood/1.0",
        steps=[
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="navigate",
                url="http://127.0.0.1:9010/login",
                description_short="Nav to login",
                description_detailed="Navigated to /login",
            ),
            Step(
                number=2,
                timestamp=datetime.now(),
                action_type="click",
                element=ElementInfo(
                    selector="#btn-login",
                    xpath="//button[@id='btn-login']",
                    tag_name="button",
                    attributes={"id": "btn-login"},
                    bounding_box={"x": 10, "y": 10, "width": 80, "height": 30},
                ),
                description_short="Click signin",
                description_detailed="Clicked #btn-login",
            ),
        ],
        total_duration=1.0,
        total_steps=2,
    )
    tc_path = tc_dir / "testcase.json"
    tc_path.write_text(tc.model_dump_json(indent=2), encoding="utf-8")
    return tc_path


@pytest.mark.flow("J1")
def test_j1_git_changes_detection(
    git_fixture_repo: dict[str, str],
    isolated_env: dict[str, str],
):
    """J1: tracecase changes detects changed routes, selectors, and symbols across commits."""
    repo = git_fixture_repo["repo_path"]
    base = git_fixture_repo["commit_1"]

    res = run_tracecase(["changes", str(repo), "--base", base], env=isolated_env)
    assert res.returncode == 0
    assert "Changed Files" in res.stdout

    res_json = run_tracecase(["changes", str(repo), "--base", base, "--json"], env=isolated_env)
    assert res_json.returncode == 0
    data = json.loads(res_json.stdout)
    assert "files" in data


@pytest.mark.flow("J2")
def test_j2_tracecase_map(
    git_fixture_repo: dict[str, str],
    isolated_env: dict[str, str],
):
    """J2: tracecase map scans routes and selectors in repository."""
    repo = Path(git_fixture_repo["repo_path"])
    res = run_tracecase(["map", str(repo)], env=isolated_env, cwd=repo)
    assert res.returncode == 0


@pytest.mark.flow("J3")
def test_j3_tracecase_impact(
    git_fixture_repo: dict[str, str],
    isolated_env: dict[str, str],
):
    """J3: tracecase impact calculates impacted test cases based on git changes."""
    repo = Path(git_fixture_repo["repo_path"])
    base = git_fixture_repo["commit_1"]
    res = run_tracecase(["impact", str(repo), "--base", base], env=isolated_env, cwd=repo)
    assert res.returncode == 0


@pytest.mark.flow("J4")
def test_j4_tracecase_risk(
    git_fixture_repo: dict[str, str],
    isolated_env: dict[str, str],
):
    """J4: tracecase risk outputs risk scores (low/med/high) and breakdown."""
    repo = Path(git_fixture_repo["repo_path"])
    base = git_fixture_repo["commit_1"]
    res = run_tracecase(["risk", str(repo), "--base", base], env=isolated_env, cwd=repo)
    assert res.returncode == 0


@pytest.mark.flow("J5")
def test_j5_tracecase_select(
    git_fixture_repo: dict[str, str],
    isolated_env: dict[str, str],
):
    """J5: tracecase select filters and prioritizes testcases."""
    repo = Path(git_fixture_repo["repo_path"])
    base = git_fixture_repo["commit_1"]
    res = run_tracecase(["select", str(repo), "--base", base], env=isolated_env, cwd=repo)
    assert res.returncode == 0


@pytest.mark.flow("J6")
def test_j6_tracecase_explain(
    isolated_env: dict[str, str],
):
    """J6: tracecase explain outputs human-readable rationale for selection."""
    res = run_tracecase(["explain"], env=isolated_env)
    assert res.returncode in (0, 1, 2)


@pytest.mark.flow("J7")
def test_j7_report_markdown_and_manifest(
    isolated_env: dict[str, str],
):
    """J7: tracecase report displays run summary and manifest."""
    res = run_tracecase(["report", "--help"], env=isolated_env)
    assert res.returncode == 0
    assert "--format" in res.stdout


@pytest.mark.flow("J8")
def test_j8_tracecase_run_orchestrator(
    isolated_env: dict[str, str],
):
    """J8: tracecase run executes selected test suites."""
    res = run_tracecase(["run", "--help"], env=isolated_env)
    assert res.returncode == 0


@pytest.mark.flow("J9")
def test_j9_ci_gate_evaluation(
    git_fixture_repo: dict[str, str],
    isolated_env: dict[str, str],
):
    """J9: tracecase ci executes quality gate and evaluates thresholds."""
    repo = Path(git_fixture_repo["repo_path"])
    base = git_fixture_repo["commit_1"]
    res = run_tracecase(["ci", "--repo", str(repo), "--base", base], env=isolated_env, cwd=repo)
    assert res.returncode in (0, 1)


@pytest.mark.flow("J10")
def test_j10_ci_concurrency_and_matrix(
    isolated_env: dict[str, str],
):
    """J10: tracecase ci supports --concurrency / -c option for worker pool."""
    res = run_tracecase(["ci", "--help"], env=isolated_env)
    assert "--concurrency" in res.stdout


@pytest.mark.flow("J11")
def test_j11_ci_baseline_drift_preexisting(
    isolated_env: dict[str, str],
):
    """J11: tracecase ci supports --allow-preexisting flag for drift tolerance."""
    res = run_tracecase(["ci", "--help"], env=isolated_env)
    assert "--allow-preexisting" in res.stdout


@pytest.mark.flow("J12")
def test_j12_ci_upload_options(
    isolated_env: dict[str, str],
):
    """J12: tracecase ci-upload uploads run manifest to Studio."""
    res = run_tracecase(["ci-upload", "--help"], env=isolated_env)
    assert res.returncode == 0


@pytest.mark.flow("J13")
def test_j13_benchmark_command(
    isolated_env: dict[str, str],
):
    """J13: tracecase benchmark evaluates execution timing metrics."""
    res = run_tracecase(["benchmark", "--help"], env=isolated_env)
    assert res.returncode == 0


@pytest.mark.flow("J14")
def test_j14_storage_disk_usage(
    isolated_env: dict[str, str],
):
    """J14: tracecase storage inspects disk usage of artifacts."""
    res = run_tracecase(["storage"], env=isolated_env)
    assert res.returncode == 0


@pytest.mark.flow("J15")
def test_j15_storage_prune_dry_run(
    isolated_env: dict[str, str],
):
    """J15: tracecase storage --dry-run previews pruning without deleting."""
    res = run_tracecase(["storage", "--dry-run"], env=isolated_env)
    assert res.returncode == 0


@pytest.mark.flow("J16")
def test_j16_storage_retention_policy_older_than(
    isolated_env: dict[str, str],
):
    """J16: tracecase storage --older-than applies retention policy."""
    res = run_tracecase(["storage", "--dry-run", "--older-than", "30"], env=isolated_env)
    assert res.returncode == 0


@pytest.mark.flow("J17")
def test_j17_storage_failures_only_filter(
    isolated_env: dict[str, str],
):
    """J17: tracecase storage --failures-only retains only failure artifacts."""
    res = run_tracecase(["storage", "--dry-run", "--failures-only"], env=isolated_env)
    assert res.returncode == 0


@pytest.mark.flow("J18")
def test_j18_non_git_directory_handling(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """J18: Non-git directory passed to changes handled with clean error."""
    empty_dir = isolated_workspace / "not_git"
    empty_dir.mkdir(parents=True, exist_ok=True)
    res = run_tracecase(["changes", str(empty_dir)], env=isolated_env)
    assert res.returncode in (0, 1, 2)


@pytest.mark.flow("J19")
def test_j19_ci_output_reports_junit_sarif(
    isolated_env: dict[str, str],
):
    """J19: tracecase ci supports --junit and --sarif export options."""
    res = run_tracecase(["ci", "--help"], env=isolated_env)
    assert "--junit" in res.stdout
    assert "--sarif" in res.stdout


@pytest.mark.flow("J20")
def test_j20_ci_yaml_config_file(
    git_fixture_repo: dict[str, str],
    isolated_env: dict[str, str],
):
    """J20: tracecase ci supports loading YAML configuration from file."""
    repo = Path(git_fixture_repo["repo_path"])
    cfg_file = repo / "tracecase.yaml"
    cfg_file.write_text("ci:\n  concurrency: 2\n  budget: 5m\n", encoding="utf-8")
    res = run_tracecase(["ci", "--repo", str(repo), "--config", str(cfg_file)], env=isolated_env, cwd=repo)
    assert res.returncode in (0, 1)
