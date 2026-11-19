"""Tests for testcase analysis (heuristics and AI enrichment)."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from tracecase.ai.analyst import analyze_testcase, write_analysis_result
from tracecase.ai.models import Message
from tracecase.ai.provider import NullProvider
from tracecase.models import ElementInfo, PageError, Step, TestCase


def _step(number: int, action: str = "click", value: str | None = None) -> Step:
    return Step(
        number=number,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type=action,
        element=ElementInfo(
            selector="#btn",
            xpath="//*[@id='btn']",
            tag_name="button",
            text="Save",
            attributes={},
            bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
        ),
        input_value=value,
        description_short=f"Step {number}",
        description_detailed=f"Step {number}",
    )


def _testcase(steps: list[Step], errors: list[PageError] | None = None) -> TestCase:
    return TestCase(
        id="tc_analyst",
        name="Profile Update",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url="https://example.com/profile",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=steps,
        console_logs=[],
        network_requests=[],
        page_errors=errors or [],
        total_duration=1.0,
        total_steps=len(steps),
    )


@pytest.mark.asyncio
async def test_heuristic_detects_empty_inputs_and_errors() -> None:
    steps = [
        _step(1, action="input", value=""),
        _step(2, action="click"),
    ]
    err = PageError(
        message="TypeError: cannot read property", timestamp=datetime(2025, 1, 1, 12, 0, 0)
    )
    tc = _testcase(steps, errors=[err])

    result = await analyze_testcase(tc, provider=NullProvider())

    assert result.testcase_id == "tc_analyst"
    assert "Profile Update" in result.summary
    assert any("empty input" in a.message.lower() for a in result.annotations)
    assert any("TypeError" in r for r in result.risks)


@pytest.mark.asyncio
async def test_ai_enrichment_integrates_suggestions() -> None:
    class FakeAIProvider:
        name: str = "mock_ai"
        model: str | None = "test-model"

        async def chat(
            self, messages: list[Message], schema: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            return {
                "summary": "Enriched test summary",
                "risks": ["Potential SQL injection"],
                "negative_scenarios": ["Submit without authentication token"],
                "suggested_assertions": [
                    {
                        "kind": "visible",
                        "target": ".alert-success",
                        "expected": True,
                        "step_number": 1,
                        "confidence": 0.9,
                    }
                ],
            }

    tc = _testcase([_step(1)])
    result = await analyze_testcase(tc, provider=FakeAIProvider())

    assert result.summary == "Enriched test summary"
    assert "Potential SQL injection" in result.risks
    assert len(result.suggested_assertions) == 1
    assert result.suggested_assertions[0].source == "ai"
    assert result.suggested_assertions[0].enforced is False


def test_write_analysis_result(temp_dir: Path) -> None:
    tc = _testcase([_step(1)])
    result = asyncio.run(analyze_testcase(tc, provider=NullProvider()))
    path = write_analysis_result(result, temp_dir)

    assert path.exists()
    assert path.name == "analysis.json"
    assert "tc_analyst" in path.read_text(encoding="utf-8")
