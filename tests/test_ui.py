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

    # Write a dummy screenshot
    mock_screenshot = screenshots_dir / "001_click_button.png"
    mock_screenshot.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR...")

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
