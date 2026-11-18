"""Tests for stdio Model Context Protocol (MCP) server."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from qa_auto.index.store import index_testcase
from qa_auto.mcp.server import MCPServer
from qa_auto.models import TestCase


def _testcase(tc_id: str, name: str) -> TestCase:
    return TestCase(
        id=tc_id,
        name=name,
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url="https://example.com",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=[],
        console_logs=[],
        network_requests=[],
        page_errors=[],
        total_duration=0.0,
        total_steps=0,
    )


@pytest.mark.asyncio
async def test_mcp_initialize() -> None:
    server = MCPServer()
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"clientInfo": {"name": "test-client"}},
    }
    resp = await server.handle_request(req)
    assert resp["id"] == 1
    assert resp["result"]["serverInfo"]["name"] == "qa_auto_mcp"


@pytest.mark.asyncio
async def test_mcp_list_tools() -> None:
    server = MCPServer()
    req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    resp = await server.handle_request(req)
    tools = {t["name"] for t in resp["result"]["tools"]}
    assert "search_testcases" in tools
    assert "get_testcase" in tools
    assert "coverage_report" in tools


@pytest.mark.asyncio
async def test_mcp_call_search(temp_dir: Path) -> None:
    db_path = temp_dir / "corpus.db"
    tc = _testcase("tc_mcp", "Billing Flow")
    index_testcase(tc, temp_dir / "tc.json", db_path)

    server = MCPServer(db_path=db_path)
    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "search_testcases", "arguments": {"query": "Billing"}},
    }
    resp = await server.handle_request(req)
    content = resp["result"]["content"][0]["text"]
    data = json.loads(content)
    assert len(data) == 1
    assert data[0]["id"] == "tc_mcp"


@pytest.mark.asyncio
async def test_mcp_call_get_testcase(temp_dir: Path) -> None:
    db_path = temp_dir / "corpus.db"
    tc_file = temp_dir / "tc.json"
    tc = _testcase("tc_get", "Settings Flow")
    tc_file.write_text(tc.model_dump_json(indent=2), encoding="utf-8")
    index_testcase(tc, tc_file, db_path)

    server = MCPServer(db_path=db_path)
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "get_testcase", "arguments": {"testcase_id": "tc_get"}},
    }
    resp = await server.handle_request(req)
    content = resp["result"]["content"][0]["text"]
    data = json.loads(content)
    assert data["id"] == "tc_get"
    assert data["name"] == "Settings Flow"


@pytest.mark.asyncio
async def test_mcp_call_coverage_report(temp_dir: Path) -> None:
    db_path = temp_dir / "corpus.db"
    tc = _testcase("tc_cov", "Auth Flow")
    index_testcase(tc, temp_dir / "tc.json", db_path)

    server = MCPServer(db_path=db_path)
    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "coverage_report", "arguments": {}},
    }
    resp = await server.handle_request(req)
    content = resp["result"]["content"][0]["text"]
    data = json.loads(content)
    assert data["total_testcases"] == 1
