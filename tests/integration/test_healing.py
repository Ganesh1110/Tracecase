"""Integration tests for selector healing."""

from datetime import datetime

import pytest
from playwright.async_api import async_playwright

from tracecase.models import ElementInfo, Step
from tracecase.replay.healing import resolve_element


def _step(
    selector: str,
    *,
    attributes: dict[str, str] | None = None,
    text: str = "Submit",
    tag: str = "button",
) -> Step:
    return Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=ElementInfo(
            selector=selector,
            xpath=f"//*[@id='{selector.lstrip('#')}']",
            tag_name=tag,
            text=text,
            attributes=attributes or {},
            bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
        ),
        description_short="Click",
        description_detailed="Click",
    )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_heals_with_data_testid(html_server: str) -> None:
    step = _step("#missing", attributes={"data-testid": "submit-btn"})

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(html_server)

        locator, result = await resolve_element(page, step, heal=True)

        assert locator is not None
        assert result.selector == '[data-testid="submit-btn"]'
        assert result.healed_from == "#missing"
        await browser.close()


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_heals_with_role_and_name(html_server: str) -> None:
    step = _step("#missing", text="Plain")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(html_server)

        locator, result = await resolve_element(page, step, heal=True)

        assert locator is not None
        assert result.selector == 'role=button[name="Plain"]'
        await browser.close()


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_no_healing_returns_none_for_missing_selector(html_server: str) -> None:
    step = _step("#missing", attributes={"data-testid": "submit-btn"})

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(html_server)

        locator, result = await resolve_element(page, step, heal=False)

        assert locator is None
        assert result.selector is None
        assert result.attempts == ["#missing"]
        await browser.close()
