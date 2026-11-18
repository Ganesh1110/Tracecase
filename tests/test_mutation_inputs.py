"""Tests for input mutation strategies."""

from datetime import datetime

from qa_auto.models import ElementInfo, Step, TestCase
from qa_auto.mutation.inputs import mutate_inputs
from qa_auto.mutation.models import MutatedTestCase


def _element(selector: str, tag: str = "input", text: str = "") -> ElementInfo:
    return ElementInfo(
        selector=selector,
        xpath=f"//*[@id='{selector.lstrip('#')}']",
        tag_name=tag,
        text=text,
        attributes={"id": selector.lstrip("#")},
        bounding_box={"x": 10, "y": 10, "width": 80, "height": 30},
    )


def _testcase_with_input() -> TestCase:
    return TestCase(
        id="tc_login",
        name="User Login",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url="https://example.com/login",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=[
            Step(
                number=1,
                timestamp=datetime(2025, 1, 1, 12, 0, 1),
                action_type="input",
                element=_element("#email"),
                input_value="user@example.com",
                description_short="Type email",
                description_detailed="Type email into #email",
                console_logs=[],
                network_requests=[],
                page_errors=[],
            ),
            Step(
                number=2,
                timestamp=datetime(2025, 1, 1, 12, 0, 2),
                action_type="click",
                element=_element("#submit", tag="button", text="Submit"),
                description_short="Click submit",
                description_detailed="Click submit button",
                console_logs=[],
                network_requests=[],
                page_errors=[],
            ),
        ],
        console_logs=[],
        network_requests=[],
        page_errors=[],
        total_duration=2.0,
        total_steps=2,
    )


def test_mutate_inputs_generates_variations() -> None:
    tc = _testcase_with_input()
    mutations = mutate_inputs(tc)

    assert len(mutations) > 0
    assert all(isinstance(m, MutatedTestCase) for m in mutations)

    mutation_types = {m.metadata.mutation_type for m in mutations}
    assert "empty" in mutation_types
    assert "boundary_long" in mutation_types
    assert "special_chars" in mutation_types
    assert "unicode" in mutation_types
    assert "invalid_format" in mutation_types

    # Check the empty variation
    empty_mut = next(m for m in mutations if m.metadata.mutation_type == "empty")
    assert empty_mut.testcase.steps[0].input_value == ""
    assert empty_mut.metadata.target_step == 1
    assert "Negative: empty" in empty_mut.testcase.name


def test_mutate_inputs_no_input_steps() -> None:
    tc = _testcase_with_input()
    tc.steps[0].action_type = "click"
    tc.steps[0].input_value = None

    mutations = mutate_inputs(tc)
    assert len(mutations) == 0
