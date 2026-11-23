"""
Tracecase Injected Control Panel Test Helper (tests/dogfood/helpers/panel.py)

Encapsulates selectors and interaction helpers for the in-browser recording control panel.
Accounts for BUG-006 legacy __qa_ prefixes while providing clean, semantic API.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page


class ControlPanelHelper:
    """Helper for interacting with the injected Tracecase recording control panel."""

    CONTAINER = "#__tracecase_panel__"
    START_BTN = "#__qa_start_btn__"
    STOP_BTN = "#__qa_stop_btn__"
    STATUS_DOT = "#__qa_status_dot__"
    STATUS_TEXT = "#__qa_status_text__"
    STEPS_COUNT = "#__qa_steps_count__"
    MESSAGE = "#__qa_message__"

    def __init__(self, page: "Page") -> None:
        self.page = page

    @property
    def panel(self) -> "Locator":
        return self.page.locator(self.CONTAINER)

    @property
    def start_button(self) -> "Locator":
        return self.page.locator(self.START_BTN)

    @property
    def stop_button(self) -> "Locator":
        return self.page.locator(self.STOP_BTN)

    @property
    def status_dot(self) -> "Locator":
        return self.page.locator(self.STATUS_DOT)

    @property
    def status_text(self) -> "Locator":
        return self.page.locator(self.STATUS_TEXT)

    @property
    def steps_count(self) -> "Locator":
        return self.page.locator(self.STEPS_COUNT)

    async def wait_for_ready(self, timeout: float = 5000) -> None:
        """Wait for control panel to inject into DOM and display ready state."""
        await self.panel.wait_for(state="visible", timeout=timeout)
        await self.start_button.wait_for(state="visible", timeout=timeout)

    async def click_start(self) -> None:
        """Click the Start recording button and wait for recording state."""
        await self.start_button.click()
        await self.stop_button.wait_for(state="visible", timeout=5000)

    async def click_stop(self) -> None:
        """Click the Stop recording button and wait for completion."""
        await self.stop_button.click()

    async def get_recorded_steps_count(self) -> int:
        """Parse step count from the panel step badge (e.g. '3 steps' -> 3)."""
        text = await self.steps_count.inner_text()
        parts = text.strip().split()
        if parts and parts[0].isdigit():
            return int(parts[0])
        return 0
