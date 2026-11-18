"""Selector resolution with a heuristically ordered fallback chain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page

    from qa_auto.models import ElementInfo, Step

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

    aria_label = element.attributes.get("aria-label")
    if aria_label:
        candidates.append(f"[aria-label={_quote(aria_label)}]")

    role = element.attributes.get("role") or _IMPLICIT_ROLES.get(element.tag_name)
    if role and element.text:
        candidates.append(f"role={role}[name={_quote(element.text)}]")

    if element.text:
        candidates.append(f"text={_quote(element.text)}")

    return list(dict.fromkeys(candidates))


async def _is_single_visible(locator: Locator) -> bool:
    try:
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
        if await _is_single_visible(locator):
            result.selector = selector
            if index > 0:
                result.healed_from = step.element.selector
            return locator.first, result

    return None, result
