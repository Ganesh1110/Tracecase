"""Integration test executing generated pytest code against the local server."""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from qa_auto.codegen.pytest_exporter import generate_pytest_code
from qa_auto.models import ElementInfo, Step, TestCase


@pytest.mark.integration
@pytest.mark.slow
def test_generated_pytest_file_runs_and_passes(html_server: str, temp_dir: Path) -> None:
    element = ElementInfo(
        selector="#load",
        xpath="//*[@id='load']",
        tag_name="button",
        text="Load",
        attributes={"id": "load"},
        bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
    )
    step = Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=element,
        description_short="Click Load",
        description_detailed="Click Load",
    )
    testcase = TestCase(
        id="tc_exec",
        name="Live Server Flow",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url=html_server,
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=[step],
        console_logs=[],
        network_requests=[],
        page_errors=[],
        total_duration=1.0,
        total_steps=1,
    )

    code = generate_pytest_code(testcase)
    test_file = temp_dir / "test_live_server.py"
    test_file.write_text(code, encoding="utf-8")

    # Execute the generated file with pytest
    res = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-v"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert res.returncode == 0
    assert "1 passed" in res.stdout
