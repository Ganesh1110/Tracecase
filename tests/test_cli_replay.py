"""Tests for replay-related CLI commands."""

import json
from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from qa_auto.cli import app
from qa_auto.models import TestCase

runner = CliRunner()


def _write_testcase(path: Path) -> Path:
    testcase = TestCase(
        id="tc_cli",
        name="CLI",
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


def test_replay_help_lists_options() -> None:
    result = runner.invoke(app, ["replay", "--help"])

    assert result.exit_code == 0
    assert "testcase" in result.stdout.lower()
    assert "--heal" in result.stdout
    assert "--from-har" in result.stdout


def test_replay_missing_file_exits_2(temp_dir: Path) -> None:
    result = runner.invoke(app, ["replay", str(temp_dir / "missing.json")])

    assert result.exit_code == 2


def test_export_har_creates_file(temp_dir: Path) -> None:
    testcase_path = _write_testcase(temp_dir / "testcase.json")
    output_path = temp_dir / "network.har"

    result = runner.invoke(
        app,
        ["export-har", str(testcase_path), "-o", str(output_path)],
    )

    assert result.exit_code == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["log"]["version"] == "1.2"
    assert data["log"]["entries"] == []


def test_export_har_missing_file_exits_2(temp_dir: Path) -> None:
    result = runner.invoke(app, ["export-har", str(temp_dir / "missing.json")])

    assert result.exit_code == 2
