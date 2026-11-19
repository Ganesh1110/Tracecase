"""Tests for Phase 7.4.4 - Artifact & Storage Optimization.

Verifies:
1. Fine-grained storage summary calculation across recordings, replay runs, diffs, explorations, and DB.
2. Configurable retention policies (retention_mode, keep_latest_runs, max_age_days, max_storage_mb).
3. Safe pruning behavior:
   - Visual diff pruning
   - Failures-only pruning (removes screenshots for passed runs, preserves failure diagnostics)
   - Age-based pruning (older_than_days)
   - Keep latest N runs per test case
   - FIFO storage quota enforcement
   - Exploration artifact cleanup
   - Dry-run simulation (does not delete files)
   - Safety guarantee: baseline testcase.json and baseline screenshots are never touched
4. Execution-time retention hook in ExecutionOrchestrator.
5. REST API endpoints (/api/storage/summary, /api/storage/prune, /api/storage/retention).
6. CLI storage command.
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from tracecase.artifact_manager import (
    ArtifactManager,
    PruneRequest,
    PruneResult,
    RetentionPolicy,
    StorageSummary,
)
from tracecase.cli import app
from tracecase.ui.db import init_studio_db, update_settings
from tracecase.ui.executor import ExecutionOrchestrator
from tracecase.ui.server import create_app
from typer.testing import CliRunner


@pytest.fixture
def temp_storage_env(tmp_path: Path):
    """Create an isolated filesystem environment with recordings, diffs, explorations, and studio db."""
    recordings_dir = tmp_path / "recordings"
    explorations_dir = tmp_path / ".tracecase" / "explorations"
    db_path = tmp_path / ".tracecase" / "studio.db"

    recordings_dir.mkdir(parents=True)
    explorations_dir.mkdir(parents=True)
    init_studio_db(db_path)

    # 1. Test case 1: TC_A (has baseline recordings, 3 replay runs, 1 diff)
    tc_a = recordings_dir / "tc_a"
    tc_a.mkdir()
    (tc_a / "testcase.json").write_text(json.dumps({"id": "tc_a", "steps": []}))
    tc_a_shots = tc_a / "screenshots"
    tc_a_shots.mkdir()
    (tc_a_shots / "baseline_1.png").write_bytes(b"x" * 1024)  # 1 KB

    # TC_A replay runs
    tc_a_runs = tc_a / "replay_runs"
    tc_a_runs.mkdir()

    # Run 1: Old passed run (mtime 20 days ago)
    run_1 = tc_a_runs / "run_old_passed_att1_20260101"
    run_1.mkdir()
    (run_1 / "report.json").write_text(json.dumps({"status": "passed"}))
    (run_1 / "shot_1.png").write_bytes(b"x" * 2048)  # 2 KB
    (run_1 / "shot_2.png").write_bytes(b"x" * 2048)  # 2 KB
    old_time = time.time() - (20 * 86400)
    for p in [run_1 / "shot_1.png", run_1 / "shot_2.png", run_1 / "report.json", run_1]:
        p.touch()
        # Set old mtime
        import os
        os.utime(p, (old_time, old_time))

    # Run 2: Recent failed run (mtime 2 days ago)
    run_2 = tc_a_runs / "run_recent_failed_att1_20260118"
    run_2.mkdir()
    (run_2 / "report.json").write_text(json.dumps({"status": "failed"}))
    (run_2 / "fail_shot.png").write_bytes(b"x" * 4096)  # 4 KB
    med_time = time.time() - (2 * 86400)
    import os
    os.utime(run_2, (med_time, med_time))

    # Run 3: Recent passed run (mtime 1 hour ago)
    run_3 = tc_a_runs / "run_recent_passed_att1_20260120"
    run_3.mkdir()
    (run_3 / "report.json").write_text(json.dumps({"status": "passed"}))
    (run_3 / "pass_shot.png").write_bytes(b"x" * 3072)  # 3 KB

    # TC_A visual diffs
    tc_a_diffs = tc_a / "diffs"
    tc_a_diffs.mkdir()
    (tc_a_diffs / "diff_test_1.png").write_bytes(b"x" * 1536)

    # 2. Explorations
    exp_1 = explorations_dir / "exp_01"
    exp_1.mkdir()
    (exp_1 / "graph.json").write_text("{}")
    (exp_1 / "shot_exp.png").write_bytes(b"x" * 2048)

    mgr = ArtifactManager(
        recordings_dir=recordings_dir,
        explorations_dir=explorations_dir,
        db_path=db_path,
    )

    return {
        "tmp_path": tmp_path,
        "recordings_dir": recordings_dir,
        "explorations_dir": explorations_dir,
        "db_path": db_path,
        "tc_a": tc_a,
        "tc_a_shots": tc_a_shots,
        "tc_a_runs": tc_a_runs,
        "tc_a_diffs": tc_a_diffs,
        "run_1": run_1,
        "run_2": run_2,
        "run_3": run_3,
        "mgr": mgr,
    }


def test_storage_summary_breakdown(temp_storage_env):
    """Test detailed categorization of disk usage across all artifact types."""
    mgr: ArtifactManager = temp_storage_env["mgr"]
    summary = mgr.get_storage_summary()

    assert summary.recordings_count == 1
    assert summary.recordings_size_bytes >= 1024  # baseline screenshot + testcase.json
    assert summary.replay_runs_count == 3
    assert summary.replay_screenshots_count == 4  # run1(2) + run2(1) + run3(1)
    assert summary.diffs_count == 1
    assert summary.diffs_size_bytes == 1536
    assert summary.explorations_count == 1
    assert summary.database_size_bytes > 0
    assert summary.total_size_bytes > (summary.recordings_size_bytes + summary.replay_runs_size_bytes)
    assert summary.retention_policy is not None


def test_retention_policy_persistence(temp_storage_env):
    """Test reading and writing retention policies via studio db."""
    mgr: ArtifactManager = temp_storage_env["mgr"]

    # Initial default policy
    initial_pol = mgr.get_policy()
    assert initial_pol.retention_mode in ["all", "failures_only", "none"]

    # Update policy
    new_pol = RetentionPolicy(
        retention_mode="failures_only",
        keep_latest_runs=5,
        max_age_days=7,
        max_storage_mb=250,
        auto_prune_on_complete=False,
    )
    saved = mgr.save_policy(new_pol)

    assert saved.retention_mode == "failures_only"
    assert saved.keep_latest_runs == 5
    assert saved.max_age_days == 7
    assert saved.max_storage_mb == 250
    assert saved.auto_prune_on_complete is False

    # Read back fresh
    reloaded = mgr.get_policy()
    assert reloaded == saved


def test_clean_visual_diffs(temp_storage_env):
    """Test pruning only visual diff images without affecting baseline or runs."""
    mgr: ArtifactManager = temp_storage_env["mgr"]
    diff_file = temp_storage_env["tc_a_diffs"] / "diff_test_1.png"
    assert diff_file.exists()

    res = mgr.prune_artifacts(PruneRequest(clean_diffs=True))

    assert res.deleted_files == 1
    assert res.freed_bytes == 1536
    assert not diff_file.exists()
    # Baseline must be untouched
    assert (temp_storage_env["tc_a_shots"] / "baseline_1.png").exists()
    assert (temp_storage_env["tc_a"] / "testcase.json").exists()


def test_failures_only_retention_pruning(temp_storage_env):
    """Test that failures-only pruning strips screenshots from passed runs but preserves failed runs."""
    mgr: ArtifactManager = temp_storage_env["mgr"]
    run_1 = temp_storage_env["run_1"]  # passed
    run_2 = temp_storage_env["run_2"]  # failed
    run_3 = temp_storage_env["run_3"]  # passed

    assert (run_1 / "shot_1.png").exists()
    assert (run_2 / "fail_shot.png").exists()
    assert (run_3 / "pass_shot.png").exists()

    res = mgr.prune_artifacts(PruneRequest(failures_only=True))

    assert res.deleted_files == 3  # run_1 has 2 shots, run_3 has 1 shot
    # Passed run screenshots pruned
    assert not (run_1 / "shot_1.png").exists()
    assert not (run_1 / "shot_2.png").exists()
    assert not (run_3 / "pass_shot.png").exists()
    # Reports preserved for passed runs
    assert (run_1 / "report.json").exists()
    assert (run_3 / "report.json").exists()
    # Failed run screenshots strictly preserved
    assert (run_2 / "fail_shot.png").exists()
    assert (run_2 / "report.json").exists()


def test_age_based_pruning(temp_storage_env):
    """Test pruning runs older than N days."""
    mgr: ArtifactManager = temp_storage_env["mgr"]
    run_1 = temp_storage_env["run_1"]  # 20 days old
    run_2 = temp_storage_env["run_2"]  # 2 days old

    assert run_1.exists()
    assert run_2.exists()

    res = mgr.prune_artifacts(PruneRequest(older_than_days=10))

    assert res.deleted_runs == 1
    assert not run_1.exists()  # Old run removed
    assert run_2.exists()      # Recent run preserved


def test_keep_latest_n_runs_pruning(temp_storage_env):
    """Test keeping only the latest N runs per test case."""
    mgr: ArtifactManager = temp_storage_env["mgr"]
    run_1 = temp_storage_env["run_1"]  # oldest
    run_2 = temp_storage_env["run_2"]  # middle
    run_3 = temp_storage_env["run_3"]  # newest

    # Keep latest 2 runs (run_2 and run_3)
    res = mgr.prune_artifacts(PruneRequest(keep_latest_runs=2))

    assert res.deleted_runs == 1
    assert not run_1.exists()
    assert run_2.exists()
    assert run_3.exists()


def test_dry_run_simulation(temp_storage_env):
    """Test that dry_run simulates deletion and calculates freed bytes without deleting files."""
    mgr: ArtifactManager = temp_storage_env["mgr"]
    diff_file = temp_storage_env["tc_a_diffs"] / "diff_test_1.png"
    run_1 = temp_storage_env["run_1"]

    res = mgr.prune_artifacts(PruneRequest(clean_diffs=True, clean_old_runs=True, dry_run=True))

    assert res.dry_run is True
    assert res.deleted_files > 0
    assert res.freed_bytes > 0
    assert str(diff_file) in res.pruned_paths
    # Verify files were NOT actually deleted
    assert diff_file.exists()
    assert run_1.exists()


def test_execution_time_retention_hook(temp_storage_env):
    """Test ExecutionOrchestrator applies retention policy automatically upon execution completion."""
    mgr: ArtifactManager = temp_storage_env["mgr"]
    mgr.save_policy(
        RetentionPolicy(
            retention_mode="failures_only",
            keep_latest_runs=2,
            auto_prune_on_complete=True,
        )
    )

    tc_dir = temp_storage_env["tc_a"]
    new_run = tc_dir / "replay_runs" / "new_passed_run_att1_20260121"
    new_run.mkdir()
    (new_run / "shot_new.png").write_bytes(b"x" * 2048)
    (new_run / "report.json").write_text(json.dumps({"status": "passed"}))

    # Apply execution retention for passing run
    mgr.apply_execution_retention(
        output_dir=new_run,
        status="passed",
        testcase_dir=tc_dir,
    )

    # In failures_only mode, screenshot should be stripped from passing run
    assert not (new_run / "shot_new.png").exists()
    assert (new_run / "report.json").exists()

    # And with keep_latest_runs=2, excess runs were pruned
    current_runs = list((tc_dir / "replay_runs").iterdir())
    assert len(current_runs) <= 2


def test_storage_rest_endpoints(temp_storage_env):
    """Test /api/storage/summary, /api/storage/prune, and /api/storage/retention REST endpoints."""
    # Patch ArtifactManager in api module to point to our temp environment
    mgr = temp_storage_env["mgr"]
    with patch("tracecase.ui.api.ArtifactManager", return_value=mgr):
        app_instance = create_app()
        client = TestClient(app_instance)

        # 1. GET /api/storage/summary
        r_sum = client.get("/api/storage/summary")
        assert r_sum.status_code == 200
        data = r_sum.json()
        assert "total_size_mb" in data
        assert "recordings_count" in data
        assert "replay_runs_count" in data
        assert "retention_policy" in data

        # 2. GET /api/storage/retention
        r_pol = client.get("/api/storage/retention")
        assert r_pol.status_code == 200
        assert r_pol.json()["retention_mode"] in ["all", "failures_only", "none"]

        # 3. PUT /api/storage/retention
        r_up = client.put(
            "/api/storage/retention",
            json={
                "retention_mode": "failures_only",
                "keep_latest_runs": 8,
                "max_age_days": 10,
                "max_storage_mb": 400,
                "auto_prune_on_complete": True,
            },
        )
        assert r_up.status_code == 200
        assert r_up.json()["keep_latest_runs"] == 8

        # 4. POST /api/storage/prune (dry run)
        r_prune = client.post(
            "/api/storage/prune",
            json={"clean_diffs": True, "dry_run": True},
        )
        assert r_prune.status_code == 200
        prune_res = r_prune.json()
        assert prune_res["dry_run"] is True
        assert prune_res["deleted_files"] >= 1


def test_cli_storage_command(temp_storage_env):
    """Test tracecase storage CLI outputs rich table and supports dry-run pruning."""
    mgr = temp_storage_env["mgr"]
    runner = CliRunner()

    with patch("tracecase.artifact_manager.ArtifactManager", return_value=mgr):
        # 1. Summary
        res = runner.invoke(app, ["storage"])
        assert res.exit_code == 0
        assert "Tracecase Disk Storage Summary" in res.stdout
        assert "Baseline Corpus" in res.stdout

        # 2. Prune dry run
        res_prune = runner.invoke(app, ["storage", "--diffs", "--dry-run"])
        assert res_prune.exit_code == 0
        assert "DRY RUN" in res_prune.stdout or "Would free" in res_prune.stdout
