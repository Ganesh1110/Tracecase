"""Tests for Phase 7.5.1 - Git Change Intelligence.

Verifies:
1. Parsing unified diffs across added, modified, deleted, and renamed files.
2. Accurate line counts (additions, deletions) and hunk headers.
3. DOM & CSS selector extraction (data-testid, id, class, querySelector, locators).
4. Route & endpoint extraction (FastAPI, Flask, Express, React Router, Next.js).
5. Symbol extraction (Python AST functions/classes, JS/TS functions/components).
6. Import and dependency tracking.
7. Live git repository analysis (dirty state, branches, commits, untracked files).
8. REST API endpoint GET /api/intelligence/git-changes.
9. CLI tracecase changes command.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from tracecase.cli import app
from tracecase.intelligence.git_analyzer import GitChangeAnalyzer
from tracecase.intelligence.models import ChangedFile, GitChangeSet
from tracecase.ui.server import create_app

SAMPLE_REACT_DIFF = """diff --git a/frontend/src/pages/Checkout.jsx b/frontend/src/pages/Checkout.jsx
index 1234567..89abcdef 100644
--- a/frontend/src/pages/Checkout.jsx
+++ b/frontend/src/pages/Checkout.jsx
@@ -10,6 +10,14 @@ import { api } from '../services/api';
+import { CreditCard } from 'lucide-react';
+
+export function CheckoutForm() {
+  const handleSubmit = async () => {
+    await api.post('/api/checkout/pay');
+  };
+  return (
+    <div className="checkout-container" data-testid="checkout-form">
+      <input id="card-number" className="form-input text-sm" placeholder="Card" />
+      <button id="pay-btn" data-testid="pay-submit-btn" onClick={handleSubmit}>Pay Now</button>
+      <a href="/order-confirmation">Review Terms</a>
+    </div>
+  );
+}
"""

SAMPLE_PYTHON_FASTAPI_DIFF = """diff --git a/backend/routes/billing.py b/backend/routes/billing.py
new file mode 100644
--- /dev/null
+++ b/backend/routes/billing.py
@@ -0,0 +1,15 @@
+from fastapi import APIRouter
+from backend.services.payment import process_payment
+
+router = APIRouter(prefix="/api/billing")
+
+class PaymentRequest:
+    pass
+
+@router.post("/process-charge")
+async def charge_customer(req: PaymentRequest):
+    return process_payment(req)
+
+@router.get("/invoices")
+def list_invoices():
+    return []
"""


def test_parse_unified_diff_basic():
    """Test parsing additions, deletions, and hunk headers from unified diff text."""
    analyzer = GitChangeAnalyzer()
    files = analyzer.parse_unified_diff(SAMPLE_REACT_DIFF)

    assert len(files) == 1
    f = files[0]
    assert f.path == "frontend/src/pages/Checkout.jsx"
    assert f.change_type == "modified"
    assert f.additions == 14
    assert f.deletions == 0
    assert len(f.hunks) == 1
    assert f.hunks[0].new_start == 10
    assert f.hunks[0].new_lines == 14


def test_extract_selectors_from_react_diff():
    """Test extracting IDs, classes, and data-testids from JSX additions."""
    analyzer = GitChangeAnalyzer()
    change_set = analyzer.analyze_diff_text(SAMPLE_REACT_DIFF)

    file_obj = change_set.files[0]
    selectors = file_obj.changed_selectors

    # Should detect testids
    assert "checkout-form" in selectors or "#checkout-form" in selectors
    assert "pay-submit-btn" in selectors or "#pay-submit-btn" in selectors

    # Should detect IDs
    assert "#card-number" in selectors
    assert "#pay-btn" in selectors

    # Should detect classes
    assert ".checkout-container" in selectors or "checkout-container" in selectors
    assert ".form-input" in selectors or "form-input" in selectors


def test_extract_routes_and_endpoints():
    """Test extracting API routes and client paths from diffs."""
    analyzer = GitChangeAnalyzer()

    # 1. From React diff
    cs_react = analyzer.analyze_diff_text(SAMPLE_REACT_DIFF)
    react_routes = cs_react.files[0].changed_routes
    assert "/api/checkout/pay" in react_routes
    assert "/order-confirmation" in react_routes

    # 2. From Python FastAPI diff
    cs_py = analyzer.analyze_diff_text(SAMPLE_PYTHON_FASTAPI_DIFF)
    py_routes = cs_py.files[0].changed_routes
    assert "/process-charge" in py_routes
    assert "/invoices" in py_routes


def test_extract_symbols_functions_and_classes():
    """Test extracting function and class symbols from diffs."""
    analyzer = GitChangeAnalyzer()

    # React component function
    cs_react = analyzer.analyze_diff_text(SAMPLE_REACT_DIFF)
    react_file = cs_react.files[0]
    assert "CheckoutForm" in react_file.changed_functions

    # Python router functions and class
    cs_py = analyzer.analyze_diff_text(SAMPLE_PYTHON_FASTAPI_DIFF)
    py_file = cs_py.files[0]
    assert "charge_customer" in py_file.changed_functions
    assert "list_invoices" in py_file.changed_functions
    assert "PaymentRequest" in py_file.changed_classes


def test_extract_dependencies_and_imports():
    """Test extracting imported dependencies from modified diff lines."""
    analyzer = GitChangeAnalyzer()

    # React imports
    cs_react = analyzer.analyze_diff_text(SAMPLE_REACT_DIFF)
    assert "lucide-react" in cs_react.files[0].dependencies

    # Python imports
    cs_py = analyzer.analyze_diff_text(SAMPLE_PYTHON_FASTAPI_DIFF)
    deps = cs_py.files[0].dependencies
    assert any("fastapi" in d for d in deps)
    assert any("backend.services.payment" in d for d in deps)


def test_nextjs_filesystem_routing():
    """Test route derivation from Next.js pages and app router conventions."""
    analyzer = GitChangeAnalyzer()
    diff_next = """diff --git a/src/pages/auth/login.jsx b/src/pages/auth/login.jsx
new file mode 100644
--- /dev/null
+++ b/src/pages/auth/login.jsx
@@ -0,0 +1,5 @@
+export default function LoginPage() {
+  return <div>Login</div>;
+}
+"""
    cs = analyzer.analyze_diff_text(diff_next)
    assert "/auth/login" in cs.files[0].changed_routes
    assert "/auth/login" in cs.summary.total_changed_routes


@pytest.fixture
def temp_git_repo(tmp_path: Path):
    """Create a temporary initialized git repository."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    # git init
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tracecase Test"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "test@tracecase.dev"], cwd=str(repo_dir), check=True)

    # Initial commit
    file1 = repo_dir / "app.py"
    file1.write_text("def hello():\n    return 'hello'\n")
    subprocess.run(["git", "add", "app.py"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True)

    return repo_dir


def test_live_repo_git_intelligence(temp_git_repo: Path):
    """Test live git analysis of working directory changes, commit info, and untracked files."""
    analyzer = GitChangeAnalyzer(temp_git_repo)

    # 1. Clean state
    cs_clean = analyzer.analyze_repo()
    assert cs_clean.is_dirty is False
    assert len(cs_clean.files) == 0

    # 2. Modify existing file
    app_py = temp_git_repo / "app.py"
    app_py.write_text("def hello():\n    return 'hello world'\n\ndef goodbye():\n    return 'bye'\n")

    # 3. Add an untracked JSX file
    comp_jsx = temp_git_repo / "Button.jsx"
    comp_jsx.write_text(
        "export function ActionButton() {\n"
        "  return <button id='action-btn' data-testid='submit-action'>Click</button>;\n"
        "}\n"
    )

    cs_dirty = analyzer.analyze_repo()
    assert cs_dirty.is_dirty is True
    assert cs_dirty.current_commit is not None
    assert len(cs_dirty.files) == 2

    # Verify semantic extractions across live dirty repo
    paths = {f.path for f in cs_dirty.files}
    assert "app.py" in paths
    assert "Button.jsx" in paths

    all_selectors = cs_dirty.summary.total_changed_selectors
    assert "submit-action" in all_selectors or "#submit-action" in all_selectors
    assert "#action-btn" in all_selectors

    all_symbols = cs_dirty.summary.total_changed_symbols
    assert "goodbye" in all_symbols
    assert "ActionButton" in all_symbols


def test_rest_api_git_changes_endpoint():
    """Test GET /api/intelligence/git-changes REST endpoint."""
    app_instance = create_app()
    client = TestClient(app_instance)

    res = client.get("/api/intelligence/git-changes")
    assert res.status_code == 200
    data = res.json()
    assert "repo_path" in data
    assert "summary" in data
    assert "files" in data
    assert "total_files_changed" in data["summary"]


def test_cli_changes_command():
    """Test tracecase changes CLI command with table output and JSON output."""
    runner = CliRunner()

    # Table output
    res_table = runner.invoke(app, ["changes"])
    assert res_table.exit_code == 0
    assert "Git Change Intelligence" in res_table.stdout

    # JSON output
    res_json = runner.invoke(app, ["changes", "--json"])
    assert res_json.exit_code == 0
    parsed = json.loads(res_json.stdout)
    assert "repo_path" in parsed
    assert "summary" in parsed
