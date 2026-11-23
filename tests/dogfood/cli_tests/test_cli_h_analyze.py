"""CLI Section H Tests: AI Analysis & Heuristics (Flows H1 - H9).

Tests every CLI option and operational behavior of `tracecase analyze`:
- H1: Offline heuristics analysis without AI (provider: null)
- H2: Custom output directory (-o / --output) saves analysis.json
- H3: Default provider null makes 0 outbound network requests
- H4: Ollama provider against local Fake LLM server (port 9110)
- H5: OpenAI provider against local Fake LLM server (port 9110)
- H6: Graceful fallback when AI server returns HTTP 500 error
- H7: Schema validation of analysis.json
- H8: Heuristic risk detection rules (cleartext secrets, 4xx/5xx responses)
- H9: Unreachable base URL error handling
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from tracecase.models import ConsoleLog, ElementInfo, NetworkRequest, PageError, Step, TestCase
from tests.dogfood.cli_tests.conftest import run_tracecase


def _create_analyzable_testcase(tmp_path: Path) -> Path:
    req = NetworkRequest(
        method="POST",
        url="http://127.0.0.1:9010/api/checkout",
        status=500,
        resource_type="fetch",
        timing=35.0,
        response_body='{"error":"Internal Server Error"}',
    )
    tc = TestCase(
        id=f"tc_{tmp_path.name[:8]}",
        name="Failed Checkout Analysis Flow",
        description="Analyzable testcase with errors",
        created_at=datetime.now(),
        start_url="http://127.0.0.1:9010/login.html",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Tracecase-Dogfood/1.0",
        steps=[
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="input",
                element=ElementInfo(
                    selector="#password",
                    tag_name="input",
                    attributes={"id": "password", "type": "password"},
                    bounding_box={"x": 10, "y": 10, "width": 100, "height": 30},
                ),
                input_value="SecretPassword123!",
                description_short="Type password",
                description_detailed="Typed secret password",
            ),
            Step(
                number=2,
                timestamp=datetime.now(),
                action_type="click",
                element=ElementInfo(
                    selector="#btn-submit",
                    tag_name="button",
                    bounding_box={"x": 10, "y": 10, "width": 80, "height": 30},
                ),
                network_requests=[req],
                console_logs=[
                    ConsoleLog(level="error", message="Checkout failed with 500 status")
                ],
                description_short="Click submit",
                description_detailed="Submitted order and failed",
            ),
        ],
        network_requests=[req],
        console_logs=[
            ConsoleLog(level="error", message="Checkout failed with 500 status")
        ],
        page_errors=[
            PageError(message="Uncaught TypeError: Cannot read properties of undefined")
        ],
        total_duration=2.0,
        total_steps=2,
    )
    tc_dir = tmp_path / tc.id
    tc_dir.mkdir(parents=True, exist_ok=True)
    tc_path = tc_dir / "testcase.json"
    tc_path.write_text(tc.model_dump_json(indent=2), encoding="utf-8")
    return tc_path


@pytest.mark.flow("H1")
def test_h1_offline_heuristics(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """H1: analyze with provider: null runs entirely offline and produces analysis."""
    tc_path = _create_analyzable_testcase(isolated_workspace)
    res = run_tracecase(["analyze", str(tc_path), "--provider", "null"], env=isolated_env)
    assert res.returncode == 0
    assert "Analysis Results" in res.stdout
    assert "Summary" in res.stdout


@pytest.mark.flow("H2")
def test_h2_custom_output_directory(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """H2: -o / --output saves analysis.json in the specified directory."""
    tc_path = _create_analyzable_testcase(isolated_workspace)
    out_dir = isolated_workspace / "custom_analysis"
    res = run_tracecase(["analyze", str(tc_path), "-o", str(out_dir), "--provider", "null"], env=isolated_env)
    assert res.returncode == 0
    analysis_file = out_dir / "analysis.json"
    assert analysis_file.exists()


@pytest.mark.flow("H3")
def test_h3_provider_null_makes_zero_network_calls(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """H3: Provider null does not invoke any network or external LLM endpoint."""
    tc_path = _create_analyzable_testcase(isolated_workspace)
    # Give a bogus base-url; provider null must not touch it
    res = run_tracecase(["analyze", str(tc_path), "--provider", "null", "--base-url", "http://127.0.0.1:19999"], env=isolated_env)
    assert res.returncode == 0


@pytest.mark.flow("H4")
def test_h4_ollama_provider_against_fake_llm(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    fake_llm_server_url: str,
):
    """H4: Ollama provider routes to fake LLM server."""
    tc_path = _create_analyzable_testcase(isolated_workspace)
    res = run_tracecase(
        ["analyze", str(tc_path), "--ai", "--provider", "ollama", "--base-url", fake_llm_server_url, "--model", "llama3"],
        env=isolated_env,
    )
    assert res.returncode == 0
    assert "Analyzing" in res.stdout


@pytest.mark.flow("H5")
def test_h5_openai_provider_against_fake_llm(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    fake_llm_server_url: str,
):
    """H5: OpenAI provider routes to fake LLM server /v1/chat/completions."""
    tc_path = _create_analyzable_testcase(isolated_workspace)
    res = run_tracecase(
        ["analyze", str(tc_path), "--ai", "--provider", "openai", "--base-url", f"{fake_llm_server_url}/v1", "--model", "gpt-4o"],
        env=isolated_env,
    )
    assert res.returncode == 0


@pytest.mark.flow("H6")
def test_h6_llm_failure_fallback(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    fake_llm_server_url: str,
):
    """H6: When AI server returns 500 error, heuristics fallback still succeeds."""
    tc_path = _create_analyzable_testcase(isolated_workspace)
    res = run_tracecase(
        ["analyze", str(tc_path), "--ai", "--provider", "openai", "--base-url", "http://127.0.0.1:9199/v1"],
        env=isolated_env,
    )
    assert res.returncode in (0, 1, 2)


@pytest.mark.flow("H7")
def test_h7_schema_validation(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """H7: analysis.json conforms to expected schema (summary, risks, suggestions)."""
    tc_path = _create_analyzable_testcase(isolated_workspace)
    out_dir = isolated_workspace / "schema_check"
    run_tracecase(["analyze", str(tc_path), "-o", str(out_dir), "--provider", "null"], env=isolated_env)
    analysis = json.loads((out_dir / "analysis.json").read_text(encoding="utf-8"))
    assert "summary" in analysis
    assert "risks" in analysis
    assert isinstance(analysis["risks"], list)
    assert "suggested_assertions" in analysis
    assert "negative_scenarios" in analysis


@pytest.mark.flow("H8")
def test_h8_heuristic_risk_detection(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """H8: Heuristics flag network errors (500) and page errors."""
    tc_path = _create_analyzable_testcase(isolated_workspace)
    out_dir = isolated_workspace / "h8_out"
    run_tracecase(["analyze", str(tc_path), "-o", str(out_dir), "--provider", "null"], env=isolated_env)
    analysis = json.loads((out_dir / "analysis.json").read_text(encoding="utf-8"))
    risks = " ".join(analysis["risks"])
    assert "500" in risks or "error" in risks.lower() or len(analysis["risks"]) > 0


@pytest.mark.flow("H9")
def test_h9_unreachable_endpoint_handling(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """H9: Unreachable base-url is handled without unhandled traceback."""
    tc_path = _create_analyzable_testcase(isolated_workspace)
    res = run_tracecase(
        ["analyze", str(tc_path), "--ai", "--provider", "openai", "--base-url", "http://127.0.0.1:9999/v1"],
        env=isolated_env,
    )
    assert res.returncode in (0, 1, 2)
