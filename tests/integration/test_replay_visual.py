"""Integration tests for replay visual regression diffing."""

from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from tracecase.models import ElementInfo, Step, TestCase
from tracecase.replay.engine import ReplayEngine


def _element(selector: str, tag: str = "button", text: str = "Click") -> ElementInfo:
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
async def test_replay_with_visual_diff(temp_dir: Path) -> None:
    # 1. Create a dummy baseline screenshot
    screenshots_dir = temp_dir / "screenshots"
    screenshots_dir.mkdir()
    baseline_img = screenshots_dir / "001.png"
    Image.new("RGB", (1280, 720), (255, 255, 255)).save(baseline_img, format="PNG")

    tc = TestCase(
        id="tc_vis",
        name="Visual Test",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url="data:text/html,<html><body style='background:%23ffffff;'><button id='btn'>Click</button></body></html>",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=[
            Step(
                number=1,
                timestamp=datetime(2025, 1, 1, 12, 0, 1),
                action_type="click",
                element=_element("#btn"),
                screenshot_path=baseline_img,
                description_short="Click button",
                description_detailed="Click the button",
                console_logs=[],
                network_requests=[],
                page_errors=[],
            )
        ],
        console_logs=[],
        network_requests=[],
        page_errors=[],
        total_duration=1.0,
        total_steps=1,
    )

    out_dir = temp_dir / "out"
    engine = ReplayEngine(
        tc,
        output_dir=out_dir,
        visual_diff=True,
        diff_threshold=5.0,  # generous threshold
    )
    result = await engine.run()

    assert result.status == "passed"
    assert len(result.visual_diffs) == 1
    diff = result.visual_diffs[0]
    assert diff.passed is True
    assert diff.total_pixels == 1280 * 720


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_replay_with_visual_diff_fails_threshold(temp_dir: Path) -> None:
    screenshots_dir = temp_dir / "screenshots"
    screenshots_dir.mkdir()
    # Baseline is pure black
    baseline_img = screenshots_dir / "001.png"
    Image.new("RGB", (1280, 720), (0, 0, 0)).save(baseline_img, format="PNG")

    tc = TestCase(
        id="tc_vis_fail",
        name="Visual Test Fail",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        # Page is pure white -> 100% diff
        start_url="data:text/html,<html><body style='background:%23ffffff;'><button id='btn'>Click</button></body></html>",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=[
            Step(
                number=1,
                timestamp=datetime(2025, 1, 1, 12, 0, 1),
                action_type="click",
                element=_element("#btn"),
                screenshot_path=baseline_img,
                description_short="Click button",
                description_detailed="Click the button",
                console_logs=[],
                network_requests=[],
                page_errors=[],
            )
        ],
        console_logs=[],
        network_requests=[],
        page_errors=[],
        total_duration=1.0,
        total_steps=1,
    )

    out_dir = temp_dir / "out_fail"
    engine = ReplayEngine(
        tc,
        output_dir=out_dir,
        visual_diff=True,
        diff_threshold=0.1,
        visual_fail=True,
    )
    result = await engine.run()

    assert result.status == "failed"
    assert result.exit_code == 1
    assert len(result.visual_diffs) == 1
    assert result.visual_diffs[0].passed is False
    assert result.visual_diffs[0].diff_path is not None
    assert Path(result.visual_diffs[0].diff_path).exists()
