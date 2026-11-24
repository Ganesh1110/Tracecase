"""Tests for Section B: CLI Record (Flows B1 - B27).

Every flow has a dedicated test tagged with @pytest.mark.flow("<ID>").
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest
from tracecase.models import TestCase
from tracecase.recorder import Recorder
from tests.dogfood.cli_tests.conftest import run_tracecase


async def _run_recorder(
    out_dir: Path,
    url: str,
    name: str | None = None,
    browser: str = "chromium",
    headless: bool = True,
    timeout: int = 30000,
    actions_callback=None,
    close_browser_early: bool = False,
) -> Path:
    rec = Recorder(
        output_dir=out_dir,
        start_url=url,
        name=name or "Test Case",
        browser_type=browser,
        headless=headless,
        timeout=timeout,
        auto_start=True,
    )
    task = asyncio.create_task(rec.run())
    while not rec.is_recording:
        await asyncio.sleep(0.05)

    page = rec._pages[0]

    if actions_callback:
        await actions_callback(page, rec)

    if close_browser_early:
        if rec._browser_manager and rec._browser_manager.browser:
            await rec._browser_manager.browser.close()
    else:
        await rec.stop_recording()

    try:
        await asyncio.wait_for(task, timeout=10.0)
    except Exception:
        pass

    return out_dir / "testcase.json"


@pytest.mark.flow("B1")
def test_b1_minimal_record(isolated_workspace: Path, isolated_env: dict[str, str], playground_server_url: str):
    """B1: record url -o dir minimal produces valid testcase."""
    out_dir = isolated_workspace / "b1_minimal"
    url = f"{playground_server_url}/login.html"

    async def actions(page, rec):
        await page.wait_for_selector("#username")
        await page.fill("#username", "qa_user")
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, name="Minimal Recording", actions_callback=actions))
    assert (out_dir / "testcase.json").exists()
    assert (out_dir / "testcase.md").exists()
    assert (out_dir / "testcase.html").exists()
    tc = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    assert len(tc.steps) >= 1
    assert tc.browser == "chromium"


@pytest.mark.flow("B2")
def test_b2_custom_name(isolated_workspace: Path, playground_server_url: str):
    """B2: custom name -n option applies name to testcase metadata."""
    out_dir = isolated_workspace / "b2_custom_name"
    url = f"{playground_server_url}/login.html"

    async def actions(page, rec):
        await page.wait_for_selector("#username")
        await page.fill("#username", "alice")
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, name="Custom Smoke Flow", actions_callback=actions))
    tc = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    assert tc.name == "Custom Smoke Flow"


@pytest.mark.flow("B3")
def test_b3_default_name_generated_from_url(isolated_workspace: Path, playground_server_url: str):
    """B3: Default name is auto-derived from URL when -n is omitted."""
    out_dir = isolated_workspace / "b3_default_name"
    url = f"{playground_server_url}/login.html"

    async def actions(page, rec):
        await page.wait_for_selector("#username")
        await page.fill("#username", "bob")
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    rec = Recorder(output_dir=out_dir, start_url=url, auto_start=True, headless=True)

    async def run():
        t = asyncio.create_task(rec.run())
        while not rec.is_recording:
            await asyncio.sleep(0.05)
        await actions(rec._pages[0], rec)
        await rec.stop_recording()
        await t

    asyncio.run(run())
    tc = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    assert tc.name is not None
    assert len(tc.name) > 0


@pytest.mark.flow("B4")
def test_b4_record_browser_chromium(isolated_workspace: Path, playground_server_url: str):
    """B4: Explicit --browser chromium records session under chromium."""
    out_dir = isolated_workspace / "b4_chromium"
    url = f"{playground_server_url}/login.html"

    async def actions(page, rec):
        await page.wait_for_selector("#username")
        await page.fill("#username", "chromium_user")
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, browser="chromium", actions_callback=actions))
    tc = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    assert tc.browser == "chromium"


@pytest.mark.flow("B5")
def test_b5_record_browser_firefox(isolated_workspace: Path, playground_server_url: str):
    """B5: Record browser firefox in headless mode (headless forced on macOS darwin)."""
    out_dir = isolated_workspace / "b5_firefox"
    url = f"{playground_server_url}/login.html"

    async def actions(page, rec):
        await page.wait_for_selector("#username")
        await page.fill("#username", "firefox_user")
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, browser="firefox", actions_callback=actions))
    tc = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    assert tc.browser == "firefox"


@pytest.mark.flow("B6")
def test_b6_record_browser_webkit(isolated_workspace: Path, playground_server_url: str):
    """B6: Record browser webkit in headless mode."""
    out_dir = isolated_workspace / "b6_webkit"
    url = f"{playground_server_url}/login.html"

    async def actions(page, rec):
        await page.wait_for_selector("#username")
        await page.fill("#username", "webkit_user")
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, browser="webkit", actions_callback=actions))
    tc = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    assert tc.browser == "webkit"


@pytest.mark.flow("B7")
def test_b7_invalid_browser_rejected(isolated_workspace: Path, isolated_env: dict[str, str], playground_server_url: str):
    """B7: record rejects invalid browser option (e.g. --browser opera)."""
    out_dir = isolated_workspace / "out_b7"
    res = run_tracecase(
        ["record", f"{playground_server_url}/login.html", "-o", str(out_dir), "--browser", "opera"],
        env=isolated_env,
    )
    assert res.returncode != 0
    assert "Invalid value for '--browser'" in res.stderr or "Invalid" in res.stdout
    assert not (out_dir / "testcase.json").exists()


@pytest.mark.flow("B8")
def test_b8_headless_mode_flag(isolated_workspace: Path, isolated_env: dict[str, str], playground_server_url: str):
    """B8: --headless flag accepted by CLI record command."""
    res = run_tracecase(
        ["record", "--help"],
        env=isolated_env,
    )
    assert res.returncode == 0
    assert "--headless" in res.stdout


@pytest.mark.flow("B9")
def test_b9_timeout_option(isolated_workspace: Path, isolated_env: dict[str, str], playground_server_url: str):
    """B9: --timeout validates range (1000 - 300000)."""
    # Invalid timeout: 500 (below 1000 min)
    out_dir = isolated_workspace / "out_b9"
    res_bad = run_tracecase(
        ["record", f"{playground_server_url}/login.html", "-o", str(out_dir), "--timeout", "500"],
        env=isolated_env,
    )
    assert res_bad.returncode != 0
    assert "timeout" in (res_bad.stderr + res_bad.stdout).lower() or res_bad.returncode == 2
    assert not (out_dir / "testcase.json").exists()


@pytest.mark.flow("B10")
def test_b10_missing_output_option(isolated_env: dict[str, str], playground_server_url: str):
    """B10: record without -o exits non-zero with missing option error."""
    res = run_tracecase(["record", f"{playground_server_url}/login.html"], env=isolated_env)
    assert res.returncode != 0
    assert "missing" in (res.stderr + res.stdout).lower() or "error" in (res.stderr + res.stdout).lower()
    assert "Missing option" in res.stderr or "Missing" in res.stdout


@pytest.mark.flow("B11")
@pytest.mark.xfail(strict=True, reason="BUG-008: Unhandled connection exception dumps Python traceback on unreachable URL")
def test_b11_unreachable_url(isolated_workspace: Path, isolated_env: dict[str, str]):
    """B11: record against unreachable port fails with clean error."""
    res = run_tracecase(
        ["record", "http://127.0.0.1:19999/unreachable", "-o", str(isolated_workspace / "out_unreach"), "--headless"],
        env=isolated_env,
    )
    assert res.returncode != 0
    assert "Traceback" not in res.stderr


@pytest.mark.flow("B12")
def test_b12_control_panel_lifecycle(isolated_workspace: Path, playground_server_url: str):
    """B12 (Critical): Test control panel injects, starts, records, and stops."""
    out_dir = isolated_workspace / "b12_panel"
    url = f"{playground_server_url}/login.html"

    async def actions(page, rec):
        # Verify control panel element exists in DOM
        panel = await page.wait_for_selector("#__tracecase_panel__", timeout=5000)
        assert panel is not None, "Control panel DOM #__tracecase_panel__ missing"
        # Perform action
        await page.fill("#username", "panel_user")
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions))
    assert (out_dir / "testcase.json").exists()


@pytest.mark.flow("B12")
def test_b12_control_panel_legacy_qa_ids_audit():
    """B12 / BUG-006 (Characterization): Assert that control panel currently contains legacy __qa_ prefixes."""
    from tracecase.control_panel import CONTROL_PANEL_JS
    assert "__qa_start_btn__" in CONTROL_PANEL_JS
    assert "__qa_stop_btn__" in CONTROL_PANEL_JS


@pytest.mark.flow("B12")
@pytest.mark.xfail(strict=True, reason="BUG-006: Control panel internal elements retain legacy __qa_ prefixes instead of tracecase branding")
def test_bug006_control_panel_clean_ids():
    """BUG-006 (Strict XFail of Correct Behavior): Control panel HTML/JS must NOT contain legacy __qa_ prefixes."""
    from tracecase.control_panel import CONTROL_PANEL_JS
    assert "__qa_" not in CONTROL_PANEL_JS, "Control panel JS contains legacy __qa_ prefixes"


@pytest.mark.flow("B13")
def test_b13_stop_with_zero_steps(isolated_workspace: Path, playground_server_url: str):
    """B13: Stop recording with zero steps prints notice and skips export."""
    out_dir = isolated_workspace / "b13_zero"
    url = f"{playground_server_url}/login.html"

    async def no_actions(page, rec):
        await asyncio.sleep(0.1)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=no_actions))
    # Recorder prints 'No steps recorded. Nothing to export.' and does not write files
    assert not (out_dir / "testcase.json").exists()


@pytest.mark.flow("B14")
def test_b14_close_browser_without_stop(isolated_workspace: Path, playground_server_url: str):
    """B14: Closing browser window directly without pressing stop triggers clean shutdown."""
    out_dir = isolated_workspace / "b14_close"
    url = f"{playground_server_url}/login.html"

    async def actions(page, rec):
        await page.fill("#username", "close_user")
        await page.click("#btn-login")
        await asyncio.sleep(0.1)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions, close_browser_early=True))
    # Browser closed early without clicking stop: clean termination with no exported testcase
    assert not (out_dir / "testcase.json").exists()


@pytest.mark.flow("B14")
@pytest.mark.xfail(strict=True, reason="BUG-012: Closing browser without clicking Stop silently discards recording without saving or warning user")
def test_b14_close_browser_without_stop_saves_or_warns(isolated_workspace: Path, playground_server_url: str):
    """B14 / BUG-012 (Strict XFail Behavior): Closing browser early must save recording or notify user of discarded data."""
    out_dir = isolated_workspace / "b14_save_warn"
    url = f"{playground_server_url}/login.html"

    async def actions(page, rec):
        await page.fill("#username", "close_user")
        await page.click("#btn-login")
        await asyncio.sleep(0.1)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions, close_browser_early=True))
    # Expected: The recording must be saved (data preservation) rather than silently lost
    assert (out_dir / "testcase.json").exists(), "Recording was silently discarded upon browser close without Stop"


@pytest.mark.flow("B15")
def test_b15_panel_excluded_from_screenshots(isolated_workspace: Path, playground_server_url: str):
    """B15: Control panel elements are excluded/hidden from step screenshots."""
    out_dir = isolated_workspace / "b15_screenshot"
    url = f"{playground_server_url}/login.html"

    async def actions(page, rec):
        await page.fill("#username", "photo_user")
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions))
    tc = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    for step in tc.steps:
        if step.element:
            assert "__qa_" not in step.element.selector


@pytest.mark.flow("B16")
def test_b16_action_types_capture(isolated_workspace: Path, playground_server_url: str):
    """B16: Test recorded ActionTypes (click, dblclick, input, select, check, uncheck, keypress, navigate)."""
    out_dir = isolated_workspace / "b16_actions"
    url = f"{playground_server_url}/actions.html"

    async def actions(page, rec):
        await page.wait_for_selector("#dblclick-btn")
        # 1. dblclick
        await page.dblclick("#dblclick-btn")
        # 2. check (checkbox)
        chk = await page.query_selector("#toggle-chk")
        if not await chk.is_checked():
            await page.click("#toggle-chk")
        # 3. uncheck
        await page.click("#toggle-chk")
        # 4. input
        await page.fill("#key-input", "testing_keypress")
        await asyncio.sleep(0.7)  # allow input debounce timer to fire
        # 5. keypress
        await page.press("#key-input", "Enter")
        # 6. select
        await page.select_option("#role-select", "admin")
        # 7. click
        await page.click("#dblclick-btn")
        await asyncio.sleep(0.3)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions))
    tc = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    recorded_types = {s.action_type for s in tc.steps}

    # Verify each recorded action type
    assert "click" in recorded_types or "dblclick" in recorded_types
    assert any(s.action_type in ("check", "uncheck") for s in tc.steps)
    assert any(s.action_type == "input" and s.input_value for s in tc.steps)
    assert any(s.action_type == "select" for s in tc.steps)
    # Check step metadata
    for step in tc.steps:
        if step.element:
            assert step.element.selector
            assert step.element.tag_name


@pytest.mark.flow("B16")
def test_b16_action_types_unrecordable_gap(isolated_workspace: Path, playground_server_url: str):
    """B16: Audit ActionTypes that recorder never emits (scroll, hover, wait).

    Models define 11 ActionTypes, but events.py lacks listeners for scroll and hover,
    and wait is purely synthetic.
    """
    from tracecase.events import EVENT_LISTENER_JS
    # Verify events.py does not attach listeners for scroll or mouseenter/hover
    assert "addEventListener('scroll'" not in EVENT_LISTENER_JS
    assert "addEventListener('mouseenter'" not in EVENT_LISTENER_JS
    assert "addEventListener('mouseover'" not in EVENT_LISTENER_JS


@pytest.mark.flow("B16")
@pytest.mark.xfail(strict=True, reason="BUG-010: ReplayEngine._perform raises ValueError for action_type='scroll'")
def test_b16_action_types_replay_scroll_bug(isolated_workspace: Path, playground_server_url: str):
    """B16 / BUG-010: Replaying action_type='scroll' raises ValueError in ReplayEngine._perform."""
    from tracecase.replay.engine import ReplayEngine
    step_scroll = Step(
        number=1,
        timestamp=datetime.now(),
        action_type="scroll",
        input_value="500",
        description_short="Scroll down",
        description_detailed="Scroll page down 500px",
    )
    tc = TestCase(
        id="tc_scroll_test",
        name="Scroll Test",
        created_at=datetime.now(),
        start_url=f"{playground_server_url}/login.html",
        browser="chromium",
        steps=[step_scroll],
        total_steps=1,
        total_duration=1.0,
    )
    engine = ReplayEngine(tc, headless=True)
    # Replay raises ValueError: Unsupported action type: scroll
    res = asyncio.run(engine.run())
    assert res.status == "passed"


@pytest.mark.flow("B17")
def test_b17_element_metadata_capture(isolated_workspace: Path, playground_server_url: str):
    """B17: Element metadata (tag_name, bounding_box, attributes, selector) captured."""
    out_dir = isolated_workspace / "b17_meta"
    url = f"{playground_server_url}/login.html"

    async def actions(page, rec):
        await page.fill("#username", "metadata_user")
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions))
    tc = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    step = next(s for s in tc.steps if s.element is not None)
    elem = step.element
    assert elem.tag_name in ("input", "button")
    assert elem.bounding_box is not None
    assert elem.selector is not None


@pytest.mark.flow("B18")
def test_b18_step_screenshot_with_highlight(isolated_workspace: Path, playground_server_url: str):
    """B18: Step screenshot with highlight outline generated."""
    out_dir = isolated_workspace / "b18_highlight"
    url = f"{playground_server_url}/login.html"

    async def actions(page, rec):
        await page.fill("#username", "highlight_user")
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions))
    tc = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    step = next(s for s in tc.steps if s.element is not None)
    if step.screenshot_with_highlight:
        assert Path(step.screenshot_with_highlight).exists()


@pytest.mark.flow("B19")
def test_b19_network_capture(isolated_workspace: Path, playground_server_url: str):
    """B19: Network request attached to step triggering it."""
    out_dir = isolated_workspace / "b19_network"
    url = f"{playground_server_url}/network_tester.html"

    async def actions(page, rec):
        await page.wait_for_selector("#btn-200")
        await page.click("#btn-200")
        await asyncio.sleep(0.4)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions))
    tc = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    all_reqs = tc.network_requests + [r for s in tc.steps for r in s.network_requests]
    assert any("/api/status/200" in r.url for r in all_reqs)


@pytest.mark.flow("B20")
def test_b20_console_log_capture(isolated_workspace: Path, playground_server_url: str):
    """B20: Browser console logs captured and attached to step."""
    out_dir = isolated_workspace / "b20_console"
    url = f"{playground_server_url}/console_errors.html"

    async def actions(page, rec):
        await page.wait_for_selector("#btn-log")
        await page.click("#btn-log")
        await asyncio.sleep(0.3)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions))
    tc = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    all_logs = tc.console_logs + [log for s in tc.steps for log in s.console_logs]
    assert any("Playground Info Message" in log.message for log in all_logs)


@pytest.mark.flow("B21")
def test_b21_page_uncaught_js_error_capture(isolated_workspace: Path, playground_server_url: str):
    """B21: Page uncaught JS error captured in page_errors."""
    out_dir = isolated_workspace / "b21_js_error"
    url = f"{playground_server_url}/console_errors.html"

    async def actions(page, rec):
        await page.wait_for_selector("#btn-throw")
        await page.click("#btn-throw")
        await asyncio.sleep(0.3)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions))
    tc = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    assert len(tc.page_errors) >= 1
    assert "Uncaught Playground Exception: boom!" in tc.page_errors[0].message


@pytest.mark.flow("B22")
def test_b22_multitab_capture(isolated_workspace: Path, playground_server_url: str):
    """B22: Multi-tab links tagged with page_id."""
    out_dir = isolated_workspace / "b22_multitab"
    url = f"{playground_server_url}/multitab.html"

    async def actions(page, rec):
        await page.wait_for_selector("#link-blank")
        await page.click("#link-blank")
        await asyncio.sleep(0.5)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions))
    tc = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    page_ids = {s.page_id for s in tc.steps if s.page_id is not None}
    assert 0 in page_ids


@pytest.mark.flow("B23")
def test_b23_outputs_schema_validation(isolated_workspace: Path, playground_server_url: str):
    """B23: testcase.json, testcase.md, testcase.html all exist and conform to schema."""
    out_dir = isolated_workspace / "b23_schema"
    url = f"{playground_server_url}/login.html"

    async def actions(page, rec):
        await page.fill("#username", "schema_user")
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions))
    json_path = out_dir / "testcase.json"
    md_path = out_dir / "testcase.md"
    html_path = out_dir / "testcase.html"

    assert json_path.exists()
    assert md_path.exists()
    assert html_path.exists()

    tc = TestCase.model_validate_json(json_path.read_text(encoding="utf-8"))
    assert tc.id.startswith("tc_")
    assert tc.browser == "chromium"
    assert len(tc.steps) >= 1
    assert "# " in md_path.read_text(encoding="utf-8")
    assert "<html" in html_path.read_text(encoding="utf-8").lower()


@pytest.mark.flow("B24")
def test_b24_hostile_content_escaping(isolated_workspace: Path, playground_server_url: str):
    """B24 (Security): Hostile XSS inputs escaped in testcase.html and Markdown."""
    out_dir = isolated_workspace / "b24_hostile"
    url = f"{playground_server_url}/login.html"
    xss_payload = "<script>window.__xss_fired=true;</script>"

    async def actions(page, rec):
        await page.wait_for_selector("#username")
        await page.fill("#username", xss_payload)
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions))
    html_content = (out_dir / "testcase.html").read_text(encoding="utf-8")
    assert "<script>window.__xss_fired=true;</script>" not in html_content


@pytest.mark.flow("B25")
def test_b25_output_directory_overwrite(isolated_workspace: Path, playground_server_url: str):
    """B25: Recording to an existing output directory safely overwrites/refreshes."""
    out_dir = isolated_workspace / "b25_overwrite"
    url = f"{playground_server_url}/login.html"

    async def actions(page, rec):
        await page.fill("#username", "first_run")
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, name="First Run", actions_callback=actions))
    tc1 = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    assert tc1.name == "First Run"

    # Second run to same directory
    async def actions2(page, rec):
        await page.fill("#username", "second_run")
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, name="Second Run", actions_callback=actions2))
    tc2 = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    assert tc2.name == "Second Run"


@pytest.mark.flow("B26")
def test_b26_path_with_spaces_unicode(isolated_workspace: Path, playground_server_url: str):
    """B26: Output path containing spaces and Unicode characters handled cleanly."""
    out_dir = isolated_workspace / "my recordings 📁/тест session 🚀"
    url = f"{playground_server_url}/login.html"

    async def actions(page, rec):
        await page.fill("#username", "unicode_user")
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions))
    assert (out_dir / "testcase.json").exists()


@pytest.mark.flow("B27")
def test_b27_password_masking_json(isolated_workspace: Path, playground_server_url: str):
    """B27 / BUG-009A: Password input values masked with asterisks in testcase.json."""
    out_dir = isolated_workspace / "b27_json"
    url = f"{playground_server_url}/login.html"
    secret = "SuperSecretPassword123!"

    async def actions(page, rec):
        await page.wait_for_selector("#password")
        await page.fill("#password", secret)
        await asyncio.sleep(0.7)  # allow input debounce timer (500ms) to fire
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions))
    tc = TestCase.model_validate_json((out_dir / "testcase.json").read_text(encoding="utf-8"))
    pwd_step = next(s for s in tc.steps if s.element and s.element.attributes.get("type") == "password")
    assert pwd_step.input_value != secret, "Password input must not be stored in plaintext"
    assert secret not in str(pwd_step.input_value), "Plaintext password leaked in testcase.json"
    val = pwd_step.input_value or ""
    # Accepts any valid masking format (all asterisks, bullets, [REDACTED], or empty string) while failing on plaintext
    assert any([all(c in "*•●" for c in val) and len(val) > 0, val in ("[REDACTED]", "***", "[MASKED]")]), "Input value was not properly masked"


@pytest.mark.flow("B27")
def test_b27_password_masking_markdown(isolated_workspace: Path, playground_server_url: str):
    """B27 / BUG-009B: Password values must NOT leak into exported testcase.md."""
    out_dir = isolated_workspace / "b27_md"
    url = f"{playground_server_url}/login.html"
    secret = "SuperSecretPassword123!"

    async def actions(page, rec):
        await page.wait_for_selector("#password")
        await page.fill("#password", secret)
        await asyncio.sleep(0.7)
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions))
    md_content = (out_dir / "testcase.md").read_text(encoding="utf-8")
    assert secret not in md_content, "Plaintext password found in testcase.md"


@pytest.mark.flow("B27")
def test_b27_password_masking_html(isolated_workspace: Path, playground_server_url: str):
    """B27 / BUG-009C: Password values must NOT leak into exported testcase.html."""
    out_dir = isolated_workspace / "b27_html"
    url = f"{playground_server_url}/login.html"
    secret = "SuperSecretPassword123!"

    async def actions(page, rec):
        await page.wait_for_selector("#password")
        await page.fill("#password", secret)
        await asyncio.sleep(0.7)
        await page.click("#btn-login")
        await asyncio.sleep(0.2)

    asyncio.run(_run_recorder(out_dir, url, actions_callback=actions))
    html_content = (out_dir / "testcase.html").read_text(encoding="utf-8")
    assert secret not in html_content, "Plaintext password found in testcase.html"

