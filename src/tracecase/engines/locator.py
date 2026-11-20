"""Engine-neutral action and locator definitions with explicit translation boundaries."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class UnsupportedLocatorError(ValueError):
    """Raised when a locator strategy cannot be safely translated to a target engine."""

    pass


class UnsupportedActionError(ValueError):
    """Raised when an action is unsupported by a target engine or platform."""

    pass


class LocatorStrategy(str, Enum):
    """Locator identification strategies across web and mobile platforms."""

    CSS = "css"
    XPATH = "xpath"
    TEXT = "text"
    ROLE = "role"
    ID = "id"
    ACCESSIBILITY_ID = "accessibility_id"
    ANDROID_UIAUTOMATOR = "android_uiautomator"
    IOS_PREDICATE = "ios_predicate"
    COORDINATES = "coordinates"


class LocatorSpec(BaseModel):
    """Structured, engine-neutral element locator definition."""

    strategy: LocatorStrategy = LocatorStrategy.CSS
    value: str
    role: str | None = None
    name: str | None = None
    exact: bool = False
    platform_context: str = "web"  # "web", "android_native", "ios_native"


class EngineActionType(str, Enum):
    """Standardized action verbs across test engines."""

    NAVIGATE = "navigate"
    CLICK = "click"
    DBLCLICK = "dblclick"
    FILL = "fill"
    SELECT = "select"
    CHECK = "check"
    UNCHECK = "uncheck"
    HOVER = "hover"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    ASSERT = "assert"
    TOUCH_TAP = "touch_tap"
    TOUCH_SWIPE = "touch_swipe"


class EngineAction(BaseModel):
    """Engine-neutral execution step representation."""

    action_type: EngineActionType
    locator: LocatorSpec | None = None
    input_value: str | None = None
    url: str | None = None
    timeout_ms: int = 10000
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


def translate_locator(spec: LocatorSpec, target_engine: str) -> str:
    """
    Translate an engine-neutral LocatorSpec into a target engine's native selector format.
    
    Guarantees:
    - Never silently alter locator semantics.
    - Explicitly fails with UnsupportedLocatorError if a strategy cannot be represented.
    """
    engine = target_engine.lower().strip()

    if engine == "playwright":
        if spec.strategy == LocatorStrategy.CSS:
            return spec.value
        elif spec.strategy == LocatorStrategy.XPATH:
            return f"xpath={spec.value}" if not spec.value.startswith("xpath=") else spec.value
        elif spec.strategy == LocatorStrategy.ID:
            clean_id = spec.value.lstrip("#")
            return f"#{clean_id}"
        elif spec.strategy == LocatorStrategy.TEXT:
            return f"text={spec.value}"
        elif spec.strategy == LocatorStrategy.ROLE:
            if spec.role:
                return f"role={spec.role}[name='{spec.value}']"
            return f"text={spec.value}"
        else:
            raise UnsupportedLocatorError(
                f"Playwright does not natively support mobile locator strategy '{spec.strategy.value}' for value '{spec.value}'."
            )

    elif engine == "selenium":
        if spec.strategy in (LocatorStrategy.CSS, LocatorStrategy.XPATH, LocatorStrategy.ID, LocatorStrategy.TEXT):
            if spec.strategy == LocatorStrategy.ID:
                return spec.value.lstrip("#")
            return spec.value
        else:
            raise UnsupportedLocatorError(
                f"Selenium WebDriver does not support locator strategy '{spec.strategy.value}' without custom extension."
            )

    elif engine == "appium":
        if spec.strategy in (
            LocatorStrategy.ACCESSIBILITY_ID,
            LocatorStrategy.ANDROID_UIAUTOMATOR,
            LocatorStrategy.IOS_PREDICATE,
            LocatorStrategy.ID,
            LocatorStrategy.XPATH,
        ):
            return spec.value
        elif spec.strategy == LocatorStrategy.CSS and spec.platform_context == "web":
            return spec.value
        else:
            raise UnsupportedLocatorError(
                f"Appium native context does not support web strategy '{spec.strategy.value}' for '{spec.value}'. Use accessibility_id or native locators."
            )

    else:
        raise ValueError(f"Unknown automation engine: '{target_engine}'")
