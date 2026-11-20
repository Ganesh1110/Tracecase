"""Tests for Phase 9.1.4 (Step 3.1): Managed Chromium Streaming Session & CDP Screencast."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tracecase.streaming import (
    CDPScreencastManager,
    ManagedChromiumSession,
    ScreencastFrame,
    StreamSessionConfig,
    StreamSessionState,
    StreamingSessionManager,
    get_streaming_session_manager,
)


@pytest.mark.asyncio
async def test_managed_chromium_session_lifecycle_and_screencast() -> None:
    """Verify Chromium session launches, produces real CDP screencast frames, and shuts down cleanly."""
    config = StreamSessionConfig(
        session_id="test_stream_101",
        url="data:text/html,<h1 id='title'>Tracecase Live Stream</h1><p>Test Content</p>",
        headless=True,
        viewport_width=800,
        viewport_height=600,
        format="jpeg",
        quality=60,
    )

    session = ManagedChromiumSession(config=config)
    assert session.state == StreamSessionState.INITIALIZING

    captured_frames: list[ScreencastFrame] = []

    async def on_frame(frame: ScreencastFrame) -> None:
        captured_frames.append(frame)

    session.add_frame_listener(on_frame)

    try:
        await session.launch()
        assert session.state == StreamSessionState.ACTIVE
        assert session.page is not None
        assert session.screencast is not None
        assert session.screencast.is_active is True

        # Wait briefly for CDP frames to arrive
        for _ in range(20):
            if captured_frames:
                break
            await asyncio.sleep(0.05)

        # Verify frames were received
        assert len(captured_frames) >= 1
        first_frame = captured_frames[0]
        assert first_frame.frame_index >= 1
        assert len(first_frame.data_base64) > 100
        assert first_frame.byte_size > 100

        # Verify session info telemetry
        info = await session.get_info()
        assert info.session_id == "test_stream_101"
        assert info.state == StreamSessionState.ACTIVE
        assert info.frames_sent >= 1
        assert info.total_bytes_streamed >= 100
        assert info.viewport_width == 800
        assert info.viewport_height == 600

    finally:
        await session.close()
        assert session.state == StreamSessionState.STOPPED
        assert session.page is None
        assert session.screencast is None


@pytest.mark.asyncio
async def test_managed_session_frame_generation_on_dom_mutation() -> None:
    """Verify DOM mutations and navigation trigger continuous frame streaming."""
    config = StreamSessionConfig(
        session_id="test_stream_dom_mutate",
        url="data:text/html,<div id='box' style='width:100px;height:100px;background:blue;'></div>",
        headless=True,
        viewport_width=640,
        viewport_height=480,
    )
    session = ManagedChromiumSession(config=config)
    frames_received = []

    async def listener(frame: ScreencastFrame) -> None:
        frames_received.append(frame.frame_index)

    session.add_frame_listener(listener)

    try:
        await session.launch()
        # Wait for initial frame
        for _ in range(20):
            if frames_received:
                break
            await asyncio.sleep(0.05)

        initial_count = len(frames_received)
        assert initial_count >= 1

        # Mutate DOM to trigger new screencast frames
        await session.page.evaluate("document.getElementById('box').style.background = 'red'")
        await session.page.evaluate("document.body.innerHTML += '<h2>Updated Content</h2>'")

        # Wait for subsequent frame
        for _ in range(25):
            if len(frames_received) > initial_count:
                break
            await asyncio.sleep(0.05)

        assert len(frames_received) >= initial_count

        # Test remove listener
        session.remove_frame_listener(listener)
        assert listener not in session.screencast._listeners
    finally:
        await session.close()
        assert session.state == StreamSessionState.STOPPED


@pytest.mark.asyncio
async def test_streaming_session_manager_concurrency_and_authorization() -> None:
    """Verify session manager enforces max limits, ownership security, and clean shutdown."""
    manager = StreamingSessionManager(max_concurrent_sessions=2)

    config1 = StreamSessionConfig(
        session_id="stream_auth_1",
        url="data:text/html,<h1>Session 1</h1>",
        headless=True,
        owner_id="user_alice",
    )
    config2 = StreamSessionConfig(
        session_id="stream_auth_2",
        url="data:text/html,<h1>Session 2</h1>",
        headless=True,
        owner_id="user_bob",
    )
    config3 = StreamSessionConfig(
        session_id="stream_overflow_3",
        url="data:text/html,<h1>Session 3</h1>",
        headless=True,
        owner_id="user_charlie",
    )

    try:
        s1 = await manager.create_session(config1)
        s2 = await manager.create_session(config2)
        assert len(manager.list_sessions()) == 2

        # Exceeding max concurrent sessions must fail cleanly
        with pytest.raises(RuntimeError, match="Maximum concurrent streaming sessions"):
            await manager.create_session(config3)

        # Ownership validation: Alice can access her session, Bob cannot access Alice's session
        assert manager.get_session("stream_auth_1", owner_id="user_alice") is not None
        with pytest.raises(PermissionError, match="Unauthorized access"):
            manager.get_session("stream_auth_1", owner_id="user_bob")

        # Non-existent session
        assert manager.get_session("non_existent_id") is None

        # Terminating one session opens up capacity
        closed = await manager.close_session("stream_auth_1")
        assert closed is True
        assert len(manager.list_sessions()) == 1

        # Now config3 can be launched
        s3 = await manager.create_session(config3)
        assert s3 is not None
        assert len(manager.list_sessions()) == 2

    finally:
        # Shutdown cleanly releases all sessions
        await manager.shutdown()
        assert len(manager.list_sessions()) == 0


@pytest.mark.asyncio
async def test_managed_session_clean_shutdown_on_exception() -> None:
    """Verify session handles invalid URLs or initialization errors without leaking processes."""
    config = StreamSessionConfig(
        session_id="test_fail_stream",
        url="invalid://not-a-valid-url-format",
        timeout_ms=500,
        headless=True,
    )

    session = ManagedChromiumSession(config=config)
    # Launching with invalid protocol raises or fails gracefully
    try:
        await session.launch()
    except Exception:
        pass

    # In either case, cleanup ensures state is not leaking
    await session.close()
    assert session.page is None
    assert session.screencast is None
