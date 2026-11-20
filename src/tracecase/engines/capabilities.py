"""Capability models, statuses, and host verification for Tracecase automation engines."""

from __future__ import annotations

import platform
import shutil
import sys
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class CapabilityStatus(str, Enum):
    """
    Explicit capability readiness state for engines, browsers, and features.
    
    Prevents presenting planned, missing, or infrastructure-dependent
    features as operational.
    """

    SUPPORTED = "supported"                                 # Fully implemented, installed, and verified on host
    UNSUPPORTED = "unsupported"                             # Architecturally unsupported by this engine or platform
    AVAILABLE_BUT_NOT_INSTALLED = "available_not_installed" # Engine supports it, but binary/driver is missing on host
    REQUIRES_EXTERNAL_INFRASTRUCTURE = "requires_infra"     # Needs external server, macOS/Xcode, or mobile hardware
    NOT_YET_IMPLEMENTED = "not_yet_implemented"             # Planned for future expansion phase


class PlatformType(str, Enum):
    """Execution platform classifications."""

    DESKTOP_WEB = "desktop_web"
    MOBILE_WEB = "mobile_web"
    ANDROID_NATIVE = "android_native"
    IOS_NATIVE = "ios_native"


class BrowserChannel(str, Enum):
    """Browser engines and channels."""

    CHROMIUM = "chromium"
    CHROME = "chrome"
    FIREFOX = "firefox"
    WEBKIT = "webkit"
    MSEDGE = "msedge"
    SAFARI = "safari"


class FeatureCapability(str, Enum):
    """Engine feature capabilities."""

    RECORDING = "recording"
    REPLAY = "replay"
    NETWORK_INSPECTION = "network_inspection"
    CONSOLE_LOGS = "console_logs"
    CDP_TRACING = "cdp_tracing"
    MOBILE_EMULATION = "mobile_emulation"
    REAL_DEVICE = "real_device"
    HEADLESS = "headless"
    VISUAL_DIFF = "visual_diff"


class EngineCapabilityProfile(BaseModel):
    """Structured capability matrix for an automation engine on the current host."""

    engine_id: str
    display_name: str
    version: str | None = None
    is_operational: bool = False
    roadmap_phase: str = "Phase 9.1.4"
    platforms: dict[str, CapabilityStatus] = Field(default_factory=dict)
    browsers: dict[str, CapabilityStatus] = Field(default_factory=dict)
    features: dict[str, CapabilityStatus] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class HostEnvironmentCapabilities(BaseModel):
    """System-level environment inspection and registered engine capabilities."""

    os_platform: str
    os_release: str
    architecture: str
    has_xcode: bool = False
    has_android_sdk: bool = False
    engines: dict[str, EngineCapabilityProfile] = Field(default_factory=dict)


def inspect_host_environment() -> dict[str, Any]:
    """Inspect the local operating system, developer tools, and driver infrastructure."""
    os_name = sys.platform
    has_xcode = False
    if os_name == "darwin":
        has_xcode = bool(shutil.which("xcodebuild"))

    has_android = bool(shutil.which("adb"))

    return {
        "os_platform": os_name,
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "has_xcode": has_xcode,
        "has_android_sdk": has_android,
    }
