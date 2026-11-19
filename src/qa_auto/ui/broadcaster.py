"""Real-time event broadcasting via WebSockets and SSE for QA Auto Studio."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("qa_auto.ui.broadcaster")


class ConnectionManager:
    """Manages active WebSocket connections and channel subscriptions."""

    def __init__(self) -> None:
        # Active connections grouped by channel
        self.active_connections: set[WebSocket] = set()
        self.channel_subscriptions: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, channel: str = "general") -> None:
        """Accept WebSocket connection and subscribe to channel."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
            if channel not in self.channel_subscriptions:
                self.channel_subscriptions[channel] = set()
            self.channel_subscriptions[channel].add(websocket)
        logger.debug("WebSocket client connected to channel: %s", channel)

    async def disconnect(self, websocket: WebSocket, channel: str = "general") -> None:
        """Remove WebSocket connection."""
        async with self._lock:
            self.active_connections.discard(websocket)
            if channel in self.channel_subscriptions:
                self.channel_subscriptions[channel].discard(websocket)
        logger.debug("WebSocket client disconnected from channel: %s", channel)

    async def broadcast(self, message: dict[str, Any], channel: str | None = None) -> None:
        """Broadcast JSON message to all subscribers or channel-specific subscribers."""
        payload = json.dumps(message)
        async with self._lock:
            if channel and channel in self.channel_subscriptions:
                targets = list(self.channel_subscriptions[channel])
            else:
                targets = list(self.active_connections)

        dead_connections: list[WebSocket] = []
        for connection in targets:
            try:
                await connection.send_text(payload)
            except Exception:
                dead_connections.append(connection)

        if dead_connections:
            async with self._lock:
                for dead in dead_connections:
                    self.active_connections.discard(dead)
                    if channel and channel in self.channel_subscriptions:
                        self.channel_subscriptions[channel].discard(dead)


# Global broadcast manager instance
manager = ConnectionManager()


async def broadcast_execution_event(
    execution_id: str,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Convenience helper to broadcast execution-specific event."""
    msg = {
        "channel": f"execution:{execution_id}",
        "type": event_type,
        "execution_id": execution_id,
        "data": data,
    }
    # Broadcast to both the specific execution channel and the general stream
    await manager.broadcast(msg, channel=f"execution:{execution_id}")
    await manager.broadcast(msg, channel="executions")


async def broadcast_recording_event(
    session_id: str,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Convenience helper to broadcast recorder-specific event."""
    msg = {
        "channel": f"recording:{session_id}",
        "type": event_type,
        "session_id": session_id,
        "data": data,
    }
    await manager.broadcast(msg, channel=f"recording:{session_id}")
    await manager.broadcast(msg, channel="recorder")


async def broadcast_exploration_event(
    exploration_id: str,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Convenience helper to broadcast autonomous exploration events."""
    msg = {
        "channel": f"exploration:{exploration_id}",
        "type": event_type,
        "exploration_id": exploration_id,
        "data": data,
    }
    await manager.broadcast(msg, channel=f"exploration:{exploration_id}")
    await manager.broadcast(msg, channel="explorations")
