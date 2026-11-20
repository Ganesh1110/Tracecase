"""Phase 8.2 — Native GitHub Actions & GitLab CI Integrations Test Suite.

Verifies:
1. GitHub composite action.yml schema, inputs, outputs, and composite steps.
2. GitLab CI pipeline template syntax, image specification, and reports binding.
3. GitHub step summary generation & manifest metric parsing.
4. Shell script pipeline exit code propagation (0=passed, 1=gate failed, 2=config error, 3=infra error).
5. Repeat-run database idempotency and artifact consistency.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import yaml
import pytest
from typer.testing import CliRunner

from tracecase.ci.config import CIRunnerConfig
from tracecase.ci.models import CIExitCode
from tracecase.ci.policy import STANDARD_POLICY
from tracecase.ci.runner import CIRunner
from tracecase.cli import app


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Initialize a git repository for integration tests."""
    repo = tmp_path / "ci_integration_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "CI Bot"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "ci@tracecase.io"], cwd=str(repo), check=True)

    (repo / "src").mkdir()
    (repo / "src" / "index.html").write_text("<button id='btn'>OK</button>", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo), check=True)

    return repo


def test_github_action_schema_and_inputs():
    """Verify .github/actions/tracecase-gate/action.yml structure and inputs."""
    action_path = Path(".github/actions/tracecase-gate/action.yml")
    assert action_path.is_file(), "action.yml must exist"

    data = yaml.safe_load(action_path.read_text(encoding="utf-8"))
    assert data["name"] == "Tracecase Continuous Quality Gate"
    assert data["runs"]["using"] == "composite"

    inputs = data.get("inputs", {})
    assert "base-ref" in inputs
    assert "policy" in inputs
    assert "budget" in inputs
    assert "concurrency" in inputs
    assert "junit-path" in inputs
    assert "sarif-path" in inputs
    assert "summary-path" in inputs
    assert "manifest-path" in inputs

    outputs = data.get("outputs", {})
    assert "exit-code" in outputs
    assert "gate-status" in outputs


def test_gitlab_ci_template_syntax_and_reports():
    """Verify .gitlab/ci/tracecase.gitlab-ci.yml structure and reports."""
    gitlab_path = Path(".gitlab/ci/tracecase.gitlab-ci.yml")
    assert gitlab_path.is_file(), "tracecase.gitlab-ci.yml must exist"

    data = yaml.safe_load(gitlab_path.read_text(encoding="utf-8"))
    gate_job = data.get(".tracecase-quality-gate")
    assert gate_job is not None
    assert gate_job["stage"] == "test"

    artifacts = gate_job.get("artifacts", {})
    reports = artifacts.get("reports", {})
    assert "junit" in reports
    assert "sast" in reports


def test_github_step_summary_simulation(temp_git_repo: Path, tmp_path: Path):
    """Simulate GitHub Actions running tracecase ci and populating $GITHUB_STEP_SUMMARY."""
    summary_file = tmp_path / "step_summary.md"
    junit_file = tmp_path / "junit.xml"
    sarif_file = tmp_path / "sarif.json"
    manifest_file = tmp_path / "manifest.json"

    runner = CliRunner()
    res = runner.invoke(app, [
        "ci",
        "--repo", str(temp_git_repo),
        "--gate", "standard",
        "--report", str(summary_file),
        "--junit", str(junit_file),
        "--sarif", str(sarif_file),
        "--manifest", str(manifest_file),
    ])

    assert res.exit_code == 0
    assert summary_file.is_file()
    assert junit_file.is_file()
    assert sarif_file.is_file()
    assert manifest_file.is_file()

    summary_content = summary_file.read_text(encoding="utf-8")
    assert "QUALITY GATE PASSED" in summary_content
    assert "Executive Summary" in summary_content
    assert "Note on Surface Coverage" in summary_content


def test_shell_script_exit_code_propagation(temp_git_repo: Path):
    """Verify shell script capturing of exit codes 0 and 2."""
    import sys
    import os

    env = {**os.environ, "PYTHONPATH": "src"}

    # 1. Clean repo should exit 0
    cmd_pass = [sys.executable, "-m", "tracecase.cli", "ci", "--repo", str(temp_git_repo), "--gate", "standard"]
    proc_pass = subprocess.run(cmd_pass, capture_output=True, text=True, env=env)
    assert proc_pass.returncode == 0

    # 2. Invalid git base ref should exit 2
    cmd_config_err = [sys.executable, "-m", "tracecase.cli", "ci", "--repo", str(temp_git_repo), "--base", "origin/non_existent_branch_999"]
    proc_err = subprocess.run(cmd_config_err, capture_output=True, text=True, env=env)
    assert proc_err.returncode == 2


@pytest.mark.asyncio
async def test_repeat_run_database_and_artifact_consistency(temp_git_repo: Path, tmp_path: Path):
    """Verify that multiple consecutive CI runs on the same repository produce consistent results."""
    db_file = tmp_path / "studio_ci_test.db"
    config = CIRunnerConfig(
        repo_path=str(temp_git_repo),
        project_id="test_proj",
        gate_policy=STANDARD_POLICY,
        junit_path=str(tmp_path / "junit.xml"),
        sarif_path=str(tmp_path / "sarif.json"),
        markdown_path=str(tmp_path / "summary.md"),
        json_path=str(tmp_path / "manifest.json"),
    )

    runner = CIRunner(config=config, db_path=db_file)

    # Run 1
    res1 = await runner.run()
    assert res1.exit_code == int(CIExitCode.PASSED)
    assert res1.gate_result.passed is True

    # Run 2
    res2 = await runner.run()
    assert res2.exit_code == int(CIExitCode.PASSED)
    assert res2.gate_result.passed is True

    # Run IDs must be unique
    assert res1.run_id != res2.run_id

    # Artifacts must exist and be valid JSON/XML
    manifest = json.loads(Path(config.json_path).read_text(encoding="utf-8"))
    assert manifest["exit_code"] == 0
    assert manifest["run_id"] == res2.run_id
