"""Browser management for Tracecase."""

from typing import Literal

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

BrowserType = Literal["chromium", "firefox", "webkit", "msedge"]


class BrowserManager:
    """
    Manages Playwright browser lifecycle.

    Handles browser launch, page creation, and cleanup.
    """

    def __init__(
        self,
        browser_type: BrowserType = "chromium",
        headless: bool = False,
        viewport: tuple[int, int] = (1280, 720),
        timeout: int = 30000,
        launch_args: list[str] | None = None,
    ) -> None:
        """
        Initialize browser manager.

        Args:
            browser_type: Browser to use (chromium, firefox, webkit, msedge)
            headless: Run browser without GUI
            viewport: Browser window size (width, height)
            timeout: Default timeout for operations in ms
            launch_args: Additional command line flags for browser launch
        """
        self.browser_type = browser_type
        self.headless = headless
        self.viewport = {"width": viewport[0], "height": viewport[1]}
        self.timeout = timeout
        self.launch_args = launch_args

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def page(self) -> Page:
        """Get the current page."""
        if self._page is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    @property
    def browser(self) -> Browser:
        """Get the browser instance."""
        if self._browser is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._browser

    @property
    def context(self) -> BrowserContext:
        """Get the current browser context."""
        if self._context is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._context

    @property
    def pages(self) -> list[Page]:
        """Get all open pages in the browser context."""
        if self._context is None:
            return []
        return list(self._context.pages)

    async def start(self) -> Page:
        """
        Start browser and create a new page.

        Returns:
            The created Page object
        """
        import sys

        self._playwright = await async_playwright().start()

        if self.browser_type == "msedge":
            launch_kwargs: dict[str, Any] = {"headless": self.headless, "channel": "msedge"}
            if self.launch_args:
                launch_kwargs["args"] = self.launch_args
            self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        elif self.browser_type == "firefox":
            # Playwright's Firefox Nightly.app hits macOS WindowServer/Seatbelt
            # sandbox crashes when launched headed on macOS 26/27; run headless on darwin.
            use_headless = True if sys.platform == "darwin" else self.headless
            launch_kwargs = {"headless": use_headless}
            if self.launch_args:
                launch_kwargs["args"] = self.launch_args
            self._browser = await self._playwright.firefox.launch(**launch_kwargs)
        else:
            launcher = getattr(self._playwright, self.browser_type)
            launch_kwargs = {"headless": self.headless}
            if self.launch_args:
                launch_kwargs["args"] = self.launch_args
            self._browser = await launcher.launch(**launch_kwargs)

        self._context = await self._browser.new_context(
            viewport={"width": self.viewport["width"], "height": self.viewport["height"]},
        )
        self._context.set_default_timeout(self.timeout)
        self._page = await self._context.new_page()

        return self._page

    async def navigate(self, url: str) -> None:
        """
        Navigate to a URL.

        Args:
            url: URL to navigate to
        """
        await self.page.goto(url, wait_until="domcontentloaded")

    async def close(self) -> None:
        """Close browser and cleanup resources."""
        if self._page:
            await self._page.close()
            self._page = None

        if self._context:
            await self._context.close()
            self._context = None

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    def get_user_agent(self) -> str:
        """Get the browser's user agent string."""
        if self._page is None or self._page.context.browser is None:
            return ""
        # This will be populated after page is created
        return str(self._page.context.browser.browser_type.name)

    async def __aenter__(self) -> "BrowserManager":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """Async context manager exit."""
        await self.close()
