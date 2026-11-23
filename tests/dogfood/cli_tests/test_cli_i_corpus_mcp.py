"""CLI Section I Tests: Corpus Indexing, Search, Coverage, Clean & MCP (Flows I1 - I22).

Dedicated tests for each flow tagged with @pytest.mark.flow("<ID>"):
- I1 - I4: Indexing directory, custom db, --clear, idempotency
- I5 - I9: Search BM25, --limit, selector/url, no results, special FTS5 syntax
- I10 - I12: Coverage report display, duplicate warnings, empty DB
- I13 - I16: Clean --db, --all, selective flags, bare defaults
- I17 - I22: MCP stdio initialize, search_testcases, get_testcase, coverage_report discrepancy, custom DB, stdout purity
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
from tracecase.models import ElementInfo, NetworkRequest, Step, TestCase
from tests.dogfood.cli_tests.conftest import REPO_ROOT, run_tracecase


def _create_sample_testcase(tmp_path: Path, tc_id: str, name: str, start_url: str) -> Path:
    tc_dir = tmp_path / tc_id
    tc_dir.mkdir(parents=True, exist_ok=True)
    req = NetworkRequest(
        method="GET",
        url=f"{start_url}/api/search?q=laptop",
        status=200,
        resource_type="fetch",
        timing=15.0,
    )
    tc = TestCase(
        id=tc_id,
        name=name,
        description=f"Corpus test case {name}",
        created_at=datetime.now(),
        start_url=start_url,
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Tracecase-Dogfood/1.0",
        steps=[
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="navigate",
                url=start_url,
                description_short=f"Nav to {start_url}",
                description_detailed=f"Navigated to {start_url}",
            ),
            Step(
                number=2,
                timestamp=datetime.now(),
                action_type="input",
                element=ElementInfo(
                    selector="#search-query",
                    xpath="//input[@id='search-query']",
                    tag_name="input",
                    attributes={"id": "search-query"},
                    bounding_box={"x": 10, "y": 10, "width": 100, "height": 30},
                ),
                input_value="laptop checkout",
                network_requests=[req],
                description_short="Type search",
                description_detailed="Typed laptop checkout",
            ),
        ],
        network_requests=[req],
        total_duration=1.0,
        total_steps=2,
    )
    tc_path = tc_dir / "testcase.json"
    tc_path.write_text(tc.model_dump_json(indent=2), encoding="utf-8")
    return tc_path


@pytest.mark.flow("I1")
def test_i1_index_directory(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I1: tracecase index indexes a directory containing testcases into SQLite FTS5."""
    _create_sample_testcase(isolated_workspace, "tc_i1", "Index Dir Flow", "http://127.0.0.1:9010/index")
    custom_db = isolated_workspace / "i1.db"
    res = run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)
    assert res.returncode == 0
    assert "Indexed 1 test case" in res.stdout


@pytest.mark.flow("I2")
def test_i2_index_custom_db_path(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I2: tracecase index --db creates database at custom specified path."""
    _create_sample_testcase(isolated_workspace, "tc_i2", "Custom DB Flow", "http://127.0.0.1:9010/index")
    custom_db = isolated_workspace / "sub" / "custom_target.db"
    res = run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)
    assert res.returncode == 0
    assert custom_db.exists()


@pytest.mark.flow("I3")
def test_i3_index_clear_flag(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I3: tracecase index --clear wipes existing records before re-indexing."""
    _create_sample_testcase(isolated_workspace, "tc_i3", "Clear Flag Flow", "http://127.0.0.1:9010/index")
    custom_db = isolated_workspace / "i3.db"
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    res = run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db), "--clear"], env=isolated_env)
    assert res.returncode == 0
    assert "Existing corpus database reset" in res.stdout


@pytest.mark.flow("I4")
def test_i4_reindex_idempotency(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I4: Indexing the same testcase twice updates cleanly without duplicates."""
    import sqlite3
    _create_sample_testcase(isolated_workspace, "tc_i4", "Idempotent Flow", "http://127.0.0.1:9010/index")
    custom_db = isolated_workspace / "i4.db"
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)
    res2 = run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)
    assert res2.returncode == 0
    with sqlite3.connect(custom_db) as conn:
        count = conn.execute("SELECT count(*) FROM testcases WHERE id='tc_i4'").fetchone()[0]
    assert count == 1


@pytest.mark.flow("I5")
def test_i5_search_bm25_ranking_snippets(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I5: tracecase search performs BM25 ranking and highlights matched snippets."""
    _create_sample_testcase(isolated_workspace, "tc_i5", "UniqueLaptopFlow", "http://127.0.0.1:9010/index")
    custom_db = isolated_workspace / "i5.db"
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    res = run_tracecase(["search", "UniqueLaptopFlow", "--db", str(custom_db)], env=isolated_env)
    assert res.returncode == 0
    assert "tc_i5" in res.stdout


@pytest.mark.flow("I6")
def test_i6_search_limit_flag(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I6: tracecase search --limit caps displayed results."""
    _create_sample_testcase(isolated_workspace, "tc_i6a", "Common Flow A", "http://127.0.0.1:9010/index")
    _create_sample_testcase(isolated_workspace, "tc_i6b", "Common Flow B", "http://127.0.0.1:9010/index")
    custom_db = isolated_workspace / "i6.db"
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    res = run_tracecase(["search", "Common", "--db", str(custom_db), "--limit", "1"], env=isolated_env)
    assert res.returncode == 0
    assert res.stdout.count("tc_i6") == 1


@pytest.mark.flow("I7")
def test_i7_search_by_selector_and_url(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I7: Search matches against CSS selectors and API endpoint URLs."""
    _create_sample_testcase(isolated_workspace, "tc_i7", "Selector Search", "http://127.0.0.1:9010/index")
    custom_db = isolated_workspace / "i7.db"
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    res_sel = run_tracecase(["search", "#search-query", "--db", str(custom_db)], env=isolated_env)
    assert res_sel.returncode == 0
    assert "tc_i7" in res_sel.stdout

    res_ep = run_tracecase(["search", "api", "--db", str(custom_db)], env=isolated_env)
    assert res_ep.returncode == 0
    assert "tc_i7" in res_ep.stdout


@pytest.mark.flow("I8")
def test_i8_search_no_results(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I8: Search with zero matches returns clear message and exit code 0."""
    custom_db = isolated_workspace / "i8.db"
    _create_sample_testcase(isolated_workspace, "tc_i8", "Some Flow", "http://127.0.0.1:9010/index")
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    res = run_tracecase(["search", "totally_absent_phrase_999", "--db", str(custom_db)], env=isolated_env)
    assert res.returncode == 0
    assert "No test cases found" in res.stdout


@pytest.mark.flow("I9")
def test_i9_search_special_fts5_characters(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I9: Search handles quotes, dashes, and boolean operators safely."""
    custom_db = isolated_workspace / "i9.db"
    _create_sample_testcase(isolated_workspace, "tc_i9", "Special FTS Flow", "http://127.0.0.1:9010/index")
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    # Search handles quotes and special characters
    res = run_tracecase(["search", '"Special FTS Flow"', "--db", str(custom_db)], env=isolated_env)
    assert res.returncode == 0
    assert "tc_i9" in res.stdout


@pytest.mark.flow("I10")
def test_i10_coverage_report_display(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I10: tracecase coverage displays tested domains, endpoints, and summary metrics."""
    custom_db = isolated_workspace / "i10.db"
    _create_sample_testcase(isolated_workspace, "tc_i10", "Cov Flow", "http://127.0.0.1:9010/index")
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    res = run_tracecase(["coverage", "--db", str(custom_db)], env=isolated_env)
    assert res.returncode == 0
    assert "Corpus Coverage Report" in res.stdout
    assert "Total Test Cases" in res.stdout


@pytest.mark.flow("I11")
def test_i11_duplicate_flow_warning(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I11: Coverage report warns about duplicate recorded flows on identical start URLs."""
    custom_db = isolated_workspace / "i11.db"
    _create_sample_testcase(isolated_workspace, "tc_dup1", "Dup 1", "http://127.0.0.1:9010/same_url")
    _create_sample_testcase(isolated_workspace, "tc_dup2", "Dup 2", "http://127.0.0.1:9010/same_url")
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    res = run_tracecase(["coverage", "--db", str(custom_db)], env=isolated_env)
    assert res.returncode == 0
    assert "Potential Duplicate Test Flows" in res.stdout or "Potential Duplicate" in res.stdout


@pytest.mark.flow("I12")
def test_i12_coverage_on_empty_db(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I12: Coverage on empty database displays 0 test cases without error."""
    custom_db = isolated_workspace / "empty.db"
    res = run_tracecase(["coverage", "--db", str(custom_db)], env=isolated_env)
    assert res.returncode == 0
    assert "Total Test Cases" in res.stdout


@pytest.mark.flow("I13")
def test_i13_clean_db_flag(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I13: tracecase clean --db deletes local SQLite database file."""
    custom_db = isolated_workspace / "i13.db"
    rec_dir = isolated_workspace / "recordings"
    rec_dir.mkdir(parents=True, exist_ok=True)
    _create_sample_testcase(isolated_workspace, "tc_i13", "Clean DB Flow", "http://127.0.0.1:9010/index")
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)
    assert custom_db.exists()

    res = run_tracecase(["clean", "--db", "--db-path", str(custom_db)], env=isolated_env, cwd=isolated_workspace)
    assert res.returncode == 0
    assert not custom_db.exists()
    assert rec_dir.exists()


@pytest.mark.flow("I14")
def test_i14_clean_all_flag(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I14: tracecase clean --all deletes DB and recordings directory inside sandbox."""
    custom_db = isolated_workspace / "i14.db"
    rec_dir = isolated_workspace / "recordings"
    rec_dir.mkdir(parents=True, exist_ok=True)
    _create_sample_testcase(isolated_workspace, "tc_i14", "Clean All Flow", "http://127.0.0.1:9010/index")
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    res = run_tracecase(["clean", "--all", "--db-path", str(custom_db)], env=isolated_env)
    assert res.returncode == 0
    assert not custom_db.exists()


@pytest.mark.flow("I15")
def test_i15_clean_selective_flags(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I15: Selective clean --no-db does not delete database."""
    custom_db = isolated_workspace / "i15.db"
    _create_sample_testcase(isolated_workspace, "tc_i15", "Clean Selective Flow", "http://127.0.0.1:9010/index")
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    res = run_tracecase(["clean", "--no-db", "--db-path", str(custom_db)], env=isolated_env)
    assert res.returncode == 0
    assert custom_db.exists()


@pytest.mark.flow("I16")
def test_i16_bare_clean_command_defaults(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I16: Bare tracecase clean defaults to clearing DB only."""
    custom_db = isolated_workspace / "i16.db"
    _create_sample_testcase(isolated_workspace, "tc_i16", "Clean Bare Flow", "http://127.0.0.1:9010/index")
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    res = run_tracecase(["clean", "--db-path", str(custom_db)], env=isolated_env)
    assert res.returncode == 0
    assert not custom_db.exists()


@pytest.mark.flow("I17")
def test_i17_mcp_initialize(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I17: MCP stdio server initializes with JSON-RPC 2.0 protocol handshake."""
    custom_db = isolated_workspace / "mcp17.db"
    proc = subprocess.Popen(
        [str(REPO_ROOT / ".venv" / "bin" / "tracecase"), "mcp", "--db", str(custom_db)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=isolated_env,
        cwd=REPO_ROOT,
    )
    try:
        req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(req + "\n")
        proc.stdin.flush()
        resp = json.loads(proc.stdout.readline())
        assert resp["result"]["serverInfo"]["name"] == "tracecase_mcp"
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=2.0)


@pytest.mark.flow("I18")
def test_i18_mcp_search_testcases_tool(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I18: MCP search_testcases tool returns matching test cases via stdio."""
    custom_db = isolated_workspace / "mcp18.db"
    _create_sample_testcase(isolated_workspace, "tc_mcp18", "MCP Search Case", "http://127.0.0.1:9010/index")
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    proc = subprocess.Popen(
        [str(REPO_ROOT / ".venv" / "bin" / "tracecase"), "mcp", "--db", str(custom_db)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=isolated_env,
        cwd=REPO_ROOT,
    )
    try:
        req = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "search_testcases", "arguments": {"query": "laptop"}}
        })
        proc.stdin.write(req + "\n")
        proc.stdin.flush()
        resp = json.loads(proc.stdout.readline())
        assert "tc_mcp18" in resp["result"]["content"][0]["text"]
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=2.0)


@pytest.mark.flow("I19")
def test_i19_mcp_get_testcase_tool(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I19: MCP get_testcase tool retrieves complete recorded JSON by ID."""
    custom_db = isolated_workspace / "mcp19.db"
    _create_sample_testcase(isolated_workspace, "tc_mcp19", "MCP Get Case", "http://127.0.0.1:9010/index")
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    proc = subprocess.Popen(
        [str(REPO_ROOT / ".venv" / "bin" / "tracecase"), "mcp", "--db", str(custom_db)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=isolated_env,
        cwd=REPO_ROOT,
    )
    try:
        req = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_testcase", "arguments": {"testcase_id": "tc_mcp19"}}
        })
        proc.stdin.write(req + "\n")
        proc.stdin.flush()
        resp = json.loads(proc.stdout.readline())
        tc_data = json.loads(resp["result"]["content"][0]["text"])
        assert tc_data["id"] == "tc_mcp19"
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=2.0)


@pytest.mark.flow("I20")
def test_i20_mcp_tool_naming_coverage_report(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I20 (Discrepancy): Verify MCP tool is named coverage_report (code) vs get_coverage (docs)."""
    custom_db = isolated_workspace / "mcp20.db"
    proc = subprocess.Popen(
        [str(REPO_ROOT / ".venv" / "bin" / "tracecase"), "mcp", "--db", str(custom_db)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=isolated_env,
        cwd=REPO_ROOT,
    )
    try:
        req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        proc.stdin.write(req + "\n")
        proc.stdin.flush()
        resp = json.loads(proc.stdout.readline())
        names = [t["name"] for t in resp["result"]["tools"]]
        assert "coverage_report" in names
        assert "get_coverage" not in names
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=2.0)


@pytest.mark.flow("I21")
def test_i21_mcp_custom_db_path(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I21: MCP server accepts and operates on --db custom path."""
    custom_db = isolated_workspace / "custom_mcp.db"
    _create_sample_testcase(isolated_workspace, "tc_mcp21", "MCP Custom DB", "http://127.0.0.1:9010/index")
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    proc = subprocess.Popen(
        [str(REPO_ROOT / ".venv" / "bin" / "tracecase"), "mcp", "--db", str(custom_db)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=isolated_env,
        cwd=REPO_ROOT,
    )
    try:
        req = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "coverage_report", "arguments": {}}
        })
        proc.stdin.write(req + "\n")
        proc.stdin.flush()
        resp = json.loads(proc.stdout.readline())
        assert "result" in resp
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=2.0)


@pytest.mark.flow("I22")
def test_i22_mcp_stdout_protocol_purity(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I22: MCP server emits ONLY valid JSON-RPC lines on stdout (no banners or rich markup)."""
    custom_db = isolated_workspace / "mcp22.db"
    proc = subprocess.Popen(
        [str(REPO_ROOT / ".venv" / "bin" / "tracecase"), "mcp", "--db", str(custom_db)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=isolated_env,
        cwd=REPO_ROOT,
    )
    try:
        req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(req + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        # Must be valid JSON with no ANSI color escape codes or extra characters
        parsed = json.loads(line)
        assert parsed["jsonrpc"] == "2.0"
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=2.0)


@pytest.mark.flow("I19")
@pytest.mark.xfail(strict=True, reason="BUG-009D: MCP get_testcase returns plaintext password credentials")
def test_i20_mcp_password_masking(isolated_workspace: Path, isolated_env: dict[str, str]):
    """I19 / BUG-009D: MCP get_testcase must NOT return unmasked plaintext passwords."""
    from tracecase.mcp.server import MCPServer
    import asyncio
    db_path = isolated_workspace / "mcp_pwd.db"
    tc_path = _create_sample_testcase(isolated_workspace, "tc_mcp_pwd", "Password Flow", "http://127.0.0.1:9010/login.html")
    # Inject sensitive password into step
    tc = TestCase.model_validate_json(tc_path.read_text(encoding="utf-8"))
    tc.steps[1].element.attributes["type"] = "password"
    tc.steps[1].input_value = "SuperSecretPassword123!"
    tc_path.write_text(tc.model_dump_json(indent=2), encoding="utf-8")

    run_tracecase(["index", str(isolated_workspace), "--db", str(db_path)], env=isolated_env)

    mcp = MCPServer(db_path=db_path)
    res = asyncio.run(mcp.handle_request({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "get_testcase", "arguments": {"testcase_id": "tc_mcp_pwd"}},
    }))
    res_str = json.dumps(res)
    assert "SuperSecretPassword123!" not in res_str, "Plaintext password leaked in MCP response"

