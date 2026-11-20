"""Base contracts and abstract interfaces for Tracecase automation engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from tracecase.engines.capabilities import EngineCapabilityProfile
from tracecase.models import TestCase


class SessionRequest(BaseModel):
    """Specification for initiating an automation session."""

    url: str
    browser: str = "chromium"
    headless: bool = True
    viewport: tuple[int, int] = (1280, 720)
    timeout_ms: int = 30000
    options: dict[str, Any] = Field(default_factory=dict)


class BaseSession(ABC):
    """Abstract active automation session (page, browser context, or device)."""

    def __init__(self, session_id: str, engine_id: str) -> None:
        self.session_id = session_id
        self.engine_id = engine_id

    @abstractmethod
    async def navigate(self, url: str) -> None:
        """Navigate active context to URL."""
        ...

    @abstractmethod
    async def take_screenshot(self, path: Path | str | None = None) -> bytes:
        """Capture screenshot of the active viewport or device."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close active session and release underlying resources."""
        ...


class BaseRecorder(ABC):
    """Abstract recorder interface for user action capture."""

    @abstractmethod
    async def start(self) -> None:
        """Begin recording user interactions."""
        ...

    @abstractmethod
    async def pause(self) -> None:
        """Pause interaction capture without terminating the session."""
        ...

    @abstractmethod
    async def resume(self) -> None:
        """Resume interaction capture."""
        ...

    @abstractmethod
    async def stop(self) -> TestCase:
        """Stop recording and finalize the generated TestCase."""
        ...


class BaseExecutor(ABC):
    """Abstract execution adapter for running tests against an engine."""

    @abstractmethod
    async def execute_testcase(
        self,
        testcase: TestCase,
        browser: str = "chromium",
        headless: bool = True,
        **kwargs: Any,
    ) -> Any:
        """Execute a TestCase definition against the engine."""
        ...


class BaseAutomationEngine(ABC):
    """
    Contract for pluggable automation engines in Tracecase.
    
    Unifies Playwright, Selenium WebDriver, and Appium under a single
    lifecycle and capability interface while keeping engine-specific
    driver operations isolated inside dedicated adapters.
    """

    @property
    @abstractmethod
    def engine_id(self) -> str:
        """Unique engine identifier: 'playwright', 'selenium', 'appium'."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name."""
        ...

    @property
    def is_operational(self) -> bool:
        """Whether this engine is fully operational on this host."""
        return False

    @abstractmethod
    async def get_capabilities(self) -> EngineCapabilityProfile:
        """Return the verified capabilities of this engine for the host environment."""
        ...

    @abstractmethod
    async def create_session(self, request: SessionRequest) -> BaseSession:
        """Create and initialize a new automation session."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up all pools, processes, and background servers."""
        ...
