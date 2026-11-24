"""Local Device & Browser Discovery Engine for Tracecase.

Discovers locally installed desktop browsers, connected Android devices / emulators via ADB,
local iOS simulators via Apple simctl, and responsive mobile viewport profiles.
Everything runs 100% locally on the host machine with zero cloud dependencies.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any


def discover_desktop_browsers() -> list[dict[str, Any]]:
    """Auto-detect locally installed desktop browsers and Playwright browser caches."""
    browsers: list[dict[str, Any]] = []
    system = platform.system()

    if system == "Darwin":
        # macOS Application paths
        mac_targets = [
            ("Google Chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "chrome"),
            ("Google Chrome Canary", "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary", "chrome-canary"),
            ("Brave Browser", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser", "brave"),
            ("Microsoft Edge", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "msedge"),
            ("Firefox", "/Applications/Firefox.app/Contents/MacOS/firefox", "firefox"),
            ("Safari", "/Applications/Safari.app/Contents/MacOS/Safari", "safari"),
            ("Arc", "/Applications/Arc.app/Contents/MacOS/Arc", "arc"),
            ("Chromium", "/Applications/Chromium.app/Contents/MacOS/Chromium", "chromium"),
        ]
        for name, exe_path, engine in mac_targets:
            if os.path.exists(exe_path):
                browsers.append({
                    "id": f"desktop_{engine}",
                    "name": name,
                    "engine": engine,
                    "path": exe_path,
                    "type": "desktop",
                    "channel": "stable" if "canary" not in engine else "canary",
                    "status": "ready",
                    "is_system_default": name == "Google Chrome",
                })

    elif system == "Linux":
        # Linux binaries in PATH or /usr/bin
        linux_targets = [
            ("google-chrome", "Google Chrome", "chrome"),
            ("google-chrome-stable", "Google Chrome", "chrome"),
            ("chromium", "Chromium", "chromium"),
            ("chromium-browser", "Chromium", "chromium"),
            ("firefox", "Firefox", "firefox"),
            ("microsoft-edge", "Microsoft Edge", "msedge"),
            ("brave-browser", "Brave Browser", "brave"),
        ]
        for bin_name, display_name, engine in linux_targets:
            found_path = shutil.which(bin_name)
            if found_path:
                browsers.append({
                    "id": f"desktop_{engine}",
                    "name": display_name,
                    "engine": engine,
                    "path": found_path,
                    "type": "desktop",
                    "channel": "stable",
                    "status": "ready",
                    "is_system_default": False,
                })

    # Discover Playwright bundled browsers (Hermetic testing engines)
    cache_dirs = [
        Path.home() / "Library" / "Caches" / "ms-playwright",
        Path.home() / ".cache" / "ms-playwright",
    ]
    seen_engines: set[str] = set()
    for c_dir in cache_dirs:
        if c_dir.exists():
            for child in c_dir.iterdir():
                if not child.is_dir():
                    continue
                name_lower = child.name.lower()
                engine = "chromium"
                if "firefox" in name_lower:
                    engine = "firefox"
                elif "webkit" in name_lower:
                    engine = "webkit"

                if engine not in seen_engines and "headless_shell" not in name_lower:
                    seen_engines.add(engine)
                    browsers.append({
                        "id": f"pw_{engine}",
                        "name": f"Playwright {engine.title()}",
                        "engine": engine,
                        "path": str(child),
                        "type": "playwright_hermetic",
                        "channel": "bundled",
                        "status": "ready",
                        "is_system_default": False,
                    })

    # Fallback to system chrome or playwright chromium if nothing detected
    if not browsers:
        browsers.append({
            "id": "desktop_chromium_default",
            "name": "Local Chromium",
            "engine": "chromium",
            "path": "chromium",
            "type": "desktop",
            "channel": "default",
            "status": "ready",
            "is_system_default": True,
        })

    return browsers


def discover_android_devices() -> dict[str, Any]:
    """Auto-detect connected Android devices and Android Studio emulators using ADB."""
    adb_bin = shutil.which("adb")
    # Also check standard Android SDK paths if adb is not in PATH
    if not adb_bin:
        common_sdk_adbs = [
            Path.home() / "Library" / "Android" / "sdk" / "platform-tools" / "adb",
            Path.home() / "Android" / "Sdk" / "platform-tools" / "adb",
            Path("/opt/homebrew/bin/adb"),
            Path("/usr/local/bin/adb"),
        ]
        for p in common_sdk_adbs:
            if p.exists() and os.access(p, os.X_OK):
                adb_bin = str(p)
                break

    devices: list[dict[str, Any]] = []
    if not adb_bin:
        return {
            "installed": False,
            "path": None,
            "devices": [],
            "message": "ADB not found. Install Android SDK Platform-Tools to test on Android devices.",
        }

    try:
        res = subprocess.run([adb_bin, "devices", "-l"], capture_output=True, text=True, timeout=4)
        for line in res.stdout.splitlines()[1:]:
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            dev_id = parts[0]
            dev_state = parts[1] if len(parts) > 1 else "unknown"

            # Parse model and product
            model = "Android Device"
            product = ""
            for p in parts[2:]:
                if p.startswith("model:"):
                    model = p.split(":", 1)[1].replace("_", " ")
                elif p.startswith("product:"):
                    product = p.split(":", 1)[1]

            is_emulator = dev_id.startswith("emulator-") or "sdk" in product.lower()
            devices.append({
                "id": dev_id,
                "name": model,
                "state": dev_state,
                "platform": "android",
                "type": "emulator" if is_emulator else "physical_usb",
                "status": "ready" if dev_state == "device" else dev_state,
            })
    except Exception as exc:
        return {
            "installed": True,
            "path": adb_bin,
            "devices": [],
            "error": str(exc),
        }

    return {
        "installed": True,
        "path": adb_bin,
        "devices": devices,
        "message": f"Discovered {len(devices)} Android device(s)." if devices else "ADB ready. Connect a device via USB with USB debugging enabled.",
    }


def discover_ios_simulators() -> dict[str, Any]:
    """Auto-detect available local iOS Simulators using Apple simctl on macOS."""
    if platform.system() != "Darwin":
        return {
            "installed": False,
            "simulators": [],
            "message": "iOS Simulators require macOS with Xcode installed.",
        }

    xcrun_bin = shutil.which("xcrun")
    if not xcrun_bin:
        return {
            "installed": False,
            "simulators": [],
            "message": "Xcode Command Line Tools (xcrun) not found.",
        }

    simulators: list[dict[str, Any]] = []
    try:
        res = subprocess.run(
            [xcrun_bin, "simctl", "list", "devices", "available", "-j"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        data = json.loads(res.stdout)
        for runtime_key, dlist in data.get("devices", {}).items():
            if "iOS" not in runtime_key:
                continue
            # Extract clean OS version, e.g. "iOS 18.1"
            clean_os = runtime_key.split(".")[-1].replace("-", " ")

            for d in dlist:
                if d.get("isAvailable", False):
                    simulators.append({
                        "id": d.get("udid"),
                        "name": d.get("name"),
                        "os": clean_os,
                        "state": d.get("state", "Shutdown"),
                        "platform": "ios",
                        "type": "simulator",
                        "status": "booted" if d.get("state") == "Booted" else "ready",
                    })
    except Exception as exc:
        return {
            "installed": True,
            "simulators": [],
            "error": str(exc),
        }

    return {
        "installed": True,
        "simulators": simulators[:15],  # Top 15 simulators
        "message": f"Discovered {len(simulators)} iOS simulator(s)." if simulators else "Xcode installed. Open Simulator app or create virtual device.",
    }


def get_mobile_emulation_presets() -> list[dict[str, Any]]:
    """Return responsive mobile device profiles matching KaneAI device matrices."""
    return [
        {
            "id": "iphone_16_pro_max",
            "name": "Apple iPhone 16 Pro Max",
            "platform": "iOS",
            "viewport": {"width": 430, "height": 932},
            "deviceScaleFactor": 3.0,
            "isMobile": True,
            "hasTouch": True,
            "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
        },
        {
            "id": "iphone_15_pro",
            "name": "Apple iPhone 15 Pro",
            "platform": "iOS",
            "viewport": {"width": 393, "height": 852},
            "deviceScaleFactor": 3.0,
            "isMobile": True,
            "hasTouch": True,
            "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        },
        {
            "id": "pixel_8_pro",
            "name": "Google Pixel 8 Pro",
            "platform": "Android",
            "viewport": {"width": 412, "height": 892},
            "deviceScaleFactor": 3.5,
            "isMobile": True,
            "hasTouch": True,
            "userAgent": "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.102 Mobile Safari/537.36",
        },
        {
            "id": "galaxy_s24_ultra",
            "name": "Samsung Galaxy S24 Ultra",
            "platform": "Android",
            "viewport": {"width": 412, "height": 915},
            "deviceScaleFactor": 3.5,
            "isMobile": True,
            "hasTouch": True,
            "userAgent": "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.102 Mobile Safari/537.36",
        },
        {
            "id": "ipad_pro_11",
            "name": "Apple iPad Pro 11-inch",
            "platform": "iPadOS",
            "viewport": {"width": 834, "height": 1194},
            "deviceScaleFactor": 2.0,
            "isMobile": True,
            "hasTouch": True,
            "userAgent": "Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        },
    ]


def get_all_available_devices() -> dict[str, Any]:
    """Aggregate all local discovery results into a single response."""
    return {
        "browsers": discover_desktop_browsers(),
        "adb": discover_android_devices(),
        "simulators": discover_ios_simulators(),
        "mobile_emulation_presets": get_mobile_emulation_presets(),
    }
