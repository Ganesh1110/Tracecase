"""Input event dispatching and client-to-browser coordinate mapping for Playwright."""

from __future__ import annotations

import logging
from typing import Any

from playwright.async_api import Page

from tracecase.streaming.models import (
    ClientViewportDimensions,
    InputEvent,
    InputEventType,
)

logger = logging.getLogger("tracecase.streaming.input")


def map_client_coordinates(
    x: float | None,
    y: float | None,
    client_viewport: ClientViewportDimensions | None,
    browser_width: int,
    browser_height: int,
) -> tuple[float, float]:
    """
    Map client-side display coordinates to actual Chromium browser viewport coordinates.
    
    Handles:
    - Viewport scaling (e.g. 800x450 display of a 1280x720 browser).
    - Letterboxing / pillarboxing offsets (content_x, content_y).
    - Boundary clamping to prevent negative or out-of-bounds clicks.
    """
    if x is None or y is None:
        return 0.0, 0.0

    bw = float(browser_width)
    bh = float(browser_height)

    if client_viewport is not None:
        cw = client_viewport.content_width
        ch = client_viewport.content_height
        cx = client_viewport.content_x
        cy = client_viewport.content_y

        if cw <= 0 or ch <= 0:
            return 0.0, 0.0

        # Clamp client coordinates within rendered content box
        clamped_x = max(cx, min(x, cx + cw))
        clamped_y = max(cy, min(y, cy + ch))

        # Normalized ratio 0.0 - 1.0
        norm_x = (clamped_x - cx) / cw
        norm_y = (clamped_y - cy) / ch

        target_x = norm_x * bw
        target_y = norm_y * bh
        return round(target_x, 2), round(target_y, 2)

    # Fallback when no client viewport metadata is provided
    # If coordinates are already normalized (0.0 <= x <= 1.0)
    if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
        return round(x * bw, 2), round(y * bh, 2)

    # Direct raw coordinates clamped to browser viewport
    clamped_x = max(0.0, min(float(x), bw))
    clamped_y = max(0.0, min(float(y), bh))
    return round(clamped_x, 2), round(clamped_y, 2)


async def dispatch_input_event(
    page: Page,
    event: InputEvent,
    browser_viewport: tuple[int, int],
) -> None:
    """
    Deliver validated input event to Playwright page using native page.mouse and page.keyboard.
    
    Guarantees:
    - Never uses synthetic DOM injection.
    - Dispatches native OS-level events via Playwright.
    - Triggers active recorder event listeners naturally.
    """
    bw, bh = browser_viewport
    event_type = event.event_type

    if event_type in (
        InputEventType.MOUSE_MOVE,
        InputEventType.MOUSE_DOWN,
        InputEventType.MOUSE_UP,
        InputEventType.CLICK,
        InputEventType.DBLCLICK,
    ):
        mapped_x, mapped_y = map_client_coordinates(
            x=event.x,
            y=event.y,
            client_viewport=event.client_viewport,
            browser_width=bw,
            browser_height=bh,
        )

        if event_type == InputEventType.CLICK:
            await page.mouse.move(x=mapped_x, y=mapped_y)
            await page.mouse.click(
                x=mapped_x,
                y=mapped_y,
                button=event.button.value,
                click_count=event.click_count,
            )
        elif event_type == InputEventType.DBLCLICK:
            await page.mouse.move(x=mapped_x, y=mapped_y)
            await page.mouse.dblclick(
                x=mapped_x,
                y=mapped_y,
                button=event.button.value,
            )
        elif event_type == InputEventType.MOUSE_MOVE:
            await page.mouse.move(x=mapped_x, y=mapped_y)
        elif event_type == InputEventType.MOUSE_DOWN:
            await page.mouse.move(x=mapped_x, y=mapped_y)
            await page.mouse.down(button=event.button.value)
        elif event_type == InputEventType.MOUSE_UP:
            await page.mouse.move(x=mapped_x, y=mapped_y)
            await page.mouse.up(button=event.button.value)

    elif event_type == InputEventType.KEY_DOWN:
        if event.key:
            action_keys = (
                "Enter",
                "Backspace",
                "Tab",
                "Escape",
                "Delete",
                "ArrowLeft",
                "ArrowRight",
                "ArrowUp",
                "ArrowDown",
                "Space",
                "Home",
                "End",
                "PageUp",
                "PageDown",
            )
            if event.key in action_keys:
                await page.keyboard.press(event.key)
            else:
                await page.keyboard.down(event.key)

    elif event_type == InputEventType.KEY_UP:
        if event.key:
            await page.keyboard.up(event.key)

    elif event_type == InputEventType.TYPE:
        if event.text:
            # Native typing simulates key events
            await page.keyboard.type(event.text)

    elif event_type == InputEventType.PASTE:
        if event.text:
            # Use insert_text (CDP Input.insertText) for fast paste and IME input
            await page.keyboard.insert_text(event.text)

    elif event_type == InputEventType.WHEEL:
        if event.x is not None and event.y is not None:
            mapped_x, mapped_y = map_client_coordinates(
                x=event.x,
                y=event.y,
                client_viewport=event.client_viewport,
                browser_width=bw,
                browser_height=bh,
            )
            await page.mouse.move(x=mapped_x, y=mapped_y)

        await page.mouse.wheel(delta_x=event.delta_x, delta_y=event.delta_y)

    else:
        logger.warning("Unrecognized or unsupported input event type: %s", event_type)
