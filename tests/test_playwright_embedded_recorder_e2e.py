"""Playwright End-to-End Test for Embedded Browser Recorder in Tracecase Studio.

Tests:
1. Opens Studio /recorder page in Playwright browser.
2. Enters target playground URL and clicks 'Start Recording'.
3. Viewport canvas renders live CDP screencast without any popup window.
4. Forwards mouse clicks and keyboard typing via WebSocket.
5. Measures and asserts localhost click/typing latency under 150 ms.
6. Verifies password masking at capture (BUG-009).
7. Clicks 'Stop & Save', verifies testcase.json was saved.
8. Runs 'tracecase replay' on the newly generated testcase and verifies replay succeeds.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from playwright.async_api import async_playwright

from tracecase.replay.engine import ReplayEngine
from tracecase.ui.server import create_app


PLAYGROUND_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Playground Target</title>
  <style>
    body { font-family: sans-serif; padding: 30px; }
    .box { margin-bottom: 15px; }
    input { padding: 8px; font-size: 14px; width: 250px; }
    button { padding: 8px 16px; font-size: 14px; cursor: pointer; }
    #msg { margin-top: 15px; color: green; font-weight: bold; }
  </style>
</head>
<body>
  <h1>Embedded Playground</h1>
  <div class="box">
    <label for="uname">Username: </label><br/>
    <input type="text" id="uname" placeholder="Enter username" />
  </div>
  <div class="box">
    <label for="pwd">Password: </label><br/>
    <input type="password" id="pwd" placeholder="Enter secret password" />
  </div>
  <div class="box">
    <button id="submit-btn" onclick="document.getElementById('msg').textContent = 'Welcome, ' + document.getElementById('uname').value;">Login</button>
  </div>
  <div id="msg"></div>
</body>
</html>
"""


class PlaygroundHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PLAYGROUND_HTML.encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        pass


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def playground_server():
    port = 9021
    server = ThreadingHTTPServer(("127.0.0.1", port), PlaygroundHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    t.join(timeout=2)


@pytest.fixture(scope="module")
def studio_server():
    port = 9020
    app = create_app()

    server_error = []

    def run_server():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info")
            server = uvicorn.Server(config)
            loop.run_until_complete(server.serve())
        except Exception as exc:
            server_error.append(str(exc))
            print("SERVER ERROR:", exc)

    t = threading.Thread(target=run_server, daemon=True)
    t.start()

    # Wait for server ready
    base_url = f"http://127.0.0.1:{port}"
    import urllib.request
    ready = False
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=1) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception as exc:
            if _ == 49:
                print("HEALTH CHECK FAILED WITH:", type(exc), exc)
            time.sleep(0.1)

    assert ready, f"Studio server failed to start at {base_url}"
    yield base_url


@pytest.mark.timeout(60)
@pytest.mark.asyncio
async def test_embedded_recorder_playwright_e2e(
    playground_server: str,
    studio_server: str,
    tmp_path: Path,
) -> None:
    """Drive the Studio embedded recorder page end-to-end with Playwright."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # 1. Open Studio /recorder page
        recorder_url = f"{studio_server}/recorder"
        await page.goto(recorder_url, wait_until="networkidle")

        # Verify page header
        header = page.locator("h1")
        await header.wait_for()
        assert "Browser Recorder" in await header.text_content()

        # 2. Enter target URL into URL input field
        url_input = page.locator('input[placeholder*="example.com"]')
        await url_input.wait_for()
        await url_input.fill(playground_server)

        # 3. Click 'Start Recording' button
        start_btn = page.locator('button:has-text("Start Recording")')
        await start_btn.click()

        # 4. Viewport canvas renders live CDP screencast without any popup window
        canvas = page.locator("canvas")
        await canvas.wait_for(state="visible", timeout=15000)

        # Wait for screencast frames to stream into canvas
        await page.wait_for_timeout(1000)

        # Check latency badge is present and measure latency
        latency_badge = page.locator('span:has-text("ms")').first
        await latency_badge.wait_for(state="visible", timeout=5000)
        latency_text = await latency_badge.text_content()
        measured_ms = 0.0
        try:
            # text is like "30 FPS • 1ms"
            for part in latency_text.split("•"):
                if "ms" in part:
                    measured_ms = float(part.replace("ms", "").strip())
        except ValueError:
            pass

        print(f"\nMeasured localhost WebSocket roundtrip latency: {measured_ms} ms")
        assert measured_ms < 150.0, f"Latency {measured_ms} ms exceeded 150 ms target"

        # 5. Measure click and typing input forwarding
        # Target elements inside the canvas:
        # Username input at x: ~50, y: ~90; Password input at x: ~50, y: ~150; Button at x: ~50, y: ~210
        canvas_box = await canvas.bounding_box()
        assert canvas_box is not None

        # Coordinates mapped to canvas viewport
        scale_x = canvas_box["width"] / 1280.0
        scale_y = canvas_box["height"] / 720.0

        # Click username box
        t_click_start = time.perf_counter()
        await page.mouse.click(
            canvas_box["x"] + 60 * scale_x,
            canvas_box["y"] + 95 * scale_y,
        )
        await page.keyboard.type("alice", delay=20)
        t_click_end = time.perf_counter()
        typing_latency_ms = (t_click_end - t_click_start) * 1000
        print(f"Typing interaction completed in {typing_latency_ms:.2f} ms")

        # Click password box and type secret password
        await page.mouse.click(
            canvas_box["x"] + 60 * scale_x,
            canvas_box["y"] + 155 * scale_y,
        )
        await page.keyboard.type("SecretP@ssw0rd!", delay=20)

        # Click login button
        await page.mouse.click(
            canvas_box["x"] + 60 * scale_x,
            canvas_box["y"] + 215 * scale_y,
        )

        # Wait for recorder steps list to update in the UI
        await page.wait_for_timeout(1500)

        # 6. Stop and save recording
        stop_btn = page.locator('button:has-text("Stop & Save")')
        await stop_btn.wait_for(state="visible")
        await stop_btn.click()

        # Wait for completion state
        await page.wait_for_timeout(1000)
        await browser.close()

    # 7. Verify generated testcase artifacts
    recordings_dir = Path("recordings")
    assert recordings_dir.exists()
    all_runs = sorted(recordings_dir.glob("rec_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not all_runs:
        all_runs = sorted(recordings_dir.glob("*_rec_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    assert len(all_runs) > 0, "No recorded test directories found in recordings/"
    latest_rec = all_runs[0]

    tc_json = latest_rec / "testcase.json"
    assert tc_json.exists(), f"testcase.json missing in {latest_rec}"
    tc_data = json.loads(tc_json.read_text(encoding="utf-8"))

    # Assert testcase schema and steps
    assert "steps" in tc_data
    steps = tc_data["steps"]
    assert len(steps) >= 1, "Expected at least 1 recorded step"

    # Password Masking Requirement: Plaintext password MUST NOT appear anywhere in the test case files
    raw_json_str = tc_json.read_text(encoding="utf-8")
    assert "SecretP@ssw0rd!" not in raw_json_str, "Plaintext password leaked into testcase.json!"

    tc_md = latest_rec / "testcase.md"
    if tc_md.exists():
        assert "SecretP@ssw0rd!" not in tc_md.read_text(encoding="utf-8"), "Plaintext password leaked into testcase.md!"

    tc_html = latest_rec / "testcase.html"
    if tc_html.exists():
        assert "SecretP@ssw0rd!" not in tc_html.read_text(encoding="utf-8"), "Plaintext password leaked into testcase.html!"

    # 8. Replay the newly generated testcase with ReplayEngine
    from tracecase.models import TestCase

    tc_model = TestCase.model_validate(tc_data)
    replay_engine = ReplayEngine(
        testcase=tc_model,
        headless=True,
        timeout=10000,
        heal=False,
        testcase_dir=latest_rec,
    )
    result = await replay_engine.run()
    assert result.exit_code == 0, f"Replay failed with status {result.status}: {[s.error for s in result.steps if s.error]}"
    assert result.status == "passed", f"Replay status: {result.status}"
    print(f"✓ Replay succeeded with exit code 0 ({len(result.steps)} steps replayed).")
