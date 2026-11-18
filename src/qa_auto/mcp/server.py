"""Local stdio Model Context Protocol (MCP) server for qa_auto."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from qa_auto.index.search import get_coverage_report, search_testcases
from qa_auto.index.store import DEFAULT_DB_PATH, init_db


class MCPServer:
    """Stdio-based Model Context Protocol server exposing test corpus to LLM agents."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH

    async def handle_request(self, req: dict[str, Any]) -> dict[str, Any]:
        """Handle a single JSON-RPC 2.0 request."""
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {}) or {}

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                    },
                    "serverInfo": {
                        "name": "qa_auto_mcp",
                        "version": "0.1.0",
                    },
                }
                return {"jsonrpc": "2.0", "id": req_id, "result": result}

            if method == "notifications/initialized":
                return {"jsonrpc": "2.0", "id": req_id, "result": {}}

            if method == "tools/list":
                tools = [
                    {
                        "name": "search_testcases",
                        "description": (
                            "Search indexed test cases by keyword, selector, URL, or action description using SQLite FTS5."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search query string",
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "Maximum number of results to return",
                                    "default": 10,
                                },
                            },
                            "required": ["query"],
                        },
                    },
                    {
                        "name": "get_testcase",
                        "description": "Retrieve complete recorded test case JSON by its ID.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "testcase_id": {
                                    "type": "string",
                                    "description": "ID of the test case",
                                },
                            },
                            "required": ["testcase_id"],
                        },
                    },
                    {
                        "name": "coverage_report",
                        "description": (
                            "Get analytics report on corpus coverage including domains, start URLs, and endpoints."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                ]
                return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}

            if method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {}) or {}
                result_content = await self._execute_tool(tool_name, arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result_content, indent=2),
                            }
                        ]
                    },
                }

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {e}",
                },
            }

    async def _execute_tool(self, name: str | None, arguments: dict[str, Any]) -> Any:
        if name == "search_testcases":
            query = arguments.get("query", "")
            limit = int(arguments.get("limit", 10))
            return search_testcases(query=query, limit=limit, db_path=self.db_path)

        if name == "get_testcase":
            tc_id = arguments.get("testcase_id", "")
            con = init_db(self.db_path)
            cur = con.cursor()
            cur.execute("SELECT file_path FROM testcases WHERE id = ?", (tc_id,))
            row = cur.fetchone()
            con.close()
            if not row:
                raise ValueError(f"Testcase '{tc_id}' not found in corpus.")
            file_path = Path(row[0])
            if not file_path.exists():
                raise FileNotFoundError(f"Testcase file '{file_path}' does not exist.")
            return json.loads(file_path.read_text(encoding="utf-8"))

        if name == "coverage_report":
            return get_coverage_report(db_path=self.db_path)

        raise ValueError(f"Unknown tool: {name}")

    async def run_stdio(self) -> None:
        """Run stdio loop reading JSON-RPC requests from stdin and writing to stdout."""
        loop = asyncio.get_running_loop()

        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            try:
                req = json.loads(line)
            except Exception:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()
                continue

            resp = await self.handle_request(req)
            if resp:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
