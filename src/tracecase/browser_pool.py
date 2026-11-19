"""Context-isolated browser pool for Tracecase Studio.

Maintains warm Playwright Browser processes owned by the central execution manager,
while guaranteeing 100% strict context isolation: each execution and retry attempt
receives a fresh, isolated BrowserContext and Page that is safely destroyed upon completion.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Literal, cast

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from tracecase.browser import BrowserType

logger = logging.getLogger("tracecase.browser_pool")


class BrowserPool:
    """Centralized, context-isolated Playwright browser lifecycle manager.

    Invariants:
    1. Centrally owned by the ExecutionOrchestrator.
    2. Maintains at most one warm Playwright Browser process per (browser_type, headless) key.
    3. Strict Context Isolation:
       - Every test execution receives a brand new BrowserContext via browser.new_context().
       - Every retry attempt receives a fresh, isolated BrowserContext.
       - BrowserContexts and Pages are NEVER shared between workers, runs, or retries.
    4. Crash Recovery & Disconnect Resilience:
       - Disconnected or crashed browsers are detected via is_connected() and disconnect hooks,
         safely purged, and re-launched cleanly on demand.
    5. Safe Shutdown:
       - Active contexts are closed before terminating browser processes.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._playwrights: dict[str, Playwright] = {}
        self._browsers: dict[str, Browser] = {}
        self._active_contexts: dict[str, set[BrowserContext]] = {}
        self._context_to_key: dict[int, str] = {}
        self._is_shutting_down = False

    def _pool_key(self, browser_type: str, headless: bool) -> str:
        return f"{browser_type}_{'headless' if headless else 'headed'}"

    def is_browser_active(self, browser_type: str = "chromium", headless: bool = True) -> bool:
        """Check whether a managed browser process is currently running and connected."""
        key = self._pool_key(browser_type, headless)
        browser = self._browsers.get(key)
        return bool(browser and browser.is_connected())

    def get_active_browser_count(self) -> int:
        """Return the number of connected browser processes."""
        return sum(1 for b in self._browsers.values() if b and b.is_connected())

    def get_browser(self, browser_type: str = "chromium", headless: bool = True) -> Browser | None:
        """Return the active Browser instance for the given configuration if running."""
        key = self._pool_key(browser_type, headless)
        return self._browsers.get(key)

    def get_active_context_count(self, browser_type: str = "chromium", headless: bool = True) -> int:
        """Return the number of in-flight active contexts for the specified browser."""
        key = self._pool_key(browser_type, headless)
        return len(self._active_contexts.get(key, set()))

    def get_status(self) -> dict[str, Any]:
        """Return a summary of pool health and active context allocations."""
        res: dict[str, Any] = {}
        for key, browser in self._browsers.items():
            res[key] = {
                "connected": browser.is_connected() if browser else False,
                "active_contexts": len(self._active_contexts.get(key, set())),
            }
        return res

    def _handle_disconnect(self, key: str) -> None:
        """Handle unexpected browser process termination or crash."""
        if self._is_shutting_down:
            return
        logger.warning("Browser process for %s disconnected or crashed unexpectedly.", key)
        self._browsers.pop(key, None)
        # Clear tracked contexts for this dead browser instance
        dead_contexts = self._active_contexts.pop(key, set())
        for ctx in dead_contexts:
            self._context_to_key.pop(id(ctx), None)

    async def _get_or_create_browser(self, browser_type: str, headless: bool) -> Browser:
        """Acquire existing warm browser or launch a new one under lock."""
        key = self._pool_key(browser_type, headless)

        # Check if current browser is alive
        existing = self._browsers.get(key)
        if existing is not None:
            if existing.is_connected():
                return existing
            logger.info("Discarding disconnected browser instance for %s", key)
            self._handle_disconnect(key)

        # Launch fresh Playwright and Browser instance
        pw = await async_playwright().start()
        self._playwrights[key] = pw

        launcher = getattr(pw, browser_type, None)
        if launcher is None:
            await pw.stop()
            self._playwrights.pop(key, None)
            raise ValueError(f"Unsupported browser type: {browser_type}")

        logger.info("Launching pooled %s process (headless=%s)", browser_type, headless)
        browser: Browser = await launcher.launch(headless=headless)

        # Hook disconnection callback for crash detection
        browser.on("disconnected", lambda: self._handle_disconnect(key))

        self._browsers[key] = browser
        self._active_contexts[key] = set()
        return browser

    async def acquire_context(
        self,
        browser_type: str = "chromium",
        headless: bool = True,
        viewport: tuple[int, int] = (1280, 720),
        timeout: int = 30000,
    ) -> tuple[BrowserContext, Page]:
        """Create a fresh, completely isolated BrowserContext and Page on the managed browser.

        Guarantees:
        - 100% separate cookie jar, cache, storage, and DOM state.
        - The underlying browser process is reused across tests if healthy.
        """
        if self._is_shutting_down:
            raise RuntimeError("BrowserPool is shutting down. Cannot allocate new contexts.")

        key = self._pool_key(browser_type, headless)

        async with self._lock:
            browser = await self._get_or_create_browser(browser_type, headless)

        # Create isolated context and page
        context = await browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
        )
        context.set_default_timeout(timeout)
        page = await context.new_page()

        # Track active allocation
        async with self._lock:
            if key not in self._active_contexts:
                self._active_contexts[key] = set()
            self._active_contexts[key].add(context)
            self._context_to_key[id(context)] = key

        return context, page

    async def release_context(
        self,
        context: BrowserContext | None,
        browser_type: str | None = None,
        headless: bool | None = None,
    ) -> None:
        """Safely close and destroy a BrowserContext, releasing all associated pages and resources."""
        if context is None:
            return

        ctx_id = id(context)
        key = self._context_to_key.pop(ctx_id, None)

        if key and key in self._active_contexts:
            self._active_contexts[key].discard(context)

        with contextlib.suppress(Exception):
            await context.close()

    async def close_browser(self, browser_type: str, headless: bool = True, force: bool = False) -> None:
        """Close a specific browser process and all its remaining contexts."""
        key = self._pool_key(browser_type, headless)
        async with self._lock:
            browser = self._browsers.pop(key, None)
            pw = self._playwrights.pop(key, None)
            contexts = self._active_contexts.pop(key, set())

            for ctx in contexts:
                self._context_to_key.pop(id(ctx), None)
                with contextlib.suppress(Exception):
                    await ctx.close()

            if browser:
                with contextlib.suppress(Exception):
                    await browser.close()

            if pw:
                with contextlib.suppress(Exception):
                    await pw.stop()

    async def simulate_crash(self, browser_type: str = "chromium", headless: bool = True) -> None:
        """For testing only: forcibly close the browser process to verify crash recovery."""
        key = self._pool_key(browser_type, headless)
        browser = self._browsers.get(key)
        if browser:
            # Forcibly close the browser connection
            await browser.close()

    async def shutdown(self) -> None:
        """Gracefully close all managed contexts, browser processes, and Playwright drivers."""
        self._is_shutting_down = True
        logger.info("Shutting down BrowserPool...")

        async with self._lock:
            # 1. Close all active contexts
            for key, contexts in list(self._active_contexts.items()):
                for ctx in list(contexts):
                    with contextlib.suppress(Exception):
                        await ctx.close()
            self._active_contexts.clear()
            self._context_to_key.clear()

            # 2. Close all browser processes
            for key, browser in list(self._browsers.items()):
                with contextlib.suppress(Exception):
                    await browser.close()
            self._browsers.clear()

            # 3. Stop all Playwright drivers
            for key, pw in list(self._playwrights.items()):
                with contextlib.suppress(Exception):
                    await pw.stop()
            self._playwrights.clear()

        self._is_shutting_down = False
        logger.info("BrowserPool shutdown complete.")
