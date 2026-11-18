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
