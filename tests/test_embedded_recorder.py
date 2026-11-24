"""Integration and security tests for embedded recorder in Tracecase Studio."""

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
    get_streaming_session_manager,
    map_client_coordinates,
)
from tracecase.ui.server import create_app
from tracecase.ui.service import recording_manager


def test_coordinate_mapping_comprehensive() -> None:
    """Verify coordinate scaling, letterboxing, and clamping."""
    browser_w = 1280
    browser_h = 720

    # 1. Scaled down with letterboxing
    # Viewport container is 1000x600, image rendered at (100, 50) with size 800x450
    vp = ClientViewportDimensions(
        client_width=1000.0,
        client_height=600.0,
        content_x=100.0,
        content_y=50.0,
        content_width=800.0,
        content_height=450.0,
    )

    # Click in top-left of content (100, 50) -> should be (0, 0)
    bx, by = map_client_coordinates(100.0, 50.0, vp, browser_w, browser_h)
    assert bx == 0.0
    assert by == 0.0

    # Click in center of content (500, 275) -> should be (640, 360)
    bx, by = map_client_coordinates(500.0, 275.0, vp, browser_w, browser_h)
    assert abs(bx - 640.0) < 1e-4
    assert abs(by - 360.0) < 1e-4

    # Click out of bounds (in pillarbox area left of content: x=20, y=50) -> clamped to 0,0
    bx, by = map_client_coordinates(20.0, 50.0, vp, browser_w, browser_h)
    assert bx == 0.0
    assert by == 0.0

    # Click out of bounds (right of content: x=950, y=50) -> clamped to browser_w
    bx, by = map_client_coordinates(950.0, 50.0, vp, browser_w, browser_h)
    assert bx == 1280.0


def test_security_single_recording_session_limit(tmp_path: Path) -> None:
    """Starting a second concurrent recording session returns HTTP 409 Conflict."""
    app = create_app()
    with TestClient(app) as client:
        # Mock or start session
        session_mgr = recording_manager
        session_mgr.current_session = None

        # Start first session
        res1 = client.post(
            "/api/record/start",
            json={"url": "data:text/html,<h1>Test</h1>", "embedded": True},
        )
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["status"] == "recording"
        session_id = data1["session_id"]
        token = data1["stream_token"]
        assert token is not None

        try:
            # Attempt second session while first is active
            res2 = client.post(
                "/api/record/start",
                json={"url": "data:text/html,<h1>Test2</h1>", "embedded": True},
            )
            assert res2.status_code == 409
            assert "already active" in res2.json()["detail"].lower()
        finally:
            # Clean up first session
            client.post("/api/record/stop")


def test_security_websocket_token_validation() -> None:
    """Verify WebSocket rejects missing or incorrect tokens with 1008 policy violation."""
    app = create_app()
    with TestClient(app) as client:
        session_mgr = recording_manager
        session_mgr.current_session = None

        # Start recording
        res = client.post(
            "/api/record/start",
            json={"url": "data:text/html,<h1>Test</h1>", "embedded": True},
        )
        assert res.status_code == 200
        data = res.json()
        session_id = data["session_id"]
        valid_token = data["stream_token"]

        try:
            # 1. Missing token
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(f"/api/ws/record/stream/{session_id}"):
                    pass
            assert exc_info.value.code == 1008

            # 2. Wrong token
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(f"/api/ws/record/stream/{session_id}?token=invalid-secret-token"):
                    pass
            assert exc_info.value.code == 1008

            # 3. Valid token connects successfully
            with client.websocket_connect(f"/api/ws/record/stream/{session_id}?token={valid_token}") as ws:
                # First message should be session_state or frame
                init_msg = ws.receive_json()
                assert init_msg.get("type") in ("session_state", "frame")
        finally:
            client.post("/api/record/stop")


def test_security_websocket_origin_check() -> None:
    """Verify WebSocket rejects untrusted cross-origin requests."""
    app = create_app()
    with TestClient(app) as client:
        session_mgr = recording_manager
        session_mgr.current_session = None

        res = client.post(
            "/api/record/start",
            json={"url": "data:text/html,<h1>Test</h1>", "embedded": True},
        )
        assert res.status_code == 200
        data = res.json()
        session_id = data["session_id"]
        token = data["stream_token"]

        try:
            # Untrusted origin
            headers = {"Origin": "https://evil-attacker-website.com"}
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(
                    f"/api/ws/record/stream/{session_id}?token={token}",
                    headers=headers,
                ):
                    pass
            assert exc_info.value.code == 1008

            # Trusted origin (e.g. localhost)
            headers_ok = {"Origin": "http://localhost:9010"}
            with client.websocket_connect(
                f"/api/ws/record/stream/{session_id}?token={token}",
                headers=headers_ok,
            ) as ws:
                msg = ws.receive_json()
                assert msg.get("type") in ("session_state", "frame")
        finally:
            client.post("/api/record/stop")


def test_embedded_recorder_multitab_and_dialog_handling() -> None:
    """Verify tab switching and dialog responses over WebSocket."""
    app = create_app()
    with TestClient(app) as client:
        session_mgr = recording_manager
        session_mgr.current_session = None

        res = client.post(
            "/api/record/start",
            json={
                "url": "data:text/html,<button id='btn' onclick='confirm(\"Are you sure?\")'>Ask</button>",
                "embedded": True,
            },
        )
        assert res.status_code == 200
        data = res.json()
        session_id = data["session_id"]
        token = data["stream_token"]

        try:
            with client.websocket_connect(f"/api/ws/record/stream/{session_id}?token={token}") as ws:
                # Drain until we get frame or session_state
                msg = ws.receive_json()
                assert msg is not None

                # Test tab switch command over WS
                ws.send_json({"type": "switch_tab", "page_id": "page_0"})

                # Test dialog response message over WS
                ws.send_json({"type": "dialog_response", "accept": True, "prompt_text": ""})

                # Test ping / pong message over WS
                ws.send_json({"type": "ping", "data": {"client_ts": 1000}})
                pong = ws.receive_json()
                while pong.get("type") != "pong":
                    pong = ws.receive_json()
                assert pong["type"] == "pong"
                assert pong["payload"]["pong"] is True
                assert pong["payload"]["client_ts"] == 1000
        finally:
            client.post("/api/record/stop")


def test_embedded_recorder_disconnect_preserves_steps_bug012(tmp_path: Path) -> None:
    """Disconnect or tab-close preserves recorded steps on session teardown without silent loss."""
    app = create_app()
    with TestClient(app) as client:
        session_mgr = recording_manager
        session_mgr.current_session = None

        res = client.post(
            "/api/record/start",
            json={"url": "data:text/html,<h1 id='title'>Bug012</h1>", "embedded": True},
        )
        assert res.status_code == 200
        data = res.json()
        session_id = data["session_id"]
        token = data["stream_token"]

        # Simulate adding a step to recorder
        recorder = session_mgr._recorder
        assert recorder is not None
        from datetime import datetime
        from tracecase.models import ElementInfo, Step
        recorder.steps.append(
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="click",
                element=ElementInfo(
                    selector="#title",
                    tag_name="h1",
                    bounding_box={"x": 10.0, "y": 10.0, "width": 100.0, "height": 30.0},
                ),
                description_short="Click on title",
                description_detailed="Click on heading element #title",
            )
        )

        # Abrupt stop/disconnect
        stop_res = client.post("/api/record/stop")
        assert stop_res.status_code == 200

        # Verify testcase.json was preserved and exported
        out_dir = Path(data["output_dir"])
        assert (out_dir / "testcase.json").exists()
        tc_data = json.loads((out_dir / "testcase.json").read_text(encoding="utf-8"))
        assert len(tc_data["steps"]) >= 1
        assert tc_data["steps"][0]["element"]["selector"] == "#title"
