"""Data models and schemas for embedded browser streaming sessions."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StreamSessionState(str, Enum):
    """Lifecycle states of an embedded streaming browser session."""

    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED = "paused"
    DISCONNECTED = "disconnected"
    STOPPED = "stopped"
    FAILED = "failed"


class StreamSessionConfig(BaseModel):
    """Configuration parameters for a managed streaming browser session."""

    session_id: str = Field(default_factory=lambda: f"stream_{uuid.uuid4().hex[:8]}")
    url: str = "about:blank"
    browser: str = "chromium"
    headless: bool = False
    viewport_width: int = 1280
    viewport_height: int = 720
    format: str = "jpeg"  # "jpeg" or "png"
    quality: int = 75     # 1-100
    every_nth_frame: int = 1
    timeout_ms: int = 30000
    owner_id: str = "default_user"
    project_id: str = "default_project"


class ScreencastMetadata(BaseModel):
    """CDP Screencast frame metadata."""

    offset_top: float = 0.0
    page_scale_factor: float = 1.0
    device_width: float = 1280.0
    device_height: float = 720.0
    scroll_offset_x: float = 0.0
    scroll_offset_y: float = 0.0
    timestamp: float | None = None


class ScreencastFrame(BaseModel):
    """Single captured screencast frame."""

    frame_index: int
    data_base64: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    byte_size: int = 0


class StreamSessionInfo(BaseModel):
    """Public status and telemetry for a streaming session."""

    session_id: str
    state: StreamSessionState
    url: str
    browser: str
    headless: bool
    viewport_width: int
    viewport_height: int
    started_at: datetime
    last_frame_at: datetime | None = None
    frames_sent: int = 0
    total_bytes_streamed: int = 0
    owner_id: str
    error: str | None = None
