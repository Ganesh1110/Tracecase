"""Appium Mobile Automation capability specification (Platform Expansion B)."""

from __future__ import annotations

import sys

from tracecase.engines.capabilities import (
    BrowserChannel,
    CapabilityStatus,
    EngineCapabilityProfile,
    FeatureCapability,
    PlatformType,
)


def get_appium_capability_profile() -> EngineCapabilityProfile:
    """Return declared capabilities for Appium mobile automation adapter."""
    is_mac = sys.platform == "darwin"

    platforms = {
        PlatformType.ANDROID_NATIVE.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        PlatformType.IOS_NATIVE.value: CapabilityStatus.REQUIRES_EXTERNAL_INFRASTRUCTURE if is_mac else CapabilityStatus.UNSUPPORTED,
        PlatformType.MOBILE_WEB.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        PlatformType.DESKTOP_WEB.value: CapabilityStatus.UNSUPPORTED,
    }

    browsers = {
        BrowserChannel.CHROME.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        BrowserChannel.SAFARI.value: CapabilityStatus.REQUIRES_EXTERNAL_INFRASTRUCTURE if is_mac else CapabilityStatus.UNSUPPORTED,
        BrowserChannel.CHROMIUM.value: CapabilityStatus.UNSUPPORTED,
        BrowserChannel.FIREFOX.value: CapabilityStatus.UNSUPPORTED,
        BrowserChannel.WEBKIT.value: CapabilityStatus.UNSUPPORTED,
        BrowserChannel.MSEDGE.value: CapabilityStatus.UNSUPPORTED,
    }

    features = {
        FeatureCapability.RECORDING.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        FeatureCapability.REPLAY.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        FeatureCapability.NETWORK_INSPECTION.value: CapabilityStatus.UNSUPPORTED,
        FeatureCapability.CONSOLE_LOGS.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        FeatureCapability.CDP_TRACING.value: CapabilityStatus.UNSUPPORTED,
        FeatureCapability.MOBILE_EMULATION.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        FeatureCapability.REAL_DEVICE.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
        FeatureCapability.HEADLESS.value: CapabilityStatus.UNSUPPORTED,
        FeatureCapability.VISUAL_DIFF.value: CapabilityStatus.NOT_YET_IMPLEMENTED,
    }

    notes = [
        "Planned for Platform Expansion B: Appium mobile automation adapter.",
        "iOS testing strictly requires macOS with Xcode and local simulators or real devices.",
        "Android testing requires Android SDK, adb, and emulator or real device infrastructure.",
        "Engine adapter is currently in design specification stage and not yet operational.",
    ]

    return EngineCapabilityProfile(
        engine_id="appium",
        display_name="Appium Mobile",
        version=None,
        is_operational=False,
        roadmap_phase="Platform Expansion B (Planned)",
        platforms=platforms,
        browsers=browsers,
        features=features,
        notes=notes,
    )
