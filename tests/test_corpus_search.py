"""Tests for corpus search and coverage analysis."""

from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from qa_auto.index.search import get_coverage_report, search_testcases
from qa_auto.index.store import index_testcase
from qa_auto.models import ElementInfo, NetworkRequest, Step, TestCase


def _testcase(tc_id: str, name: str, url: str, selector: str = "#cart") -> TestCase:
    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}" if urlparse(url).netloc else url
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
                url=f"{origin}/api/cart",
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


def test_search_testcases_with_special_characters(temp_dir: Path) -> None:
    db_path = temp_dir / "corpus.db"
    tc = _testcase(
        "tc_btn", "Submit Flow", "https://shop.com/pay", selector="button[type='submit']"
    )
    index_testcase(tc, temp_dir / "tc.json", db_path)

    # Should not throw SQLite FTS5 syntax error with brackets or quotes
    results = search_testcases("button[type='submit']", db_path=db_path)
    assert isinstance(results, list)


def test_coverage_report_summarizes_endpoints_and_urls(temp_dir: Path) -> None:
    db_path = temp_dir / "corpus.db"
    tc1 = _testcase("tc_1", "Cart 1", "https://shop.com/cart")
    tc2 = _testcase("tc_2", "Cart 2", "https://shop.com/cart")
    index_testcase(tc1, temp_dir / "tc1.json", db_path)
    index_testcase(tc2, temp_dir / "tc2.json", db_path)

    report = get_coverage_report(db_path=db_path)

    assert report["total_testcases"] == 2
    assert "https://shop.com/cart" in report["start_urls"]
    assert "https://shop.com/api/cart" in report["network_endpoints"]
    assert len(report["potential_duplicates"]) >= 1
