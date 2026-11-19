"""Pytest Playwright code generator for recorded test cases."""

from __future__ import annotations

import re
from pathlib import Path

from tracecase.exporters.base import BaseExporter
from tracecase.models import Step, TestCase
from tracecase.replay.assertions import derive_assertions


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text).strip().lower()
    slug = re.sub(r"[-\s]+", "_", cleaned)
    return slug or "test_case"


def _best_selector(step: Step) -> str:
    element = step.element
    if not element:
        return ""
    if element.attributes.get("id"):
        return f"#{element.attributes['id']}"
    if element.attributes.get("data-testid"):
        return f"[data-testid='{element.attributes['data-testid']}']"
    if element.attributes.get("name"):
        tag = element.tag_name or ""
        return f"{tag}[name='{element.attributes['name']}']"
    if element.selector:
        return re.sub(r"\.(focus|active|hover|[\w-]+--focus|[\w-]+--active)", "", element.selector)
    if element.xpath:
        return f"xpath={element.xpath}"
    return element.selector or ""


def _format_step(step: Step) -> list[str]:
    lines: list[str] = []
    action = step.action_type
    selector = _best_selector(step)

    if action == "navigate" and step.url:
        lines.append(f'await page.goto("{step.url}")')
    elif action == "click" and selector:
        lines.append(f'await page.locator("{selector}").click()')
    elif action == "dblclick" and selector:
        lines.append(f'await page.locator("{selector}").dblclick()')
    elif action == "input" and selector:
        val = (step.input_value or "").replace('"', '\\"')
        lines.append(f'await page.locator("{selector}").fill("{val}")')
    elif action == "select" and selector:
        val = (step.input_value or "").replace('"', '\\"')
        lines.append(f'await page.locator("{selector}").select_option("{val}")')
    elif action == "check" and selector:
        lines.append(f'await page.locator("{selector}").check()')
    elif action == "uncheck" and selector:
        lines.append(f'await page.locator("{selector}").uncheck()')
    elif action == "hover" and selector:
        lines.append(f'await page.locator("{selector}").hover()')
    elif action == "keypress":
        key = step.key or "Enter"
        lines.append(f'await page.keyboard.press("{key}")')
    elif action == "wait":
        ms = int(step.input_value or "1000")
        lines.append(f"await page.wait_for_timeout({ms})")

    return lines


def generate_pytest_code(testcase: TestCase, *, har_path: str | None = None) -> str:
    """Generate executable pytest + Playwright Python test source code."""
    fn_name = f"test_{_slugify(testcase.name)}"
    assertions = derive_assertions(testcase)
    assertions_by_step: dict[int, list[str]] = {}

    for assertion in assertions:
        if assertion.step_number is None:
            continue
        step_lines = assertions_by_step.setdefault(assertion.step_number, [])
        if assertion.kind == "url" and assertion.expected:
            exp_str = str(assertion.expected)
            step_lines.append(
                f'await expect(page).to_have_url(re.compile(r".*{re.escape(exp_str)}.*"), timeout=15000)'
            )

    body_lines: list[str] = []

    if har_path:
        body_lines.append(f'await page.route_from_har("{har_path}")')

    body_lines.append(f'await page.goto("{testcase.start_url}")')

    for step in testcase.steps:
        body_lines.append(f"# Step {step.number}: {step.description_short}")
        body_lines.extend(_format_step(step))
        for assertion_line in assertions_by_step.get(step.number, []):
            body_lines.append(assertion_line)

    indented_body = "\n    ".join(body_lines)

    code = f'''"""Generated Playwright test for {testcase.name}."""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from playwright.async_api import Page, async_playwright, expect


@pytest_asyncio.fixture
async def page() -> AsyncGenerator[Page]:
    """Launch headless browser and create a fresh page."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        pg = await context.new_page()
        try:
            yield pg
        finally:
            await context.close()
            await browser.close()


@pytest.mark.asyncio
async def {fn_name}(page: Page) -> None:
    """Recorded test flow: {testcase.name}."""
    {indented_body}
'''
    return code


class PytestExporter(BaseExporter):
    """Exports a recorded testcase to a pytest module."""

    def __init__(self, har_path: str | None = None) -> None:
        self.har_path = har_path

    def export(self, testcase: TestCase, output_dir: Path) -> Path:
        """Write the generated pytest code to output_dir."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"test_{_slugify(testcase.name)}.py"
        path = output_dir / filename
        content = generate_pytest_code(testcase, har_path=self.har_path)
        path.write_text(content, encoding="utf-8")
        return path
