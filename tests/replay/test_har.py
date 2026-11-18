"""Tests for HAR export."""

import json
from datetime import datetime
from pathlib import Path

from qa_auto.models import NetworkRequest, TestCase
from qa_auto.replay.har import build_har, export_har


def _testcase(requests: list[NetworkRequest]) -> TestCase:
    return TestCase(
        id="tc_har",
        name="HAR",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url="https://app.example.com",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=[],
        console_logs=[],
        network_requests=requests,
        page_errors=[],
        total_duration=1.0,
        total_steps=0,
    )


def _request() -> NetworkRequest:
    return NetworkRequest(
        method="POST",
        url="https://app.example.com/api/login",
        status=201,
        resource_type="fetch",
        timing=42.5,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        request_headers={"content-type": "application/json"},
        response_headers={"content-type": "application/json"},
        request_body='{"user": "qa"}',
        response_body='{"token": "abc"}',
    )


def test_build_har_has_log_and_entry() -> None:
    har = build_har(_testcase([_request()]))

    assert har["log"]["version"] == "1.2"
    assert har["log"]["creator"]["name"] == "qa_auto"
    assert len(har["log"]["entries"]) == 1

    entry = har["log"]["entries"][0]
    assert entry["request"]["method"] == "POST"
    assert entry["request"]["url"] == "https://app.example.com/api/login"
    assert entry["request"]["postData"]["text"] == '{"user": "qa"}'
    assert entry["response"]["status"] == 201
    assert entry["response"]["content"]["text"] == '{"token": "abc"}'
    assert entry["timings"]["wait"] == 42.5


def test_export_har_writes_valid_json(temp_dir: Path) -> None:
    path = export_har(_testcase([_request()]), temp_dir / "network.har")

    assert path == temp_dir / "network.har"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["log"]["entries"][0]["response"]["status"] == 201


def test_failed_request_is_preserved_in_comment() -> None:
    request = _request()
    request.status = None
    request.error = "net::ERR_FAILED"

    har = build_har(_testcase([request]))

    entry = har["log"]["entries"][0]
    assert entry["response"]["status"] == 0
    assert entry["comment"] == "net::ERR_FAILED"
