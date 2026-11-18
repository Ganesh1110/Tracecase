"""Tests for pytest Playwright code generator."""

from datetime import datetime
from pathlib import Path

from qa_auto.codegen.pytest_exporter import PytestExporter, generate_pytest_code
from qa_auto.models import ElementInfo, Step, TestCase


def _element(selector: str, tag: str = "button", text: str = "Submit") -> ElementInfo:
    return ElementInfo(
        selector=selector,
        xpath=f"//*[@id='{selector.lstrip('#')}']",
        tag_name=tag,
        text=text,
        attributes={"id": selector.lstrip("#")},
        bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
    )


def _testcase(steps: list[Step], name: str = "Sample Test") -> TestCase:
    return TestCase(
        id="tc_codegen",
        name=name,
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url="https://example.com/login",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=steps,
        console_logs=[],
        network_requests=[],
        page_errors=[],
        total_duration=1.0,
        total_steps=len(steps),
    )


def test_generate_code_has_imports_and_function() -> None:
    step = Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=_element("#btn"),
        description_short="Click button",
        description_detailed="Click button",
    )
    code = generate_pytest_code(_testcase([step], name="User Login Flow"))

    assert "import pytest" in code
    assert "from playwright.async_api import Page, expect" in code
    assert "async def test_user_login_flow(page: Page) -> None:" in code
    assert 'await page.goto("https://example.com/login")' in code
    assert 'await page.locator("#btn").click()' in code


def test_generate_code_all_action_types() -> None:
    steps = [
        Step(
            number=1,
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
            action_type="input",
            element=_element("#username", tag="input"),
            input_value="alice@example.com",
            description_short="Type username",
            description_detailed="Type username",
        ),
        Step(
            number=2,
            timestamp=datetime(2025, 1, 1, 12, 0, 1),
            action_type="select",
            element=_element("#role", tag="select"),
            input_value="admin",
            description_short="Select role",
            description_detailed="Select role",
        ),
        Step(
            number=3,
            timestamp=datetime(2025, 1, 1, 12, 0, 2),
            action_type="check",
            element=_element("#terms", tag="input"),
            description_short="Check terms",
            description_detailed="Check terms",
        ),
        Step(
            number=4,
            timestamp=datetime(2025, 1, 1, 12, 0, 3),
            action_type="uncheck",
            element=_element("#newsletter", tag="input"),
            description_short="Uncheck newsletter",
            description_detailed="Uncheck newsletter",
        ),
        Step(
            number=5,
            timestamp=datetime(2025, 1, 1, 12, 0, 4),
            action_type="hover",
            element=_element("#menu"),
            description_short="Hover menu",
            description_detailed="Hover menu",
        ),
        Step(
            number=6,
            timestamp=datetime(2025, 1, 1, 12, 0, 5),
            action_type="keypress",
            key="Enter",
            description_short="Press Enter",
            description_detailed="Press Enter",
        ),
        Step(
            number=7,
            timestamp=datetime(2025, 1, 1, 12, 0, 6),
            action_type="navigate",
            url="https://example.com/dashboard",
            description_short="Navigate dashboard",
            description_detailed="Navigate dashboard",
        ),
    ]

    code = generate_pytest_code(_testcase(steps))

    assert 'await page.locator("#username").fill("alice@example.com")' in code
    assert 'await page.locator("#role").select_option("admin")' in code
    assert 'await page.locator("#terms").check()' in code
    assert 'await page.locator("#newsletter").uncheck()' in code
    assert 'await page.locator("#menu").hover()' in code
    assert 'await page.keyboard.press("Enter")' in code
    assert 'await page.goto("https://example.com/dashboard")' in code


def test_generate_code_with_har_route() -> None:
    step = Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=_element("#load"),
        description_short="Click",
        description_detailed="Click",
    )
    code = generate_pytest_code(_testcase([step]), har_path="network.har")

    assert 'await page.route_from_har("network.har")' in code


def test_pytest_exporter_writes_file(temp_dir: Path) -> None:
    step = Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=_element("#btn"),
        description_short="Click",
        description_detailed="Click",
    )
    exporter = PytestExporter()
    out_file = exporter.export(_testcase([step], name="My Test"), temp_dir)

    assert out_file.exists()
    assert out_file.name == "test_my_test.py"
    assert "async def test_my_test(page: Page)" in out_file.read_text(encoding="utf-8")
