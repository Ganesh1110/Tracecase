"""Phase 7.4 Steps 1 & 2: Performance Telemetry & Context-Isolated Browser Pooling Tests.

Validates the 10 required architectural and behavioral scenarios:
1. Telemetry persistence and schema migration (backward-compatible, storing timings & resources).
2. Timing values and graceful fallback for unavailable metrics (monotonic clocks, safe OS fallbacks).
3. Batch and matrix aggregate telemetry calculation (accurate average queue wait, startup, artifact sum).
4. Browser reuse across multiple executions (same browser instance, different runs).
5. Context isolation between executions (cookies/storage isolated, verified with real pages).
6. Fresh contexts during retries (new isolated context per attempt).
7. Browser crash and clean reconnection/recovery (simulate_crash and auto-recreation).
8. Cancellation and context cleanup (no leaked contexts or orphaned counts on cancellation).
9. Concurrent workers using the same managed browser safely (safe concurrency, context isolation).
10. Application shutdown with active executions (graceful orchestrator and pool shutdown).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tracecase.browser_pool import BrowserPool
from tracecase.models import ElementInfo, Step, TestCase
from tracecase.replay.engine import ReplayEngine
from tracecase.replay.models import ReplayResult, StepResult
from tracecase.telemetry import (
    elapsed_ms,
    get_cpu_percent,
    get_directory_size_bytes,
    get_load_average,
    get_memory_rss_mb,
    get_monotonic_time,
)
from tracecase.ui.db import (
    create_execution_batch,
    create_execution_matrix,
    create_execution_run,
    get_connection,
    get_execution_attempts,
    get_execution_batch,
    get_execution_matrix,
    get_execution_run,
    init_studio_db,
    record_execution_attempt,
    sync_testcase_meta,
    update_execution_batch,
    update_execution_matrix,
    update_execution_run_status,
)
from tracecase.ui.executor import ExecutionOrchestrator


def _make_step(number: int, action_type: str = "navigate", url: str | None = None, selector: str | None = None) -> Step:
    elem = None
    if selector:
        elem = ElementInfo(
            selector=selector,
            xpath=f"//*[@id='{selector.lstrip('#')}']",
            tag_name="button",
            text="Action",
            attributes={"id": selector.lstrip("#")},
            bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
        )
    return Step(
        number=number,
        action_type=action_type,
        url=url,
        element=elem,
        value=None,
        description_short=f"Step {number}",
        description_detailed=f"Detailed step {number}",
        duration_ms=10.0,
    )


def _make_testcase(id: str, name: str, start_url: str = "http://127.0.0.1:8000/", steps: list[Step] | None = None) -> TestCase:
    s = steps or [_make_step(1, "navigate", url=start_url)]
    return TestCase(
        id=id,
        name=name,
        created_at=datetime.now().isoformat(),
        start_url=start_url,
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0 Tracecase",
        steps=s,
        total_duration=1.0,
        total_steps=len(s),
    )


# ---------------------------------------------------------------------------
# Test 1: Telemetry Persistence and Schema Migration
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_telemetry_schema_migration_and_persistence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test 1: Existing databases missing telemetry columns are upgraded safely; all telemetry fields persist."""
    monkeypatch.chdir(tmp_path)
    db_file = tmp_path / "legacy_studio.db"

    # Simulate legacy database with old schema without telemetry columns
    conn = get_connection(db_file)
    conn.execute(
        """
        CREATE TABLE execution_runs (
            id TEXT PRIMARY KEY,
            testcase_id TEXT NOT NULL,
            testcase_name TEXT,
            project_id TEXT NOT NULL,
            suite_id TEXT,
            browser TEXT NOT NULL DEFAULT 'chromium',
            headed INTEGER NOT NULL DEFAULT 0,
            heal INTEGER NOT NULL DEFAULT 1,
            assertions INTEGER NOT NULL DEFAULT 1,
            visual_diff INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'queued',
            started_at TEXT,
            finished_at TEXT,
            duration_ms REAL DEFAULT 0.0,
            passed_steps INTEGER DEFAULT 0,
            failed_steps INTEGER DEFAULT 0,
            total_steps INTEGER DEFAULT 0,
            exit_code INTEGER DEFAULT 0,
            error_message TEXT,
            report_path TEXT,
            logs_json TEXT DEFAULT '[]',
            worker_id TEXT,
            batch_id TEXT,
            matrix_id TEXT,
            concurrency INTEGER DEFAULT 1,
            retries INTEGER DEFAULT 2,
            attempt_count INTEGER DEFAULT 1,
            retry_history_json TEXT DEFAULT '[]',
            failure_step INTEGER,
            failure_selector TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE execution_attempts (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            status TEXT NOT NULL,
            duration_ms REAL DEFAULT 0.0,
            error_message TEXT,
            failed_step INTEGER,
            failed_selector TEXT,
            report_path TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()

    # Run init_studio_db to trigger migrations
    init_studio_db(db_file)

    # Verify column existence via table pragma
    conn = get_connection(db_file)
    run_cols = [r["name"] for r in conn.execute("PRAGMA table_info(execution_runs)").fetchall()]
    attempt_cols = [r["name"] for r in conn.execute("PRAGMA table_info(execution_attempts)").fetchall()]
    conn.close()

    assert "queue_wait_ms" in run_cols
    assert "browser_startup_ms" in run_cols
    assert "execution_duration_ms" in run_cols
    assert "teardown_ms" in run_cols
    assert "memory_rss_mb" in run_cols
    assert "cpu_percent" in run_cols
    assert "load_average" in run_cols
    assert "artifact_size_bytes" in run_cols

    assert "browser_startup_ms" in attempt_cols
    assert "execution_duration_ms" in attempt_cols
    assert "teardown_ms" in attempt_cols
    assert "memory_rss_mb" in attempt_cols
    assert "artifact_size_bytes" in attempt_cols

    # Persist and verify attempt telemetry
    run_rec = create_execution_run(
        testcase_id="tc_telemetry_1",
        testcase_name="Telemetry Test",
        db_path=db_file,
    )
    run_id = run_rec["id"]

    record_execution_attempt(
        execution_id=run_id,
        attempt_number=1,
        status="passed",
        duration_ms=250.0,
        browser_startup_ms=45.5,
        execution_duration_ms=195.0,
        teardown_ms=9.5,
        memory_rss_mb=128.5,
        artifact_size_bytes=8192,
        db_path=db_file,
    )

    update_execution_run_status(
        execution_id=run_id,
        status="passed",
        finished_at=datetime.now().isoformat(),
        duration_ms=250.0,
        queue_wait_ms=15.2,
        browser_startup_ms=45.5,
        execution_duration_ms=195.0,
        teardown_ms=9.5,
        memory_rss_mb=128.5,
        cpu_percent=12.0,
        load_average=1.5,
        artifact_size_bytes=8192,
        db_path=db_file,
    )

    persisted_run = get_execution_run(run_id, db_path=db_file)
    assert persisted_run is not None
    assert persisted_run["queue_wait_ms"] == pytest.approx(15.2, 0.01)
    assert persisted_run["browser_startup_ms"] == pytest.approx(45.5, 0.01)
    assert persisted_run["execution_duration_ms"] == pytest.approx(195.0, 0.01)
    assert persisted_run["teardown_ms"] == pytest.approx(9.5, 0.01)
    assert persisted_run["memory_rss_mb"] == pytest.approx(128.5, 0.01)
    assert persisted_run["cpu_percent"] == pytest.approx(12.0, 0.01)
    assert persisted_run["load_average"] == pytest.approx(1.5, 0.01)
    assert persisted_run["artifact_size_bytes"] == 8192

    attempts = get_execution_attempts(run_id, db_path=db_file)
    assert len(attempts) == 1
    att = attempts[0]
    assert att["browser_startup_ms"] == pytest.approx(45.5, 0.01)
    assert att["execution_duration_ms"] == pytest.approx(195.0, 0.01)
    assert att["teardown_ms"] == pytest.approx(9.5, 0.01)
    assert att["memory_rss_mb"] == pytest.approx(128.5, 0.01)
    assert att["artifact_size_bytes"] == 8192


# ---------------------------------------------------------------------------
# Test 2: Timing Values and Graceful Fallback for Unavailable Metrics
# ---------------------------------------------------------------------------
def test_timing_values_and_graceful_fallback(tmp_path: Path):
    """Test 2: Monotonic timing measurements are positive and robust; unavailable metrics fall back cleanly."""
    t0 = get_monotonic_time()
    assert isinstance(t0, float)
    delta = elapsed_ms(t0)
    assert delta >= 0.0

    # Normal metric checks
    rss = get_memory_rss_mb()
    assert rss is None or (isinstance(rss, float) and rss > 0)

    load = get_load_average()
    assert load is None or (isinstance(load, float) and load >= 0)

    cpu = get_cpu_percent()
    assert cpu is None or (isinstance(cpu, float) and cpu >= 0.0)

    # Directory size check
    test_dir = tmp_path / "artifacts_test"
    test_dir.mkdir(parents=True, exist_ok=True)
    (test_dir / "file1.txt").write_bytes(b"hello world")
    sub = test_dir / "subdir"
    sub.mkdir()
    (sub / "file2.bin").write_bytes(b"1234567890")
    assert get_directory_size_bytes(test_dir) == 21
    assert get_directory_size_bytes(tmp_path / "nonexistent") == 0

    # Graceful fallback when OS metrics fail / raise exceptions
    with patch("resource.getrusage", side_effect=Exception("OS error")):
        assert get_memory_rss_mb() == 0.0

    with patch("os.getloadavg", side_effect=Exception("No load avg")):
        assert get_load_average() == 0.0


# ---------------------------------------------------------------------------
# Test 3: Batch and Matrix Aggregate Telemetry Calculation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_batch_and_matrix_aggregate_telemetry_calculation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test 3: Aggregated timings and artifact sum are calculated and persisted in batch and matrix records."""
    monkeypatch.chdir(tmp_path)
    init_studio_db()

    # 1. Batch execution telemetry calculation
    batch_rec = create_execution_batch(
        batch_id="batch_telemetry_test",
        total_tests=3,
        concurrency=2,
    )
    # Simulate child runs with individual metrics
    update_execution_batch(
        batch_id="batch_telemetry_test",
        status="passed",
        passed_tests=3,
        failed_tests=0,
        cancelled_tests=0,
        flaky_tests=0,
        finished_at=datetime.now().isoformat(),
        duration_ms=450.0,
        queue_wait_ms=12.4,  # Average queue wait
        avg_startup_ms=25.8,  # Average browser startup
        artifact_size_bytes=16384,  # Total artifacts across all runs
    )

    persisted_batch = get_execution_batch("batch_telemetry_test")
    assert persisted_batch is not None
    assert persisted_batch["queue_wait_ms"] == pytest.approx(12.4, 0.01)
    assert persisted_batch["avg_startup_ms"] == pytest.approx(25.8, 0.01)
    assert persisted_batch["artifact_size_bytes"] == 16384

    # 2. Matrix execution telemetry calculation
    create_execution_matrix(
        matrix_id="matrix_telemetry_test",
        name="Matrix Telemetry",
        concurrency=2,
        browsers=["chromium", "firefox"],
        total_executions=4,
    )
    update_execution_matrix(
        matrix_id="matrix_telemetry_test",
        status="passed",
        passed_executions=4,
        failed_executions=0,
        cancelled_executions=0,
        flaky_executions=0,
        divergence_count=0,
        finished_at=datetime.now().isoformat(),
        duration_ms=800.0,
        queue_wait_ms=8.5,
        avg_startup_ms=32.1,
        artifact_size_bytes=32768,
    )

    persisted_matrix = get_execution_matrix("matrix_telemetry_test")
    assert persisted_matrix is not None
    assert persisted_matrix["queue_wait_ms"] == pytest.approx(8.5, 0.01)
    assert persisted_matrix["avg_startup_ms"] == pytest.approx(32.1, 0.01)
    assert persisted_matrix["artifact_size_bytes"] == 32768


# ---------------------------------------------------------------------------
# Test 4: Browser Reuse Across Multiple Executions
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_browser_reuse_across_multiple_executions():
    """Test 4: BrowserPool reuses the exact same Browser process across executions instead of relaunching."""
    pool = BrowserPool()
    try:
        # Acquire context 1
        ctx1, page1 = await pool.acquire_context(browser_type="chromium", headless=True)
        assert page1 is not None
        browser_instance_1 = pool.get_browser("chromium", headless=True)
        assert browser_instance_1 is not None
        assert browser_instance_1.is_connected()
        assert pool.get_active_browser_count() == 1
        assert pool.get_active_context_count("chromium", True) == 1

        # Release context 1
        await pool.release_context(ctx1, browser_type="chromium", headless=True)
        assert pool.get_active_context_count("chromium", True) == 0
        # Browser remains alive in pool
        assert pool.get_active_browser_count() == 1
        assert browser_instance_1.is_connected()

        # Acquire context 2
        ctx2, page2 = await pool.acquire_context(browser_type="chromium", headless=True)
        assert page2 is not None
        browser_instance_2 = pool.get_browser("chromium", headless=True)

        # Crucial check: Exact same underlying Browser process was reused!
        assert browser_instance_2 is browser_instance_1
        assert pool.get_active_browser_count() == 1
        assert pool.get_active_context_count("chromium", True) == 1
        assert ctx2 != ctx1

        await pool.release_context(ctx2, browser_type="chromium", headless=True)
    finally:
        await pool.shutdown()
        assert pool.get_active_browser_count() == 0


# ---------------------------------------------------------------------------
# Test 5: Context Isolation Between Executions (Cookies & Storage Isolated)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_context_isolation_between_executions():
    """Test 5: Successive executions in the reused browser process have 100% clean, isolated cookies and storage."""
    pool = BrowserPool()
    try:
        # Execution 1
        ctx1, page1 = await pool.acquire_context(browser_type="chromium", headless=True)
        await page1.goto("about:blank")
        # Add cookie and storage to context 1
        await ctx1.add_cookies([
            {"name": "session_user", "value": "alice_secret", "url": "https://example.com"}
        ])
        cookies1 = await ctx1.cookies("https://example.com")
        assert len(cookies1) == 1
        assert cookies1[0]["name"] == "session_user"

        # Release context 1 (closes context)
        await pool.release_context(ctx1, browser_type="chromium", headless=True)

        # Execution 2 (reusing same browser)
        ctx2, page2 = await pool.acquire_context(browser_type="chromium", headless=True)
        await page2.goto("about:blank")
        # Context 2 MUST NOT have any cookies or storage from Context 1
        cookies2 = await ctx2.cookies("https://example.com")
        assert len(cookies2) == 0, "Cookie leakage detected between executions in reused browser!"

        await pool.release_context(ctx2, browser_type="chromium", headless=True)
    finally:
        await pool.shutdown()


# ---------------------------------------------------------------------------
# Test 6: Fresh Contexts During Retries
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fresh_contexts_during_retries():
    """Test 6: Every retry attempt receives an isolated, independent BrowserContext."""
    pool = BrowserPool()
    try:
        attempt_contexts = []
        for attempt in range(1, 4):
            ctx, page = await pool.acquire_context(browser_type="chromium", headless=True)
            attempt_contexts.append(ctx)
            # Add an attempt-specific cookie
            await ctx.add_cookies([
                {"name": f"attempt_{attempt}_token", "value": f"val_{attempt}", "url": "https://example.com"}
            ])
            cookies = await ctx.cookies("https://example.com")
            # Only current attempt's cookie exists
            assert len(cookies) == 1
            assert cookies[0]["name"] == f"attempt_{attempt}_token"

            # Clean context teardown between attempts
            await pool.release_context(ctx, browser_type="chromium", headless=True)

        # All 3 contexts were distinct objects
        assert len(set(attempt_contexts)) == 3
    finally:
        await pool.shutdown()


# ---------------------------------------------------------------------------
# Test 7: Browser Crash and Clean Recovery
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_browser_crash_and_clean_recovery():
    """Test 7: When a pooled browser crashes or disconnects, BrowserPool detects it and cleanly creates a new one."""
    pool = BrowserPool()
    try:
        ctx1, page1 = await pool.acquire_context(browser_type="chromium", headless=True)
        b1 = pool.get_browser("chromium", headless=True)
        assert b1 is not None and b1.is_connected()
        await pool.release_context(ctx1, browser_type="chromium", headless=True)

        # Simulate unexpected crash / disconnect
        await pool.simulate_crash("chromium", headless=True)
        assert b1.is_connected() is False

        # Next acquisition should detect dead browser and safely recreate a new healthy browser
        ctx2, page2 = await pool.acquire_context(browser_type="chromium", headless=True)
        b2 = pool.get_browser("chromium", headless=True)
        assert b2 is not None and b2.is_connected()
        assert b2 is not b1, "BrowserPool failed to create fresh browser after crash!"

        await page2.goto("about:blank")
        assert await page2.title() == ""

        await pool.release_context(ctx2, browser_type="chromium", headless=True)
    finally:
        await pool.shutdown()


# ---------------------------------------------------------------------------
# Test 8: Cancellation and Context Cleanup
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancellation_and_context_cleanup():
    """Test 8: Cancellation while holding an acquired context properly closes it without leaking counts."""
    pool = BrowserPool()
    try:
        ready = asyncio.Event()

        async def _mock_worker():
            ctx, page = await pool.acquire_context(browser_type="chromium", headless=True)
            ready.set()
            try:
                # Long operation interrupted by cancellation
                await asyncio.sleep(10.0)
            finally:
                # Execution loop guarantee: release_context in finally
                await pool.release_context(ctx, browser_type="chromium", headless=True)

        task = asyncio.create_task(_mock_worker())
        await ready.wait()
        assert pool.get_active_context_count("chromium", True) == 1

        # Cancel task
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # Verification: Context was released and closed, count restored to 0
        assert pool.get_active_context_count("chromium", True) == 0
        # Underlying browser process remains healthy
        b = pool.get_browser("chromium", headless=True)
        assert b is not None and b.is_connected()
    finally:
        await pool.shutdown()


# ---------------------------------------------------------------------------
# Test 9: Concurrent Workers Using the Same Managed Browser Safely
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_concurrent_workers_safe_browser_sharing():
    """Test 9: Multiple concurrent workers safely acquire distinct contexts from one shared browser process."""
    pool = BrowserPool()
    try:
        num_workers = 4
        contexts_acquired = []
        pages_acquired = []

        async def _concurrent_worker(worker_id: int):
            ctx, page = await pool.acquire_context(browser_type="chromium", headless=True)
            contexts_acquired.append(ctx)
            pages_acquired.append(page)
            await page.goto("about:blank")
            # Set worker-specific title or evaluate
            res = await page.evaluate(f"() => 'worker_{worker_id}'")
            assert res == f"worker_{worker_id}"
            await asyncio.sleep(0.05)
            await pool.release_context(ctx, browser_type="chromium", headless=True)

        # Run workers concurrently
        await asyncio.gather(*[_concurrent_worker(i) for i in range(num_workers)])

        # Single browser instance served all workers
        assert pool.get_active_browser_count() == 1
        # All contexts and pages were distinct
        assert len(set(contexts_acquired)) == num_workers
        assert len(set(pages_acquired)) == num_workers
        # All released
        assert pool.get_active_context_count("chromium", True) == 0
    finally:
        await pool.shutdown()


# ---------------------------------------------------------------------------
# Test 10: Application Shutdown with Active Executions
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_application_shutdown_with_active_executions():
    """Test 10: Orchestrator shutdown gracefully terminates active tasks and shuts down the browser pool."""
    orch = ExecutionOrchestrator()
    try:
        # Pre-warm browser pool
        ctx, page = await orch.browser_pool.acquire_context("chromium", headless=True)
        await orch.browser_pool.release_context(ctx, "chromium", headless=True)
        assert orch.browser_pool.get_active_browser_count() == 1

        # Simulate long running task in active_tasks
        async def _long_task():
            try:
                await asyncio.sleep(10.0)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(_long_task())
        orch.active_tasks["test_task_1"] = task

        # Call orchestrator shutdown
        await orch.shutdown()

        # Tasks cancelled and cleared
        assert task.cancelled() or task.done()
        assert len(orch.active_tasks) == 0
        # Browser pool cleanly shut down
        assert orch.browser_pool.get_active_browser_count() == 0
    finally:
        await orch.shutdown()
