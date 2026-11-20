"""Managed Chromium streaming session coordinating Playwright, CDP screencast, and lifecycle."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from tracecase.streaming.input import dispatch_input_event
from tracecase.streaming.models import (
    InputEvent,
    ScreencastFrame,
    StreamSessionConfig,
    StreamSessionInfo,
    StreamSessionState,
)
from tracecase.streaming.screencast import CDPScreencastManager, FrameCallback

logger = logging.getLogger("tracecase.streaming.session")


class ManagedChromiumSession:
    """
    Manages a single dedicated headed/headless Chromium browser instance for live Studio streaming.
    
    Guarantees:
    - Dedicated browser process and isolated context per session.
    - Zero shared state with Phase 9.1.3 sandbox validation sessions.
    - Clean process termination on close (no orphaned processes).
    """

    def __init__(self, config: StreamSessionConfig) -> None:
        self.config = config
        self.session_id = config.session_id
        self.state = StreamSessionState.INITIALIZING
        self.started_at = datetime.now()
        self.error: str | None = None

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._screencast: CDPScreencastManager | None = None
        self._listeners: list[FrameCallback] = []
        self._lock = asyncio.Lock()

    @property
    def page(self) -> Page | None:
        return self._page

    @property
    def screencast(self) -> CDPScreencastManager | None:
        return self._screencast

    def add_frame_listener(self, callback: FrameCallback) -> None:
        """Register a callback to receive live screencast frames."""
        if callback not in self._listeners:
            self._listeners.append(callback)
        if self._screencast:
            self._screencast.add_listener(callback)

    def remove_frame_listener(self, callback: FrameCallback) -> None:
        """Remove a registered frame callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)
        if self._screencast:
            self._screencast.remove_listener(callback)

    async def launch(self) -> None:
        """Launch managed Chromium instance, initialize page, and start CDP screencast."""
        async with self._lock:
            if self.state == StreamSessionState.ACTIVE:
                return

            try:
                logger.info(
                    "Launching managed Chromium session %s (url=%s, headless=%s, viewport=%dx%d)",
                    self.session_id,
                    self.config.url,
                    self.config.headless,
                    self.config.viewport_width,
                    self.config.viewport_height,
                )

                self._playwright = await async_playwright().start()

                # Launch Chromium (headed or headless as configured)
                # Arguments optimize for smooth CDP screencasting and low latency
                launch_args = [
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                ]

                self._browser = await self._playwright.chromium.launch(
                    headless=self.config.headless,
                    args=launch_args,
                )

                self._context = await self._browser.new_context(
                    viewport={
                        "width": self.config.viewport_width,
                        "height": self.config.viewport_height,
                    },
                    device_scale_factor=1,
                    user_agent="Mozilla/5.0 Tracecase Embedded Studio (Chromium)",
                )

                self._page = await self._context.new_page()

                # Navigate to initial URL if provided and not blank
                target_url = self.config.url.strip() if self.config.url else "about:blank"
                if target_url and target_url != "about:blank":
                    try:
                        await self._page.goto(
                            target_url,
                            timeout=self.config.timeout_ms,
                            wait_until="domcontentloaded",
                        )
                    except Exception as nav_err:
                        logger.warning("Initial navigation error for %s: %s", target_url, nav_err)

                # Initialize CDP Screencast Manager
                self._screencast = CDPScreencastManager(
                    page=self._page,
                    format=self.config.format,
                    quality=self.config.quality,
                    max_width=self.config.viewport_width,
                    max_height=self.config.viewport_height,
                    every_nth_frame=self.config.every_nth_frame,
                )
                for listener in self._listeners:
                    self._screencast.add_listener(listener)

                await self._screencast.start()

                self.state = StreamSessionState.ACTIVE
                logger.info("Managed Chromium session %s is now ACTIVE", self.session_id)

            except Exception as exc:
                self.state = StreamSessionState.FAILED
                self.error = str(exc)
                logger.exception("Failed launching managed Chromium session %s: %s", self.session_id, exc)
                await self._cleanup()
                raise

    async def get_info(self) -> StreamSessionInfo:
        """Return structured session telemetry and status."""
        frames_sent = self._screencast.frames_captured if self._screencast else 0
        total_bytes = self._screencast.total_bytes if self._screencast else 0
        last_frame = self._screencast.last_frame_at if self._screencast else None
        current_url = self._page.url if self._page else self.config.url

        return StreamSessionInfo(
            session_id=self.session_id,
            state=self.state,
            url=current_url,
            browser=self.config.browser,
            headless=self.config.headless,
            viewport_width=self.config.viewport_width,
            viewport_height=self.config.viewport_height,
            started_at=self.started_at,
            last_frame_at=last_frame,
            frames_sent=frames_sent,
            total_bytes_streamed=total_bytes,
            owner_id=self.config.owner_id,
            error=self.error,
        )

    async def handle_input(self, event: InputEvent) -> None:
        """Forward validated user input event directly to active Playwright page."""
        if self.state != StreamSessionState.ACTIVE or not self._page:
            logger.warning(
                "Dropped input event %s: session %s is not ACTIVE",
                event.event_type,
                self.session_id,
            )
            return

        browser_vp = (self.config.viewport_width, self.config.viewport_height)
        await dispatch_input_event(
            page=self._page, event=event, browser_viewport=browser_vp
        )

    async def resize_viewport(self, width: int, height: int) -> None:
        """Resize browser viewport and adjust screencast frame dimensions."""
        if not self._page:
            return

        w = max(320, min(width, 3840))
        h = max(240, min(height, 2160))
        self.config.viewport_width = w
        self.config.viewport_height = h
        await self._page.set_viewport_size({"width": w, "height": h})
        if self._screencast:
            self._screencast.max_width = w
            self._screencast.max_height = h

    async def close(self) -> None:
        """Gracefully terminate screencast, close context, and reap browser process."""
        async with self._lock:
            if self.state in (StreamSessionState.STOPPED, StreamSessionState.FAILED):
                return

            logger.info("Stopping managed Chromium session %s", self.session_id)
            self.state = StreamSessionState.STOPPED
            await self._cleanup()

    async def _cleanup(self) -> None:
        """Internal cleanup ensuring all resources and processes are released."""
        if self._screencast:
            try:
                await self._screencast.stop()
            except Exception as exc:
                logger.debug("Error stopping screencast during cleanup: %s", exc)
            self._screencast = None

        if self._page:
            try:
                await self._page.close()
            except Exception as exc:
                logger.debug("Error closing page: %s", exc)
            self._page = None

        if self._context:
            try:
                await self._context.close()
            except Exception as exc:
                logger.debug("Error closing context: %s", exc)
            self._context = None

        if self._browser:
            try:
                await self._browser.close()
            except Exception as exc:
                logger.debug("Error closing browser: %s", exc)
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logger.debug("Error stopping playwright: %s", exc)
            self._playwright = None

        logger.info("Managed Chromium session %s cleanup complete", self.session_id)
