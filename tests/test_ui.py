"""Tests for QA Auto Web Studio (FastAPI server & service layer)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from qa_auto.models import TestCase
from qa_auto.ui.server import create_app

runner = CliRunner()


@pytest.fixture
def client() -> TestClient:
    """Create a FastAPI test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def sample_testcase_dir(temp_dir: Path, sample_testcase: TestCase) -> Path:
    """Create a mock testcase directory with testcase.json and screenshot."""
    case_dir = temp_dir / "sample_case"
    case_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir = case_dir / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)

    # Write a valid dummy PNG screenshot
    from PIL import Image

    mock_screenshot = screenshots_dir / "001_click_button.png"
    Image.new("RGB", (100, 100), color=(10, 20, 30)).save(mock_screenshot)

    # Update step screenshot path to relative
    sample_testcase.steps[0].screenshot_path = Path("screenshots/001_click_button.png")
    tc_file = case_dir / "testcase.json"
    tc_file.write_text(sample_testcase.model_dump_json(indent=2), encoding="utf-8")

    return case_dir


def test_health_check(client: TestClient) -> None:
    """Test health endpoint."""
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "qa_auto_studio"}


def test_index_page(client: TestClient) -> None:
    """Test root HTML endpoint."""
    res = client.get("/")
    assert res.status_code == 200
    assert "QA AUTO" in res.text


def test_list_testcases(
    client: TestClient, sample_testcase_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test listing testcases from search paths."""
    monkeypatch.setattr(
        "qa_auto.ui.service.find_testcase_files",
        lambda search_paths=None: [sample_testcase_dir / "testcase.json"],
    )

    res = client.get("/api/testcases")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert data[0]["name"] == "User Login Flow"
    assert data[0]["total_steps"] == 2


def test_get_testcase_details(
    client: TestClient, sample_testcase_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test retrieving full testcase details."""
    tc_file = sample_testcase_dir / "testcase.json"
    monkeypatch.setattr(
        "qa_auto.ui.service.find_testcase_files",
        lambda search_paths=None: [tc_file],
    )

    data = json.loads(tc_file.read_text())
    case_id = data["id"]

    res = client.get(f"/api/testcases/{case_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == case_id
    assert len(body["steps"]) == 2
    assert body["steps"][0]["action_type"] == "click"


def test_get_testcase_not_found(client: TestClient) -> None:
    """Test 404 for unknown testcase."""
    res = client.get("/api/testcases/non_existent_id_999999")
    assert res.status_code == 404


def test_get_screenshot(
    client: TestClient, sample_testcase_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test retrieving step screenshot."""
    tc_file = sample_testcase_dir / "testcase.json"
    monkeypatch.setattr(
        "qa_auto.ui.service.find_testcase_files",
        lambda search_paths=None: [tc_file],
    )

    data = json.loads(tc_file.read_text())
    case_id = data["id"]

    res = client.get(f"/api/testcases/{case_id}/screenshots/001_click_button.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"


def test_codegen_endpoint(
    client: TestClient, sample_testcase_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test generating pytest script."""
    tc_file = sample_testcase_dir / "testcase.json"
    monkeypatch.setattr(
        "qa_auto.ui.service.find_testcase_files",
        lambda search_paths=None: [tc_file],
    )

    data = json.loads(tc_file.read_text())
    case_id = data["id"]

    res = client.post(f"/api/testcases/{case_id}/codegen")
    assert res.status_code == 200
    code = res.json()["code"]
    assert "async def test_" in code
    assert "page.locator" in code


def test_record_status_idle(client: TestClient) -> None:
    """Test recording status endpoint when idle."""
    res = client.get("/api/record/status")
    assert res.status_code == 200
    assert "status" in res.json()


def test_ui_cli_command() -> None:
    """Test that qa_auto ui is invokable with --help."""
    from qa_auto.cli import app

    result = runner.invoke(app, ["ui", "--help"])
    assert result.exit_code == 0
    assert "Launch the QA Auto Studio" in result.stdout


def test_update_step(
    client: TestClient, sample_testcase_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test updating step fields via API."""
    tc_file = sample_testcase_dir / "testcase.json"
    monkeypatch.setattr(
        "qa_auto.ui.service.find_testcase_files",
        lambda search_paths=None: [tc_file],
    )
    case_id = json.loads(tc_file.read_text())["id"]

    res = client.put(
        f"/api/testcases/{case_id}/steps/1",
        json={
            "action_type": "input",
            "input_value": "secret123",
            "description_short": "Enter secret password",
            "element": {"selector": "input#pass"},
        },
    )
    assert res.status_code == 200
    updated = res.json()
    step1 = updated["steps"][0]
    assert step1["action_type"] == "input"
    assert step1["input_value"] == "secret123"
    assert step1["element"]["selector"] == "input#pass"


def test_reorder_step(
    client: TestClient, sample_testcase_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test reordering steps up and down."""
    tc_file = sample_testcase_dir / "testcase.json"
    monkeypatch.setattr(
        "qa_auto.ui.service.find_testcase_files",
        lambda search_paths=None: [tc_file],
    )
    case_id = json.loads(tc_file.read_text())["id"]

    # Reorder step 1 down
    res = client.post(
        f"/api/testcases/{case_id}/steps/1/reorder",
        json={"direction": "down"},
    )
    assert res.status_code == 200
    updated = res.json()
    assert updated["steps"][0]["number"] == 1
    assert updated["steps"][1]["number"] == 2


def test_add_and_delete_step(
    client: TestClient, sample_testcase_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test adding a new step and deleting it."""
    tc_file = sample_testcase_dir / "testcase.json"
    monkeypatch.setattr(
        "qa_auto.ui.service.find_testcase_files",
        lambda search_paths=None: [tc_file],
    )
    case_id = json.loads(tc_file.read_text())["id"]

    # Add step
    res = client.post(
        f"/api/testcases/{case_id}/steps",
        json={
            "action_type": "click",
            "selector": "button#submit-form",
            "description_short": "Submit form",
        },
    )
    assert res.status_code == 200
    updated = res.json()
    assert updated["total_steps"] == 3
    assert updated["steps"][2]["element"]["selector"] == "button#submit-form"

    # Delete newly added step 3
    del_res = client.delete(f"/api/testcases/{case_id}/steps/3")
    assert del_res.status_code == 200
    assert del_res.json()["total_steps"] == 2


def test_add_and_delete_assertion(
    client: TestClient, sample_testcase_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test attaching a custom assertion and deleting it."""
    tc_file = sample_testcase_dir / "testcase.json"
    monkeypatch.setattr(
        "qa_auto.ui.service.find_testcase_files",
        lambda search_paths=None: [tc_file],
    )
    case_id = json.loads(tc_file.read_text())["id"]

    # Add assertion
    res = client.post(
        f"/api/testcases/{case_id}/assertions",
        json={
            "kind": "visible",
            "target": "div#welcome-banner",
            "step_number": 1,
            "enforced": True,
        },
    )
    assert res.status_code == 200
    updated = res.json()
    assert len(updated["custom_assertions"]) == 1
    assert updated["custom_assertions"][0]["kind"] == "visible"
    assert updated["custom_assertions"][0]["target"] == "div#welcome-banner"

    # Delete assertion
    del_res = client.delete(f"/api/testcases/{case_id}/assertions/0")
    assert del_res.status_code == 200
    assert len(del_res.json()["custom_assertions"]) == 0


def test_step_visual_diff(
    client: TestClient, sample_testcase_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test step visual diff execution."""
    tc_file = sample_testcase_dir / "testcase.json"
    monkeypatch.setattr(
        "qa_auto.ui.service.find_testcase_files",
        lambda search_paths=None: [tc_file],
    )
    case_id = json.loads(tc_file.read_text())["id"]

    # Run visual diff for step 1
    res = client.post(
        f"/api/testcases/{case_id}/steps/1/visual-diff",
        json={"threshold": 0.1},
    )
    assert res.status_code == 200
    data = res.json()
    assert "diff_percentage" in data
    assert "passed" in data
    assert data["diff_percentage"] == 0.0
    assert data["passed"] is True
