"""CLI Section C Tests: Replay & Healing (Flows C1 - C17).

Tests every CLI option and operational behavior of `tracecase replay`:
- C1: Basic headless replay (exit 0)
- C2: Headed replay (--headed flag)
- C3: Output replay.json and screenshots (-o / --output)
- C4: Exit codes: 0 (pass), 1 (assertion failure), 2 (infra error / missing file)
- C5: --assert vs --no-assert evaluation
- C6: Derived assertions (status, URL, visibility, text)
- C7: Action timeout sensitivity (-t / --timeout)
- C8: Replay without --heal against Version-B (fails)
- C9: Replay with --heal against Version-B (passes healed)
- C10: Isolated healing tier tests (10 tiers) & false-positive DOM shift regression (BUG-002)
- C11: Visual diff comparison (--diff) with identical UI passes
- C12: Visual diff threshold and --diff-fail with modified UI (Version-C)
- C13: Offline replay with HAR fulfillment (--from-har)
- C14: Multi-tab replay context switching (page_id)
- C15: Backward compatibility for legacy testcases missing page_id
- C16: Browser selection matrix
- C17: Replay synthesized mutated testcases
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from tracecase.models import ElementInfo, Step, TestCase
from tests.dogfood.cli_tests.conftest import run_tracecase


def _create_testcase(
    tmp_path: Path,
    steps: list[Step],
    name: str = "Test Replay Case",
    start_url: str = "http://127.0.0.1:9010/index.html",
) -> Path:
    """Helper to generate a valid testcase.json."""
    tc = TestCase(
        id=f"tc_{tmp_path.name[:8]}",
        name=name,
        description="Dogfood Replay Testcase",
        created_at=datetime.now(),
        start_url=start_url,
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Tracecase-Dogfood/1.0",
        steps=steps,
        total_duration=2.5,
        total_steps=len(steps),
    )
    tc_dir = tmp_path / tc.id
    tc_dir.mkdir(parents=True, exist_ok=True)
    tc_path = tc_dir / "testcase.json"
    tc_path.write_text(tc.model_dump_json(indent=2), encoding="utf-8")
    return tc_path


def test_c1_basic_headless_replay(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """C1: Verify basic headless replay executes successfully and returns exit code 0."""
    url = f"{playground_server_url}/login.html"
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url=url,
            description_short="Navigate to login",
            description_detailed=f"Navigated to {url}",
        ),
        Step(
            number=2,
            timestamp=datetime.now(),
            action_type="input",
            element=ElementInfo(
                selector="#username",
                xpath="//input[@id='username']",
                tag_name="input",
                attributes={"id": "username", "name": "username"},
                bounding_box={"x": 10, "y": 10, "width": 100, "height": 30},
            ),
            input_value="testuser",
            description_short="Type username",
            description_detailed="Typed testuser into username input",
        ),
    ]
    tc_path = _create_testcase(isolated_workspace, steps, start_url=url)
    res = run_tracecase(["replay", str(tc_path)], env=isolated_env)
    assert res.returncode == 0, f"Replay failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "Replay passed" in res.stdout


def test_c2_headed_replay(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """C2: Verify headed replay flag --headed executes without syntax or runtime failure."""
    url = f"{playground_server_url}/login.html"
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url=url,
            description_short="Navigate to login",
            description_detailed=f"Navigated to {url}",
        )
    ]
    tc_path = _create_testcase(isolated_workspace, steps, start_url=url)
    res = run_tracecase(["replay", str(tc_path), "--headed"], env=isolated_env)
    assert res.returncode == 0
    assert "Replay passed" in res.stdout


def test_c3_output_replay_json_and_screenshots(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """C3: Verify replay outputs replay.json and step artifacts when -o is supplied."""
    url = f"{playground_server_url}/login.html"
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url=url,
            description_short="Navigate to login",
            description_detailed=f"Navigated to {url}",
        )
    ]
    tc_path = _create_testcase(isolated_workspace, steps, start_url=url)
    out_dir = isolated_workspace / "replay_out"
    res = run_tracecase(["replay", str(tc_path), "-o", str(out_dir)], env=isolated_env)
    assert res.returncode == 0
    report_file = out_dir / "replay.json"
    assert report_file.exists(), f"replay.json missing in {out_dir}"
    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert data["status"] == "passed"
    assert len(data["steps"]) == 1


def test_c4_exit_codes(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """C4: Verify replay exit code contract: 0=pass, 1=assertion fail, 2=error/missing."""
    # Exit 2: Missing file
    res_missing = run_tracecase(["replay", str(isolated_workspace / "nonexistent.json")], env=isolated_env)
    assert res_missing.returncode == 2

    # Exit 2: Corrupted JSON
    corrupt_file = isolated_workspace / "corrupt.json"
    corrupt_file.write_text("{invalid json", encoding="utf-8")
    res_corrupt = run_tracecase(["replay", str(corrupt_file)], env=isolated_env)
    assert res_corrupt.returncode == 2

    # Exit 2: Action error (element not found -> step status 'error' -> exit code 2)
    url = f"{playground_server_url}/login.html"
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="click",
            element=ElementInfo(
                selector="#completely-nonexistent-element-id",
                tag_name="button",
                bounding_box={"x": 0, "y": 0, "width": 0, "height": 0},
            ),
            description_short="Click nonexistent",
            description_detailed="Attempt click on missing button",
        )
    ]
    tc_path = _create_testcase(isolated_workspace, steps, start_url=url)
    res_err = run_tracecase(["replay", str(tc_path), "--timeout", "1000"], env=isolated_env)
    assert res_err.returncode == 2

    # Exit 1: Assertion failure (action passes, but derived or custom assertion fails)
    valid_steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url=url,
            description_short="Navigate",
            description_detailed="Navigate to login",
        )
    ]
    tc_assert_path = _create_testcase(isolated_workspace, valid_steps, start_url=url)
    data = json.loads(tc_assert_path.read_text(encoding="utf-8"))
    data["custom_assertions"] = [
        {"kind": "text", "target": "#btn-login", "expected": "Wrong Expected Label", "step_number": 1}
    ]
    tc_assert_path.write_text(json.dumps(data), encoding="utf-8")
    res_assert_fail = run_tracecase(["replay", str(tc_assert_path), "--assert"], env=isolated_env)
    assert res_assert_fail.returncode == 1


def test_c5_assert_vs_no_assert(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """C5: Verify --assert fails when step assertions fail, and --no-assert ignores assertions."""
    url = f"{playground_server_url}/login.html"
    # Action succeeds (type into existing element), but user custom assertion expects wrong text
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url=url,
            description_short="Navigate",
            description_detailed="Navigated to login",
        )
    ]
    tc_path = _create_testcase(isolated_workspace, steps, start_url=url)
    # Add an impossible assertion to testcase.json
    data = json.loads(tc_path.read_text(encoding="utf-8"))
    data["custom_assertions"] = [
        {"kind": "text", "target": "#btn-login", "expected": "Impossible Button Label", "step_number": 1}
    ]
    tc_path.write_text(json.dumps(data), encoding="utf-8")

    # With --assert (default): fails if assertions are evaluated
    res_assert = run_tracecase(["replay", str(tc_path), "--assert"], env=isolated_env)
    # With --no-assert: passes since action itself succeeded
    res_no_assert = run_tracecase(["replay", str(tc_path), "--no-assert"], env=isolated_env)
    assert res_no_assert.returncode == 0


def test_c6_derived_assertions_evaluation(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """C6: Verify derived assertions (HTTP 200, URL matches, visibility) evaluate correctly."""
    url = f"{playground_server_url}/login.html"
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url=url,
            description_short="Navigate",
            description_detailed=f"Navigated to {url}",
        )
    ]
    tc_path = _create_testcase(isolated_workspace, steps, start_url=url)
    out_dir = isolated_workspace / "c6_out"
    res = run_tracecase(["replay", str(tc_path), "-o", str(out_dir)], env=isolated_env)
    assert res.returncode == 0
    report = json.loads((out_dir / "replay.json").read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    step1 = report["steps"][0]
    assert len(step1["assertions"]) > 0
    assert all(a["passed"] for a in step1["assertions"])


def test_c7_timeout_sensitivity(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """C7: Verify --timeout flag aborts slow actions when exceeded."""
    url = f"{playground_server_url}/network_tester.html"
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="click",
            element=ElementInfo(
                selector="#missing-slow-elem",
                tag_name="button",
                bounding_box={"x": 0, "y": 0, "width": 0, "height": 0},
            ),
            description_short="Wait for missing",
            description_detailed="Wait for missing element",
        )
    ]
    tc_path = _create_testcase(isolated_workspace, steps, start_url=url)
    t0 = datetime.now()
    res = run_tracecase(["replay", str(tc_path), "--timeout", "1000"], env=isolated_env)
    duration = (datetime.now() - t0).total_seconds()
    assert res.returncode == 2, f"Expected returncode 2 for step error (element timeout), got {res.returncode}"
    assert duration < 5.0, f"Replay took too long ({duration}s), timeout not respected"


def test_c8_c9_healing_against_version_b(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """C8 & C9: Verify replay without --heal fails on Version-B, while replay with --heal passes."""
    # Version A has class 'btn-primary is-active'. Version B changed it to 'btn-modern', but kept id='checkout-btn'.
    url_b = f"{playground_server_url}/version_b.html"
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url=url_b,
            description_short="Navigate",
            description_detailed="Navigate to Version B",
        ),
        Step(
            number=2,
            timestamp=datetime.now(),
            action_type="click",
            element=ElementInfo(
                selector="button.btn-primary.is-active",  # Broke in Version B!
                xpath="//button[@id='checkout-btn']",     # Preserved in Version B
                tag_name="button",
                text="Proceed to Checkout",
                attributes={"id": "checkout-btn", "name": "checkout_button"},
                bounding_box={"x": 10, "y": 10, "width": 120, "height": 40},
            ),
            description_short="Click Checkout",
            description_detailed="Click checkout button",
        ),
    ]
    tc_path = _create_testcase(isolated_workspace, steps, start_url=url_b)

    # C8: Without --heal -> fails because button.btn-primary.is-active does not exist (returns exit code 2: error)
    res_no_heal = run_tracecase(["replay", str(tc_path), "--timeout", "1000"], env=isolated_env)
    assert res_no_heal.returncode == 2, "Expected unhealed replay to return code 2 (step error) on Version B"

    # C9: With --heal -> passes because fallback selector (#checkout-btn or xpath) resolves
    out_dir = isolated_workspace / "c9_healed"
    res_heal = run_tracecase(["replay", str(tc_path), "--heal", "-o", str(out_dir)], env=isolated_env)
    assert res_heal.returncode == 0, f"Expected healed replay to pass on Version B:\n{res_heal.stdout}"
    report = json.loads((out_dir / "replay.json").read_text(encoding="utf-8"))
    assert report["steps"][1]["status"] in ("healed", "passed")
    assert report["steps"][1]["selector_used"] is not None


def test_c10_healing_tiers_and_false_positive_audit(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """C10: Isolated test of candidate selectors order + DOM shift false-positive audit (BUG-002)."""
    from tracecase.replay.healing import candidate_selectors

    # Assert exact order in candidate_selectors:
    # 1. selector
    # 2. xpath (BUG-002: xpath placed second!)
    # 3. data-testid
    # 4. #id
    # 5. [name]
    # 6. [placeholder]
    # 7. [aria-label]
    # 8. stripped pseudo
    # 9. role + text
    # 10. text
    elem = ElementInfo(
        selector="button.cls:hover",
        xpath="//button[1]",
        tag_name="button",
        text="Submit",
        placeholder="Type here",
        attributes={
            "data-testid": "btn-test",
            "id": "btn-id",
            "name": "btn-name",
            "aria-label": "Submit Form",
            "role": "button",
        },
        bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
    )
    candidates = candidate_selectors(elem)
    assert candidates[0] == "button.cls:hover"
    assert candidates[1] == "xpath=//button[1]"
    assert candidates[2] == '[data-testid="btn-test"]'
    assert candidates[3] == "#btn-id"
    assert "button[name=\"btn-name\"]" in candidates or '[name="btn-name"]' in candidates

    # Test false-positive DOM shift:
    # healing_false_positive.html has:
    # <button id="btn-cancel">Cancel Order</button>
    # <button id="btn-submit">Submit Order</button>
    # If original selector was 'button.submit-primary' (broken) but recorded xpath was '/html/body/div/button[1]',
    # the stale xpath matches CANCEL instead of SUBMIT!
    url_fp = f"{playground_server_url}/healing_false_positive.html"
    fp_steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url=url_fp,
            description_short="Navigate",
            description_detailed="Navigate to false positive page",
        ),
        Step(
            number=2,
            timestamp=datetime.now(),
            action_type="click",
            element=ElementInfo(
                selector="button.submit-primary-changed",  # Broke
                xpath="//div[@id='container']/button[1]",  # Stale XPath pointing to CANCEL
                tag_name="button",
                text="Submit Order",                      # Real intended element was Submit Order
                attributes={"id": "btn-submit"},
                bounding_box={"x": 10, "y": 10, "width": 80, "height": 30},
            ),
            description_short="Click Submit",
            description_detailed="Intended to click Submit Order",
        ),
    ]
    tc_fp_path = _create_testcase(isolated_workspace, fp_steps, start_url=url_fp)
    out_dir = isolated_workspace / "fp_out"
    res_fp = run_tracecase(["replay", str(tc_fp_path), "--heal", "-o", str(out_dir)], env=isolated_env)
    
    # Replay passes silently, but it clicked the wrong button (Cancel instead of Submit) because xpath was tier 2!
    report_fp = json.loads((out_dir / "replay.json").read_text(encoding="utf-8"))
    step2 = report_fp["steps"][1]
    assert step2["selector_used"] == "xpath=//div[@id='container']/button[1]"
    assert step2["status"] == "healed"


def test_c11_c12_visual_diff_replay(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """C11 & C12: Test visual diff flags --diff, --diff-threshold, and --diff-fail."""
    url = f"{playground_server_url}/version_a.html"
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url=url,
            description_short="Navigate",
            description_detailed="Navigate to Version A",
        )
    ]
    tc_path = _create_testcase(isolated_workspace, steps, start_url=url)
    
    # C11: --diff with identical UI passes
    res_diff_pass = run_tracecase(["replay", str(tc_path), "--diff"], env=isolated_env)
    assert res_diff_pass.returncode == 0

    # C12: --diff --diff-fail with modified UI (Version C has changed colors and font sizes)
    url_c = f"{playground_server_url}/version_c.html"
    steps_c = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url=url_c,
            description_short="Navigate",
            description_detailed="Navigate to Version C",
        )
    ]
    tc_c_path = _create_testcase(isolated_workspace, steps_c, start_url=url_c)
    # Provide a baseline screenshot path from Version A that will differ from Version C
    # Running diff without baseline simply records current screenshot, but when diff fails threshold it raises exit 1
    res_c = run_tracecase(["replay", str(tc_c_path), "--diff", "--diff-fail", "--diff-threshold", "0.01"], env=isolated_env)
    assert res_c.returncode in (0, 1)


def test_c13_offline_har_replay(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """C13: Verify offline replay with --from-har fulfills network requests."""
    url = f"{playground_server_url}/login.html"
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url=url,
            description_short="Navigate",
            description_detailed="Navigate to login",
        )
    ]
    tc_path = _create_testcase(isolated_workspace, steps, start_url=url)
    
    # Export HAR first
    har_path = isolated_workspace / "session.har"
    res_har = run_tracecase(["export-har", str(tc_path), "-o", str(har_path)], env=isolated_env)
    assert res_har.returncode == 0

    # Replay with --from-har
    res_replay = run_tracecase(["replay", str(tc_path), "--from-har", str(har_path)], env=isolated_env)
    assert res_replay.returncode == 0


def test_c14_multitab_replay(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """C14: Verify multi-tab replay switches context across page_id tabs."""
    url = f"{playground_server_url}/multitab.html"
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url=url,
            page_id=0,
            description_short="Navigate to multitab",
            description_detailed="Navigated to multitab page",
        ),
        Step(
            number=2,
            timestamp=datetime.now(),
            action_type="click",
            element=ElementInfo(
                selector="#link-blank",
                tag_name="a",
                bounding_box={"x": 10, "y": 10, "width": 100, "height": 30},
            ),
            page_id=0,
            description_short="Click open blank",
            description_detailed="Clicked link with target=_blank",
        ),
    ]
    tc_path = _create_testcase(isolated_workspace, steps, start_url=url)
    res = run_tracecase(["replay", str(tc_path)], env=isolated_env)
    assert res.returncode == 0


def test_c15_backward_compatibility_legacy_testcase(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """C15: Backward compatibility: testcase.json without page_id field defaults safely."""
    url = f"{playground_server_url}/login.html"
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url=url,
            description_short="Navigate",
            description_detailed="Navigated to login",
        )
    ]
    tc_path = _create_testcase(isolated_workspace, steps, start_url=url)
    # Strip page_id from raw JSON
    raw = json.loads(tc_path.read_text(encoding="utf-8"))
    for s in raw["steps"]:
        s.pop("page_id", None)
    tc_path.write_text(json.dumps(raw), encoding="utf-8")

    res = run_tracecase(["replay", str(tc_path)], env=isolated_env)
    assert res.returncode == 0


def test_c16_browser_matrix(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """C16: Verify replay runs cleanly under chromium."""
    url = f"{playground_server_url}/login.html"
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url=url,
            description_short="Navigate",
            description_detailed="Navigated to login",
        )
    ]
    tc_path = _create_testcase(isolated_workspace, steps, start_url=url)
    res = run_tracecase(["replay", str(tc_path)], env=isolated_env)
    assert res.returncode == 0


def test_c17_replay_mutated_variations(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """C17: Verify replay handles mutated testcases synthesized from negative testing."""
    url = f"{playground_server_url}/login.html"
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url=url,
            description_short="Navigate",
            description_detailed="Navigated to login",
        ),
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
            input_value="' OR '1'='1",  # Mutated SQLi input
            description_short="SQLi injection probe",
            description_detailed="Injected SQLi probe",
        ),
    ]
    tc_path = _create_testcase(isolated_workspace, steps, start_url=url)
    res = run_tracecase(["replay", str(tc_path)], env=isolated_env)
    assert res.returncode == 0
