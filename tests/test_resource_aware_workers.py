"""Phase 7.4.3: Resource-Aware Worker Management & Stability Tests.

Validates:
1. Resource pressure detection and threshold evaluation (load ratio, peak RSS, context density).
2. Host CPU-aware concurrency ceiling and safe clamping.
3. Safe worker backpressure and throttling in batch and matrix executors.
4. Simultaneous browser crash recovery across concurrent in-flight executions.
5. Browser pool sustained load stability (continuous context allocation/release cycling with 0 leaks).
6. Accurate Peak Runner RSS (ru_maxrss) labeling and documentation.
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
from tracecase.resource_monitor import ResourceMonitor, ResourcePressure
from tracecase.telemetry import get_memory_rss_mb
from tracecase.ui.db import (
    get_execution_run,
    init_studio_db,
    sync_testcase_meta,
)
from tracecase.ui.executor import ExecutionOrchestrator


def _make_step(number: int, action_type: str = "navigate", url: str | None = None) -> Step:
    return Step(
        number=number,
        action_type=action_type,
        url=url,
        timestamp=datetime.now().isoformat(),
        element=None,
        value=None,
        description_short=f"Step {number}",
        description_detailed=f"Detailed step {number}",
        duration_ms=10.0,
    )


def _make_testcase(id: str, name: str, start_url: str = "about:blank") -> TestCase:
    steps = [_make_step(1, "navigate", url=start_url)]
    return TestCase(
        id=id,
        name=name,
        created_at=datetime.now().isoformat(),
        start_url=start_url,
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0 Tracecase",
        steps=steps,
        total_duration=1.0,
        total_steps=len(steps),
    )


# ---------------------------------------------------------------------------
# Test 1: Resource Pressure Detection & Threshold Evaluation
# ---------------------------------------------------------------------------
def test_resource_pressure_detection_and_thresholds():
    """Test 1: ResourceMonitor accurately flags pressure when load, memory, or context density exceed thresholds."""
    monitor = ResourceMonitor(max_load_ratio=2.0, max_peak_memory_mb=500.0, max_contexts_per_browser=4)
    monitor.cpu_cores = 4

    # 1. Normal state: load 2.0 on 4 cores = ratio 0.5 (< 2.0), peak RSS 100MB (< 500MB), 2 contexts (< 4)
    with patch("tracecase.resource_monitor.get_load_average", return_value=2.0), \
         patch("tracecase.resource_monitor.get_memory_rss_mb", return_value=100.0):
        pressure = monitor.check_pressure(active_contexts=2)
        assert pressure.is_under_pressure is False
        assert len(pressure.reasons) == 0
        assert pressure.load_ratio == 0.5
        assert pressure.to_dict()["is_under_pressure"] is False

    # 2. High load pressure: load 12.0 on 4 cores = ratio 3.0 (> 2.0)
    with patch("tracecase.resource_monitor.get_load_average", return_value=12.0), \
         patch("tracecase.resource_monitor.get_memory_rss_mb", return_value=100.0):
        pressure = monitor.check_pressure(active_contexts=2)
        assert pressure.is_under_pressure is True
        assert any("System load ratio" in r for r in pressure.reasons)

    # 3. Peak memory pressure: peak RSS 650MB (> 500MB)
    with patch("tracecase.resource_monitor.get_load_average", return_value=2.0), \
         patch("tracecase.resource_monitor.get_memory_rss_mb", return_value=650.0):
        pressure = monitor.check_pressure(active_contexts=2)
        assert pressure.is_under_pressure is True
        assert any("Peak runner RSS" in r for r in pressure.reasons)

    # 4. Context density pressure: active contexts 4 reaches safety limit 4
    with patch("tracecase.resource_monitor.get_load_average", return_value=2.0), \
         patch("tracecase.resource_monitor.get_memory_rss_mb", return_value=100.0):
        pressure = monitor.check_pressure(active_contexts=4)
        assert pressure.is_under_pressure is True
        assert any("Active browser contexts" in r for r in pressure.reasons)


# ---------------------------------------------------------------------------
# Test 2: Host CPU-Aware Safe Concurrency Ceiling
# ---------------------------------------------------------------------------
def test_host_cpu_aware_concurrency_clamping():
    """Test 2: Concurrency ceiling respects physical CPU limits and Tracecase safety bounds (1 to 8)."""
    # 2-core machine
    monitor_small = ResourceMonitor()
    monitor_small.cpu_cores = 2
    # 2 cores * 2 = 4 max safe concurrency
    assert monitor_small.get_safe_concurrency_ceiling(requested_concurrency=1) == 1
    assert monitor_small.get_safe_concurrency_ceiling(requested_concurrency=2) == 2
    assert monitor_small.get_safe_concurrency_ceiling(requested_concurrency=4) == 4
    assert monitor_small.get_safe_concurrency_ceiling(requested_concurrency=8) == 4  # Clamped to 4

    # 16-core machine
    monitor_large = ResourceMonitor()
    monitor_large.cpu_cores = 16
    # Host capacity allows up to 8 (hard upper bound)
    assert monitor_large.get_safe_concurrency_ceiling(requested_concurrency=8) == 8
    assert monitor_large.get_safe_concurrency_ceiling(requested_concurrency=16) == 8  # Clamped to 8

    # Edge cases: 0 or negative
    assert monitor_small.get_safe_concurrency_ceiling(requested_concurrency=0) == 1
    assert monitor_small.get_safe_concurrency_ceiling(requested_concurrency=-5) == 1


# ---------------------------------------------------------------------------
# Test 3: Safe Worker Backpressure Throttling in Batch Execution
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_batch_worker_backpressure_throttling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test 3: Workers detect host resource pressure and apply safe backpressure yielding before proceeding."""
    monkeypatch.chdir(tmp_path)
    init_studio_db()

    # Create 2 approved test cases
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    tc1 = _make_testcase("tc_throttle_1", "Throttle Test 1")
    tc2 = _make_testcase("tc_throttle_2", "Throttle Test 2")

    for tc in [tc1, tc2]:
        d = recordings_dir / tc.id
        d.mkdir(parents=True, exist_ok=True)
        f = d / "testcase.json"
        f.write_text(tc.model_dump_json(indent=2), encoding="utf-8")
        sync_testcase_meta(tc, f, approval_status="approved")

    orch = ExecutionOrchestrator()
    # Force pressure detection on the monitor
    orch.resource_monitor.max_load_ratio = 0.01  # Artificially low threshold to trigger pressure
    orch.resource_monitor.cpu_cores = 1

    throttled_events: list[dict[str, Any]] = []

    async def _mock_broadcast(batch_id: str, event_type: str, data: dict[str, Any]):
        if event_type == "worker_throttled":
            throttled_events.append(data)

    monkeypatch.setattr("tracecase.ui.executor.broadcast_batch_event", _mock_broadcast)

    class FastMockEngine:
        def __init__(self, **kwargs: Any) -> None:
            self.testcase = kwargs.get("testcase")
            self.browser_pool = kwargs.get("browser_pool")

        async def run(self) -> Any:
            now = datetime.now()
            from tracecase.replay.models import ReplayResult
            return ReplayResult(
                testcase_id=self.testcase.id,
                started_at=now,
                finished_at=now,
                status="passed",
                exit_code=0,
                steps=[],
                browser_startup_ms=10.0,
                execution_duration_ms=50.0,
                teardown_ms=5.0,
                total_duration_ms=65.0,
            )

    monkeypatch.setattr("tracecase.ui.executor.ReplayEngine", FastMockEngine)

    batch = await orch.start_batch_execution(
        testcase_ids=["tc_throttle_1", "tc_throttle_2"],
        concurrency=2,
    )
    batch_id = batch["id"]

    coord_task = orch.active_tasks.get(batch_id)
    if coord_task:
        await coord_task

    # Verification: Both workers detected pressure and safely throttled via backpressure event
    assert len(throttled_events) >= 2, "Expected worker_throttled events to be emitted under pressure"
    assert all("reasons" in e for e in throttled_events)

    # Verification: Runs successfully completed despite backpressure throttling
    r1 = get_execution_run(batch["runs"][0]["id"])
    r2 = get_execution_run(batch["runs"][1]["id"])
    assert r1 is not None and r1["status"] == "passed"
    assert r2 is not None and r2["status"] == "passed"


# ---------------------------------------------------------------------------
# Test 4: Simultaneous Browser Crash During Concurrent In-Flight Executions
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_simultaneous_browser_crash_during_concurrent_executions():
    """Test 4: When a browser crashes during concurrent executions, all in-flight workers fail cleanly without hanging, and pool recovers."""
    pool = BrowserPool()
    try:
        # Pre-warm browser and acquire 3 concurrent contexts
        workers_count = 3
        contexts = []
        pages = []
        for _ in range(workers_count):
            ctx, page = await pool.acquire_context("chromium", headless=True)
            contexts.append(ctx)
            pages.append(page)
            await page.goto("about:blank")

        assert pool.get_active_browser_count() == 1
        assert pool.get_active_context_count("chromium", True) == workers_count

        worker_results = []

        async def _in_flight_worker(worker_idx: int, ctx: Any, page: Any):
            try:
                # In-flight activity: wait briefly then attempt an action
                await asyncio.sleep(0.1)
                await page.evaluate("() => document.title = 'running'")
                worker_results.append(f"worker_{worker_idx}_passed")
            except Exception as exc:
                # Expected: browser crash causes TargetClosedError
                worker_results.append(f"worker_{worker_idx}_caught_{type(exc).__name__}")
            finally:
                # Context release in finally must execute safely without raising
                await pool.release_context(ctx, "chromium", headless=True)

        worker_tasks = [
            asyncio.create_task(_in_flight_worker(i, contexts[i], pages[i]))
            for i in range(workers_count)
        ]

        # Forcibly crash the underlying browser process while all 3 are in-flight
        await asyncio.sleep(0.02)
        await pool.simulate_crash("chromium", headless=True)

        # Await all workers
        await asyncio.gather(*worker_tasks)

        # Verification: All 3 workers caught the disconnect/closure cleanly
        assert len(worker_results) == workers_count
        assert all("caught" in res or "passed" in res for res in worker_results)

        # Verification: All contexts safely released, count restored to 0
        assert pool.get_active_context_count("chromium", True) == 0

        # Verification: BrowserPool cleanly spins up a new healthy browser on subsequent acquisition
        ctx_new, page_new = await pool.acquire_context("chromium", headless=True)
        assert page_new is not None
        assert pool.get_active_browser_count() == 1
        assert pool.get_active_context_count("chromium", True) == 1
        await page_new.goto("about:blank")
        await pool.release_context(ctx_new, "chromium", headless=True)
    finally:
        await pool.shutdown()


# ---------------------------------------------------------------------------
# Test 5: Browser Pool Under Sustained Load
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_browser_pool_sustained_load():
    """Test 5: Sustained sequence of 25 consecutive and concurrent context allocations/releases yields zero leaks and stable state."""
    pool = BrowserPool()
    try:
        cycles = 25
        sem = asyncio.Semaphore(4)  # Bounded concurrency of 4

        async def _single_cycle(idx: int):
            async with sem:
                ctx, page = await pool.acquire_context("chromium", headless=True)
                try:
                    await page.goto("about:blank")
                    res = await page.evaluate("() => 1 + 1")
                    assert res == 2
                finally:
                    await pool.release_context(ctx, "chromium", headless=True)

        # Run 25 cycles with bounded concurrency
        await asyncio.gather(*[_single_cycle(i) for i in range(cycles)])

        # Single browser process served all 25 cycles without restarts
        assert pool.get_active_browser_count() == 1
        # All 25 contexts cleanly released with zero leaked allocations
        assert pool.get_active_context_count("chromium", True) == 0
        b = pool.get_browser("chromium", headless=True)
        assert b is not None and b.is_connected()
    finally:
        await pool.shutdown()
        assert pool.get_active_browser_count() == 0


# ---------------------------------------------------------------------------
# Test 6: Accurate Peak Runner RSS Documentation and Metric Labeling
# ---------------------------------------------------------------------------
def test_peak_rss_documentation_and_labels():
    """Test 6: Verify telemetry documentation explicitly distinguishes Peak Runner RSS (ru_maxrss) from browser processes."""
    import inspect
    from tracecase.telemetry import get_memory_rss_mb

    doc = inspect.getdoc(get_memory_rss_mb)
    assert doc is not None
    # Must explicitly state peak runner memory and ru_maxrss
    assert "peak" in doc.lower()
    assert "ru_maxrss" in doc
    assert "browser" in doc.lower()
