"""Tests for multi-page support in models and BrowserManager."""

from datetime import datetime

import pytest

from qa_auto.browser import BrowserManager
from qa_auto.models import Step


def test_step_model_supports_page_id() -> None:
    # 1. Defaults to None
    step1 = Step(
        number=1,
        timestamp=datetime.now(),
        action_type="click",
        description_short="Click",
        description_detailed="Click element",
    )
    assert step1.page_id is None

    # 2. Can be set explicitly
    step2 = Step(
        number=2,
        timestamp=datetime.now(),
        action_type="click",
        page_id=1,
        description_short="Click on popup",
        description_detailed="Click element on popup tab",
    )
    assert step2.page_id == 1


@pytest.mark.asyncio
async def test_browser_manager_context_and_pages() -> None:
    bm = BrowserManager(headless=True)
    try:
        page1 = await bm.start()
        assert bm.context is not None
        assert page1 in bm.pages
        assert len(bm.pages) == 1

        # Open a second page/tab
        page2 = await bm.context.new_page()
        assert len(bm.pages) == 2
        assert page2 in bm.pages
    finally:
        await bm.close()
