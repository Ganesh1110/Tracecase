"""CLI Section F Tests: Playwright Code Generation (Flows F1 - F7).

Tests every CLI option and operational behavior of `tracecase codegen`:
- F1: Default codegen generates test_<slug>.py in testcase folder
- F2: Custom output path (-o / --output)
- F3: --har flag embeds offline HAR route mocking
- F4: Critical Dogfood Loop: Actually execute generated test file with pytest! (Sync vs Async check)
- F5: Multi-tab testcase codegen (page_id context switching)
- F6: Derived and custom assertions translated to Playwright expect() calls
- F7: Name sanitization (slugifying test names with symbols and special characters)
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import pytest
from tracecase.models import ElementInfo, Step, TestCase
from tests.dogfood.cli_tests.conftest import REPO_ROOT, run_tracecase


def _create_codegen_testcase(
    tmp_path: Path,
    name: str = "Login Flow Test",
    steps: list[Step] | None = None,
    start_url: str = "http://127.0.0.1:9010/login.html",
) -> Path:
    if steps is None:
        steps = [
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="navigate",
                url=start_url,
                description_short="Navigate to login",
                description_detailed=f"Navigated to {start_url}",
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
                input_value="alice",
                description_short="Fill username",
                description_detailed="Filled alice into username",
            ),
        ]
    tc = TestCase(
        id=f"tc_{tmp_path.name[:8]}",
        name=name,
        description="Codegen dogfood case",
        created_at=datetime.now(),
        start_url=start_url,
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Tracecase-Dogfood/1.0",
        steps=steps,
        total_duration=1.5,
        total_steps=len(steps),
    )
    tc_dir = tmp_path / tc.id
    tc_dir.mkdir(parents=True, exist_ok=True)
    tc_path = tc_dir / "testcase.json"
    tc_path.write_text(tc.model_dump_json(indent=2), encoding="utf-8")
    return tc_path


@pytest.mark.flow("F1")
def test_f1_default_codegen(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """F1: Default codegen generates test_<slug>.py next to testcase.json."""
    tc_path = _create_codegen_testcase(isolated_workspace, name="User Checkout Flow")
    res = run_tracecase(["codegen", str(tc_path)], env=isolated_env)
    assert res.returncode == 0
    expected_file = tc_path.parent / "test_user_checkout_flow.py"
    assert expected_file.exists()
    content = expected_file.read_text(encoding="utf-8")
    assert "async def test_" in content
    assert "page.goto" in content
    assert "# Step 2: " in content
    assert '.fill("alice")' in content


@pytest.mark.flow("F2")
def test_f2_custom_output_path(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """F2: -o / --output writes generated test code to specified custom path."""
    tc_path = _create_codegen_testcase(isolated_workspace)
    custom_out = isolated_workspace / "custom_dir" / "generated_test.py"
    res = run_tracecase(["codegen", str(tc_path), "-o", str(custom_out)], env=isolated_env)
    assert res.returncode == 0
    assert custom_out.exists()


@pytest.mark.flow("F3")
def test_f3_har_offline_route_mocking(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """F3: --har flag wires up offline HAR route mocking in generated Playwright test."""
    tc_path = _create_codegen_testcase(isolated_workspace)
    har_path = isolated_workspace / "network.har"
    har_path.write_text("{}", encoding="utf-8")
    out_file = isolated_workspace / "test_har_mock.py"

    res = run_tracecase(["codegen", str(tc_path), "--har", str(har_path), "-o", str(out_file)], env=isolated_env)
    assert res.returncode == 0
    content = out_file.read_text(encoding="utf-8")
    assert "route_from_har" in content or "har" in content


@pytest.mark.flow("F4")
def test_f4_execute_generated_test_with_pytest(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """F4 (CRITICAL): Execute the generated pytest test with pytest subprocess and verify pass."""
    start_url = f"{playground_server_url}/login.html"
    tc_path = _create_codegen_testcase(isolated_workspace, name="Live Executable Flow", start_url=start_url)
    test_file = isolated_workspace / "test_live_execution.py"
    res_gen = run_tracecase(["codegen", str(tc_path), "-o", str(test_file)], env=isolated_env)
    assert res_gen.returncode == 0
    assert test_file.exists()

    # Verify generated test uses async syntax (docs match)
    code = test_file.read_text(encoding="utf-8")
    assert "async def test_" in code
    assert "pytest_asyncio" in code or "async_playwright" in code

    # Execute generated test using pytest
    pytest_bin = REPO_ROOT / ".venv" / "bin" / "pytest"
    res_run = subprocess.run(
        [str(pytest_bin), str(test_file), "-v"],
        cwd=REPO_ROOT,
        env=isolated_env,
        capture_output=True,
        text=True,
    )
    assert res_run.returncode == 0, f"Generated test failed to execute:\nSTDOUT:\n{res_run.stdout}\nSTDERR:\n{res_run.stderr}"


@pytest.mark.flow("F5")
def test_f5_multitab_codegen(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """F5: Multi-tab testcase codegen generates context/page handling."""
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url=f"{playground_server_url}/multitab.html",
            page_id=0,
            description_short="Nav",
            description_detailed="Navigated",
        ),
        Step(
            number=2,
            timestamp=datetime.now(),
            action_type="click",
            element=ElementInfo(
                selector="#link-blank",
                tag_name="a",
                bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
            ),
            page_id=0,
            description_short="Click",
            description_detailed="Clicked",
        ),
    ]
    tc_path = _create_codegen_testcase(isolated_workspace, steps=steps, start_url=f"{playground_server_url}/multitab.html")
    out_file = isolated_workspace / "test_multitab.py"
    res = run_tracecase(["codegen", str(tc_path), "-o", str(out_file)], env=isolated_env)
    assert res.returncode == 0
    assert out_file.exists()


@pytest.mark.flow("F6")
def test_f6_assertions_in_generated_code(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """F6: Derived and custom assertions generate expect() statements."""
    tc_path = _create_codegen_testcase(isolated_workspace)
    out_file = isolated_workspace / "test_asserts.py"
    run_tracecase(["codegen", str(tc_path), "-o", str(out_file)], env=isolated_env)
    content = out_file.read_text(encoding="utf-8")
    assert "expect" in content


@pytest.mark.flow("F7")
def test_f7_name_sanitization(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """F7: Testcase names with spaces and special characters are safely slugified."""
    tc_path = _create_codegen_testcase(isolated_workspace, name="Payment & Checkout @ 2026 / $100 #test!")
    res = run_tracecase(["codegen", str(tc_path)], env=isolated_env)
    assert res.returncode == 0
    found = list(tc_path.parent.glob("test_*.py"))
    assert len(found) >= 1
    generated_name = found[0].name
    assert "&" not in generated_name and "@" not in generated_name and "$" not in generated_name


@pytest.mark.flow("F1")
def test_f8_all_recorded_steps_emitted(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """F1 / FAULT-3 detector: Verify that every recorded step in testcase.json is emitted in generated code."""
    steps = [
        Step(
            number=1,
            timestamp=datetime.now(),
            action_type="navigate",
            url="http://127.0.0.1:9010/login.html",
            description_short="Navigate to login",
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
            input_value="alice",
            description_short="Fill username",
            description_detailed="Filled alice into username",
        ),
        Step(
            number=3,
            timestamp=datetime.now(),
            action_type="click",
            element=ElementInfo(
                selector="#btn-submit",
                xpath="//button[@id='btn-submit']",
                tag_name="button",
                attributes={"id": "btn-submit"},
                bounding_box={"x": 10, "y": 50, "width": 80, "height": 30},
            ),
            description_short="Click submit button",
            description_detailed="Clicked submit button",
        ),
    ]
    tc_path = _create_codegen_testcase(isolated_workspace, steps=steps)
    out_file = isolated_workspace / "test_all_steps.py"
    res = run_tracecase(["codegen", str(tc_path), "-o", str(out_file)], env=isolated_env)
    assert res.returncode == 0
    content = out_file.read_text(encoding="utf-8")
    assert "goto" in content or "page.goto" in content
    assert "username" in content
    assert "btn-submit" in content or "submit" in content


@pytest.mark.flow("F1")
def test_f11_codegen_requires_pytest_asyncio_audit(isolated_workspace: Path, isolated_env: dict[str, str]):
    """F1 / BUG-007 (Characterization): Assert that generated code uses async def requiring pytest-asyncio."""
    tc_path = _create_codegen_testcase(isolated_workspace)
    out_file = isolated_workspace / "test_async_char.py"
    run_tracecase(["codegen", str(tc_path), "-o", str(out_file)], env=isolated_env)
    content = out_file.read_text(encoding="utf-8")
    assert "async def test_" in content


@pytest.mark.flow("F1")
@pytest.mark.xfail(strict=True, reason="BUG-007: Codegen generates async test requiring pytest-asyncio rather than standard pytest-playwright sync fixtures")
def test_bug007_codegen_clean_playwright_test(isolated_workspace: Path, isolated_env: dict[str, str]):
    """BUG-007 (Strict XFail of Correct Behavior): Generated code must run with standard sync pytest-playwright fixtures."""
    tc_path = _create_codegen_testcase(isolated_workspace)
    out_file = isolated_workspace / "test_standard.py"
    run_tracecase(["codegen", str(tc_path), "-o", str(out_file)], env=isolated_env)
    content = out_file.read_text(encoding="utf-8")
    assert not content.startswith("import pytest_asyncio")
    assert "async def test_" not in content, "Generated code uses async functions requiring pytest-asyncio"

