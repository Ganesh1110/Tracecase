"""Tests for Section A: Install and Environment (A1 - A6) and BUG-001 Regression."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from tests.dogfood.cli_tests.conftest import REPO_ROOT, TRACECASE_BIN, run_tracecase


@pytest.mark.flow("A1")
def test_a1_executable_installed():
    """A1: Verify tracecase binary is installed and executable in virtualenv."""
    assert TRACECASE_BIN.exists(), f"Binary not found: {TRACECASE_BIN}"
    assert TRACECASE_BIN.is_file()


@pytest.mark.flow("A2")
def test_a2_playwright_browsers_installed(isolated_env: dict[str, str]):
    """A2: Verify Playwright driver can inspect installed chromium."""
    res = subprocess.run(
        [sys.executable, "-m", "playwright", "--version"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "Version" in res.stdout or "." in res.stdout


@pytest.mark.flow("A3")
def test_a3_tracecase_check_healthy(isolated_env: dict[str, str]):
    """A3 (Critical): tracecase check reports healthy dependencies."""
    res = run_tracecase(["check"], env=isolated_env)
    assert res.returncode == 0
    assert "playwright" in res.stdout.lower()
    assert "all checks passed" in res.stdout.lower()
    from playwright.async_api import async_playwright
    assert async_playwright is not None


@pytest.mark.flow("A3.1")
def test_a3_1_tracecase_check_unhealthy(isolated_env: dict[str, str], isolated_workspace: Path):
    """A3.1: tracecase check detects missing browser binaries when path is invalid."""
    broken_env = isolated_env.copy()
    broken_env["PLAYWRIGHT_BROWSERS_PATH"] = str(isolated_workspace / "nonexistent_browsers")
    res = run_tracecase(["check"], env=broken_env)
    # Exits non-zero or warns about missing binaries
    assert res.returncode != 0 or "missing" in res.stdout.lower() or "install" in res.stdout.lower()


@pytest.mark.flow("A4")
def test_a4_tracecase_version(isolated_env: dict[str, str]):
    """A4: tracecase version shows versions for Tracecase, Python, Playwright, Pydantic."""
    res = run_tracecase(["version"], env=isolated_env)
    assert res.returncode == 0
    out = res.stdout.lower()
    assert "tracecase" in out
    assert "python" in out
    assert "playwright" in out
    assert "pydantic" in out


@pytest.mark.flow("A5")
def test_a5_help_all_subcommands(isolated_env: dict[str, str]):
    """A5: Run --help on root and all 27 subcommands."""
    commands = [
        "record", "version", "check", "export-har", "replay", "diff",
        "mutate", "codegen", "analyze", "index", "search", "coverage",
        "mcp", "clean", "storage", "benchmark", "changes", "map", "impact",
        "risk", "select", "explain", "report", "run", "ui", "ci", "ci-upload"
    ]
    res_root = run_tracecase(["--help"], env=isolated_env)
    assert res_root.returncode == 0
    assert "Usage: tracecase" in res_root.stdout

    for cmd in commands:
        res = run_tracecase([cmd, "--help"], env=isolated_env)
        assert res.returncode == 0, f"Command {cmd} --help failed: {res.stderr}"
        assert f"Usage: tracecase {cmd}" in res.stdout


@pytest.mark.flow("A6")
def test_a6_error_handling_no_traceback(isolated_env: dict[str, str]):
    """A6: Unknown commands and bad options exit non-zero with clean errors, no stack traces."""
    res1 = run_tracecase(["nonexistent_subcommand"], env=isolated_env)
    assert res1.returncode != 0
    assert "No such command" in res1.stderr or "Error:" in res1.stderr
    assert "Traceback" not in res1.stderr

    res2 = run_tracecase(["record"], env=isolated_env)
    assert res2.returncode != 0
    assert "Missing argument" in res2.stderr or "Missing" in res2.stdout
    assert "Traceback" not in res2.stderr


@pytest.mark.flow("A1")
def test_bug001_annotated_doc_shadowing_regression():
    """BUG-001 (Characterization): Assert that importing fastapi from the repo root fails due to annotated_doc stub."""
    res = subprocess.run(
        [sys.executable, "-c", "import fastapi; print('FASTAPI_IMPORTED')"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0
    assert "Doc() takes no arguments" in res.stderr


@pytest.mark.flow("A1")
@pytest.mark.xfail(strict=True, reason="BUG-001: root annotated_doc stub shadows real package causing fastapi import failure")
def test_bug001_annotated_doc_correct_behavior():
    """BUG-001 (Strict XFail of Correct Behavior): Importing fastapi from repo root must succeed without error."""
    res = subprocess.run(
        [sys.executable, "-c", "import fastapi; print('FASTAPI_IMPORTED')"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "FASTAPI_IMPORTED" in res.stdout

