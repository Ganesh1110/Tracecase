"""Tracecase Multi-Engine Automation Architecture Package (Phase 9.1.4)."""

from tracecase.engines.base import (
    BaseAutomationEngine,
    BaseExecutor,
    BaseRecorder,
    BaseSession,
    SessionRequest,
)
from tracecase.engines.capabilities import (
    BrowserChannel,
    CapabilityStatus,
    EngineCapabilityProfile,
    FeatureCapability,
    HostEnvironmentCapabilities,
    PlatformType,
    inspect_host_environment,
)
from tracecase.engines.locator import (
    EngineAction,
    EngineActionType,
    LocatorSpec,
    LocatorStrategy,
    UnsupportedActionError,
    UnsupportedLocatorError,
    translate_locator,
)
from tracecase.engines.registry import (
    EngineRegistry,
    engine_registry,
    get_engine_registry,
)

__all__ = [
    "BaseAutomationEngine",
    "BaseExecutor",
    "BaseRecorder",
    "BaseSession",
    "SessionRequest",
    "CapabilityStatus",
    "PlatformType",
    "BrowserChannel",
    "FeatureCapability",
    "EngineCapabilityProfile",
    "HostEnvironmentCapabilities",
    "inspect_host_environment",
    "LocatorStrategy",
    "LocatorSpec",
    "EngineAction",
    "EngineActionType",
    "translate_locator",
    "UnsupportedLocatorError",
    "UnsupportedActionError",
    "EngineRegistry",
    "engine_registry",
    "get_engine_registry",
]
