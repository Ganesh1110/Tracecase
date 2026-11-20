"""CDP Screencast Manager for high-frequency Chromium frame capture."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any

from playwright.async_api import CDPSession, Page

from tracecase.streaming.models import ScreencastFrame

logger = logging.getLogger("tracecase.streaming.screencast")

FrameCallback = Callable[[ScreencastFrame], Coroutine[Any, Any, None]]


class CDPScreencastManager:
    """
    Manages Chrome DevTools Protocol screencast for a Playwright Page.
    
    Streams JPEG or PNG frames at native display refresh rates,
    handles frame acknowledgments to maintain steady frame delivery,
    and dispatches frames asynchronously to registered listeners.
    """

    def __init__(
        self,
        page: Page,
        format: str = "jpeg",
        quality: int = 75,
        max_width: int = 1280,
        max_height: int = 720,
        every_nth_frame: int = 1,
    ) -> None:
        self.page = page
        self.format = format
        self.quality = quality
        self.max_width = max_width
        self.max_height = max_height
        self.every_nth_frame = every_nth_frame

        self._cdp: CDPSession | None = None
        self._is_active = False
        self._frame_index = 0
        self._total_bytes = 0
        self._last_frame_at: datetime | None = None
        self._latest_frame: ScreencastFrame | None = None
        self._listeners: list[FrameCallback] = []
        self._lock = asyncio.Lock()

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def frames_captured(self) -> int:
        return self._frame_index

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    @property
    def last_frame_at(self) -> datetime | None:
        return self._last_frame_at

    @property
    def latest_frame(self) -> ScreencastFrame | None:
        return self._latest_frame

    def add_listener(self, callback: FrameCallback) -> None:
        """Register an async callback to receive new screencast frames."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: FrameCallback) -> None:
        """Remove a previously registered frame callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    async def start(self) -> None:
        """Attach CDP session and begin screencast stream."""
        async with self._lock:
            if self._is_active:
                return

            try:
                self._cdp = await self.page.context.new_cdp_session(self.page)
                self._cdp.on(
                    "Page.screencastFrame",
                    lambda event: asyncio.create_task(self._handle_frame(event)),
                )

                await self._cdp.send(
                    "Page.startScreencast",
                    {
                        "format": self.format,
                        "quality": self.quality,
                        "maxWidth": self.max_width,
                        "maxHeight": self.max_height,
                        "everyNthFrame": self.every_nth_frame,
                    },
                )
                self._is_active = True

                # Wait briefly for Chromium to deliver the initial viewport frame
                for _ in range(15):
                    if self._latest_frame is not None:
                        break
                    await asyncio.sleep(0.04)

                logger.info(
                    "CDP Screencast started for page (format=%s, quality=%d, size=%dx%d, initial_frame=%s)",
                    self.format,
                    self.quality,
                    self.max_width,
                    self.max_height,
                    self._latest_frame is not None,
                )
            except Exception as exc:
                logger.exception("Failed to start CDP screencast: %s", exc)
                self._is_active = False
                raise

    async def _handle_frame(self, event: dict[str, Any]) -> None:
        """Process incoming CDP frame, dispatch to listeners, and send acknowledgment."""
        session_id = event.get("sessionId")
        data_base64 = event.get("data", "")
        metadata = event.get("metadata", {})

        # Acknowledge immediately so Chromium produces subsequent frames without lag
        if self._cdp and session_id is not None:
            try:
                await self._cdp.send("Page.screencastFrameAck", {"sessionId": session_id})
            except Exception as ack_err:
                logger.debug("Failed to ack screencast frame: %s", ack_err)

        if not self._is_active:
            return

        self._frame_index += 1
        now = datetime.now()
        self._last_frame_at = now
        byte_size = len(data_base64)
        self._total_bytes += byte_size

        frame = ScreencastFrame(
            frame_index=self._frame_index,
            data_base64=data_base64,
            metadata=metadata,
            timestamp=now,
            byte_size=byte_size,
        )
        self._latest_frame = frame

        # Broadcast to listeners safely
        for listener in list(self._listeners):
            try:
                await listener(frame)
            except Exception as listener_exc:
                logger.warning("Error in screencast frame listener: %s", listener_exc)

    async def stop(self) -> None:
        """Stop screencast and detach CDP session."""
        async with self._lock:
            if not self._is_active:
                return

            self._is_active = False
            if self._cdp:
                try:
                    await self._cdp.send("Page.stopScreencast")
                except Exception as exc:
                    logger.debug("Error stopping screencast: %s", exc)

                try:
                    await self._cdp.detach()
                except Exception as exc:
                    logger.debug("Error detaching CDP session: %s", exc)

                self._cdp = None

            logger.info("CDP Screencast stopped cleanly. Total frames: %d", self._frame_index)
