"""Tests for CLI analyze command."""

from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from tracecase.cli import app
from tracecase.models import TestCase

runner = CliRunner()


def _write_testcase(path: Path) -> Path:
    testcase = TestCase(
        id="tc_cli_analyze",
        name="Cart Checkout",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url="https://example.com/cart",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=[],
        console_logs=[],
        network_requests=[],
        page_errors=[],
        total_duration=0.0,
        total_steps=0,
    )
    path.write_text(testcase.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_analyze_help() -> None:
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "testcase" in result.stdout.lower()
    assert "--ai" in result.stdout
    assert "--provider" in result.stdout


def test_analyze_runs_heuristics_default(temp_dir: Path) -> None:
    tc_path = _write_testcase(temp_dir / "testcase.json")
    result = runner.invoke(app, ["analyze", str(tc_path)])

    assert result.exit_code == 0
    assert "Analysis Results" in result.stdout
    assert (temp_dir / "analysis.json").exists()


def test_analyze_missing_file_exits_2(temp_dir: Path) -> None:
    result = runner.invoke(app, ["analyze", str(temp_dir / "missing.json")])
    assert result.exit_code == 2
