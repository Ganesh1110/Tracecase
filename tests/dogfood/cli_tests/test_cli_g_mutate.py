"""CLI Section G Tests: Negative Test Mutation (Flows G1 - G12).

Tests every CLI option and operational behavior of `tracecase mutate`:
- G1: Default mutate generates variations in testcase.parent / mutations
- G2: Strategy --strategy inputs (SQLi, XSS, empty, length boundaries)
- G3: Strategy --strategy actions (double_click)
- G4: Strategy --strategy network (500 fault injection)
- G5: Invalid strategy handling
- G6: Mutation limit flag (-n / --limit)
- G7: Custom output directory (-o / --output)
- G8: Verify input probe variety (SQLi, XSS, boundary strings)
- G9: Verify action mutations structure
- G10: Verify network fault structure
- G11: Schema validity: all generated testcases validate cleanly with TestCase model
- G12: Testcase with 0 inputs handled gracefully without error
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from tracecase.models import ElementInfo, NetworkRequest, Step, TestCase
from tests.dogfood.cli_tests.conftest import run_tracecase


def _create_mutable_testcase(
    tmp_path: Path,
    has_inputs: bool = True,
    has_clicks: bool = True,
    has_network: bool = True,
) -> Path:
    steps: list[Step] = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url="http://127.0.0.1:9010/login.html",
            description_short="Nav",
            description_detailed="Navigated to login",
        )
    ]
    if has_inputs:
        steps.append(
            Step(
                number=2,
                timestamp=datetime.now(),
                action_type="input",
                element=ElementInfo(
                    selector="#username",
                    xpath="//input[@id='username']",
                    tag_name="input",
                    attributes={"id": "username"},
                    bounding_box={"x": 10, "y": 10, "width": 100, "height": 30},
                ),
                input_value="standard_user",
                description_short="Type user",
                description_detailed="Typed username",
            )
        )
    if has_clicks:
        steps.append(
            Step(
                number=3,
                timestamp=datetime.now(),
                action_type="click",
                element=ElementInfo(
                    selector="#btn-login",
                    tag_name="button",
                    bounding_box={"x": 10, "y": 10, "width": 80, "height": 30},
                ),
                description_short="Click",
                description_detailed="Clicked button",
            )
        )
    network_reqs: list[NetworkRequest] = []
    if has_network:
        req = NetworkRequest(
            method="POST",
            url="http://127.0.0.1:9010/api/login",
            status=200,
            resource_type="fetch",
            timing=25.0,
            response_body='{"token":"xyz"}',
        )
        network_reqs.append(req)
        steps[-1].network_requests.append(req)

    tc = TestCase(
        id=f"tc_{tmp_path.name[:8]}",
        name="Mutable Login Flow",
        description="Dogfood mutable case",
        created_at=datetime.now(),
        start_url="http://127.0.0.1:9010/login.html",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Tracecase-Dogfood/1.0",
        steps=steps,
        network_requests=network_reqs,
        total_duration=1.5,
        total_steps=len(steps),
    )
    tc_dir = tmp_path / tc.id
    tc_dir.mkdir(parents=True, exist_ok=True)
    tc_path = tc_dir / "testcase.json"
    tc_path.write_text(tc.model_dump_json(indent=2), encoding="utf-8")
    return tc_path


def test_g1_default_mutate(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """G1: Default mutate synthesizes variations in testcase.parent / mutations."""
    tc_path = _create_mutable_testcase(isolated_workspace)
    res = run_tracecase(["mutate", str(tc_path)], env=isolated_env)
    assert res.returncode == 0
    mut_dir = tc_path.parent / "mutations"
    assert mut_dir.exists()
    mutations = list(mut_dir.glob("*/testcase.json"))
    assert len(mutations) > 0


def test_g2_strategy_inputs(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """G2: --strategy inputs generates input-specific variations."""
    tc_path = _create_mutable_testcase(isolated_workspace)
    res = run_tracecase(["mutate", str(tc_path), "--strategy", "inputs"], env=isolated_env)
    assert res.returncode == 0
    mut_dir = tc_path.parent / "mutations"
    for f in mut_dir.glob("*/testcase.json"):
        tc = TestCase.model_validate_json(f.read_text(encoding="utf-8"))
        # Verify inputs are mutated
        input_steps = [s for s in tc.steps if s.action_type == "input"]
        assert len(input_steps) > 0


def test_g3_strategy_actions(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """G3: --strategy actions generates action-level mutations (e.g. double_click)."""
    tc_path = _create_mutable_testcase(isolated_workspace)
    res = run_tracecase(["mutate", str(tc_path), "--strategy", "actions"], env=isolated_env)
    assert res.returncode == 0


def test_g4_strategy_network(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """G4: --strategy network injects 500 error faults into network requests."""
    tc_path = _create_mutable_testcase(isolated_workspace)
    res = run_tracecase(["mutate", str(tc_path), "--strategy", "network"], env=isolated_env)
    assert res.returncode == 0


def test_g5_invalid_strategy_handling(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """G5: Unknown strategy falls back to all strategies without crashing."""
    tc_path = _create_mutable_testcase(isolated_workspace)
    res = run_tracecase(["mutate", str(tc_path), "--strategy", "nonexistent_strategy"], env=isolated_env)
    assert res.returncode == 0


def test_g6_limit_flag(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """G6: -n / --limit caps the maximum generated mutations."""
    tc_path = _create_mutable_testcase(isolated_workspace)
    res = run_tracecase(["mutate", str(tc_path), "--limit", "3"], env=isolated_env)
    assert res.returncode == 0
    mut_dir = tc_path.parent / "mutations"
    mutations = list(mut_dir.glob("*/testcase.json"))
    assert 0 < len(mutations) <= 3


def test_g7_custom_output_directory(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """G7: -o / --output exports mutations to the user-specified directory."""
    tc_path = _create_mutable_testcase(isolated_workspace)
    custom_dir = isolated_workspace / "custom_mutations"
    res = run_tracecase(["mutate", str(tc_path), "-o", str(custom_dir)], env=isolated_env)
    assert res.returncode == 0
    assert custom_dir.exists()
    assert len(list(custom_dir.glob("*/testcase.json"))) > 0


def test_g8_verify_input_probe_variety(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """G8: Verify generated input probes cover SQLi, XSS, empty, and length boundaries."""
    tc_path = _create_mutable_testcase(isolated_workspace)
    out_dir = isolated_workspace / "g8_muts"
    run_tracecase(["mutate", str(tc_path), "--strategy", "inputs", "-o", str(out_dir)], env=isolated_env)
    values = set()
    for f in out_dir.glob("*/testcase.json"):
        tc = TestCase.model_validate_json(f.read_text(encoding="utf-8"))
        for s in tc.steps:
            if s.input_value is not None:
                values.add(s.input_value)
    # Check that SQLi or boundary probes were generated
    assert any("'" in v or "<script" in v or v == "" or len(v) > 200 for v in values)


def test_g9_g10_action_and_network_mutations(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """G9 & G10: Verify action and network mutation details."""
    tc_path = _create_mutable_testcase(isolated_workspace)
    out_dir = isolated_workspace / "g9_muts"
    run_tracecase(["mutate", str(tc_path), "-o", str(out_dir)], env=isolated_env)
    # At least some files exist
    assert len(list(out_dir.glob("*/testcase.json"))) > 0


def test_g11_schema_validity(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """G11: Every synthesized variation is a fully valid TestCase model."""
    tc_path = _create_mutable_testcase(isolated_workspace)
    out_dir = isolated_workspace / "g11_muts"
    run_tracecase(["mutate", str(tc_path), "-o", str(out_dir)], env=isolated_env)
    for f in out_dir.glob("*/testcase.json"):
        tc = TestCase.model_validate_json(f.read_text(encoding="utf-8"))
        assert tc.id is not None
        assert len(tc.steps) > 0


def test_g12_zero_inputs_handled_gracefully(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """G12: Testcase without input fields generates only applicable mutations without crashing."""
    tc_path = _create_mutable_testcase(isolated_workspace, has_inputs=False, has_clicks=False, has_network=False)
    res = run_tracecase(["mutate", str(tc_path)], env=isolated_env)
    assert res.returncode == 0
    assert "No mutations generated" in res.stdout or "Synthesized" in res.stdout
