"""Global Engine Registry for discovering, verifying, and selecting automation engines."""

from __future__ import annotations

import logging
from typing import Any

from tracecase.engines.appium.capabilities import get_appium_capability_profile
from tracecase.engines.base import BaseAutomationEngine
from tracecase.engines.capabilities import (
    EngineCapabilityProfile,
    HostEnvironmentCapabilities,
    inspect_host_environment,
)
from tracecase.engines.playwright.adapter import PlaywrightEngineAdapter
from tracecase.engines.selenium.capabilities import get_selenium_capability_profile

logger = logging.getLogger("tracecase.engines.registry")


class EngineRegistry:
    """
    Central catalog of automation engines and host capability discovery.
    
    Guarantees:
    - Only genuinely operational engines (Playwright in Phase 9.1.4) can be instantiated.
    - Planned engines (Selenium, Appium) expose verified capability profiles without pretending to be runnable.
    - Accurately reports host-level developer infrastructure (macOS/Xcode, Android SDK).
    """

    def __init__(self) -> None:
        self._operational_engines: dict[str, BaseAutomationEngine] = {
            "playwright": PlaywrightEngineAdapter(),
        }

    def list_engines(self) -> list[str]:
        """Return all cataloged engine identifiers."""
        return ["playwright", "selenium", "appium"]

    def is_engine_operational(self, engine_id: str) -> bool:
        """Check if an engine has an active, operational adapter installed."""
        adapter = self._operational_engines.get(engine_id.lower().strip())
        return bool(adapter and adapter.is_operational)

    def get_engine(self, engine_id: str) -> BaseAutomationEngine:
        """
        Retrieve an operational automation engine adapter.
        
        Raises RuntimeError if the requested engine is planned but not yet operational.
        """
        norm_id = engine_id.lower().strip()
        if norm_id in self._operational_engines:
            return self._operational_engines[norm_id]

        if norm_id == "selenium":
            raise RuntimeError(
                "Selenium WebDriver adapter is planned for Platform Expansion A and is not yet operational. "
                "Use Playwright for web test execution in Phase 9.1.4."
            )
        elif norm_id == "appium":
            raise RuntimeError(
                "Appium mobile automation adapter is planned for Platform Expansion B and is not yet operational."
            )
        else:
            raise ValueError(f"Unknown automation engine: '{engine_id}'. Valid choices: {self.list_engines()}")

    async def get_engine_profile(self, engine_id: str) -> EngineCapabilityProfile:
        """Get the capability profile for an individual engine."""
        norm_id = engine_id.lower().strip()
        if norm_id == "playwright":
            return await self._operational_engines["playwright"].get_capabilities()
        elif norm_id == "selenium":
            return get_selenium_capability_profile()
        elif norm_id == "appium":
            return get_appium_capability_profile()
        else:
            raise ValueError(f"Unknown automation engine: '{engine_id}'")

    async def get_host_capabilities(self) -> HostEnvironmentCapabilities:
        """Evaluate and return verified host capabilities across all cataloged engines."""
        host_meta = inspect_host_environment()

        profiles: dict[str, EngineCapabilityProfile] = {
            "playwright": await self.get_engine_profile("playwright"),
            "selenium": await self.get_engine_profile("selenium"),
            "appium": await self.get_engine_profile("appium"),
        }

        return HostEnvironmentCapabilities(
            os_platform=host_meta["os_platform"],
            os_release=host_meta["os_release"],
            architecture=host_meta["architecture"],
            has_xcode=host_meta["has_xcode"],
            has_android_sdk=host_meta["has_android_sdk"],
            engines=profiles,
        )


# Global singleton registry instance
engine_registry = EngineRegistry()


def get_engine_registry() -> EngineRegistry:
    """Access the global engine registry."""
    return engine_registry
