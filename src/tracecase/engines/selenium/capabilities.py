"""Selenium WebDriver capability specification (Platform Expansion A)."""

from __future__ import annotations

import sys

from tracecase.engines.capabilities import (
    BrowserChannel,
    CapabilityStatus,
    EngineCapabilityProfile,
    FeatureCapability,
    PlatformType,
)


def get_selenium_capability_profile() -> EngineCapabilityProfile:
    """Return declared capabilities for Selenium WebDriver adapter."""
    is_mac = sys.platform == "darwin"

    platforms = {
        PlatformType.DESKTOP_WEB.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        PlatformType.MOBILE_WEB.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        PlatformType.ANDROID_NATIVE.value: CapabilityStatus.UNSUPPORTED,
        PlatformType.IOS_NATIVE.value: CapabilityStatus.UNSUPPORTED,
    }

    browsers = {
        BrowserChannel.CHROME.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        BrowserChannel.FIREFOX.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        BrowserChannel.MSEDGE.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        BrowserChannel.SAFARI.value: CapabilityStatus.REQUIRES_EXTERNAL_INFRASTRUCTURE if is_mac else CapabilityStatus.UNSUPPORTED,
        BrowserChannel.CHROMIUM.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        BrowserChannel.WEBKIT.value: CapabilityStatus.UNSUPPORTED,
    }

    features = {
        FeatureCapability.RECORDING.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        FeatureCapability.REPLAY.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        FeatureCapability.NETWORK_INSPECTION.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        FeatureCapability.CONSOLE_LOGS.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        FeatureCapability.CDP_TRACING.value: CapabilityStatus.UNSUPPORTED,
        FeatureCapability.MOBILE_EMULATION.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        FeatureCapability.REAL_DEVICE.value: CapabilityStatus.UNSUPPORTED,
        FeatureCapability.HEADLESS.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        FeatureCapability.VISUAL_DIFF.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
    }

    notes = [
        "Planned for Platform Expansion A: Selenium WebDriver adapter.",
        "Will provide real Apple Safari browser coverage on macOS via safaridriver.",
        "Engine adapter is currently in design specification stage and not yet operational.",
    ]

    return EngineCapabilityProfile(
        engine_id="selenium",
        display_name="Selenium WebDriver",
        version=None,
        is_operational=False,
        roadmap_phase="Platform Expansion A (Planned)",
        platforms=platforms,
        browsers=browsers,
        features=features,
        notes=notes,
    )
