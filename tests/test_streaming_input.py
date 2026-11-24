"""Tests for Phase 9.1.4 (Step 3.2): Real Playwright Chromium Input Forwarding & WebSocket Streaming."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tracecase.streaming import (
    ClientViewportDimensions,
    InputEvent,
    InputEventType,
    ManagedChromiumSession,
    MouseButton,
    StreamSessionConfig,
    dispatch_input_event,
    get_streaming_session_manager,
    map_client_coordinates,
)
from tracecase.ui.server import create_app

HTML_INTERACTIVE_PAGE = """<!doctype html>
<html>
<head><meta charset="utf-8"><title>Interactive Streaming Test</title></head>
<body style="margin:0; padding:20px; font-family:sans-serif; height:2000px;">
  <h1>Interactive Test Bench</h1>
  <div>
    <button id="test-btn" onclick="this.textContent = 'Clicked ' + (++window.clicks || (window.clicks=1));">Click Me</button>
  </div>
  <div style="margin-top:15px;">
    <input id="test-input" placeholder="Type here" type="text" />
  </div>
  <div style="margin-top:15px;">
    <input id="test-checkbox" type="checkbox" />
    <label for="test-checkbox">Enable Feature</label>
  </div>
</body>
</html>"""


def test_coordinate_mapping_scaling_and_letterboxing() -> None:
    """Verify coordinate scaling math between client displayed viewport and actual Chromium viewport."""
    browser_w = 1280
    browser_h = 720

    # 1. Exact 1:1 match
    vp_exact = ClientViewportDimensions(
        client_width=1280.0,
        client_height=720.0,
        content_x=0.0,
        content_y=0.0,
        content_width=1280.0,
        content_height=720.0,
    )
    bx, by = map_client_coordinates(640.0, 360.0, vp_exact, browser_w, browser_h)
    assert (bx, by) == (640.0, 360.0)

    # 2. Scaled down (800x450 in UI for 1280x720 in browser)
    # Ratio = 1280/800 = 1.6, 720/450 = 1.6
    vp_scaled = ClientViewportDimensions(
        client_width=800.0,
        client_height=450.0,
        content_x=0.0,
        content_y=0.0,
        content_width=800.0,
        content_height=450.0,
    )
    bx, by = map_client_coordinates(400.0, 225.0, vp_scaled, browser_w, browser_h)
    assert (bx, by) == (640.0, 360.0)

    # 3. Scaled with letterboxing (container is 1000x500, but image is 800x450 centered at x=100, y=25)
    vp_letterboxed = ClientViewportDimensions(
        client_width=1000.0,
        client_height=500.0,
        content_x=100.0,
        content_y=25.0,
        content_width=800.0,
        content_height=450.0,
    )
    # Center of content image is at x = 100 + 400 = 500, y = 25 + 225 = 250
    bx, by = map_client_coordinates(500.0, 250.0, vp_letterboxed, browser_w, browser_h)
    assert (bx, by) == (640.0, 360.0)

    # Top-left of content image (100, 25) -> (0, 0)
    bx, by = map_client_coordinates(100.0, 25.0, vp_letterboxed, browser_w, browser_h)
    assert (bx, by) == (0.0, 0.0)

    # Clamping out-of-bounds clicks (e.g. clicked inside letterbox black bar at x=20, y=10)
    bx, by = map_client_coordinates(20.0, 10.0, vp_letterboxed, browser_w, browser_h)
    assert (bx, by) == (0.0, 0.0)


@pytest.mark.asyncio
async def test_real_playwright_mouse_click_and_keyboard_typing() -> None:
    """Verify real Playwright Chromium page receives native clicks and typing via dispatch_input_event."""
    import urllib.parse
    encoded_html = urllib.parse.quote(HTML_INTERACTIVE_PAGE)
    data_url = f"data:text/html,{encoded_html}"

    config = StreamSessionConfig(
        session_id="stream_real_input",
        url=data_url,
        headless=True,
        viewport_width=1000,
        viewport_height=700,
    )

    session = ManagedChromiumSession(config=config)
    try:
        await session.launch()
        page = session.page
        assert page is not None

        # 1. Test Mouse Click on Button
        btn_box = await page.locator("#test-btn").bounding_box()
        assert btn_box is not None
        target_x = btn_box["x"] + btn_box["width"] / 2
        target_y = btn_box["y"] + btn_box["height"] / 2

        click_event = InputEvent(
            event_type=InputEventType.CLICK,
            x=target_x,
            y=target_y,
            button=MouseButton.LEFT,
            click_count=1,
        )
        await session.handle_input(click_event)

        btn_text = await page.locator("#test-btn").text_content()
        assert btn_text == "Clicked 1"

        # Click again
        await session.handle_input(click_event)
        btn_text2 = await page.locator("#test-btn").text_content()
        assert btn_text2 == "Clicked 2"

        # 2. Test Keyboard Typing into Input Element
        input_box = await page.locator("#test-input").bounding_box()
        assert input_box is not None
        inp_x = input_box["x"] + 10
        inp_y = input_box["y"] + 10

        # Click to focus
        await session.handle_input(InputEvent(event_type=InputEventType.CLICK, x=inp_x, y=inp_y))

        # Type text
        type_event = InputEvent(event_type=InputEventType.TYPE, text="Tracecase Automated Studio")
        await session.handle_input(type_event)

        input_val = await page.locator("#test-input").input_value()
        assert input_val == "Tracecase Automated Studio"

        # 3. Test Scroll Wheel
        wheel_event = InputEvent(
            event_type=InputEventType.WHEEL,
            x=200.0,
            y=200.0,
            delta_x=0.0,
            delta_y=350.0,
        )
        await session.handle_input(wheel_event)
        await asyncio.sleep(0.1)
        scroll_y = await page.evaluate("window.scrollY")
        assert scroll_y > 0

    finally:
        await session.close()


def test_websocket_streaming_and_interactive_controls() -> None:
    """Verify live WebSocket frame delivery, input forwarding, resize, and ping/pong."""
    import urllib.parse
    encoded_html = urllib.parse.quote(HTML_INTERACTIVE_PAGE)
    data_url = f"data:text/html,{encoded_html}"

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    mgr = get_streaming_session_manager()
    session_id = "stream_ws_test_01"
    config = StreamSessionConfig(
        session_id=session_id,
        url=data_url,
        headless=True,
        viewport_width=800,
        viewport_height=600,
        owner_id="default_user",
    )

    session = loop.run_until_complete(mgr.create_session(config=config))
    client = TestClient(create_app())

    try:
        with client.websocket_connect(f"/api/ws/record/stream/{session_id}") as ws:
            # 1. First message should be session_state or frame
            msg1 = json.loads(ws.receive_text())
            assert msg1["type"] in ("session_state", "frame")

            # 2. Receive at least one frame message with valid base64 image data
            frame_received = False
            for _ in range(15):
                raw = ws.receive_text()
                parsed = json.loads(raw)
                if parsed["type"] == "frame":
                    assert len(parsed["payload"]["data_base64"]) > 50
                    frame_received = True
                    break
            assert frame_received is True

            # 3. Test Ping -> Pong
            ws.send_text(json.dumps({"type": "ping", "data": {}}))
            pong_msg = json.loads(ws.receive_text())
            assert pong_msg["type"] == "pong"

            # 4. Test Click Event via WebSocket
            btn_box = loop.run_until_complete(session.page.locator("#test-btn").bounding_box())
            assert btn_box is not None
            click_msg = {
                "type": "input",
                "data": {
                    "event_type": "click",
                    "x": btn_box["x"] + btn_box["width"] / 2,
                    "y": btn_box["y"] + btn_box["height"] / 2,
                    "button": "left",
                    "click_count": 1,
                },
            }
            ws.send_text(json.dumps(click_msg))

            # Allow brief moment for Playwright event loop to process
            loop.run_until_complete(asyncio.sleep(0.15))
            btn_text = loop.run_until_complete(session.page.locator("#test-btn").text_content())
            assert btn_text == "Clicked 1"

            # 5. Test Typing Event via WebSocket
            inp_box = loop.run_until_complete(session.page.locator("#test-input").bounding_box())
            assert inp_box is not None
            focus_msg = {
                "type": "input",
                "data": {
                    "event_type": "click",
                    "x": inp_box["x"] + 10,
                    "y": inp_box["y"] + 10,
                },
            }
            ws.send_text(json.dumps(focus_msg))
            loop.run_until_complete(asyncio.sleep(0.1))

            type_msg = {
                "type": "input",
                "data": {
                    "event_type": "type",
                    "text": "Live WebSocket Input",
                },
            }
            ws.send_text(json.dumps(type_msg))
            loop.run_until_complete(asyncio.sleep(0.15))

            val = loop.run_until_complete(session.page.locator("#test-input").input_value())
            assert val == "Live WebSocket Input"

            # 6. Test Resize Viewport Command
            resize_msg = {
                "type": "resize",
                "data": {"width": 1024, "height": 768},
            }
            ws.send_text(json.dumps(resize_msg))
            loop.run_until_complete(asyncio.sleep(0.1))
            info = loop.run_until_complete(session.get_info())
            assert info.viewport_width == 1024
            assert info.viewport_height == 768

    finally:
        loop.run_until_complete(mgr.close_session(session_id))
        loop.close()


def test_websocket_security_and_error_handling() -> None:
    """Verify unauthorized access, non-existent sessions, and oversized payloads are rejected safely."""
    client = TestClient(create_app())

    # 1. Non-existent session must be closed with 1008
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/ws/record/stream/non_existent_session"):
            pass
    assert exc_info.value.code == 1008

    # 2. Unauthorized session ownership check
    # Create session owned by 'user_secret'
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    mgr = get_streaming_session_manager()
    conf = StreamSessionConfig(
        session_id="stream_private_123",
        url="data:text/html,<h1>Private</h1>",
        headless=True,
        owner_id="user_secret",
    )
    loop.run_until_complete(mgr.create_session(conf))

    try:
        # Connecting without token or with wrong token must fail with 1008
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/api/ws/record/stream/stream_private_123?token=wrong_user"):
                pass
        assert exc_info.value.code == 1008

        # Connecting with correct token succeeds
        with client.websocket_connect("/api/ws/record/stream/stream_private_123?token=user_secret") as ws:
            # Test oversized message rejection
            oversized_payload = "x" * 70000
            ws.send_text(oversized_payload)
            err_msg = None
            for _ in range(5):
                msg = json.loads(ws.receive_text())
                if msg.get("type") == "error":
                    err_msg = msg
                    break
            assert err_msg is not None
            assert err_msg["type"] == "error"
            assert "64KB" in err_msg["payload"]["error"]

            # Test malformed JSON
            ws.send_text("{not: valid: json")
            err_json = None
            for _ in range(5):
                msg = json.loads(ws.receive_text())
                if msg.get("type") == "error":
                    err_json = msg
                    break
            assert err_json is not None
            assert err_json["type"] == "error"

    finally:
        loop.run_until_complete(mgr.close_session("stream_private_123"))
        loop.close()


@pytest.mark.asyncio
async def test_cross_session_input_isolation() -> None:
    """Verify input delivered to Session A never leaks or affects Session B."""
    mgr = get_streaming_session_manager()

    s1 = await mgr.create_session(
        StreamSessionConfig(
            session_id="isolate_sess_a",
            url="data:text/html,<input id='fld' value='Initial A' />",
            headless=True,
        )
    )
    s2 = await mgr.create_session(
        StreamSessionConfig(
            session_id="isolate_sess_b",
            url="data:text/html,<input id='fld' value='Initial B' />",
            headless=True,
        )
    )

    try:
        # Focus and type into Session A
        await s1.page.locator("#fld").click()
        await s1.handle_input(InputEvent(event_type=InputEventType.TYPE, text=" Edit A"))

        val_a = await s1.page.locator("#fld").input_value()
        val_b = await s2.page.locator("#fld").input_value()

        assert val_a == "Initial A Edit A"
        assert val_b == "Initial B"  # Completely untouched!
    finally:
        await mgr.close_session("isolate_sess_a")
        await mgr.close_session("isolate_sess_b")
