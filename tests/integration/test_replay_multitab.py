"""Integration tests for replaying multi-tab and popup flows."""

from datetime import datetime
from pathlib import Path

import pytest

from tracecase.models import ElementInfo, Step, TestCase
from tracecase.replay.engine import ReplayEngine


def _element(selector: str, tag: str = "button", text: str = "Open") -> ElementInfo:
    return ElementInfo(
        selector=selector,
        xpath=f"//*[@id='{selector.lstrip('#')}']",
        tag_name=tag,
        text=text,
        attributes={"id": selector.lstrip("#")},
        bounding_box={"x": 10, "y": 10, "width": 80, "height": 30},
    )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_replay_across_multiple_tabs(temp_dir: Path) -> None:
    # Page 1 has a button that opens a popup window
    html_main = (
        "data:text/html,"
        "<html><body>"
        "<button id='open-btn' onclick=\"const w = window.open('about:blank', '_blank'); w.document.write('<button id=popup-btn>Popup Click</button>'); w.document.close();\">Open Tab</button>"
        "</body></html>"
    )

    tc = TestCase(
        id="tc_multitab",
        name="Multi Tab Flow",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url=html_main,
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=[
            # Step 1: Click button on Tab 0 (opens Tab 1)
            Step(
                number=1,
                timestamp=datetime(2025, 1, 1, 12, 0, 1),
                action_type="click",
                element=_element("#open-btn", text="Open Tab"),
                page_id=0,
                description_short="Click open popup",
                description_detailed="Open new tab with window.open",
                console_logs=[],
                network_requests=[],
                page_errors=[],
            ),
            # Step 2: Click button on Tab 1 (the popup)
            Step(
                number=2,
                timestamp=datetime(2025, 1, 1, 12, 0, 2),
                action_type="click",
                element=_element("#popup-btn", text="Popup Click"),
                page_id=1,
                description_short="Click inside popup",
                description_detailed="Click the button on Tab 1",
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

    engine = ReplayEngine(tc, output_dir=temp_dir / "out")
    result = await engine.run()

    assert result.status == "passed"
    assert result.exit_code == 0
    assert len(result.steps) == 2
    assert result.steps[0].status == "passed"
    assert result.steps[1].status == "passed"
