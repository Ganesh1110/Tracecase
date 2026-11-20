"""Playwright automation engine adapter wrapping existing Tracecase infrastructure."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from tracecase.browser import BrowserManager
from tracecase.browser_pool import BrowserPool
from tracecase.engines.base import BaseAutomationEngine, BaseSession, SessionRequest
from tracecase.engines.capabilities import (
    BrowserChannel,
    CapabilityStatus,
    EngineCapabilityProfile,
    FeatureCapability,
    PlatformType,
)
from tracecase.models import TestCase
from tracecase.recorder import Recorder
from tracecase.replay.engine import ReplayEngine


class PlaywrightSession(BaseSession):
    """Active Playwright browser session wrapper."""

    def __init__(self, session_id: str, manager: BrowserManager) -> None:
        super().__init__(session_id=session_id, engine_id="playwright")
        self.manager = manager

    async def navigate(self, url: str) -> None:
        if self.manager.page:
            await self.manager.page.goto(url, wait_until="domcontentloaded")

    async def take_screenshot(self, path: Path | str | None = None) -> bytes:
        if not self.manager.page:
            raise RuntimeError("No active Playwright page in session.")
        raw_bytes = await self.manager.page.screenshot()
        if path:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw_bytes)
        return raw_bytes

    async def close(self) -> None:
        await self.manager.close()


class PlaywrightEngineAdapter(BaseAutomationEngine):
    """
    Production operational adapter for Playwright.
    
    Delegates to existing Tracecase BrowserManager, BrowserPool,
    Recorder, and ReplayEngine without modifying their internal pipelines.
    """

    def __init__(self) -> None:
        self._active_sessions: dict[str, PlaywrightSession] = {}

    @property
    def engine_id(self) -> str:
        return "playwright"

    @property
    def display_name(self) -> str:
        return "Playwright"

    @property
    def is_operational(self) -> bool:
        return True

    async def get_capabilities(self) -> EngineCapabilityProfile:
        """Return the verified capabilities of Playwright on this host."""
        import playwright
        pw_version = getattr(playwright, "__version__", "1.40+")

        platforms = {
            PlatformType.DESKTOP_WEB.value: CapabilityStatus.SUPPORTED,
            PlatformType.MOBILE_WEB.value: CapabilityStatus.SUPPORTED,
            PlatformType.ANDROID_NATIVE.value: CapabilityStatus.UNSUPPORTED,
            PlatformType.IOS_NATIVE.value: CapabilityStatus.UNSUPPORTED,
        }

        browsers = {
            BrowserChannel.CHROMIUM.value: CapabilityStatus.SUPPORTED,
            BrowserChannel.CHROME.value: CapabilityStatus.SUPPORTED,
            BrowserChannel.FIREFOX.value: CapabilityStatus.SUPPORTED,
            BrowserChannel.WEBKIT.value: CapabilityStatus.SUPPORTED,
            BrowserChannel.MSEDGE.value: CapabilityStatus.SUPPORTED,
            BrowserChannel.SAFARI.value: CapabilityStatus.UNSUPPORTED,
        }

        features = {
            FeatureCapability.RECORDING.value: CapabilityStatus.SUPPORTED,
            FeatureCapability.REPLAY.value: CapabilityStatus.SUPPORTED,
            FeatureCapability.NETWORK_INSPECTION.value: CapabilityStatus.SUPPORTED,
            FeatureCapability.CONSOLE_LOGS.value: CapabilityStatus.SUPPORTED,
            FeatureCapability.CDP_TRACING.value: CapabilityStatus.SUPPORTED,
            FeatureCapability.MOBILE_EMULATION.value: CapabilityStatus.SUPPORTED,
            FeatureCapability.REAL_DEVICE.value: CapabilityStatus.UNSUPPORTED,
            FeatureCapability.HEADLESS.value: CapabilityStatus.SUPPORTED,
            FeatureCapability.VISUAL_DIFF.value: CapabilityStatus.SUPPORTED,
        }

        notes = [
            "Playwright WebKit runs the open-source WebKit engine, not Apple's native Safari browser.",
            "Native mobile applications (Android/iOS) are unsupported by Playwright; use Appium.",
            "Full parallel execution supported via Tracecase BrowserPool.",
        ]

        return EngineCapabilityProfile(
            engine_id=self.engine_id,
            display_name=self.display_name,
            version=pw_version,
            is_operational=True,
            roadmap_phase="Phase 9.1.4 (Active Operational)",
            platforms=platforms,
            browsers=browsers,
            features=features,
            notes=notes,
        )

    async def create_session(self, request: SessionRequest) -> BaseSession:
        """Launch a Playwright browser session using BrowserManager."""
        import uuid
        session_id = f"pw_sess_{uuid.uuid4().hex[:8]}"
        manager = BrowserManager(
            browser_type=request.browser,
            headless=request.headless,
            viewport=request.viewport,
            timeout=request.timeout_ms,
        )
        await manager.launch()
        if request.url:
            await manager.new_page(request.url)
        session = PlaywrightSession(session_id=session_id, manager=manager)
        self._active_sessions[session_id] = session
        return session

    def create_recorder(
        self,
        output_dir: Path | str,
        start_url: str,
        name: str = "Recorded Test",
        browser_type: str = "chromium",
        headless: bool = False,
        **kwargs: Any,
    ) -> Recorder:
        """Instantiate standard Tracecase Recorder."""
        return Recorder(
            output_dir=Path(output_dir),
            start_url=start_url,
            name=name,
            browser_type=browser_type,
            headless=headless,
            **kwargs,
        )

    def create_replay_engine(
        self,
        testcase: TestCase,
        browser_type: str | None = None,
        headless: bool = True,
        **kwargs: Any,
    ) -> ReplayEngine:
        """Instantiate standard Tracecase ReplayEngine."""
        return ReplayEngine(
            testcase=testcase,
            browser_type=browser_type,
            headless=headless,
            **kwargs,
        )

    async def shutdown(self) -> None:
        """Close active sessions."""
        for session in list(self._active_sessions.values()):
            try:
                await session.close()
            except Exception:
                pass
        self._active_sessions.clear()
