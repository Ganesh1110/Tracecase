"""Integration tests for HAR route fulfillment."""

import pytest
from playwright.async_api import async_playwright

from qa_auto.replay.har import install_har_routes


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_har_route_serves_recorded_response(html_server: str) -> None:
    har = {
        "log": {
            "version": "1.2",
            "entries": [
                {
                    "request": {
                        "method": "GET",
                        "url": f"{html_server}/api/data",
                    },
                    "response": {
                        "status": 200,
                        "headers": [{"name": "content-type", "value": "application/json"}],
                        "content": {"text": '{"source": "har"}'},
                    },
                }
            ],
        }
    }

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        await install_har_routes(context, har)
        page = await context.new_page()

        await page.goto(html_server)
        await page.click("#load")
        await page.wait_for_function(
            "document.getElementById('out').textContent !== ''",
        )

        assert await page.text_content("#out") == "har"
        await browser.close()
