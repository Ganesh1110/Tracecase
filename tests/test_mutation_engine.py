"""Tests for the MutationEngine orchestrator."""

import json
from datetime import datetime
from pathlib import Path

from tracecase.models import ElementInfo, NetworkRequest, Step, TestCase
from tracecase.mutation.engine import MutationEngine


def _element(selector: str, tag: str = "button", text: str = "Submit") -> ElementInfo:
    return ElementInfo(
        selector=selector,
        xpath=f"//*[@id='{selector.lstrip('#')}']",
        tag_name=tag,
        text=text,
        attributes={"id": selector.lstrip("#")},
        bounding_box={"x": 10, "y": 10, "width": 80, "height": 30},
    )


def _sample_testcase() -> TestCase:
    req = NetworkRequest(
        method="POST",
        url="https://api.example.com/login",
        status=200,
        resource_type="xhr",
        timing=50.0,
        request_headers={"Content-Type": "application/json"},
        response_headers={"Content-Type": "application/json"},
        request_body='{"email": "test@test.com"}',
        response_body='{"token": "xyz"}',
    )
    return TestCase(
        id="tc_engine",
        name="Engine Test Flow",
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
                element=_element("#email", tag="input"),
                input_value="test@test.com",
                description_short="Type email",
                description_detailed="Type email into input",
                console_logs=[],
                network_requests=[],
                page_errors=[],
            ),
            Step(
                number=2,
                timestamp=datetime(2025, 1, 1, 12, 0, 2),
                action_type="click",
                element=_element("#submit-btn"),
                description_short="Click submit",
                description_detailed="Click submit button",
                console_logs=[],
                network_requests=[req],
                page_errors=[],
            ),
        ],
        console_logs=[],
        network_requests=[req],
        total_duration=2.0,
        total_steps=2,
    )


def test_mutation_engine_generate_all() -> None:
    tc = _sample_testcase()
    engine = MutationEngine()
    mutations = engine.generate(tc, strategies=["inputs", "actions", "network"])

    assert len(mutations) >= 7  # 5 inputs + 1 action + 1 network fault
    strategies = {m.metadata.strategy for m in mutations}
    assert strategies == {"inputs", "actions", "network"}


def test_mutation_engine_limit() -> None:
    tc = _sample_testcase()
    engine = MutationEngine()
    mutations = engine.generate(tc, limit=3)
    assert len(mutations) == 3


def test_mutation_engine_export(temp_dir: Path) -> None:
    tc = _sample_testcase()
    engine = MutationEngine()
    mutations = engine.generate(tc, limit=2)

    exported_paths = engine.export_mutations(mutations, temp_dir / "mutations_out")
    assert len(exported_paths) == 2
    for path in exported_paths:
        assert path.exists()
        assert path.name == "testcase.json"
        # Validate that written file is valid TestCase JSON
        loaded = TestCase.model_validate_json(path.read_text(encoding="utf-8"))
        assert loaded.id.startswith("tc_engine_mut_")

        # Validate that metadata is written alongside
        meta_path = path.parent / "mutation_meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert "mutation_type" in meta
        assert "strategy" in meta
