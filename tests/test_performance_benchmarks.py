"""Tests for Phase 7.4.5 - Performance Benchmarking Harness.

Verifies:
1. Benchmark data models (ParadigmResult, BenchmarkReport).
2. Metric calculations (throughput, P50, P95, startup overhead reduction, speedup factors).
3. Markdown report rendering with tabular columns.
4. CLI benchmark command interface and markdown export option.
5. End-to-end execution of parallel pooled vs cold paradigms.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from tracecase.benchmark import (
    BenchmarkReport,
    ParadigmResult,
    _build_paradigm_result,
    run_benchmark_suite,
)
from tracecase.cli import app


def test_build_paradigm_result_statistics():
    """Test statistical aggregation (throughput, P50, P95, mean) in paradigm results."""
    startups = [250.0, 30.0, 35.0, 32.0]
    executions = [100.0, 110.0, 95.0, 120.0]
    wall_s = 2.5

    result = _build_paradigm_result(
        name="Test Paradigm",
        total_tests=4,
        wall_s=wall_s,
        startups=startups,
        executions=executions,
    )

    assert result.name == "Test Paradigm"
    assert result.total_tests == 4
    assert result.wall_clock_seconds == 2.5
    # (4 / 2.5) * 60 = 96 tests/min
    assert result.throughput_tests_per_min == pytest.approx(96.0)
    assert result.startup_min_ms == 30.0
    assert result.startup_max_ms == 250.0
    assert result.startup_mean_ms == pytest.approx(86.75)
    # Sorted executions: [95.0, 100.0, 110.0, 120.0] -> P50 is 110.0 (idx 2)
    assert result.execution_p50_ms == 110.0
    assert result.execution_p95_ms == 120.0


def test_benchmark_report_markdown_generation():
    """Test generating markdown table comparison from BenchmarkReport."""
    seq = ParadigmResult(
        name="Sequential Cold",
        total_tests=6,
        wall_clock_seconds=6.0,
        throughput_tests_per_min=60.0,
        startup_mean_ms=280.0,
        startup_min_ms=250.0,
        startup_max_ms=310.0,
        startup_warm_mean_ms=280.0,
        execution_mean_ms=120.0,
        execution_p50_ms=115.0,
        execution_p95_ms=130.0,
        peak_rss_mb=85.0,
    )
    par_cold = ParadigmResult(
        name="Parallel Cold",
        total_tests=6,
        wall_clock_seconds=3.0,
        throughput_tests_per_min=120.0,
        startup_mean_ms=290.0,
        startup_min_ms=260.0,
        startup_max_ms=320.0,
        startup_warm_mean_ms=290.0,
        execution_mean_ms=125.0,
        execution_p50_ms=120.0,
        execution_p95_ms=140.0,
        peak_rss_mb=120.0,
    )
    par_pool = ParadigmResult(
        name="Parallel Pooled (Tracecase)",
        total_tests=6,
        wall_clock_seconds=1.5,
        throughput_tests_per_min=240.0,
        startup_mean_ms=45.0,
        startup_min_ms=30.0,
        startup_max_ms=270.0,
        startup_warm_mean_ms=32.0,
        execution_mean_ms=118.0,
        execution_p50_ms=112.0,
        execution_p95_ms=128.0,
        peak_rss_mb=92.0,
    )

    report = BenchmarkReport(
        timestamp="2026-11-19T21:00:00Z",
        iterations=6,
        concurrency=3,
        sequential_cold=seq,
        parallel_cold=par_cold,
        parallel_pooled=par_pool,
        startup_reduction_pct=83.9,
        wall_clock_speedup_vs_sequential=4.0,
        wall_clock_speedup_vs_parallel_cold=2.0,
    )

    md = report.to_markdown()
    assert "# Tracecase Execution Performance Benchmark" in md
    assert "| Metric | Sequential Cold | Parallel Cold | Parallel Pooled (Tracecase) |" in md
    assert "240.0 tests/min" in md
    assert "83.9%" in md
    assert "4.00x" in md


@pytest.mark.asyncio
async def test_run_benchmark_suite_live():
    """Run real Playwright benchmark suite with 4 iterations and verify empirical metrics."""
    report = await run_benchmark_suite(iterations=4, concurrency=2)

    assert report.sequential_cold.total_tests == 4
    assert report.parallel_cold.total_tests == 4
    assert report.parallel_pooled.total_tests == 4

    # Verify Parallel Pooled achieves higher throughput and wall clock speedup
    assert report.parallel_pooled.throughput_tests_per_min > report.sequential_cold.throughput_tests_per_min
    assert report.wall_clock_speedup_vs_sequential > 1.0


def test_cli_benchmark_command(tmp_path: Path):
    """Test running tracecase benchmark via CLI with markdown output file."""
    runner = CliRunner()
    out_file = tmp_path / "benchmark_report.md"

    # Invoke CLI with 2 iterations
    res = runner.invoke(app, ["benchmark", "-n", "2", "-c", "2", "-o", str(out_file)])
    assert res.exit_code == 0
    assert "Tracecase Execution Performance Benchmark" in res.stdout
    assert out_file.exists()
    file_content = out_file.read_text()
    assert "Tracecase Execution Performance Benchmark" in file_content
    assert "Overhead Reduction" in file_content
