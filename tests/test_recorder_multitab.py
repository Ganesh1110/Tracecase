"""Tests for multi-tab recording and page tracking."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tracecase.recorder import Recorder


def test_recorder_tracks_multiple_pages(temp_dir: Path) -> None:
    recorder = Recorder(output_dir=temp_dir, start_url="https://example.com")
    assert recorder._pages == []


@pytest.mark.asyncio
async def test_recorder_on_action_with_page_id(temp_dir: Path) -> None:
    recorder = Recorder(output_dir=temp_dir, start_url="https://example.com")
    recorder.is_recording = True

    # Mock page for screenshots
    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value={"x": 0, "y": 0, "width": 10, "height": 10})
    recorder._pages = [mock_page, mock_page]

    # Action performed on tab 1 (popup)
    action_data = {
        "eventType": "click",
        "selector": "#login-popup-btn",
        "tagName": "button",
        "text": "Sign In",
        "boundingBox": {"x": 0, "y": 0, "width": 50, "height": 20},
    }

    await recorder.on_action(action_data, page_id=1)

    assert len(recorder.steps) == 1
    assert recorder.steps[0].page_id == 1
    assert recorder.steps[0].action_type == "click"
