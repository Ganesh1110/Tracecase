"""Tests for action sequence and network fault mutation strategies."""

from datetime import datetime

from tracecase.models import ElementInfo, NetworkRequest, Step, TestCase
from tracecase.mutation.actions import mutate_actions
from tracecase.mutation.models import MutatedTestCase
from tracecase.mutation.network import mutate_network_faults


def _element(selector: str, tag: str = "button", text: str = "Submit") -> ElementInfo:
    return ElementInfo(
        selector=selector,
        xpath=f"//*[@id='{selector.lstrip('#')}']",
        tag_name=tag,
        text=text,
        attributes={"id": selector.lstrip("#")},
        bounding_box={"x": 10, "y": 10, "width": 80, "height": 30},
    )


def _testcase_with_actions_and_network() -> TestCase:
    req = NetworkRequest(
        method="POST",
        url="https://api.example.com/checkout",
        status=200,
        resource_type="xhr",
        timing=50.0,
        request_headers={"Content-Type": "application/json"},
        response_headers={"Content-Type": "application/json"},
        request_body='{"item": "book"}',
        response_body='{"order_id": "123"}',
    )

    return TestCase(
        id="tc_order",
        name="Place Order",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url="https://example.com/cart",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=[
            Step(
                number=1,
                timestamp=datetime(2025, 1, 1, 12, 0, 1),
                action_type="click",
                element=_element("#checkout-btn"),
                description_short="Click checkout",
                description_detailed="Click the checkout button",
                console_logs=[],
                network_requests=[req],
                page_errors=[],
            ),
            Step(
                number=2,
                timestamp=datetime(2025, 1, 1, 12, 0, 2),
                action_type="click",
                element=_element("#confirm-btn"),
                description_short="Click confirm",
                description_detailed="Click the confirm button",
                console_logs=[],
                network_requests=[],
                page_errors=[],
            ),
        ],
        console_logs=[],
        network_requests=[req],
        page_errors=[],
        total_duration=2.0,
        total_steps=2,
    )


def test_mutate_actions_duplicates_clicks() -> None:
    tc = _testcase_with_actions_and_network()
    mutations = mutate_actions(tc)

    assert len(mutations) == 2
    assert all(isinstance(m, MutatedTestCase) for m in mutations)

    # First mutation duplicates step 1
    mut1 = mutations[0]
    assert mut1.metadata.strategy == "actions"
    assert mut1.metadata.mutation_type == "double_click"
    assert mut1.metadata.target_step == 1
    # Mutated testcase now has 3 steps (1, duplicated 1, 2)
    assert len(mut1.testcase.steps) == 3
    assert mut1.testcase.steps[0].action_type == "click"
    assert mut1.testcase.steps[1].action_type == "click"
    assert mut1.testcase.steps[0].number == 1
    assert mut1.testcase.steps[1].number == 2
    assert mut1.testcase.steps[2].number == 3


def test_mutate_network_faults_injects_server_error() -> None:
    tc = _testcase_with_actions_and_network()
    mutations = mutate_network_faults(tc)

    assert len(mutations) > 0
    assert all(isinstance(m, MutatedTestCase) for m in mutations)

    fault = mutations[0]
    assert fault.metadata.strategy == "network"
    assert fault.metadata.mutation_type == "network_error"
    assert fault.metadata.target_step == 1

    # Check that injected network request has status 500
    step_req = fault.testcase.steps[0].network_requests[0]
    assert step_req.status == 500
