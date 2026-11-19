"""Integration tests for the replay engine."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from tracecase.models import ElementInfo, NetworkRequest, Step, TestCase
from tracecase.replay.engine import ReplayEngine, write_replay_result


def _element(selector: str, text: str = "Load") -> ElementInfo:
    return ElementInfo(
        selector=selector,
        xpath=f"//*[@id='{selector.lstrip('#')}']",
        tag_name="button",
        text=text,
        attributes={"id": selector.lstrip("#")},
        bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
    )


def _request(url: str, status: int = 200) -> NetworkRequest:
    return NetworkRequest(
        method="GET",
        url=url,
        status=status,
        resource_type="fetch",
        timing=5.0,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        response_headers={"content-type": "application/json"},
        response_body=json.dumps({"source": "recorded"}),
    )


def _testcase(base_url: str, step: Step) -> TestCase:
    return TestCase(
        id="tc_replay",
        name="Replay",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url=f"{base_url}/",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=[step],
        console_logs=[],
        network_requests=[],
        page_errors=[],
        total_duration=1.0,
        total_steps=1,
    )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_replay_passes_when_status_matches(html_server: str) -> None:
    step = Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=_element("#load"),
        network_requests=[_request(f"{html_server}/api/data")],
        description_short="Click Load",
        description_detailed="Click Load",
    )
    engine = ReplayEngine(_testcase(html_server, step), headless=True)

    result = await engine.run()

    assert result.exit_code == 0
    assert result.status == "passed"
    assert result.steps[0].status == "passed"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_replay_fails_when_status_differs(html_server: str) -> None:
    step = Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=_element("#fail", "Fail"),
        network_requests=[_request(f"{html_server}/api/fail", status=200)],
        description_short="Click Fail",
        description_detailed="Click Fail",
    )
    engine = ReplayEngine(_testcase(html_server, step), headless=True)

    result = await engine.run()

    assert result.exit_code == 1
    assert result.status == "failed"
    assert result.steps[0].status == "failed"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_replay_fails_on_new_page_error(html_server: str) -> None:
    step = Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=_element("#boom", "Boom"),
        network_requests=[],
        description_short="Click Boom",
        description_detailed="Click Boom",
    )
    engine = ReplayEngine(_testcase(html_server, step), headless=True)

    result = await engine.run()

    assert result.exit_code == 1
    assert result.steps[0].status == "failed"
    assert "boom" in result.steps[0].assertions[0].actual


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_replay_heals_missing_selector(html_server: str) -> None:
    element = ElementInfo(
        selector="#missing",
        xpath="//*[@id='missing']",
        tag_name="button",
        text="Submit",
        attributes={"data-testid": "submit-btn"},
        bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
    )
    step = Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=element,
        description_short="Click Submit",
        description_detailed="Click Submit",
    )
    engine = ReplayEngine(_testcase(html_server, step), headless=True, heal=True)

    result = await engine.run()

    assert result.exit_code == 0
    assert result.steps[0].status == "healed"
    assert result.steps[0].healed_from == "#missing"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_replay_errors_when_element_missing_without_healing(html_server: str) -> None:
    element = ElementInfo(
        selector="#missing",
        xpath="//*[@id='missing']",
        tag_name="button",
        text="Submit",
        attributes={"data-testid": "submit-btn"},
        bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
    )
    step = Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=element,
        description_short="Click Submit",
        description_detailed="Click Submit",
    )
    engine = ReplayEngine(_testcase(html_server, step), headless=True, heal=False)

    result = await engine.run()

    assert result.exit_code == 2
    assert result.steps[0].status == "error"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_replay_uses_har_and_writes_report(html_server: str, temp_dir: Path) -> None:
    har = {
        "log": {
            "version": "1.2",
            "entries": [
                {
                    "request": {"method": "GET", "url": f"{html_server}/api/data"},
                    "response": {
                        "status": 200,
                        "headers": [{"name": "content-type", "value": "application/json"}],
                        "content": {"text": '{"source": "recorded"}'},
                    },
                }
            ],
        }
    }
    step = Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=_element("#load"),
        description_short="Click Load",
        description_detailed="Click Load",
    )
    engine = ReplayEngine(
        _testcase(html_server, step),
        headless=True,
        har=har,
        output_dir=temp_dir,
    )

    result = await engine.run()
    report = write_replay_result(result, temp_dir)

    assert result.exit_code == 0
    assert (temp_dir / "replay" / "001.png").exists()
    assert report.exists()
    assert '"exit_code": 0' in report.read_text(encoding="utf-8")
