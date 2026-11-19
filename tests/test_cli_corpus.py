"""Tests for corpus CLI commands: index, search, coverage."""

from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from tracecase.cli import app
from tracecase.models import TestCase

runner = CliRunner()


def _write_testcase(path: Path, name: str, url: str) -> Path:
    testcase = TestCase(
        id="tc_cli_corpus",
        name=name,
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url=url,
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


def test_index_and_search_cli_flow(temp_dir: Path) -> None:
    db_file = temp_dir / "test_corpus.db"
    tc_dir = temp_dir / "records"
    tc_dir.mkdir()
    _write_testcase(tc_dir / "testcase.json", "User Payment Flow", "https://checkout.com")

    # 1. Index
    res_index = runner.invoke(app, ["index", str(tc_dir), "--db", str(db_file)])
    assert res_index.exit_code == 0
    assert "Indexed 1 test case" in res_index.stdout

    # 2. Search
    res_search = runner.invoke(app, ["search", "Payment", "--db", str(db_file)])
    assert res_search.exit_code == 0
    assert "User Payment Flow" in res_search.stdout

    # 3. Coverage
    res_cov = runner.invoke(app, ["coverage", "--db", str(db_file)])
    assert res_cov.exit_code == 0
    assert "checkout.com" in res_cov.stdout

    # 4. Clean DB
    assert db_file.exists()
    res_clean = runner.invoke(app, ["clean", "--db-path", str(db_file)])
    assert res_clean.exit_code == 0
    assert "Wiped local corpus database" in res_clean.stdout
    assert not db_file.exists()
