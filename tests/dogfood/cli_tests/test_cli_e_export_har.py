"""CLI Section E Tests: Export HAR (Flows E1 - E4).

Tests every CLI option and operational behavior of `tracecase export-har`:
- E1: Export HAR from testcase (-o output)
- E2: Verify exported HAR is valid and replayable with --from-har
- E3: Export HAR for testcase with 0 network requests
- E4: Missing -o defaults to network.har next to testcase.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from tracecase.models import NetworkRequest, Step, TestCase
from tests.dogfood.cli_tests.conftest import run_tracecase


def _create_har_testcase(tmp_path: Path, requests: list[NetworkRequest]) -> Path:
    tc = TestCase(
        id=f"tc_{tmp_path.name[:8]}",
        name="HAR Export Testcase",
        description="Dogfood HAR export case",
        created_at=datetime.now(),
        start_url="http://127.0.0.1:9010/index.html",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Tracecase-Dogfood/1.0",
        steps=[
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="navigate",
                url="http://127.0.0.1:9010/index.html",
                network_requests=requests,
                description_short="Navigate",
                description_detailed="Navigated to index",
            )
        ],
        network_requests=requests,
        total_duration=1.0,
        total_steps=1,
    )
    tc_dir = tmp_path / tc.id
    tc_dir.mkdir(parents=True, exist_ok=True)
    tc_path = tc_dir / "testcase.json"
    tc_path.write_text(tc.model_dump_json(indent=2), encoding="utf-8")
    return tc_path


@pytest.mark.flow("E1")
def test_e1_export_har_with_output_flag(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """E1: Export HAR with -o writes valid HAR structure."""
    req = NetworkRequest(
        method="GET",
        url="http://127.0.0.1:9010/api/status/200",
        status=200,
        resource_type="fetch",
        timing=12.5,
        response_body='{"status":"ok"}',
    )
    tc_path = _create_har_testcase(isolated_workspace, [req])
    har_out = isolated_workspace / "custom.har"

    res = run_tracecase(["export-har", str(tc_path), "-o", str(har_out)], env=isolated_env)
    assert res.returncode == 0
    assert har_out.exists()

    data = json.loads(har_out.read_text(encoding="utf-8"))
    assert "log" in data
    assert data["log"]["version"] == "1.2"
    assert len(data["log"]["entries"]) == 1
    assert data["log"]["entries"][0]["request"]["url"] == req.url
    assert data["log"]["entries"][0]["response"]["status"] == 200


@pytest.mark.flow("E2")
def test_e2_exported_har_replayability(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
    playground_server_url: str,
):
    """E2: Replay testcase using the exported HAR fulfills network requests."""
    url = f"{playground_server_url}/login.html"
    req = NetworkRequest(
        method="GET",
        url=url,
        status=200,
        resource_type="document",
        timing=10.0,
        response_body="<html><body><h1>Login Form</h1></body></html>",
    )
    tc = TestCase(
        id=f"tc_{isolated_workspace.name[:8]}",
        name="HAR Replay Case",
        description="Dogfood HAR case",
        created_at=datetime.now(),
        start_url=url,
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Tracecase-Dogfood/1.0",
        steps=[
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="navigate",
                url=url,
                network_requests=[req],
                description_short="Navigate",
                description_detailed=f"Navigated to {url}",
            )
        ],
        network_requests=[req],
        total_duration=1.0,
        total_steps=1,
    )
    tc_dir = isolated_workspace / tc.id
    tc_dir.mkdir(parents=True, exist_ok=True)
    tc_path = tc_dir / "testcase.json"
    tc_path.write_text(tc.model_dump_json(indent=2), encoding="utf-8")

    har_path = isolated_workspace / "replay_test.har"
    run_tracecase(["export-har", str(tc_path), "-o", str(har_path)], env=isolated_env)
    assert har_path.exists()

    res_rep = run_tracecase(["replay", str(tc_path), "--from-har", str(har_path)], env=isolated_env)
    assert res_rep.returncode == 0


@pytest.mark.flow("E3")
def test_e3_testcase_zero_network_requests(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """E3: Export HAR for testcase with 0 requests outputs empty entries list."""
    tc_path = _create_har_testcase(isolated_workspace, [])
    har_path = isolated_workspace / "empty.har"

    res = run_tracecase(["export-har", str(tc_path), "-o", str(har_path)], env=isolated_env)
    assert res.returncode == 0
    assert har_path.exists()

    data = json.loads(har_path.read_text(encoding="utf-8"))
    assert data["log"]["entries"] == []


@pytest.mark.flow("E4")
def test_e4_missing_output_flag_defaults(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """E4: Omitting -o writes network.har in the testcase directory."""
    tc_path = _create_har_testcase(isolated_workspace, [])
    res = run_tracecase(["export-har", str(tc_path)], env=isolated_env)
    assert res.returncode == 0

    default_har = tc_path.parent / "network.har"
    assert default_har.exists(), f"Expected default HAR at {default_har}"
