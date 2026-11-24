"""Session manager and ownership coordinator for active streaming sessions."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from tracecase.streaming.models import (
    StreamSessionConfig,
    StreamSessionInfo,
    StreamSessionState,
)
from tracecase.streaming.session import ManagedChromiumSession

logger = logging.getLogger("tracecase.streaming.manager")


class StreamingSessionManager:
    """
    Coordinates active streaming browser sessions.
    
    Guarantees:
    - Thread-safe / coroutine-safe lifecycle management.
    - Session isolation and owner validation.
    - Reliable process cleanup on application shutdown or cancellation.
    """

    def __init__(self, max_concurrent_sessions: int = 4) -> None:
        self.max_concurrent_sessions = max_concurrent_sessions
        self._sessions: dict[str, ManagedChromiumSession] = {}
        self._lock = asyncio.Lock()

    def get_session(
        self,
        session_id: str,
        owner_id: str | None = None,
        token: str | None = None,
    ) -> Any | None:
        """
        Retrieve an active session with optional ownership and per-session token validation.
        
        Raises PermissionError if token or owner_id does not match the session.
        """
        session = self._sessions.get(session_id)
        if not session:
            return None

        # Verify secret session token if session was created with one
        session_token = getattr(session, "stream_token", None)
        if session_token is not None:
            if not token or token != session_token:
                raise PermissionError(
                    f"Unauthorized access: invalid or missing security token for session '{session_id}'."
                )

        # Verify owner_id if session has a restricted owner
        if hasattr(session, "config"):
            session_owner = getattr(session.config, "owner_id", None)
            if session_owner and session_owner != "default_user":
                if token != session_owner and owner_id != session_owner:
                    raise PermissionError(
                        f"Unauthorized access: session '{session_id}' belongs to a different user."
                    )

        return session

    def register_session(self, session: Any) -> None:
        """Register an externally created streaming session (such as unified Recorder)."""
        sid = getattr(session, "session_id", None)
        if sid:
            self._sessions[sid] = session

    def unregister_session(self, session_id: str) -> None:
        """Unregister a streaming session."""
        self._sessions.pop(session_id, None)

    def list_sessions(self) -> list[ManagedChromiumSession]:
        """List all active streaming sessions."""
        return list(self._sessions.values())

    async def create_session(
        self, config: StreamSessionConfig
    ) -> ManagedChromiumSession:
        """Create and launch a new managed streaming session."""
        async with self._lock:
            # Clean up terminated sessions
            self._prune_inactive_sessions()

            if len(self._sessions) >= self.max_concurrent_sessions:
                raise RuntimeError(
                    f"Maximum concurrent streaming sessions limit ({self.max_concurrent_sessions}) reached."
                )

            session = ManagedChromiumSession(config=config)
            await session.launch()
            self._sessions[config.session_id] = session
            return session

    async def close_session(self, session_id: str) -> bool:
        """Terminate and unregister a streaming session."""
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if not session:
                return False

            await session.close()
            return True

    def _prune_inactive_sessions(self) -> None:
        """Remove stopped or failed sessions from memory."""
        inactive_ids = [
            sid
            for sid, s in self._sessions.items()
            if s.state in (StreamSessionState.STOPPED, StreamSessionState.FAILED)
        ]
        for sid in inactive_ids:
            self._sessions.pop(sid, None)

    async def shutdown(self) -> None:
        """Terminate all active sessions and release all browser processes."""
        async with self._lock:
            logger.info("Shutting down all streaming sessions (%d active)", len(self._sessions))
            for sid, session in list(self._sessions.items()):
                try:
                    await session.close()
                except Exception as exc:
                    logger.debug("Error closing streaming session %s on shutdown: %s", sid, exc)
            self._sessions.clear()


# Global singleton streaming manager instance
streaming_session_manager = StreamingSessionManager()


def get_streaming_session_manager() -> StreamingSessionManager:
    """Access the global streaming session manager."""
    return streaming_session_manager
