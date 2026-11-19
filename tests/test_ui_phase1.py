"""Unit and integration tests for Phase 1: Persistence, Projects, Suites, Executions, and APIs."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qa_auto.models import TestCase
from qa_auto.ui.db import (
    create_project,
    create_suite,
    delete_project,
    get_dashboard_metrics,
    get_project,
    get_settings,
    get_suite,
    init_studio_db,
    list_projects,
    list_suites,
    update_project,
    update_settings,
    update_suite,
)
from qa_auto.ui.server import create_app


@pytest.fixture
def test_db_path(temp_dir: Path) -> Path:
    p = temp_dir / "test_studio.db"
    init_studio_db(p)
    return p


@pytest.fixture
def sample_testcase_dir(temp_dir: Path, sample_testcase: TestCase) -> Path:
    case_dir = temp_dir / "sample_case"
    case_dir.mkdir(parents=True, exist_ok=True)
    tc_file = case_dir / "testcase.json"
    tc_file.write_text(sample_testcase.model_dump_json(indent=2), encoding="utf-8")
    return case_dir


@pytest.fixture
def client(test_db_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("qa_auto.ui.db.DEFAULT_STUDIO_DB_PATH", test_db_path)
    monkeypatch.setattr("qa_auto.ui.api.sync_all_testcases_from_disk", lambda **kwargs: 0)
    app = create_app()
    return TestClient(app)


def test_db_project_crud(test_db_path: Path) -> None:
    # Initial list has default project
    projs = list_projects(test_db_path)
    assert len(projs) >= 1
    assert projs[0]["id"] == "default_project"

    # Create new project
    created = create_project("E-Commerce Portal", "Storefront tests", db_path=test_db_path)
    assert created["name"] == "E-Commerce Portal"
    p_id = created["id"]

    # Get
    fetched = get_project(p_id, db_path=test_db_path)
    assert fetched is not None
    assert fetched["name"] == "E-Commerce Portal"

    # Update
    updated = update_project(p_id, name="Updated Portal", db_path=test_db_path)
    assert updated is not None
    assert updated["name"] == "Updated Portal"

    # Delete
    deleted = delete_project(p_id, db_path=test_db_path)
    assert deleted is True
    assert get_project(p_id, db_path=test_db_path) is None


def test_db_suite_crud(test_db_path: Path) -> None:
    suite = create_suite(
        name="Smoke Suite",
        project_id="default_project",
        testcase_ids=["tc_01", "tc_02"],
        db_path=test_db_path,
    )
    s_id = suite["id"]
    assert suite["name"] == "Smoke Suite"
    assert suite["total_cases"] == 2

    # Get suite
    fetched = get_suite(s_id, db_path=test_db_path)
    assert fetched is not None
    assert fetched["testcase_ids"] == ["tc_01", "tc_02"]

    # Update suite
    updated = update_suite(s_id, name="Updated Smoke Suite", db_path=test_db_path)
    assert updated is not None
    assert updated["name"] == "Updated Smoke Suite"

    # List suites
    suites = list_suites(db_path=test_db_path)
    assert len(suites) >= 1


def test_api_dashboard_metrics(client: TestClient) -> None:
    res = client.get("/api/dashboard/metrics")
    assert res.status_code == 200
    data = res.json()
    assert "total_testcases" in data
    assert "total_executions" in data
    assert "success_rate" in data
    assert "recent_executions" in data


def test_api_projects_endpoints(client: TestClient) -> None:
    # List
    res = client.get("/api/projects")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # Create
    create_res = client.post(
        "/api/projects",
        json={"name": "Billing Service", "description": "Payment flow tests"},
    )
    assert create_res.status_code == 200
    proj_data = create_res.json()
    p_id = proj_data["id"]
    assert proj_data["name"] == "Billing Service"

    # Get details
    get_res = client.get(f"/api/projects/{p_id}")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Billing Service"

    # Update
    put_res = client.put(f"/api/projects/{p_id}", json={"name": "Billing Service v2"})
    assert put_res.status_code == 200
    assert put_res.json()["name"] == "Billing Service v2"

    # Delete
    del_res = client.delete(f"/api/projects/{p_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True


def test_api_suites_endpoints(client: TestClient) -> None:
    # Create suite
    create_res = client.post(
        "/api/suites",
        json={"name": "Regression Suite", "testcase_ids": ["tc_1", "tc_2"]},
    )
    assert create_res.status_code == 200
    suite_id = create_res.json()["id"]

    # List
    list_res = client.get("/api/suites")
    assert list_res.status_code == 200
    assert any(s["id"] == suite_id for s in list_res.json())

    # Get
    get_res = client.get(f"/api/suites/{suite_id}")
    assert get_res.status_code == 200
    assert get_res.json()["total_cases"] == 2

    # Update
    put_res = client.put(f"/api/suites/{suite_id}", json={"name": "Regression Suite v2"})
    assert put_res.status_code == 200
    assert put_res.json()["name"] == "Regression Suite v2"

    # Delete
    del_res = client.delete(f"/api/suites/{suite_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True


def test_api_settings_endpoints(client: TestClient) -> None:
    get_res = client.get("/api/settings")
    assert get_res.status_code == 200
    settings = get_res.json()
    assert "theme" in settings

    put_res = client.put("/api/settings", json={"settings": {"theme": "light", "default_browser": "firefox"}})
    assert put_res.status_code == 200
    updated = put_res.json()
    assert updated["theme"] == "light"
    assert updated["default_browser"] == "firefox"


def test_api_storage_stats(client: TestClient) -> None:
    res = client.get("/api/storage/stats")
    assert res.status_code == 200
    data = res.json()
    assert "total_size_mb" in data
    assert "screenshots_count" in data


def test_api_mutations_generate(
    client: TestClient, sample_testcase_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tc_file = sample_testcase_dir / "testcase.json"
    data = json.loads(tc_file.read_text())
    case_id = data["id"]

    monkeypatch.setattr(
        "qa_auto.ui.service.find_testcase_files",
        lambda search_paths=None: [tc_file],
    )

    res = client.post(
        "/api/mutations/generate",
        json={"testcase_id": case_id, "strategies": ["inputs"], "limit": 5},
    )
    assert res.status_code == 200
    mutants = res.json()
    assert isinstance(mutants, list)


def test_api_ai_chat_heuristic(client: TestClient) -> None:
    res = client.post(
        "/api/ai/chat",
        json={"prompt": "How can I improve my login test case?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    assert len(data["reply"]) > 0


def test_api_websocket_connection(client: TestClient) -> None:
    with client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps({"action": "ping"}))
        resp = ws.receive_text()
        data = json.loads(resp)
        assert data.get("type") == "pong"


def test_api_create_and_delete_testcase(client: TestClient) -> None:
    # Create testcase
    res = client.post(
        "/api/testcases",
        json={
            "name": "Audit Test Flow",
            "start_url": "https://example.com/login",
            "browser": "chromium",
            "description": "Integration audit test",
        },
    )
    assert res.status_code == 200
    tc_data = res.json()
    assert tc_data["name"] == "Audit Test Flow"
    assert len(tc_data["steps"]) == 1
    tc_id = tc_data["id"]

    # Delete testcase
    del_res = client.delete(f"/api/testcases/{tc_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True


def test_api_record_stop(client: TestClient) -> None:
    # When no session is recording, returns idle/safe status
    res = client.post("/api/record/stop")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
