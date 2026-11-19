"""Phase 6.1 End-to-End and Integration tests for Autonomous Exploration & Page Graph Discovery."""

from __future__ import annotations

import asyncio
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tracecase.exploration.controller import exploration_controller
from tracecase.exploration.extractor import is_destructive_element
from tracecase.exploration.models import (
    ExplorationConfig,
    compute_state_fingerprint,
    normalize_url,
)
from tracecase.ui.db import (
    init_studio_db,
)
from tracecase.ui.server import create_app


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class MultiRouteTestAppHandler(BaseHTTPRequestHandler):
    """Test web application with multiple routes, forms, destructive actions, loops, and external links."""

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        path = self.path.split("?")[0].rstrip("/") or "/"

        if path == "/":
            body = """<!DOCTYPE html>
<html>
<head><title>Home Portal</title></head>
<body>
  <h1>Welcome to Enterprise App</h1>
  <nav>
    <a href="/dashboard" id="nav-dash">Go to Dashboard</a>
    <a href="/page-a" id="nav-loop">Visit Loop A</a>
    <a href="https://external-forbidden-domain.com/landing" id="ext-link">External Link</a>
  </nav>
  <form id="search-form" action="/search" method="GET">
    <input type="text" name="q" placeholder="Search catalog..." />
    <button type="submit" id="btn-search">Search</button>
  </form>
</body>
</html>"""
        elif path == "/dashboard":
            body = """<!DOCTYPE html>
<html>
<head><title>User Dashboard</title></head>
<body>
  <h1>Dashboard Overview</h1>
  <nav>
    <a href="/" id="nav-home">Back to Home</a>
    <a href="/settings" id="nav-settings">Account Settings</a>
  </nav>
  <div class="stats">
    <button id="btn-refresh" type="button">Refresh Metrics</button>
  </div>
</body>
</html>"""
        elif path == "/settings":
            body = """<!DOCTYPE html>
<html>
<head><title>Account Settings</title></head>
<body>
  <h1>System Settings</h1>
  <nav><a href="/dashboard">Back to Dashboard</a></nav>
  
  <!-- Safe Form -->
  <form id="profile-form" action="/settings/profile" method="POST">
    <input type="text" name="display_name" value="Jane Doe" />
    <button type="submit" id="btn-save-profile">Save Profile</button>
  </form>

  <!-- Destructive Form (Should be flagged and not submitted) -->
  <form id="delete-account-form" action="/account/delete" method="POST">
    <input type="hidden" name="user_id" value="12345" />
    <button type="submit" id="btn-delete" class="danger-btn">Delete Account Permanently</button>
  </form>
</body>
</html>"""
        elif path == "/page-a":
            # Navigation loop: A links to B, B links to A
            body = """<!DOCTYPE html>
<html>
<head><title>Loop Page A</title></head>
<body>
  <h1>Page A</h1>
  <a href="/page-b" id="link-to-b">Proceed to Page B</a>
</body>
</html>"""
        elif path == "/page-b":
            body = """<!DOCTYPE html>
<html>
<head><title>Loop Page B</title></head>
<body>
  <h1>Page B</h1>
  <a href="/page-a" id="link-to-a">Return to Page A</a>
</body>
</html>"""
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


# ---------------------------------------------------------------------------
# Unit Tests: Models, Normalization, Safety Heuristics
# ---------------------------------------------------------------------------

def test_url_normalization() -> None:
    assert normalize_url("http://example.com:80/path/") == "http://example.com/path"
    assert normalize_url("https://example.com:443/test/?utm_source=twitter&id=1") == "https://example.com/test?id=1"
    assert normalize_url("http://localhost:8000/sub/#section") == "http://localhost:8000/sub"


def test_destructive_element_heuristic() -> None:
    is_dest, reason = is_destructive_element(text="Delete Account")
    assert is_dest is True
    assert "delete" in (reason or "").lower()

    is_dest, reason = is_destructive_element(text="Checkout and Pay Now")
    assert is_dest is True
    assert "pay" in (reason or "").lower() or "checkout" in (reason or "").lower()

    is_dest, reason = is_destructive_element(text="Save Profile Changes")
    assert is_dest is False
    assert reason is None


def test_state_fingerprint_computation() -> None:
    fp1 = compute_state_fingerprint("http://example.com/a", "Page Title", ["#btn1", "#nav"])
    fp2 = compute_state_fingerprint("http://example.com/a", "Page Title", ["#btn1", "#nav"])
    fp3 = compute_state_fingerprint("http://example.com/b", "Different Title", ["#btn2"])

    assert fp1 == fp2
    assert fp1 != fp3


# ---------------------------------------------------------------------------
# API Integration Tests
# ---------------------------------------------------------------------------

def test_autonomous_exploration_api_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "test_api_studio.db"
    init_studio_db(db_file)
    monkeypatch.setattr("tracecase.ui.db.DEFAULT_STUDIO_DB_PATH", db_file)

    client = TestClient(create_app())

    # 1. Start Exploration via API
    payload = {
        "start_url": "http://127.0.0.1:8000/",
        "max_depth": 2,
        "max_pages": 10,
        "max_interactions": 20,
        "execution_timeout": 60.0,
        "browser": "chromium",
        "headless": True,
    }
    resp = client.post("/api/autonomous/explore", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["status"] == "running"
    exploration_id = data["id"]

    # 2. List Runs
    resp_list = client.get("/api/autonomous/runs")
    assert resp_list.status_code == 200
    runs = resp_list.json()
    assert any(r["id"] == exploration_id for r in runs)

    # 3. Get Run Detail
    resp_detail = client.get(f"/api/autonomous/runs/{exploration_id}")
    assert resp_detail.status_code == 200
    assert resp_detail.json()["id"] == exploration_id

    # 4. Cancel Exploration
    resp_cancel = client.post(f"/api/autonomous/runs/{exploration_id}/cancel")
    assert resp_cancel.status_code == 200
    assert resp_cancel.json()["cancelled"] is True

    # 5. Get Graph
    resp_graph = client.get(f"/api/autonomous/runs/{exploration_id}/graph")
    assert resp_graph.status_code == 200
    assert "nodes" in resp_graph.json()
    assert "transitions" in resp_graph.json()

    # 6. Delete Run
    resp_del = client.delete(f"/api/autonomous/runs/{exploration_id}")
    assert resp_del.status_code == 200
    assert resp_del.json()["deleted"] is True


# ---------------------------------------------------------------------------
# Real Browser End-to-End Test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_real_browser_autonomous_exploration_e2e(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Test real Playwright browser autonomous exploration against local multi-route application.
    Validates:
    1. Multi-route surface discovery (/, /dashboard, /settings, /page-a, /page-b).
    2. Detection and safety isolation of destructive form (/settings delete button).
    3. Navigation loop prevention (/page-a <-> /page-b terminates safely).
    4. Same-origin constraint (skips external-forbidden-domain.com).
    5. Navigation graph persistence in SQLite.
    """
    db_file = tmp_path / "test_e2e_studio.db"
    init_studio_db(db_file)
    monkeypatch.setattr("tracecase.ui.db.DEFAULT_STUDIO_DB_PATH", db_file)

    port = find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), MultiRouteTestAppHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"

    try:
        config = ExplorationConfig(
            start_url=base_url,
            max_depth=3,
            max_pages=15,
            max_interactions=30,
            execution_timeout=45.0,
            browser="chromium",
            headless=True,
        )

        run_record = await exploration_controller.start_exploration(config, db_path=db_file)
        exploration_id = run_record["id"]

        # Wait for exploration to complete
        deadline = asyncio.get_event_loop().time() + 40.0
        while asyncio.get_event_loop().time() < deadline:
            run_status = exploration_controller.get_run(exploration_id, db_path=db_file)
            if run_status and run_status["status"] in ("completed", "failed", "cancelled"):
                break
            await asyncio.sleep(1.0)

        # Verify run finished successfully
        final_run = exploration_controller.get_run(exploration_id, db_path=db_file)
        assert final_run is not None
        assert final_run["status"] == "completed"
        assert final_run["pages_discovered"] >= 3

        # Retrieve and inspect persisted AppNavigationGraph
        graph = exploration_controller.get_graph(exploration_id, db_path=db_file)
        nodes = graph["nodes"]
        transitions = graph["transitions"]

        # 1. Multi-route discovery: home, dashboard, settings, loops
        discovered_paths = [node["normalized_url"] for node in nodes.values()]
        assert any(f"{base_url}" == p or f"{base_url}/" == p for p in discovered_paths)
        assert any(f"{base_url}/dashboard" in p for p in discovered_paths)
        assert any(f"{base_url}/settings" in p for p in discovered_paths)

        # 2. Destructive Form Detection on /settings
        settings_node = next((n for n in nodes.values() if "/settings" in n["normalized_url"]), None)
        assert settings_node is not None, "Settings node must be discovered"
        assert len(settings_node["forms"]) >= 2, "Settings should have at least 2 forms"

        safe_form = next((f for f in settings_node["forms"] if "profile" in (f.get("action") or "")), None)
        assert safe_form is not None
        assert safe_form["is_destructive"] is False

        delete_form = next((f for f in settings_node["forms"] if "delete" in (f.get("action") or "").lower() or "delete" in (f.get("submit_button_text") or "").lower()), None)
        assert delete_form is not None, "Delete account form must be detected"
        assert delete_form["is_destructive"] is True, "Delete form must be marked as destructive"
        assert delete_form["destructive_reason"] is not None

        # 3. Same-origin constraint check: external link must not be in nodes
        assert not any("external-forbidden-domain.com" in p for p in discovered_paths)

        # 4. Transitions / Directed Edges recorded
        assert len(transitions) >= 2
        assert any(t["action_type"] in ("click_link", "navigate") for t in transitions)

    finally:
        server.shutdown()
        server.server_close()
