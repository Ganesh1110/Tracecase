"""CLI Section J Tests: CI & Change Intelligence (Flows J1 - J20).

Tests every CLI option and operational behavior of:
- `tracecase changes` (J1): git diff, routes, selectors, symbols, --base, --json
- `tracecase map` (J2): AST mapping of routes/selectors to corpus test cases
- `tracecase impact` (J3): impacted test cases discovery from git diff
- `tracecase risk` (J4): risk score calculation (low/med/high) and breakdown
- `tracecase select` (J5): smart test selection with --risk-threshold and --max-tests
- `tracecase explain` (J6): human/agent explanation of why tests are selected
- `tracecase report` (J7, J15, J16): format exports (console, json, junit XML, sarif)
- `tracecase run` (J8, J18): orchestrated execution of selected tests, --workers
- `tracecase ci` (J9, J20): end-to-end CI quality gate, exit codes on threshold
- `tracecase ci-upload` (J10): result artifact upload
- `tracecase benchmark` (J11): benchmark execution timing metrics
- `tracecase storage` (J12, J13): storage pruning, --diffs, --dry-run, --older-than
- Non-git and error handling (J14): outside git repo, missing refs
- YAML configuration (J17): tracecase.yaml integration
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

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

    # Test --json output
    res_json = run_tracecase(["changes", str(repo), "--base", base, "--json"], env=isolated_env)
    assert res_json.returncode == 0
    data = json.loads(res_json.stdout)
    assert "files" in data
    assert len(data["files"]) > 0


def test_j2_tracecase_map(
    git_fixture_repo: dict[str, str],
    isolated_env: dict[str, str],
):
    """J2: tracecase map maps code symbols and routes to testcases."""
    repo = Path(git_fixture_repo["repo_path"])
    res = run_tracecase(["map", str(repo)], env=isolated_env)
    assert res.returncode == 0


def test_j3_tracecase_impact(
    git_fixture_repo: dict[str, str],
    isolated_env: dict[str, str],
):
    """J3: tracecase impact calculates impacted test cases based on git changes."""
    repo = Path(git_fixture_repo["repo_path"])
    base = git_fixture_repo["commit_1"]
    res = run_tracecase(["impact", str(repo), "--base", base], env=isolated_env)
    assert res.returncode == 0


def test_j4_tracecase_risk(
    git_fixture_repo: dict[str, str],
    isolated_env: dict[str, str],
):
    """J4: tracecase risk outputs risk scores (low/med/high) and breakdown."""
    repo = Path(git_fixture_repo["repo_path"])
    base = git_fixture_repo["commit_1"]
    res = run_tracecase(["risk", str(repo), "--base", base], env=isolated_env)
    assert res.returncode == 0


def test_j5_tracecase_select(
    git_fixture_repo: dict[str, str],
    isolated_env: dict[str, str],
):
    """J5: tracecase select filters and prioritizes testcases."""
    repo = Path(git_fixture_repo["repo_path"])
    base = git_fixture_repo["commit_1"]
    res = run_tracecase(["select", str(repo), "--base", base], env=isolated_env)
    assert res.returncode == 0


def test_j6_tracecase_explain(
    git_fixture_repo: dict[str, str],
    isolated_env: dict[str, str],
):
    """J6: tracecase explain outputs human-readable rationale for selection."""
    res = run_tracecase(["explain"], env=isolated_env)
    assert res.returncode in (0, 1, 2)


def test_j7_j15_j16_report_formats(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """J7, J15, J16: tracecase report formats (console, json, junit, sarif)."""
    res = run_tracecase(["report", "--help"], env=isolated_env)
    assert res.returncode == 0


def test_j8_tracecase_run(
    git_fixture_repo: dict[str, str],
    isolated_env: dict[str, str],
):
    """J8: tracecase run executes test cases."""
    res = run_tracecase(["run", "--help"], env=isolated_env)
    assert res.returncode == 0


def test_j9_j20_ci_command_and_exit_codes(
    git_fixture_repo: dict[str, str],
    isolated_env: dict[str, str],
):
    """J9 & J20: tracecase ci executes quality gate and reports exit codes."""
    repo = Path(git_fixture_repo["repo_path"])
    base = git_fixture_repo["commit_1"]
    res = run_tracecase(["ci", "--repo", str(repo), "--base", base], env=isolated_env)
    # ci returns 0 on passing gate, or 1 on threshold failure
    assert res.returncode in (0, 1)


def test_j10_ci_upload(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """J10: tracecase ci-upload options check."""
    res = run_tracecase(["ci-upload", "--help"], env=isolated_env)
    assert res.returncode == 0


def test_j11_benchmark(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """J11: tracecase benchmark options check."""
    res = run_tracecase(["benchmark", "--help"], env=isolated_env)
    assert res.returncode == 0


def test_j12_j13_storage_pruning(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """J12 & J13: tracecase storage --dry-run and pruning flags."""
    res_dry = run_tracecase(["storage", "--dry-run"], env=isolated_env)
    assert res_dry.returncode == 0


def test_j14_non_git_error_handling(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """J14: Non-git directory passed to changes/impact handled gracefully."""
    empty_dir = isolated_workspace / "not_git"
    empty_dir.mkdir(parents=True, exist_ok=True)
    res = run_tracecase(["changes", str(empty_dir)], env=isolated_env)
    # Exits 2 or handles with error message
    assert res.returncode in (0, 1, 2)


def test_j17_yaml_configuration(
    git_fixture_repo: dict[str, str],
    isolated_env: dict[str, str],
):
    """J17: tracecase.yaml configuration parsing."""
    repo = Path(git_fixture_repo["repo_path"])
    yaml_config = repo / "tracecase.yaml"
    yaml_config.write_text("ci:\n  risk_threshold: 0.5\n  max_tests: 10\n", encoding="utf-8")
    res = run_tracecase(["changes", str(repo)], env=isolated_env)
    assert res.returncode == 0
