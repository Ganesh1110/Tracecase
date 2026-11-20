"""Tracecase Embedded Browser Streaming Package (Phase 9.1.4)."""

from tracecase.streaming.manager import (
    StreamingSessionManager,
    get_streaming_session_manager,
    streaming_session_manager,
)
from tracecase.streaming.models import (
    ScreencastFrame,
    ScreencastMetadata,
    StreamSessionConfig,
    StreamSessionInfo,
    StreamSessionState,
)
from tracecase.streaming.screencast import CDPScreencastManager, FrameCallback
from tracecase.streaming.session import ManagedChromiumSession

__all__ = [
    "StreamSessionConfig",
    "StreamSessionState",
    "ScreencastMetadata",
    "ScreencastFrame",
    "StreamSessionInfo",
    "CDPScreencastManager",
    "FrameCallback",
    "ManagedChromiumSession",
    "StreamingSessionManager",
    "streaming_session_manager",
    "get_streaming_session_manager",
]
