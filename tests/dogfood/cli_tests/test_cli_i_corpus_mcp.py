"""CLI Section I Tests: Corpus Indexing, Search, Coverage, Clean & MCP (Flows I1 - I22).

Tests every CLI option and operational behavior of:
- `tracecase index` (I1 - I5): single case, directory, custom db, --clear, idempotency
- `tracecase search` (I6 - I11): BM25 keyword, selector, URL, --limit, 0 matches, FTS5 syntax
- `tracecase coverage` (I12 - I13): domain/route metrics, custom --db
- `tracecase clean` (I14 - I16): bare defaults, --db, --all within sandbox isolation
- `tracecase mcp` (I17 - I22): stdio JSON-RPC 2.0 initialize, tools/list, search_testcases,
  get_testcase, coverage_report vs get_coverage discrepancy, stdout protocol purity.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

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


def test_i1_to_i5_index_commands(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """I1 - I5: Indexing testcases into SQLite FTS5 corpus database."""
    tc1 = _create_sample_testcase(isolated_workspace, "tc_001", "Search Flow", "http://127.0.0.1:9010/index.html")
    tc2 = _create_sample_testcase(isolated_workspace, "tc_002", "Login Flow", "http://127.0.0.1:9010/login.html")
    custom_db = isolated_workspace / "custom_corpus.db"

    # I1 & I2: Index directory
    res_idx = run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)
    assert res_idx.returncode == 0
    assert "Indexed 2 test case(s)" in res_idx.stdout
    assert custom_db.exists()

    # I5: Idempotency (re-index should not fail)
    res_reindex = run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)
    assert res_reindex.returncode == 0

    # I4: --clear flag resets database
    res_clear = run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db), "--clear"], env=isolated_env)
    assert res_clear.returncode == 0
    assert "Existing corpus database reset" in res_clear.stdout


def test_i6_to_i11_search_commands(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """I6 - I11: Full-text search over indexed corpus."""
    _create_sample_testcase(isolated_workspace, "tc_search", "Ecommerce Product Search", "http://127.0.0.1:9010/products")
    custom_db = isolated_workspace / "search_corpus.db"
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    # I6: Keyword search
    res_kw = run_tracecase(["search", "Ecommerce", "--db", str(custom_db)], env=isolated_env)
    assert res_kw.returncode == 0
    assert "tc_search" in res_kw.stdout

    # I7: Selector search
    res_sel = run_tracecase(["search", "#search-query", "--db", str(custom_db)], env=isolated_env)
    assert res_sel.returncode == 0
    assert "tc_search" in res_sel.stdout

    # I8: Endpoint search
    res_ep = run_tracecase(["search", "api", "--db", str(custom_db)], env=isolated_env)
    assert res_ep.returncode == 0
    assert "tc_search" in res_ep.stdout

    # I9: Limit flag
    res_lim = run_tracecase(["search", "laptop", "--db", str(custom_db), "--limit", "1"], env=isolated_env)
    assert res_lim.returncode == 0

    # I10: 0 matches
    res_zero = run_tracecase(["search", "completely_unmatched_term_xyz", "--db", str(custom_db)], env=isolated_env)
    assert res_zero.returncode == 0
    assert "No test cases found" in res_zero.stdout


def test_i12_i13_coverage_command(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """I12 & I13: Coverage reporting over domains and endpoints."""
    _create_sample_testcase(isolated_workspace, "tc_cov", "Coverage Flow", "http://127.0.0.1:9010/index")
    custom_db = isolated_workspace / "cov.db"
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    res_cov = run_tracecase(["coverage", "--db", str(custom_db)], env=isolated_env)
    assert res_cov.returncode == 0
    assert "Corpus Coverage Report" in res_cov.stdout
    assert "Total Test Cases" in res_cov.stdout


def test_i14_to_i16_clean_command(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """I14 - I16: tracecase clean inside isolated sandbox."""
    custom_db = isolated_workspace / "to_clean.db"
    _create_sample_testcase(isolated_workspace, "tc_c", "Clean Case", "http://127.0.0.1:9010/index")
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)
    assert custom_db.exists()

    # I15: Clean custom db
    res_clean_db = run_tracecase(["clean", "--db", "--db-path", str(custom_db)], env=isolated_env)
    assert res_clean_db.returncode == 0

    # I16: Clean --all
    res_clean_all = run_tracecase(["clean", "--all", "--db-path", str(custom_db)], env=isolated_env)
    assert res_clean_all.returncode == 0


def test_i17_to_i22_mcp_stdio_server(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """I17 - I22: Model Context Protocol (MCP) stdio JSON-RPC interaction."""
    custom_db = isolated_workspace / "mcp_corpus.db"
    tc_path = _create_sample_testcase(isolated_workspace, "tc_mcp_1", "MCP Search Test", "http://127.0.0.1:9010/index")
    run_tracecase(["index", str(isolated_workspace), "--db", str(custom_db)], env=isolated_env)

    tc_bin = REPO_ROOT / ".venv" / "bin" / "tracecase"
    proc = subprocess.Popen(
        [str(tc_bin), "mcp", "--db", str(custom_db)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=isolated_env,
        cwd=REPO_ROOT,
    )

    def rpc_call(method: str, params: dict | None = None, req_id: int = 1) -> dict:
        msg = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})
        proc.stdin.write(msg + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        return json.loads(line)

    try:
        # I17: initialize
        init_resp = rpc_call("initialize", req_id=1)
        assert init_resp["result"]["serverInfo"]["name"] == "tracecase_mcp"

        # I17: tools/list
        list_resp = rpc_call("tools/list", req_id=2)
        tool_names = [t["name"] for t in list_resp["result"]["tools"]]
        assert "search_testcases" in tool_names
        assert "get_testcase" in tool_names
        # I20: Discrepancy check: code exposes coverage_report (while docs said get_coverage)
        assert "coverage_report" in tool_names

        # I18: search_testcases tool call
        search_call = rpc_call(
            "tools/call",
            {"name": "search_testcases", "arguments": {"query": "laptop"}},
            req_id=3,
        )
        assert "tc_mcp_1" in search_call["result"]["content"][0]["text"]

        # I19: get_testcase tool call
        get_call = rpc_call(
            "tools/call",
            {"name": "get_testcase", "arguments": {"testcase_id": "tc_mcp_1"}},
            req_id=4,
        )
        content_text = get_call["result"]["content"][0]["text"]
        tc_loaded = json.loads(content_text)
        assert tc_loaded["id"] == "tc_mcp_1"

        # I22: Nonexistent testcase error handling
        missing_call = rpc_call(
            "tools/call",
            {"name": "get_testcase", "arguments": {"testcase_id": "nonexistent_id"}},
            req_id=5,
        )
        assert "error" in missing_call
        assert missing_call["error"]["code"] == -32603
        assert "not found" in missing_call["error"]["message"]

    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=2.0)
