"""Tests for the mutate CLI command."""

from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from tracecase.cli import app
from tracecase.models import ElementInfo, Step, TestCase

runner = CliRunner()


def _element(selector: str, tag: str = "input") -> ElementInfo:
    return ElementInfo(
        selector=selector,
        xpath=f"//*[@id='{selector.lstrip('#')}']",
        tag_name=tag,
        text="",
        attributes={"id": selector.lstrip("#")},
        bounding_box={"x": 10, "y": 10, "width": 80, "height": 30},
    )


def _write_testcase(path: Path) -> Path:
    tc = TestCase(
        id="tc_cli_mutate",
        name="Checkout Flow",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url="https://example.com/checkout",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=[
            Step(
                number=1,
                timestamp=datetime(2025, 1, 1, 12, 0, 1),
                action_type="input",
                element=_element("#coupon"),
                input_value="SUMMER20",
                description_short="Type coupon",
                description_detailed="Type coupon code",
                console_logs=[],
                network_requests=[],
                page_errors=[],
            ),
            Step(
                number=2,
                timestamp=datetime(2025, 1, 1, 12, 0, 2),
                action_type="click",
                element=_element("#apply", tag="button"),
                description_short="Apply coupon",
                description_detailed="Click apply button",
                console_logs=[],
                network_requests=[],
                page_errors=[],
            ),
        ],
        console_logs=[],
        network_requests=[],
        page_errors=[],
        total_duration=2.0,
        total_steps=2,
    )
    path.write_text(tc.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_cli_mutate_success(temp_dir: Path) -> None:
    tc_file = _write_testcase(temp_dir / "testcase.json")
    out_dir = temp_dir / "mutations"

    result = runner.invoke(app, ["mutate", str(tc_file), "-o", str(out_dir), "--limit", "5"])
    assert result.exit_code == 0
    assert "Synthesized" in result.stdout
    assert out_dir.exists()
    assert len(list(out_dir.iterdir())) == 5


def test_cli_mutate_strategy_filter(temp_dir: Path) -> None:
    tc_file = _write_testcase(temp_dir / "testcase.json")
    out_dir = temp_dir / "mutations_actions"

    result = runner.invoke(
        app,
        ["mutate", str(tc_file), "-o", str(out_dir), "--strategy", "actions"],
    )
    assert result.exit_code == 0
    assert "double_click" in result.stdout
    assert len(list(out_dir.iterdir())) == 1


def test_cli_mutate_missing_file_fails(temp_dir: Path) -> None:
    result = runner.invoke(app, ["mutate", str(temp_dir / "missing.json")])
    assert result.exit_code == 2
