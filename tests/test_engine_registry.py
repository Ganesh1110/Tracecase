"""Tests for Phase 9.1.4: Multi-Engine Abstraction, Capability Registry & Locator Translation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tracecase.engines import (
    BrowserChannel,
    CapabilityStatus,
    EngineAction,
    EngineActionType,
    EngineRegistry,
    LocatorSpec,
    LocatorStrategy,
    PlatformType,
    UnsupportedLocatorError,
    engine_registry,
    get_engine_registry,
    translate_locator,
)
from tracecase.engines.playwright.adapter import PlaywrightEngineAdapter
from tracecase.models import TestCase
from tracecase.ui.server import create_app


def test_registry_engine_catalog_and_operational_status() -> None:
    """Verify engine catalog lists Playwright, Selenium, and Appium with strict operational boundaries."""
    registry = get_engine_registry()
    engines = registry.list_engines()
    assert "playwright" in engines
    assert "selenium" in engines
    assert "appium" in engines

    # Playwright is the sole operational engine in Phase 9.1.4
    assert registry.is_engine_operational("playwright") is True
    assert registry.is_engine_operational("selenium") is False
    assert registry.is_engine_operational("appium") is False

    # Operational engine retrieval
    pw_adapter = registry.get_engine("playwright")
    assert isinstance(pw_adapter, PlaywrightEngineAdapter)
    assert pw_adapter.engine_id == "playwright"
    assert pw_adapter.is_operational is True

    # Planned engines must refuse execution with informative error
    with pytest.raises(RuntimeError, match="Platform Expansion A"):
        registry.get_engine("selenium")

    with pytest.raises(RuntimeError, match="Platform Expansion B"):
        registry.get_engine("appium")

    with pytest.raises(ValueError, match="Unknown automation engine"):
        registry.get_engine("unsupported_engine")


@pytest.mark.asyncio
async def test_playwright_capability_profile_verifications() -> None:
    """Verify Playwright capabilities accurately distinguish WebKit from Apple Safari."""
    registry = get_engine_registry()
    profile = await registry.get_engine_profile("playwright")

    assert profile.engine_id == "playwright"
    assert profile.is_operational is True
    assert profile.platforms[PlatformType.DESKTOP_WEB.value] == CapabilityStatus.SUPPORTED
    assert profile.platforms[PlatformType.MOBILE_WEB.value] == CapabilityStatus.SUPPORTED
    assert profile.platforms[PlatformType.ANDROID_NATIVE.value] == CapabilityStatus.UNSUPPORTED
    assert profile.platforms[PlatformType.IOS_NATIVE.value] == CapabilityStatus.UNSUPPORTED

    # Browsers
    assert profile.browsers[BrowserChannel.CHROMIUM.value] == CapabilityStatus.SUPPORTED
    assert profile.browsers[BrowserChannel.FIREFOX.value] == CapabilityStatus.SUPPORTED
    assert profile.browsers[BrowserChannel.WEBKIT.value] == CapabilityStatus.SUPPORTED
    # Playwright WebKit is NOT native Safari
    assert profile.browsers[BrowserChannel.SAFARI.value] == CapabilityStatus.UNSUPPORTED

    # Features
    assert profile.features["recording"] == CapabilityStatus.SUPPORTED
    assert profile.features["replay"] == CapabilityStatus.SUPPORTED
    assert profile.features["cdp_tracing"] == CapabilityStatus.SUPPORTED
    assert profile.features["real_device"] == CapabilityStatus.UNSUPPORTED


@pytest.mark.asyncio
async def test_selenium_capability_profile_verifications() -> None:
    """Verify Selenium capabilities are marked NOT_YET_IMPLEMENTED and reflect OS safari status."""
    registry = get_engine_registry()
    profile = await registry.get_engine_profile("selenium")

    assert profile.engine_id == "selenium"
    assert profile.is_operational is False
    assert "Platform Expansion A" in profile.roadmap_phase

    # Desktop web is planned, not yet operational
    assert profile.platforms[PlatformType.DESKTOP_WEB.value] == CapabilityStatus.NOT_YET_IMPLEMENTED
    assert profile.browsers[BrowserChannel.CHROME.value] == CapabilityStatus.NOT_YET_IMPLEMENTED

    # Safari requires macOS infrastructure
    if sys.platform == "darwin":
        assert profile.browsers[BrowserChannel.SAFARI.value] == CapabilityStatus.REQUIRES_EXTERNAL_INFRASTRUCTURE
    else:
        assert profile.browsers[BrowserChannel.SAFARI.value] == CapabilityStatus.UNSUPPORTED


@pytest.mark.asyncio
async def test_appium_capability_profile_verifications() -> None:
    """Verify Appium capabilities are marked NOT_YET_IMPLEMENTED and reflect mobile requirements."""
    registry = get_engine_registry()
    profile = await registry.get_engine_profile("appium")

    assert profile.engine_id == "appium"
    assert profile.is_operational is False
    assert "Platform Expansion B" in profile.roadmap_phase

    # Desktop web is architecturally unsupported by Appium
    assert profile.platforms[PlatformType.DESKTOP_WEB.value] == CapabilityStatus.UNSUPPORTED

    # iOS native requires macOS and Xcode
    if sys.platform == "darwin":
        assert profile.platforms[PlatformType.IOS_NATIVE.value] == CapabilityStatus.REQUIRES_EXTERNAL_INFRASTRUCTURE
    else:
        assert profile.platforms[PlatformType.IOS_NATIVE.value] == CapabilityStatus.UNSUPPORTED


def test_locator_translation_and_rejection_boundaries() -> None:
    """Verify explicit locator translation across engines without silent semantic alterations."""
    # 1. Playwright Web Locators
    css_spec = LocatorSpec(strategy=LocatorStrategy.CSS, value="#submit-btn")
    assert translate_locator(css_spec, "playwright") == "#submit-btn"

    xpath_spec = LocatorSpec(strategy=LocatorStrategy.XPATH, value="//button[@type='submit']")
    assert translate_locator(xpath_spec, "playwright") == "xpath=//button[@type='submit']"

    id_spec = LocatorSpec(strategy=LocatorStrategy.ID, value="login-input")
    assert translate_locator(id_spec, "playwright") == "#login-input"

    text_spec = LocatorSpec(strategy=LocatorStrategy.TEXT, value="Log In")
    assert translate_locator(text_spec, "playwright") == "text=Log In"

    # Playwright MUST explicitly reject mobile-only locators
    mobile_spec = LocatorSpec(strategy=LocatorStrategy.ACCESSIBILITY_ID, value="login_accessibility_tag")
    with pytest.raises(UnsupportedLocatorError, match="Playwright does not natively support"):
        translate_locator(mobile_spec, "playwright")

    uiautomator_spec = LocatorSpec(strategy=LocatorStrategy.ANDROID_UIAUTOMATOR, value="new UiSelector().text('Login')")
    with pytest.raises(UnsupportedLocatorError, match="Playwright does not natively support"):
        translate_locator(uiautomator_spec, "playwright")

    # 2. Appium Mobile Locators
    assert translate_locator(mobile_spec, "appium") == "login_accessibility_tag"
    assert translate_locator(uiautomator_spec, "appium") == "new UiSelector().text('Login')"

    # Appium native context rejects web-only CSS
    native_css = LocatorSpec(strategy=LocatorStrategy.CSS, value=".header-btn", platform_context="android_native")
    with pytest.raises(UnsupportedLocatorError, match="Appium native context does not support"):
        translate_locator(native_css, "appium")


def test_playwright_engine_factory_methods() -> None:
    """Verify PlaywrightEngineAdapter can instantiate existing Recorder and ReplayEngine without rewrites."""
    adapter = PlaywrightEngineAdapter()

    recorder = adapter.create_recorder(
        output_dir=Path("./recordings/tmp_test"),
        start_url="http://127.0.0.1:8000",
        name="Factory Test",
        browser_type="chromium",
        headless=True,
    )
    assert recorder is not None
    assert recorder.name == "Factory Test"
    assert recorder.browser_type == "chromium"

    dummy_tc = TestCase(
        id="tc_dummy",
        name="Dummy Case",
        created_at="2026-11-20T10:00:00",
        start_url="http://127.0.0.1:8000",
        browser="chromium",
        viewport={"width": 1280, "height": 800},
        user_agent="Tracecase",
        steps=[],
        total_duration=0.0,
        total_steps=0,
    )
    replay = adapter.create_replay_engine(testcase=dummy_tc, browser_type="chromium", headless=True)
    assert replay is not None
    assert replay.browser_type == "chromium"


def test_rest_api_engine_capabilities() -> None:
    """Verify REST API endpoint GET /api/engines/capabilities returns host and engine profiles."""
    client = TestClient(create_app())

    # 1. Host capabilities
    resp = client.get("/api/engines/capabilities")
    assert resp.status_code == 200
    data = resp.json()

    assert "os_platform" in data
    assert "engines" in data
    assert "playwright" in data["engines"]
    assert "selenium" in data["engines"]
    assert "appium" in data["engines"]

    # Playwright is operational
    assert data["engines"]["playwright"]["is_operational"] is True

    # Selenium and Appium are planned
    assert data["engines"]["selenium"]["is_operational"] is False
    assert data["engines"]["appium"]["is_operational"] is False

    # 2. Single engine endpoint
    resp_pw = client.get("/api/engines/playwright")
    assert resp_pw.status_code == 200
    assert resp_pw.json()["engine_id"] == "playwright"

    resp_sel = client.get("/api/engines/selenium")
    assert resp_sel.status_code == 200
    assert resp_sel.json()["engine_id"] == "selenium"

    # 3. Invalid engine
    resp_inv = client.get("/api/engines/unknown_engine")
    assert resp_inv.status_code == 404
