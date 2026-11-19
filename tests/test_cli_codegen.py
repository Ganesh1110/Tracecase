"""Tests for CLI codegen command."""

from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from tracecase.cli import app
from tracecase.models import TestCase

runner = CliRunner()


def _write_testcase(path: Path) -> Path:
    testcase = TestCase(
        id="tc_cli_codegen",
        name="Checkout Flow",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url="https://example.com",
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


def test_codegen_help() -> None:
    result = runner.invoke(app, ["codegen", "--help"])
    assert result.exit_code == 0
    assert "testcase" in result.stdout.lower()
    assert "--output" in result.stdout


def test_codegen_creates_python_file(temp_dir: Path) -> None:
    tc_path = _write_testcase(temp_dir / "testcase.json")
    out_file = temp_dir / "test_checkout.py"

    result = runner.invoke(app, ["codegen", str(tc_path), "-o", str(out_file)])

    assert result.exit_code == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "async def test_checkout_flow" in content


def test_codegen_missing_file_exits_2(temp_dir: Path) -> None:
    result = runner.invoke(app, ["codegen", str(temp_dir / "missing.json")])
    assert result.exit_code == 2
