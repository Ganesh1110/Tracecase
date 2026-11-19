"""Selector resolution with a heuristically ordered fallback chain."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page

    from tracecase.models import ElementInfo, Step

_IMPLICIT_ROLES = {
    "a": "link",
    "button": "button",
    "select": "combobox",
    "textarea": "textbox",
}


@dataclass
class HealResult:
    """Outcome of resolving an element for a step."""

    selector: str | None = None
    healed_from: str | None = None
    attempts: list[str] = field(default_factory=list)


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def candidate_selectors(element: ElementInfo) -> list[str]:
    """Return ordered selector candidates, most specific first."""
    candidates: list[str] = []
    if element.selector:
        candidates.append(element.selector)
    if element.xpath:
        candidates.append(f"xpath={element.xpath}")

    test_id = element.attributes.get("data-testid")
    if test_id:
        candidates.append(f"[data-testid={_quote(test_id)}]")

    elem_id = element.attributes.get("id")
    if elem_id:
        candidates.append(f"#{elem_id}")

    name = element.attributes.get("name")
    if name:
        if element.tag_name:
            candidates.append(f"{element.tag_name}[name={_quote(name)}]")
        candidates.append(f"[name={_quote(name)}]")

    if element.placeholder:
        candidates.append(f"[placeholder={_quote(element.placeholder)}]")

    aria_label = element.attributes.get("aria-label")
    if aria_label:
        candidates.append(f"[aria-label={_quote(aria_label)}]")

    if element.selector:
        clean = re.sub(r"\.(focus|active|hover|[\w-]+--focus|[\w-]+--active)", "", element.selector)
        if clean and clean != element.selector:
            candidates.append(clean)

    role = element.attributes.get("role") or _IMPLICIT_ROLES.get(element.tag_name)
    if role and element.text:
        candidates.append(f"role={role}[name={_quote(element.text)}]")

    if element.text:
        candidates.append(f"text={_quote(element.text)}")

    return list(dict.fromkeys(candidates))


async def _is_single_visible(locator: Locator, wait_ms: float = 0) -> bool:
    try:
        if wait_ms > 0:
            await locator.first.wait_for(state="visible", timeout=wait_ms)
        if await locator.count() != 1:
            return False
        return await locator.first.is_visible()
    except Exception:
        return False


async def resolve_element(
    page: Page,
    step: Step,
    *,
    heal: bool,
    timeout_ms: float = 5000,
) -> tuple[Locator | None, HealResult]:
    """Resolve a step target, optionally trying fallback selectors."""
    if step.element is None:
        return None, HealResult()

    candidates = candidate_selectors(step.element)
    if not heal:
        candidates = candidates[:1]

    result = HealResult(attempts=candidates)
    for index, selector in enumerate(candidates):
        locator = page.locator(selector)
        # Give candidate 0 time to mount (for SPAs), fallbacks check quickly
        wait_ms = timeout_ms if index == 0 else 500
        if await _is_single_visible(locator, wait_ms=wait_ms):
            result.selector = selector
            if index > 0:
                result.healed_from = step.element.selector
            return locator.first, result

    return None, result
