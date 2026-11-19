"""Tests for Phase 7.5.2 - Test-to-Code Mapping.

Verifies:
1. TestReferenceExtractor extracting routes, selectors, actions, and API endpoints from TestCase.
2. CodebaseFileIndex scanning and indexing routes, selectors, and import dependencies.
3. Confidence hierarchy and evidence tracking:
   - exact_route (1.00)
   - exact_selector (0.95)
   - api_endpoint (0.90)
   - dependency_import (0.70)
4. Bidirectional graph navigation (test-to-files and file-to-tests).
5. Transitive impact propagation when an imported dependency changes.
6. Handling of removed / broken selectors with elevated risk.
7. SQLite persistence in test_code_mappings table.
8. REST API endpoints:
   - POST /api/intelligence/map
   - GET /api/intelligence/mappings
   - POST /api/intelligence/impact
9. CLI commands:
   - tracecase map
   - tracecase impact
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from tracecase.cli import app
from tracecase.intelligence.code_mapper import (
    CodebaseFileIndex,
    TestReferenceExtractor,
    TestToCodeGraph,
    TestToCodeMapper,
)
from tracecase.intelligence.models import (
    ChangedFile,
    DiffHunk,
    TestCodeMapping,
    TestCoverageProfile,
)
from tracecase.models import ElementInfo, NetworkRequest, Step, TestCase
from tracecase.ui.db import (
    clear_test_code_mappings,
    get_test_code_mappings,
    init_studio_db,
    save_test_code_mappings,
)
from tracecase.ui.server import create_app


@pytest.fixture
def sample_test_case() -> TestCase:
    """Construct a mock TestCase instance with rich step metadata."""
    return TestCase(
        id="tc_login_flow",
        name="User Authentication Test",
        start_url="https://app.example.com/login",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0",
        total_duration=5.0,
        total_steps=3,
        created_at=datetime.now(),
        steps=[
            Step(
                number=1,
                timestamp=datetime.now(),
                action_type="input",
                url="https://app.example.com/login",
                element=ElementInfo(
                    selector="#email-input",
                    tag_name="input",
                    bounding_box={"x": 10, "y": 20, "width": 100, "height": 30},
                    attributes={"id": "email-input", "data-testid": "auth-email-field", "class": "form-control input-lg"},
                ),
                input_value="user@example.com",
                description_short="Type email",
                description_detailed="Enter email into the email input field",
            ),
            Step(
                number=2,
                timestamp=datetime.now(),
                action_type="click",
                url="https://app.example.com/login",
                element=ElementInfo(
                    selector="button.btn-primary",
                    tag_name="button",
                    bounding_box={"x": 10, "y": 60, "width": 80, "height": 30},
                    attributes={"id": "submit-login", "data-testid": "login-submit-button", "class": "btn-primary font-bold"},
                ),
                network_requests=[
                    NetworkRequest(
                        method="POST",
                        url="https://app.example.com/api/v1/auth/token",
                        resource_type="fetch",
                    )
                ],
                description_short="Click submit",
                description_detailed="Click the login submit button to initiate authentication",
            ),
            Step(
                number=3,
                timestamp=datetime.now(),
                action_type="navigate",
                url="https://app.example.com/dashboard/overview",
                description_short="Navigate to dashboard",
                description_detailed="Browser redirects to dashboard overview after successful auth",
            ),
        ],
    )


def test_test_reference_extractor(sample_test_case: TestCase):
    """Test extracting behavioral footprint from TestCase steps and network requests."""
    profile = TestReferenceExtractor.extract_profile(sample_test_case)

    assert profile.testcase_id == "tc_login_flow"
    assert "/login" in profile.page_routes
    assert "/dashboard/overview" in profile.page_routes
    assert "/api/v1/auth/token" in profile.api_endpoints

    # Selectors
    assert "#email-input" in profile.selectors_used
    assert "auth-email-field" in profile.selectors_used
    assert ".form-control" in profile.selectors_used
    assert "#submit-login" in profile.selectors_used
    assert "login-submit-button" in profile.selectors_used

    # Step selector mapping
    assert 1 in profile.step_selector_map
    assert 2 in profile.step_selector_map


def test_codebase_file_index_extraction(tmp_path: Path):
    """Test CodebaseFileIndex extracting routes, selectors, symbols, and imports."""
    login_page = tmp_path / "Login.jsx"
    login_page.write_text(
        "import React from 'react';\n"
        "import { authClient } from '../api/authClient';\n"
        "\n"
        "export function LoginPage() {\n"
        "  return (\n"
        "    <div className='auth-card'>\n"
        "      <input id='email-input' data-testid='auth-email-field' />\n"
        "      <button id='submit-login' data-testid='login-submit-button'>Sign In</button>\n"
        "    </div>\n"
        "  );\n"
        "}\n"
    )

    idx = CodebaseFileIndex("src/pages/Login.jsx", login_page)
    idx.scan()

    assert "#email-input" in idx.declared_selectors
    assert "auth-email-field" in idx.declared_selectors
    assert "#submit-login" in idx.declared_selectors
    assert "LoginPage" in idx.declared_symbols
    assert "../api/authClient" in idx.imported_modules


def test_test_to_code_mapper_confidence_hierarchy(tmp_path: Path, sample_test_case: TestCase):
    """Test generating mappings and verifying confidence hierarchy."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # 1. Page file (contains exact route and selectors)
    login_file = src_dir / "Login.jsx"
    login_file.write_text(
        "import { authenticate } from './auth';\n"
        "export const routes = { path: '/login' };\n"
        "export function LoginView() {\n"
        "  return <input id='email-input' data-testid='auth-email-field' />;\n"
        "}\n"
    )

    # 2. Dependency file (imported by Login.jsx)
    auth_file = src_dir / "auth.js"
    auth_file.write_text(
        "export function authenticate() {\n"
        "  return fetch('/api/v1/auth/token');\n"
        "}\n"
    )

    # 3. Backend route file (handles API endpoint)
    api_file = src_dir / "auth_api.py"
    api_file.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/api/v1/auth/token')\n"
        "def token_endpoint(): pass\n"
    )

    mapper = TestToCodeMapper(repo_path=tmp_path, project_id="test_proj")
    graph = mapper.build_graph([sample_test_case], persist=False)

    mappings = graph.get_mappings_for_test("tc_login_flow")
    assert len(mappings) >= 4

    # Verify exact_route (1.00)
    route_maps = [m for m in mappings if m.relation_type == "exact_route"]
    assert len(route_maps) >= 1
    assert route_maps[0].confidence == 1.0
    assert route_maps[0].matched_entity == "/login"

    # Verify exact_selector (0.95)
    sel_maps = [m for m in mappings if m.relation_type == "exact_selector"]
    assert len(sel_maps) >= 1
    assert sel_maps[0].confidence == 0.95
    assert sel_maps[0].matched_entity in ("#email-input", "auth-email-field")

    # Verify api_endpoint (0.90)
    api_maps = [m for m in mappings if m.relation_type == "api_endpoint"]
    assert len(api_maps) >= 1
    assert api_maps[0].confidence == 0.90
    assert api_maps[0].matched_entity == "/api/v1/auth/token"

    # Verify dependency_import (0.70)
    dep_maps = [m for m in mappings if m.relation_type == "dependency_import"]
    assert len(dep_maps) >= 1
    assert dep_maps[0].confidence == 0.70
    assert dep_maps[0].file_path == "src/auth.js"


def test_transitive_dependency_impact(tmp_path: Path, sample_test_case: TestCase):
    """Test that modifying an imported module correctly impacts test cases covering the importer."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    (src_dir / "Login.jsx").write_text(
        "import { auth } from './auth';\n"
        "// path: '/login'\n"
        "<input id='email-input' />\n"
    )
    (src_dir / "auth.js").write_text("export const auth = {};\n")

    mapper = TestToCodeMapper(repo_path=tmp_path)
    graph = mapper.build_graph([sample_test_case], persist=False)

    # Simulate Git change on the imported auth.js file
    changed_file = ChangedFile(
        path="src/auth.js",
        change_type="modified",
        additions=5,
        deletions=2,
    )

    impacted = graph.get_impacted_tests([changed_file])
    assert len(impacted) == 1
    assert impacted[0].testcase_id == "tc_login_flow"
    assert "src/auth.js" in impacted[0].affected_files


def test_removed_selector_elevates_confidence_and_severity():
    """Test that deleting/removing a selector flags test as high risk."""
    graph = TestToCodeGraph()
    graph.add_mapping(
        TestCodeMapping(
            id="map_1",
            testcase_id="tc_1",
            testcase_name="Checkout Test",
            file_path="src/pages/Checkout.jsx",
            relation_type="exact_selector",
            matched_entity="#pay-now-btn",
            confidence=0.95,
        )
    )

    # Case 1: Selector modified
    mod_file = ChangedFile(
        path="src/pages/Checkout.jsx",
        change_type="modified",
        changed_selectors=["#pay-now-btn"],
        removed_selectors=[],
    )
    res_mod = graph.get_impacted_tests([mod_file])
    assert res_mod[0].max_confidence == 0.95
    assert any("modified" in r for r in res_mod[0].affected_reasons)

    # Case 2: Selector deleted / removed
    del_file = ChangedFile(
        path="src/pages/Checkout.jsx",
        change_type="modified",
        changed_selectors=["#pay-now-btn"],
        removed_selectors=["#pay-now-btn"],
    )
    res_del = graph.get_impacted_tests([del_file])
    assert res_del[0].max_confidence == 0.98  # Elevated confidence
    assert "DELETED / BROKEN" in res_del[0].primary_reason


def test_sqlite_mapping_persistence(tmp_path: Path):
    """Test saving, retrieving, and clearing mappings in SQLite studio.db."""
    db_file = tmp_path / "studio.db"
    init_studio_db(db_file)

    mappings = [
        TestCodeMapping(
            id="m_1",
            testcase_id="tc_alpha",
            testcase_name="Alpha Test",
            project_id="p1",
            file_path="src/Alpha.jsx",
            relation_type="exact_route",
            matched_entity="/alpha",
            confidence=1.0,
            evidence={"type": "route"},
        ),
        TestCodeMapping(
            id="m_2",
            testcase_id="tc_beta",
            testcase_name="Beta Test",
            project_id="p1",
            file_path="src/Beta.jsx",
            relation_type="exact_selector",
            matched_entity="#beta-id",
            confidence=0.95,
            evidence={"type": "selector"},
        ),
    ]

    # Save
    count = save_test_code_mappings(mappings, db_path=db_file)
    assert count == 2

    # Query by testcase_id
    rows_tc = get_test_code_mappings(testcase_id="tc_alpha", db_path=db_file)
    assert len(rows_tc) == 1
    assert rows_tc[0]["file_path"] == "src/Alpha.jsx"
    assert rows_tc[0]["confidence"] == 1.0

    # Query by file_path
    rows_f = get_test_code_mappings(file_path="src/Beta.jsx", db_path=db_file)
    assert len(rows_f) == 1
    assert rows_f[0]["testcase_id"] == "tc_beta"

    # Clear
    cleared = clear_test_code_mappings(project_id="p1", db_path=db_file)
    assert cleared == 2
    assert len(get_test_code_mappings(db_path=db_file)) == 0


def test_rest_api_mapping_and_impact_endpoints():
    """Test /api/intelligence/map, /api/intelligence/mappings, and /api/intelligence/impact endpoints."""
    app_instance = create_app()
    client = TestClient(app_instance)

    # 1. Trigger mapping
    r_map = client.post("/api/intelligence/map")
    assert r_map.status_code == 200
    data_map = r_map.json()
    assert data_map["status"] == "success"
    assert "total_mappings" in data_map

    # 2. Retrieve mappings
    r_list = client.get("/api/intelligence/mappings")
    assert r_list.status_code == 200
    assert isinstance(r_list.json(), list)

    # 3. Analyze impact
    r_impact = client.post("/api/intelligence/impact")
    assert r_impact.status_code == 200
    impact_data = r_impact.json()
    assert "changeset_summary" in impact_data
    assert "impacted_tests" in impact_data
    assert "total_impacted_tests" in impact_data


def test_cli_map_and_impact_commands():
    """Test CLI commands tracecase map and tracecase impact."""
    runner = CliRunner()

    # tracecase map
    res_map = runner.invoke(app, ["map"])
    assert res_map.exit_code == 0
    assert "Test-to-Code Mappings" in res_map.stdout
    assert "Successfully indexed" in res_map.stdout

    # tracecase impact
    res_impact = runner.invoke(app, ["impact"])
    assert res_impact.exit_code == 0
    assert "Code Change Impact Analysis" in res_impact.stdout

    # tracecase impact --json
    res_impact_json = runner.invoke(app, ["impact", "--json"])
    assert res_impact_json.exit_code == 0
    parsed = json.loads(res_impact_json.stdout)
    assert "total_impacted_tests" in parsed
    assert "impacted_tests" in parsed
