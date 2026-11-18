# Corpus Store, Search, and Local MCP Server Plan (Phase 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a local-first SQLite/FTS5 test case corpus store (`qa_auto.index`), search and coverage analysis, and a stdio Model Context Protocol (MCP) server (`qa_auto.mcp`) to enable coding assistants (Antigravity, Cursor, Claude Code) to discover and interact with recorded test cases.

**Architecture:**
- `qa_auto.index`: `store.py` (SQLite schema + FTS5), `search.py` (BM25 search, coverage, dedupe).
- `qa_auto.mcp`: `server.py` (JSON-RPC 2.0 stdio MCP server exposing `search_testcases`, `get_testcase`, `coverage_report`, `analyze_testcase`, `replay_testcase`).
- CLI gains: `index`, `search`, `coverage`, and `mcp`.

**Tech Stack:** Python 3.13, sqlite3 with FTS5, Pydantic v2, Typer, Rich, pytest.

## Global Constraints

- Python `>=3.13`, Ruff `target-version = "py313"`, line length 100.
- Offline by default: `~/.qa_auto/corpus.db` (or `--db` / `QA_AUTO_DB`). Zero external databases.
- `testcase.json` schema is unchanged.
- MCP server operates via stdio following the Model Context Protocol JSON-RPC specification.
- Replay from MCP is disabled unless `QA_AUTO_MCP_ALLOW_REPLAY=1` is explicitly set.
- Ruff rules: `E`, `F`, `I`, `UP`, `B`, `SIM`. Type annotations required (`disallow_untyped_defs`).

---

### Task 1: Corpus SQLite & FTS5 Store

**Files:**
- Create: `src/qa_auto/index/__init__.py`
- Create: `src/qa_auto/index/store.py`
- Test: `tests/test_corpus_store.py`

**Interfaces:**
- Produces:
  - `init_db(db_path: Path) -> sqlite3.Connection`
  - `index_testcase(testcase: TestCase, file_path: Path, db_path: Path) -> None`
  - `index_directory(directory: Path, db_path: Path) -> int`

- [ ] **Step 1: Write failing store tests**

Create `tests/test_corpus_store.py`:

```python
"""Tests for Corpus SQLite and FTS5 store."""

from datetime import datetime
from pathlib import Path

from qa_auto.index.store import index_directory, index_testcase, init_db
from qa_auto.models import ElementInfo, NetworkRequest, Step, TestCase


def _testcase(tc_id: str, name: str, url: str) -> TestCase:
    step = Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=ElementInfo(
            selector="#submit-btn",
            xpath="//*[@id='submit-btn']",
            tag_name="button",
            text="Submit Order",
            attributes={"id": "submit-btn"},
            bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
        ),
        description_short="Click submit button",
        description_detailed="User clicked submit button to place order",
        network_requests=[
            NetworkRequest(
                method="POST",
                url=f"{url}/api/checkout",
                status=200,
                resource_type="fetch",
                timing=10.0,
                timestamp=datetime(2025, 1, 1, 12, 0, 0),
            )
        ],
    )
    return TestCase(
        id=tc_id,
        name=name,
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url=url,
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=[step],
        console_logs=[],
        network_requests=[],
        page_errors=[],
        total_duration=1.0,
        total_steps=1,
    )


def test_init_db_creates_tables(temp_dir: Path) -> None:
    db_path = temp_dir / "corpus.db"
    con = init_db(db_path)
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cur.fetchall()}

    assert "testcases" in tables
    assert "steps_fts" in tables
    con.close()


def test_index_testcase_inserts_and_fts_indexes(temp_dir: Path) -> None:
    db_path = temp_dir / "corpus.db"
    tc = _testcase("tc_1", "Order Checkout", "https://shop.example.com")
    json_path = temp_dir / "testcase.json"
    json_path.write_text(tc.model_dump_json(), encoding="utf-8")

    index_testcase(tc, json_path, db_path)

    con = init_db(db_path)
    cur = con.cursor()
    cur.execute("SELECT id, name FROM testcases WHERE id = 'tc_1'")
    assert cur.fetchone() == ("tc_1", "Order Checkout")

    cur.execute("SELECT testcase_id, description FROM steps_fts WHERE steps_fts MATCH 'checkout'")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "tc_1"
    con.close()


def test_index_directory_indexes_all_cases(temp_dir: Path) -> None:
    db_path = temp_dir / "corpus.db"
    dir_a = temp_dir / "test_a"
    dir_b = temp_dir / "test_b"
    dir_a.mkdir()
    dir_b.mkdir()

    tc_a = _testcase("tc_a", "Flow A", "https://a.com")
    tc_b = _testcase("tc_b", "Flow B", "https://b.com")

    (dir_a / "testcase.json").write_text(tc_a.model_dump_json(), encoding="utf-8")
    (dir_b / "testcase.json").write_text(tc_b.model_dump_json(), encoding="utf-8")

    count = index_directory(temp_dir, db_path)
    assert count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_corpus_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'qa_auto.index'`.

- [ ] **Step 3: Implement `src/qa_auto/index/store.py`**

Create `src/qa_auto/index/__init__.py` and `src/qa_auto/index/store.py`:

```python
"""SQLite and FTS5 test case corpus storage."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from qa_auto.models import TestCase

DEFAULT_DB_PATH = Path.home() / ".qa_auto" / "corpus.db"


def init_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Initialize SQLite database with relational and FTS5 schema."""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    with con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS testcases (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                start_url TEXT NOT NULL,
                browser TEXT NOT NULL,
                created_at TEXT NOT NULL,
                total_steps INTEGER NOT NULL,
                total_duration REAL NOT NULL,
                file_path TEXT NOT NULL,
                indexed_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS steps_fts USING fts5(
                testcase_id UNINDEXED,
                step_number UNINDEXED,
                action_type,
                selector,
                description,
                url,
                network_urls,
                console_logs
            )
            """
        )
    return con


def index_testcase(testcase: TestCase, file_path: Path, db_path: Path | str | None = None) -> None:
    """Index a single test case into relational table and FTS5 index."""
    con = init_db(db_path)
    now = datetime.now().isoformat()

    with con:
        con.execute("DELETE FROM testcases WHERE id = ?", (testcase.id,))
        con.execute("DELETE FROM steps_fts WHERE testcase_id = ?", (testcase.id,))

        con.execute(
            """
            INSERT INTO testcases (
                id, name, start_url, browser, created_at,
                total_steps, total_duration, file_path, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                testcase.id,
                testcase.name,
                testcase.start_url,
                testcase.browser,
                testcase.created_at.isoformat(),
                testcase.total_steps,
                testcase.total_duration,
                str(Path(file_path).resolve()),
                now,
            ),
        )

        for step in testcase.steps:
            selector = step.element.selector if step.element else ""
            net_urls = " ".join(r.url for r in step.network_requests)
            logs = " ".join(l.message for l in step.console_logs)

            con.execute(
                """
                INSERT INTO steps_fts (
                    testcase_id, step_number, action_type,
                    selector, description, url, network_urls, console_logs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    testcase.id,
                    step.number,
                    step.action_type,
                    selector,
                    f"{step.description_short} {step.description_detailed}",
                    step.url or "",
                    net_urls,
                    logs,
                ),
            )
    con.close()


def index_directory(directory: Path, db_path: Path | str | None = None) -> int:
    """Recursively search for and index testcase.json files in directory."""
    directory = Path(directory)
    count = 0
    for path in directory.rglob("testcase.json"):
        try:
            tc = TestCase.model_validate_json(path.read_text(encoding="utf-8"))
            index_testcase(tc, path, db_path=db_path)
            count += 1
        except Exception:
            continue
    return count
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_corpus_store.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run lint and types**

Run: `ruff check src/qa_auto/index tests/test_corpus_store.py && mypy src/qa_auto/index --ignore-missing-imports`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/qa_auto/index/ tests/test_corpus_store.py
git commit -m "Add SQLite and FTS5 corpus store"
```

---

### Task 2: Search, Coverage & Deduplication

**Files:**
- Create: `src/qa_auto/index/search.py`
- Test: `tests/test_corpus_search.py`

**Interfaces:**
- Produces:
  - `search_testcases(query: str, db_path: Path | str | None = None, limit: int = 10) -> list[dict[str, Any]]`
  - `get_coverage_report(db_path: Path | str | None = None) -> dict[str, Any]`

- [ ] **Step 1: Write failing search & coverage tests**

Create `tests/test_corpus_search.py`:

```python
"""Tests for corpus search and coverage analysis."""

from datetime import datetime
from pathlib import Path

from qa_auto.index.search import get_coverage_report, search_testcases
from qa_auto.index.store import index_testcase
from qa_auto.models import ElementInfo, NetworkRequest, Step, TestCase


def _testcase(tc_id: str, name: str, url: str, selector: str = "#cart") -> TestCase:
    step = Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=ElementInfo(
            selector=selector,
            xpath=f"//*[@id='{selector.lstrip('#')}']",
            tag_name="button",
            text="Checkout",
            attributes={},
            bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
        ),
        description_short="Click cart",
        description_detailed="Proceed to checkout flow",
        network_requests=[
            NetworkRequest(
                method="GET",
                url=f"{url}/api/cart",
                status=200,
                resource_type="fetch",
                timing=12.0,
                timestamp=datetime(2025, 1, 1, 12, 0, 0),
            )
        ],
    )
    return TestCase(
        id=tc_id,
        name=name,
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url=url,
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=[step],
        console_logs=[],
        network_requests=[],
        page_errors=[],
        total_duration=1.0,
        total_steps=1,
    )


def test_search_testcases_matches_query(temp_dir: Path) -> None:
    db_path = temp_dir / "corpus.db"
    tc = _testcase("tc_checkout", "Cart Checkout Flow", "https://shop.com/cart")
    index_testcase(tc, temp_dir / "tc.json", db_path)

    results = search_testcases("checkout", db_path=db_path)

    assert len(results) == 1
    assert results[0]["id"] == "tc_checkout"
    assert results[0]["name"] == "Cart Checkout Flow"
    assert "snippet" in results[0]


def test_coverage_report_summarizes_endpoints_and_urls(temp_dir: Path) -> None:
    db_path = temp_dir / "corpus.db"
    tc1 = _testcase("tc_1", "Cart 1", "https://shop.com/cart")
    tc2 = _testcase("tc_2", "Cart 2", "https://shop.com/cart")  # duplicate URL
    index_testcase(tc1, temp_dir / "tc1.json", db_path)
    index_testcase(tc2, temp_dir / "tc2.json", db_path)

    report = get_coverage_report(db_path=db_path)

    assert report["total_testcases"] == 2
    assert "https://shop.com/cart" in report["start_urls"]
    assert "https://shop.com/api/cart" in report["network_endpoints"]
    assert len(report["potential_duplicates"]) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_corpus_search.py -v`
Expected: FAIL with `ImportError: cannot import name 'search_testcases'`.

- [ ] **Step 3: Implement `src/qa_auto/index/search.py`**

Create `src/qa_auto/index/search.py`:

```python
"""Search and test coverage analytics over the corpus store."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from qa_auto.index.store import init_db


def search_testcases(
    query: str,
    db_path: Path | str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search test cases using FTS5 BM25 match."""
    con = init_db(db_path)
    sanitized = query.replace('"', '""').strip()
    match_query = f'"{sanitized}"' if " " in sanitized else sanitized

    cur = con.cursor()
    cur.execute(
        """
        SELECT
            t.id,
            t.name,
            t.start_url,
            t.file_path,
            snippet(steps_fts, 4, '[b]', '[/b]', '...', 10) as match_snippet,
            bm25(steps_fts) as rank
        FROM steps_fts
        JOIN testcases t ON t.id = steps_fts.testcase_id
        WHERE steps_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (match_query, limit),
    )

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in cur.fetchall():
        tc_id = row[0]
        if tc_id in seen:
            continue
        seen.add(tc_id)
        results.append(
            {
                "id": tc_id,
                "name": row[1],
                "start_url": row[2],
                "file_path": row[3],
                "snippet": row[4],
                "score": round(abs(row[5]), 3),
            }
        )
    con.close()
    return results


def get_coverage_report(db_path: Path | str | None = None) -> dict[str, Any]:
    """Analyze corpus coverage across domains, start URLs, and network endpoints."""
    con = init_db(db_path)
    cur = con.cursor()

    cur.execute("SELECT id, name, start_url, file_path FROM testcases")
    testcases = cur.fetchall()

    start_urls: dict[str, int] = {}
    domains: dict[str, int] = {}
    for _, _, start_url, _ in testcases:
        start_urls[start_url] = start_urls.get(start_url, 0) + 1
        domain = urlparse(start_url).netloc
        if domain:
            domains[domain] = domains.get(domain, 0) + 1

    cur.execute("SELECT network_urls FROM steps_fts WHERE network_urls != ''")
    endpoints: dict[str, int] = {}
    for (net_urls,) in cur.fetchall():
        for url in net_urls.split():
            clean_url = url.split("?")[0]
            endpoints[clean_url] = endpoints.get(clean_url, 0) + 1

    potential_duplicates = [
        {"url": url, "count": count} for url, count in start_urls.items() if count > 1
    ]

    con.close()
    return {
        "total_testcases": len(testcases),
        "unique_domains": len(domains),
        "domains": domains,
        "start_urls": start_urls,
        "network_endpoints": endpoints,
        "potential_duplicates": potential_duplicates,
    }
```

- [ ] **Step 4: Run search tests to verify they pass**

Run: `pytest tests/test_corpus_search.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run lint and types**

Run: `ruff check src/qa_auto/index tests/test_corpus_search.py && mypy src/qa_auto/index --ignore-missing-imports`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/qa_auto/index/ tests/test_corpus_search.py
git commit -m "Add corpus search and coverage analytics"
```

---

### Task 3: CLI Commands: `index`, `search`, and `coverage`

**Files:**
- Modify: `src/qa_auto/cli.py`
- Test: `tests/test_cli_corpus.py`

**Interfaces:**
- Produces: CLI commands `index`, `search`, `coverage`.

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli_corpus.py`:

```python
"""Tests for corpus CLI commands: index, search, coverage."""

from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from qa_auto.cli import app
from qa_auto.models import Step, TestCase

runner = CliRunner()


def _write_testcase(path: Path, name: str, url: str) -> Path:
    testcase = TestCase(
        id="tc_cli_corpus",
        name=name,
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url=url,
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
    path.write_text(testcase.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_index_and_search_cli_flow(temp_dir: Path) -> None:
    db_file = temp_dir / "test_corpus.db"
    tc_dir = temp_dir / "records"
    tc_dir.mkdir()
    _write_testcase(tc_dir / "testcase.json", "User Payment Flow", "https://checkout.com")

    # 1. Index
    res_index = runner.invoke(app, ["index", str(tc_dir), "--db", str(db_file)])
    assert res_index.exit_code == 0
    assert "Indexed 1 test case" in res_index.stdout

    # 2. Search
    res_search = runner.invoke(app, ["search", "Payment", "--db", str(db_file)])
    assert res_search.exit_code == 0
    assert "User Payment Flow" in res_search.stdout

    # 3. Coverage
    res_cov = runner.invoke(app, ["coverage", "--db", str(db_file)])
    assert res_cov.exit_code == 0
    assert "checkout.com" in res_cov.stdout
```

- [ ] **Step 2: Run CLI tests to verify they fail**

Run: `pytest tests/test_cli_corpus.py -v`
Expected: FAIL because commands are not registered.

- [ ] **Step 3: Register `index`, `search`, and `coverage` commands in `src/qa_auto/cli.py`**

Add commands to `src/qa_auto/cli.py`.

- [ ] **Step 4: Run CLI tests to verify they pass**

Run: `pytest tests/test_cli_corpus.py -v`
Expected: 1 passed.

- [ ] **Step 5: Run lint and types**

Run: `ruff check src/qa_auto/index src/qa_auto/cli.py tests/test_cli_corpus.py && mypy src/qa_auto --ignore-missing-imports`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/qa_auto/cli.py tests/test_cli_corpus.py
git commit -m "Add index, search, and coverage CLI commands"
```

---

### Task 4: Local stdio MCP Server (`qa_auto.mcp`) and `qa_auto mcp` CLI

**Files:**
- Create: `src/qa_auto/mcp/__init__.py`
- Create: `src/qa_auto/mcp/server.py`
- Modify: `src/qa_auto/cli.py`
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Produces:
  - `MCPServer(db_path=None)`: JSON-RPC 2.0 stdio handler.
  - CLI command: `qa_auto mcp [--db <path>]`.

- [ ] **Step 1: Write failing MCP server tests**

Create `tests/test_mcp_server.py`:

```python
"""Tests for stdio Model Context Protocol (MCP) server."""

import json
from pathlib import Path

import pytest

from qa_auto.index.store import index_testcase
from qa_auto.mcp.server import MCPServer
from qa_auto.models import TestCase
from datetime import datetime


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'qa_auto.mcp'`.

- [ ] **Step 3: Implement `src/qa_auto/mcp/server.py` and register `mcp` in `src/qa_auto/cli.py`**

- [ ] **Step 4: Run MCP tests to verify they pass**

Run: `pytest tests/test_mcp_server.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run lint and types**

Run: `ruff check src/qa_auto/mcp src/qa_auto/cli.py tests/test_mcp_server.py && mypy src/qa_auto --ignore-missing-imports`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/qa_auto/mcp/ src/qa_auto/cli.py tests/test_mcp_server.py
git commit -m "Add stdio MCP server for agent integration"
```

---

### Task 5: Documentation and Phase verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document `index`, `search`, `coverage`, and `mcp` commands in `README.md`**
- [ ] **Step 2: Run full test suite and quality gate**
- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document corpus commands and MCP server"
```
