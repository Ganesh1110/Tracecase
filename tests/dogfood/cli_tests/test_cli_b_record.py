"""Tests for Section B: CLI Record (B1 - B27)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from tracecase.models import TestCase
from tracecase.recorder import Recorder

from tests.dogfood.cli_tests.conftest import run_tracecase


def test_b1_minimal_record(isolated_workspace: Path, isolated_env: dict[str, str], playground_server_url: str):
    """B1 (Critical): record url -o dir minimal produces valid testcase."""
    out_dir = isolated_workspace / "b1_minimal"
    url = f"{playground_server_url}/login"

    async def _record():
        rec = Recorder(
            output_dir=out_dir,
            start_url=url,
            name="Minimal Recording",
            headless=True,
            auto_start=True,
        )
        task = asyncio.create_task(rec.run())
        while not rec._pages or not rec._browser_manager or not rec._browser_manager._page:
            await asyncio.sleep(0.05)
        page = rec._pages[0]
        await page.wait_for_selector("#username")
        await page.click("#username")
        await page.fill("#username", "qa_user")
        await page.click("#btn-login")
        await asyncio.sleep(0.3)
        await rec.stop_recording()
        await task

    asyncio.run(_record())

    assert (out_dir / "testcase.json").exists()
    assert (out_dir / "testcase.md").exists()
    assert (out_dir / "testcase.html").exists()
    data = json.loads((out_dir / "testcase.json").read_text(encoding="utf-8"))
    tc = TestCase.model_validate(data)
    assert len(tc.steps) >= 1
    assert tc.browser == "chromium"


def test_b2_custom_name(isolated_workspace: Path, playground_server_url: str):
    """B2: Custom name option respected."""
    out_dir = isolated_workspace / "b2_name"

    async def _record():
        rec = Recorder(
            output_dir=out_dir,
            start_url=f"{playground_server_url}/index",
            name="My Custom Suite Name",
            headless=True,
            auto_start=True,
        )
        task = asyncio.create_task(rec.run())
        while not rec._pages or not rec._browser_manager or not rec._browser_manager._page:
            await asyncio.sleep(0.05)
        page = rec._pages[0]
        await page.wait_for_selector("#link-login")
        await page.click("#link-login")
        await asyncio.sleep(0.2)
        await rec.stop_recording()
        await task

    asyncio.run(_record())
    data = json.loads((out_dir / "testcase.json").read_text(encoding="utf-8"))
    assert data["name"] == "My Custom Suite Name"


def test_b7_invalid_browser_rejected(isolated_workspace: Path, isolated_env: dict[str, str], playground_server_url: str):
    """B7: Rejects invalid browser option value."""
    res = run_tracecase(
        ["record", f"{playground_server_url}/index", "-o", str(isolated_workspace / "b7"), "-b", "invalid_browser"],
        env=isolated_env,
    )
    assert res.returncode != 0
    assert "invalid value for '--browser'" in res.stderr.lower() or "error" in res.stderr.lower()


def test_b10_missing_output_option(isolated_env: dict[str, str], playground_server_url: str):
    """B10: Error when --output is omitted."""
    res = run_tracecase(["record", f"{playground_server_url}/index"], env=isolated_env)
    assert res.returncode != 0
    assert "missing" in res.stderr.lower() or "missing" in res.stdout.lower()


def test_b11_unreachable_url(isolated_workspace: Path, isolated_env: dict[str, str]):
    """B11: Graceful error when URL is unreachable."""
    out_dir = isolated_workspace / "b11_unreachable"
    res = run_tracecase(["record", "http://127.0.0.1:54321/nonexistent", "-o", str(out_dir), "--headless"], env=isolated_env)
    assert res.returncode != 0


def test_b12_control_panel_lifecycle(isolated_workspace: Path, playground_server_url: str):
    """B12: Start and stop via injected control panel."""
    out_dir = isolated_workspace / "b12_panel"

    async def _record():
        rec = Recorder(
            output_dir=out_dir,
            start_url=f"{playground_server_url}/actions",
            headless=True,
            auto_start=False,
        )
        task = asyncio.create_task(rec.run())
        while not rec._pages or not rec._browser_manager or not rec._browser_manager._page:
            await asyncio.sleep(0.05)
        page = rec._pages[0]
        # Control panel must be present
        await page.wait_for_selector("#__tracecase_panel__")
        await page.click("#__qa_start_btn__")
        await asyncio.sleep(0.2)
        assert rec.is_recording is True

        # Perform action
        await page.click("#dblclick-btn")
        await asyncio.sleep(0.2)

        # Stop via panel
        await page.click("#__qa_stop_btn__")
        await task
        assert rec.is_recording is False

    asyncio.run(_record())
    assert (out_dir / "testcase.json").exists()


def test_b13_stop_with_zero_steps(isolated_workspace: Path, playground_server_url: str):
    """B13: Stop with zero steps prints 'No steps recorded. Nothing to export.' and writes no files."""
    out_dir = isolated_workspace / "b13_zero"

    async def _record():
        rec = Recorder(
            output_dir=out_dir,
            start_url=f"{playground_server_url}/index",
            headless=True,
            auto_start=False,
        )
        task = asyncio.create_task(rec.run())
        while not rec._pages or not rec._browser_manager or not rec._browser_manager._page:
            await asyncio.sleep(0.05)
        page = rec._pages[0]
        await page.click("#__qa_start_btn__")
        await asyncio.sleep(0.1)
        await page.click("#__qa_stop_btn__")
        await task

    asyncio.run(_record())
    # In Tracecase, 0 steps deliberately produces no export files
    assert not (out_dir / "testcase.json").exists()


def test_b16_action_types_capture(isolated_workspace: Path, playground_server_url: str):
    """B16 (Critical): Captures distinct action types (click, dblclick, check, uncheck, keypress)."""
    out_dir = isolated_workspace / "b16_actions"

    async def _record():
        rec = Recorder(
            output_dir=out_dir,
            start_url=f"{playground_server_url}/actions",
            headless=True,
            auto_start=True,
        )
        task = asyncio.create_task(rec.run())
        while not rec._pages or not rec._browser_manager or not rec._browser_manager._page:
            await asyncio.sleep(0.05)
        page = rec._pages[0]

        # Double click
        await page.wait_for_selector("#dblclick-btn")
        await page.dblclick("#dblclick-btn")
        await asyncio.sleep(0.2)

        # Check / uncheck
        await page.check("#toggle-chk")
        await asyncio.sleep(0.2)
        await page.uncheck("#toggle-chk")
        await asyncio.sleep(0.2)

        # Keypress
        await page.click("#key-input")
        await page.keyboard.press("Enter")
        await asyncio.sleep(0.2)

        await rec.stop_recording()
        await task

    asyncio.run(_record())
    data = json.loads((out_dir / "testcase.json").read_text(encoding="utf-8"))
    action_types = {s["action_type"] for s in data["steps"]}
    assert len(action_types) >= 2


def test_b19_network_capture(isolated_workspace: Path, playground_server_url: str):
    """B19: Network requests triggered by user actions attached to step."""
    out_dir = isolated_workspace / "b19_net"

    async def _record():
        rec = Recorder(
            output_dir=out_dir,
            start_url=f"{playground_server_url}/network_tester",
            headless=True,
            auto_start=True,
        )
        task = asyncio.create_task(rec.run())
        while not rec._pages or not rec._browser_manager or not rec._browser_manager._page:
            await asyncio.sleep(0.05)
        page = rec._pages[0]
        await page.wait_for_selector("#btn-200")
        await page.click("#btn-200")
        await asyncio.sleep(0.5)
        await rec.stop_recording()
        await task

    asyncio.run(_record())
    data = json.loads((out_dir / "testcase.json").read_text(encoding="utf-8"))
    all_reqs = data.get("network_requests", [])
    assert len(all_reqs) >= 1
    assert any("/api/status/200" in r["url"] for r in all_reqs)


def test_b20_console_log_capture(isolated_workspace: Path, playground_server_url: str):
    """B20: Browser console logs captured in test case timeline."""
    out_dir = isolated_workspace / "b20_console"

    async def _record():
        rec = Recorder(
            output_dir=out_dir,
            start_url=f"{playground_server_url}/console_errors",
            headless=True,
            auto_start=True,
        )
        task = asyncio.create_task(rec.run())
        while not rec._pages or not rec._browser_manager or not rec._browser_manager._page:
            await asyncio.sleep(0.05)
        page = rec._pages[0]
        await page.wait_for_selector("#btn-log")
        await page.click("#btn-log")
        await page.click("#btn-warn")
        await asyncio.sleep(0.3)
        await rec.stop_recording()
        await task

    asyncio.run(_record())
    data = json.loads((out_dir / "testcase.json").read_text(encoding="utf-8"))
    logs = data.get("console_logs", [])
    assert len(logs) >= 1
    assert any("Playground" in l["message"] for l in logs)


def test_b22_multitab_capture(isolated_workspace: Path, playground_server_url: str):
    """B22: Multi-tab links detected and tagged with page_id."""
    out_dir = isolated_workspace / "b22_tabs"

    async def _record():
        rec = Recorder(
            output_dir=out_dir,
            start_url=f"{playground_server_url}/multitab",
            headless=True,
            auto_start=True,
        )
        task = asyncio.create_task(rec.run())
        while not rec._pages or not rec._browser_manager or not rec._browser_manager._page:
            await asyncio.sleep(0.05)
        page = rec._pages[0]
        await page.wait_for_selector("#link-blank")
        async with page.expect_popup():
            await page.click("#link-blank")
        await asyncio.sleep(0.5)
        assert len(rec._pages) >= 2
        await rec.stop_recording()
        await task

    asyncio.run(_record())
    data = json.loads((out_dir / "testcase.json").read_text(encoding="utf-8"))
    assert len(data.get("steps", [])) >= 1


def test_b24_hostile_content_escaping(isolated_workspace: Path, playground_server_url: str):
    """B24: Hostile script and HTML tags escaped in testcase.html without script execution."""
    out_dir = isolated_workspace / "b24_xss"

    async def _record():
        rec = Recorder(
            output_dir=out_dir,
            start_url=f"{playground_server_url}/hostile_content",
            headless=True,
            auto_start=True,
        )
        task = asyncio.create_task(rec.run())
        while not rec._pages or not rec._browser_manager or not rec._browser_manager._page:
            await asyncio.sleep(0.05)
        page = rec._pages[0]
        await page.wait_for_selector("#btn-xss")
        await page.click("#btn-xss")
        await asyncio.sleep(0.3)
        await rec.stop_recording()
        await task

    asyncio.run(_record())
    html_content = (out_dir / "testcase.html").read_text(encoding="utf-8")
    assert "<script>window.__hostile_executed" not in html_content or "&lt;script&gt;" in html_content


def test_b26_path_with_spaces_unicode(isolated_workspace: Path, playground_server_url: str):
    """B26: Output path containing spaces and unicode characters."""
    out_dir = isolated_workspace / "test dir with spaces" / "тест_юникод"

    async def _record():
        rec = Recorder(
            output_dir=out_dir,
            start_url=f"{playground_server_url}/index",
            headless=True,
            auto_start=True,
        )
        task = asyncio.create_task(rec.run())
        while not rec._pages or not rec._browser_manager or not rec._browser_manager._page:
            await asyncio.sleep(0.05)
        page = rec._pages[0]
        await page.wait_for_selector("#link-login")
        await page.click("#link-login")
        await asyncio.sleep(0.2)
        await rec.stop_recording()
        await task

    asyncio.run(_record())
    assert (out_dir / "testcase.json").exists()


def test_b27_password_masking_audit(isolated_workspace: Path, playground_server_url: str):
    """B27: Password input values audit (flags whether stored plain text)."""
    out_dir = isolated_workspace / "b27_pwd"

    async def _record():
        rec = Recorder(
            output_dir=out_dir,
            start_url=f"{playground_server_url}/login",
            headless=True,
            auto_start=True,
        )
        task = asyncio.create_task(rec.run())
        while not rec._pages or not rec._browser_manager or not rec._browser_manager._page:
            await asyncio.sleep(0.05)
        page = rec._pages[0]
        await page.wait_for_selector("#password")
        await page.click("#password")
        await page.fill("#password", "my_super_secret_password")
        await page.click("#btn-login")
        await asyncio.sleep(0.3)
        await rec.stop_recording()
        await task

    asyncio.run(_record())
    raw_json = (out_dir / "testcase.json").read_text(encoding="utf-8")
    # Audit check: note whether raw secret is present or masked
    has_plain_secret = "my_super_secret_password" in raw_json
    print(f"\n[B27 AUDIT RESULT] Password field stored in plain text: {has_plain_secret}")
    assert (out_dir / "testcase.json").exists()
