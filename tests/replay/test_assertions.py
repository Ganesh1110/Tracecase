"""Tests for assertion derivation."""

from datetime import datetime

from tracecase.models import ElementInfo, NetworkRequest, Step, TestCase
from tracecase.replay.assertions import derive_assertions, evaluate_assertions
from tracecase.replay.models import Assertion


def _element(selector: str = "#load", tag: str = "button") -> ElementInfo:
    return ElementInfo(
        selector=selector,
        xpath=f"//*[@id='{selector.lstrip('#')}']",
        tag_name=tag,
        text="Load",
        attributes={},
        bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
    )


def _step(number: int, requests: list[NetworkRequest], action: str = "click") -> Step:
    return Step(
        number=number,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type=action,
        element=_element(),
        network_requests=requests,
        description_short=f"Step {number}",
        description_detailed=f"Step {number}",
    )


def _testcase(steps: list[Step], start_url: str = "https://app.example.com/login") -> TestCase:
    return TestCase(
        id="tc_1",
        name="Login",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url=start_url,
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


def _request(
    url: str,
    status: int | None = 200,
    resource_type: str = "fetch",
    error: str | None = None,
) -> NetworkRequest:
    return NetworkRequest(
        method="GET",
        url=url,
        status=status,
        resource_type=resource_type,
        timing=10.0,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        error=error,
    )


def test_derives_2xx_assertion_for_same_origin_fetch() -> None:
    step = _step(1, [_request("https://app.example.com/api/me")])

    assertions = derive_assertions(_testcase([step]))

    status_assertions = [a for a in assertions if a.kind == "status"]
    assert len(status_assertions) == 1
    assert status_assertions[0].target == "https://app.example.com/api/me"
    assert status_assertions[0].expected == "2xx"
    assert status_assertions[0].step_number == 1


def test_ignores_cross_origin_and_failed_requests() -> None:
    step = _step(
        1,
        [
            _request("https://analytics.example.org/collect"),
            _request("https://app.example.com/api/broken", status=None, error="net::ERR_FAILED"),
        ],
    )

    assertions = derive_assertions(_testcase([step]))

    assert [a for a in assertions if a.kind == "status"] == []


def test_derives_no_page_error_for_every_step() -> None:
    steps = [_step(1, []), _step(2, [])]

    assertions = derive_assertions(_testcase(steps))

    no_error = [a for a in assertions if a.kind == "no_page_error"]
    assert [a.step_number for a in no_error] == [1, 2]


def test_derives_url_assertion_for_document_request_on_click() -> None:
    step = _step(
        1,
        [_request("https://app.example.com/dashboard?tab=1", resource_type="document")],
    )

    assertions = derive_assertions(_testcase([step]))

    url_assertions = [a for a in assertions if a.kind == "url"]
    assert len(url_assertions) == 1
    assert url_assertions[0].expected == "/dashboard"


def test_does_not_derive_url_assertion_for_non_click() -> None:
    step = _step(
        1,
        [_request("https://app.example.com/dashboard", resource_type="document")],
        action="input",
    )

    assertions = derive_assertions(_testcase([step]))

    assert [a for a in assertions if a.kind == "url"] == []


def test_does_not_derive_status_assertion_for_4xx_or_5xx() -> None:
    step = _step(
        1,
        [
            _request("https://app.example.com/api/missing", status=404),
            _request("https://app.example.com/api/broken", status=500),
        ],
    )

    assertions = derive_assertions(_testcase([step]))

    assert [a for a in assertions if a.kind == "status"] == []


def test_does_not_derive_status_assertion_for_3xx() -> None:
    step = _step(1, [_request("https://app.example.com/api/redirect", status=302)])

    assertions = derive_assertions(_testcase([step]))

    assert [a for a in assertions if a.kind == "status"] == []


def test_derives_single_url_assertion_for_final_document_request() -> None:
    step = _step(
        1,
        [
            _request("https://app.example.com/old", status=302, resource_type="document"),
            _request("https://app.example.com/dashboard", resource_type="document"),
        ],
    )

    assertions = derive_assertions(_testcase([step]))

    url_assertions = [a for a in assertions if a.kind == "url"]
    assert len(url_assertions) == 1
    assert url_assertions[0].target == "https://app.example.com/dashboard"
    assert url_assertions[0].expected == "/dashboard"


def _click_step() -> Step:
    return _step(1, [])


def test_status_2xx_passes_and_fails() -> None:
    step = _click_step()
    assertion = Assertion(kind="status", target="https://app/api", expected="2xx", step_number=1)

    passed = evaluate_assertions(
        step,
        [assertion],
        response_statuses={"https://app/api": [200]},
        final_url="https://app/",
        new_page_errors=[],
    )
    failed = evaluate_assertions(
        step,
        [assertion],
        response_statuses={"https://app/api": [500]},
        final_url="https://app/",
        new_page_errors=[],
    )

    assert passed[0].passed is True
    assert failed[0].passed is False
    assert "500" in failed[0].message


def test_status_assertion_fails_when_response_not_observed() -> None:
    step = _click_step()
    assertion = Assertion(kind="status", target="https://app/api", expected="2xx", step_number=1)

    results = evaluate_assertions(
        step,
        [assertion],
        response_statuses={},
        final_url="https://app/",
        new_page_errors=[],
    )

    assert results[0].passed is False
    assert results[0].actual == "not observed"


def test_exact_status_match_is_supported() -> None:
    step = _click_step()
    assertion = Assertion(kind="status", target="https://app/api", expected=201, step_number=1)

    results = evaluate_assertions(
        step,
        [assertion],
        response_statuses={"https://app/api": [201]},
        final_url="https://app/",
        new_page_errors=[],
    )

    assert results[0].passed is True


def test_no_page_error_assertion() -> None:
    step = _click_step()
    assertion = Assertion(kind="no_page_error", step_number=1)

    clean = evaluate_assertions(
        step,
        [assertion],
        response_statuses={},
        final_url="https://app/",
        new_page_errors=[],
    )
    dirty = evaluate_assertions(
        step,
        [assertion],
        response_statuses={},
        final_url="https://app/",
        new_page_errors=["TypeError: boom"],
    )

    assert clean[0].passed is True
    assert dirty[0].passed is False
    assert "TypeError: boom" in dirty[0].actual


def test_url_assertion_compares_paths() -> None:
    step = _click_step()
    assertion = Assertion(kind="url", expected="/dashboard", step_number=1)

    results = evaluate_assertions(
        step,
        [assertion],
        response_statuses={},
        final_url="https://app.example.com/dashboard?tab=1",
        new_page_errors=[],
    )

    assert results[0].passed is True


def test_assertions_for_other_steps_are_ignored() -> None:
    step = _click_step()
    assertion = Assertion(kind="no_page_error", step_number=2)

    results = evaluate_assertions(
        step,
        [assertion],
        response_statuses={},
        final_url="https://app/",
        new_page_errors=[],
    )

    assert results == []


def test_unsupported_assertion_kind_fails_with_message() -> None:
    step = _click_step()
    assertion = Assertion(kind="custom", step_number=1)

    results = evaluate_assertions(
        step,
        [assertion],
        response_statuses={},
        final_url="https://app/",
        new_page_errors=[],
    )

    assert results[0].passed is False
    assert "Unsupported assertion kind" in results[0].message
