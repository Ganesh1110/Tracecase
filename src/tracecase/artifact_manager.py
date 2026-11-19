"""Artifact and Storage Optimization Manager for Tracecase.

Provides fine-grained disk usage analytics, configurable artifact retention policies,
and safe multi-strategy pruning (failures-only, age-based, latest-N, and storage quota).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shutil
import time
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class RetentionPolicy(BaseModel):
    """Configurable artifact retention rules."""
    retention_mode: str = Field(
        default="all",
        description="Retention strategy: 'all' (keep everything), 'failures_only' (prune heavy artifacts on pass), 'none' (discard replay outputs)"
    )
    keep_latest_runs: int = Field(
        default=10,
        description="Number of latest replay runs to keep per testcase (0 = unlimited)"
    )
    max_age_days: int = Field(
        default=14,
        description="Maximum age of replay runs in days before eligible for pruning (0 = unlimited)"
    )
    max_storage_mb: int = Field(
        default=500,
        description="Target maximum disk quota for replay artifacts in MB (0 = unlimited)"
    )
    auto_prune_on_complete: bool = Field(
        default=True,
        description="Whether to apply retention pruning automatically at execution completion"
    )


# Alias for backward compatibility
PrunePolicy = RetentionPolicy


class StorageSummary(BaseModel):
    """Comprehensive disk storage breakdown across all Tracecase assets."""
    total_size_bytes: int
    total_size_mb: float
    recordings_count: int
    recordings_size_bytes: int
    recordings_size_mb: float
    replay_runs_count: int
    replay_runs_size_bytes: int
    replay_runs_size_mb: float
    replay_screenshots_count: int
    diffs_count: int
    diffs_size_bytes: int
    diffs_size_mb: float
    explorations_count: int
    explorations_size_bytes: int
    explorations_size_mb: float
    database_path: str
    database_size_bytes: int
    database_size_mb: float
    retention_policy: RetentionPolicy


class PruneRequest(BaseModel):
    """Parameters for on-demand artifact cleanup."""
    clean_diffs: bool = False
    clean_old_runs: bool = False
    failures_only: bool = False
    clean_explorations: bool = False
    keep_latest_runs: int | None = None
    older_than_days: int | None = None
    max_storage_mb: int | None = None
    dry_run: bool = False


class PruneResult(BaseModel):
    """Result of an artifact pruning execution."""
    deleted_runs: int = 0
    deleted_files: int = 0
    freed_bytes: int = 0
    freed_mb: float = 0.0
    dry_run: bool = False
    pruned_paths: list[str] = Field(default_factory=list)
    remaining_storage_bytes: int = 0
    remaining_storage_mb: float = 0.0


# ---------------------------------------------------------------------------
# Core Artifact Manager
# ---------------------------------------------------------------------------

class ArtifactManager:
    """Manages artifact inspection, retention policy enforcement, and pruning."""

    def __init__(
        self,
        recordings_dir: Path | str = "recordings",
        explorations_dir: Path | str = ".tracecase/explorations",
        db_path: Path | str = ".tracecase/studio.db",
    ) -> None:
        self.recordings_dir = Path(recordings_dir)
        self.explorations_dir = Path(explorations_dir)
        self.db_path = Path(db_path)

    # -----------------------------------------------------------------------
    # Policy Management
    # -----------------------------------------------------------------------

    def get_policy(self, custom_settings: dict[str, str] | None = None) -> RetentionPolicy:
        """Load retention policy from database app_settings or supplied dict."""
        if custom_settings is None:
            from tracecase.ui.db import get_settings
            try:
                custom_settings = get_settings(self.db_path)
            except Exception:
                custom_settings = {}

        mode = custom_settings.get("artifact_retention_mode", "all")
        if mode not in {"all", "failures_only", "none"}:
            mode = "all"

        try:
            keep_latest = int(custom_settings.get("artifact_keep_latest_runs", "10"))
        except (ValueError, TypeError):
            keep_latest = 10

        try:
            max_age = int(custom_settings.get("artifact_max_age_days", "14"))
        except (ValueError, TypeError):
            max_age = 14

        try:
            max_quota = int(custom_settings.get("artifact_max_storage_mb", "500"))
        except (ValueError, TypeError):
            max_quota = 500

        auto_prune = custom_settings.get("artifact_auto_prune_on_complete", "true").lower() in {
            "true",
            "1",
            "yes",
        }

        return RetentionPolicy(
            retention_mode=mode,
            keep_latest_runs=keep_latest,
            max_age_days=max_age,
            max_storage_mb=max_quota,
            auto_prune_on_complete=auto_prune,
        )

    def save_policy(self, policy: RetentionPolicy) -> RetentionPolicy:
        """Persist updated retention policy into database app_settings."""
        from tracecase.ui.db import update_settings

        settings_dict = {
            "artifact_retention_mode": policy.retention_mode,
            "artifact_keep_latest_runs": str(policy.keep_latest_runs),
            "artifact_max_age_days": str(policy.max_age_days),
            "artifact_max_storage_mb": str(policy.max_storage_mb),
            "artifact_auto_prune_on_complete": "true" if policy.auto_prune_on_complete else "false",
        }
        update_settings(settings_dict, self.db_path)
        return self.get_policy()

    # -----------------------------------------------------------------------
    # Storage Summary
    # -----------------------------------------------------------------------

    def get_storage_summary(self) -> StorageSummary:
        """Calculate detailed storage metrics across recordings, runs, diffs, and DB."""
        recordings_count = 0
        recordings_size = 0

        replay_runs_count = 0
        replay_runs_size = 0
        replay_screenshots_count = 0

        diffs_count = 0
        diffs_size = 0

        if self.recordings_dir.exists():
            for tc_dir in self.recordings_dir.iterdir():
                if not tc_dir.is_dir():
                    continue

                # Check if this is a testcase directory
                if (tc_dir / "testcase.json").exists():
                    recordings_count += 1

                # Walk all files inside tc_dir
                for p in tc_dir.rglob("*"):
                    if not p.is_file():
                        continue

                    sz = p.stat().st_size
                    rel_parts = p.relative_to(tc_dir).parts

                    if "replay_runs" in rel_parts:
                        replay_runs_size += sz
                        if p.suffix.lower() == ".png":
                            replay_screenshots_count += 1
                    elif "diffs" in rel_parts:
                        diffs_size += sz
                        if p.suffix.lower() == ".png":
                            diffs_count += 1
                    else:
                        # Baseline recordings, metadata, baseline screenshots
                        recordings_size += sz

                # Count distinct replay run directories
                replay_dir = tc_dir / "replay_runs"
                if replay_dir.exists() and replay_dir.is_dir():
                    replay_runs_count += sum(1 for d in replay_dir.iterdir() if d.is_dir())

        # Explorations
        explorations_count = 0
        explorations_size = 0
        if self.explorations_dir.exists() and self.explorations_dir.is_dir():
            for exp in self.explorations_dir.iterdir():
                if exp.is_dir():
                    explorations_count += 1
                    for p in exp.rglob("*"):
                        if p.is_file():
                            explorations_size += p.stat().st_size

        # Database
        db_size = 0
        if self.db_path.exists() and self.db_path.is_file():
            db_size = self.db_path.stat().st_size

        total_bytes = (
            recordings_size
            + replay_runs_size
            + diffs_size
            + explorations_size
            + db_size
        )

        return StorageSummary(
            total_size_bytes=total_bytes,
            total_size_mb=round(total_bytes / (1024 * 1024), 2),
            recordings_count=recordings_count,
            recordings_size_bytes=recordings_size,
            recordings_size_mb=round(recordings_size / (1024 * 1024), 2),
            replay_runs_count=replay_runs_count,
            replay_runs_size_bytes=replay_runs_size,
            replay_runs_size_mb=round(replay_runs_size / (1024 * 1024), 2),
            replay_screenshots_count=replay_screenshots_count,
            diffs_count=diffs_count,
            diffs_size_bytes=diffs_size,
            diffs_size_mb=round(diffs_size / (1024 * 1024), 2),
            explorations_count=explorations_count,
            explorations_size_bytes=explorations_size,
            explorations_size_mb=round(explorations_size / (1024 * 1024), 2),
            database_path=str(self.db_path.resolve()),
            database_size_bytes=db_size,
            database_size_mb=round(db_size / (1024 * 1024), 2),
            retention_policy=self.get_policy(),
        )

    # -----------------------------------------------------------------------
    # Pruning Engine
    # -----------------------------------------------------------------------

    def prune_artifacts(self, req: PruneRequest) -> PruneResult:
        """Execute or preview artifact pruning according to the specified request."""
        now = time.time()
        deleted_runs = 0
        deleted_files = 0
        freed_bytes = 0
        pruned_paths: list[str] = []

        # 1. Clean visual diffs
        if req.clean_diffs and self.recordings_dir.exists():
            for d in self.recordings_dir.rglob("diffs"):
                if d.is_dir():
                    for f in d.glob("*.png"):
                        sz = f.stat().st_size
                        freed_bytes += sz
                        deleted_files += 1
                        pruned_paths.append(str(f))
                        if not req.dry_run:
                            try:
                                f.unlink()
                            except OSError:
                                pass

        # 2. Clean explorations if requested
        if req.clean_explorations and self.explorations_dir.exists():
            for exp in self.explorations_dir.iterdir():
                if exp.is_dir():
                    dir_bytes = 0
                    dir_files = 0
                    for f in exp.rglob("*"):
                        if f.is_file():
                            dir_bytes += f.stat().st_size
                            dir_files += 1
                    freed_bytes += dir_bytes
                    deleted_files += dir_files
                    deleted_runs += 1
                    pruned_paths.append(str(exp))
                    if not req.dry_run:
                        shutil.rmtree(exp, ignore_errors=True)

        # 3. Clean Replay Runs
        if self.recordings_dir.exists():
            for tc_dir in self.recordings_dir.iterdir():
                replay_dir = tc_dir / "replay_runs"
                if not replay_dir.exists() or not replay_dir.is_dir():
                    continue

                run_dirs: list[tuple[Path, float]] = []
                for sub in replay_dir.iterdir():
                    if sub.is_dir():
                        run_dirs.append((sub, sub.stat().st_mtime))

                # Sort by modification time ascending (oldest first)
                run_dirs.sort(key=lambda x: x[1])

                # A. Failures-only mode: prune step screenshots from runs that passed
                if req.failures_only:
                    for sub, _ in run_dirs:
                        if self._is_run_passed(sub):
                            for shot in sub.rglob("*.png"):
                                if shot.is_file():
                                    sz = shot.stat().st_size
                                    freed_bytes += sz
                                    deleted_files += 1
                                    pruned_paths.append(str(shot))
                                    if not req.dry_run:
                                        try:
                                            shot.unlink()
                                        except OSError:
                                            pass

                # B. Age-based pruning
                if req.older_than_days and req.older_than_days > 0:
                    cutoff = now - (req.older_than_days * 86400)
                    remaining_run_dirs: list[tuple[Path, float]] = []
                    for sub, mtime in run_dirs:
                        if mtime < cutoff:
                            dir_bytes, file_count = self._calc_dir_files(sub)
                            freed_bytes += dir_bytes
                            deleted_files += file_count
                            deleted_runs += 1
                            pruned_paths.append(str(sub))
                            if not req.dry_run:
                                shutil.rmtree(sub, ignore_errors=True)
                        else:
                            remaining_run_dirs.append((sub, mtime))
                    run_dirs = remaining_run_dirs

                # C. Keep latest N runs per testcase
                if req.keep_latest_runs is not None and req.keep_latest_runs >= 0:
                    if len(run_dirs) > req.keep_latest_runs:
                        excess_count = len(run_dirs) - req.keep_latest_runs
                        to_prune = run_dirs[:excess_count]
                        run_dirs = run_dirs[excess_count:]
                        for sub, _ in to_prune:
                            dir_bytes, file_count = self._calc_dir_files(sub)
                            freed_bytes += dir_bytes
                            deleted_files += file_count
                            deleted_runs += 1
                            pruned_paths.append(str(sub))
                            if not req.dry_run:
                                shutil.rmtree(sub, ignore_errors=True)

                # D. Clean all old runs flag if requested
                if req.clean_old_runs and not req.older_than_days and req.keep_latest_runs is None:
                    for sub, _ in run_dirs:
                        dir_bytes, file_count = self._calc_dir_files(sub)
                        freed_bytes += dir_bytes
                        deleted_files += file_count
                        deleted_runs += 1
                        pruned_paths.append(str(sub))
                        if not req.dry_run:
                            shutil.rmtree(sub, ignore_errors=True)

        # 4. Storage Quota enforcement (FIFO across all testcase replay runs)
        if req.max_storage_mb and req.max_storage_mb > 0:
            quota_bytes = req.max_storage_mb * 1024 * 1024
            # Re-collect all replay run directories globally
            all_runs: list[tuple[Path, float, int, int]] = []
            if self.recordings_dir.exists():
                for tc_dir in self.recordings_dir.iterdir():
                    replay_dir = tc_dir / "replay_runs"
                    if replay_dir.exists() and replay_dir.is_dir():
                        for sub in replay_dir.iterdir():
                            if sub.is_dir() and str(sub) not in pruned_paths:
                                d_bytes, f_count = self._calc_dir_files(sub)
                                all_runs.append((sub, sub.stat().st_mtime, d_bytes, f_count))

            total_replay_bytes = sum(r[2] for r in all_runs)
            if total_replay_bytes > quota_bytes:
                # Sort oldest first
                all_runs.sort(key=lambda x: x[1])
                for sub, _, d_bytes, f_count in all_runs:
                    if total_replay_bytes <= quota_bytes:
                        break
                    freed_bytes += d_bytes
                    deleted_files += f_count
                    deleted_runs += 1
                    total_replay_bytes -= d_bytes
                    pruned_paths.append(str(sub))
                    if not req.dry_run:
                        shutil.rmtree(sub, ignore_errors=True)

        # Calculate remaining storage
        current_summary = self.get_storage_summary()
        remaining_bytes = (
            current_summary.total_size_bytes - freed_bytes
            if req.dry_run
            else current_summary.total_size_bytes
        )
        if remaining_bytes < 0:
            remaining_bytes = 0

        return PruneResult(
            deleted_runs=deleted_runs,
            deleted_files=deleted_files,
            freed_bytes=freed_bytes,
            freed_mb=round(freed_bytes / (1024 * 1024), 2),
            dry_run=req.dry_run,
            pruned_paths=pruned_paths,
            remaining_storage_bytes=remaining_bytes,
            remaining_storage_mb=round(remaining_bytes / (1024 * 1024), 2),
        )

    # -----------------------------------------------------------------------
    # Execution Lifecycle Hook
    # -----------------------------------------------------------------------

    def apply_execution_retention(
        self,
        output_dir: Path | str | None,
        status: str,
        testcase_dir: Path | str | None = None,
    ) -> None:
        """Apply retention policy to newly created execution run directory."""
        if not output_dir:
            return

        out_path = Path(output_dir)
        if not out_path.exists():
            return

        policy = self.get_policy()
        if not policy.auto_prune_on_complete:
            return

        # 1. Mode check
        if policy.retention_mode == "none":
            # Discard replay run folder completely
            shutil.rmtree(out_path, ignore_errors=True)
            return

        if policy.retention_mode == "failures_only" and status in {"passed", "completed"}:
            # Keep log/report/meta, prune heavy PNG screenshots
            for shot in out_path.rglob("*.png"):
                if shot.is_file():
                    try:
                        shot.unlink()
                    except OSError:
                        pass

        # 2. Keep latest N runs per testcase
        if policy.keep_latest_runs > 0 and testcase_dir:
            tc_path = Path(testcase_dir)
            replay_dir = tc_path / "replay_runs"
            if replay_dir.exists() and replay_dir.is_dir():
                sub_runs = [d for d in replay_dir.iterdir() if d.is_dir()]
                if len(sub_runs) > policy.keep_latest_runs:
                    sub_runs.sort(key=lambda d: d.stat().st_mtime)
                    excess = len(sub_runs) - policy.keep_latest_runs
                    for old_run in sub_runs[:excess]:
                        shutil.rmtree(old_run, ignore_errors=True)

    # -----------------------------------------------------------------------
    # Helper Methods
    # -----------------------------------------------------------------------

    def _calc_dir_files(self, dir_path: Path) -> tuple[int, int]:
        """Calculate total bytes and file count within a directory."""
        total_sz = 0
        total_files = 0
        for f in dir_path.rglob("*"):
            if f.is_file():
                total_sz += f.stat().st_size
                total_files += 1
        return total_sz, total_files

    def _is_run_passed(self, run_dir: Path) -> bool:
        """Determine if a replay run passed by checking its report or status in DB."""
        # 1. Check report.json or execution_log.json if present
        for report_file in ["report.json", "result.json", "execution.json"]:
            rep_path = run_dir / report_file
            if rep_path.exists():
                try:
                    data = json.loads(rep_path.read_text())
                    status = data.get("status", "").lower()
                    if status in {"passed", "completed"}:
                        return True
                    if status in {"failed", "error", "flaky"}:
                        return False
                except Exception:
                    pass

        # 2. Check DB via execution ID extracted from folder name
        # Folder format is typically: <execution_id>_att<attempt>_<ts>
        # or <batch_id>_<worker_id>_att<attempt>_<ts>
        folder_name = run_dir.name
        run_id = folder_name.split("_att")[0]
        if self.db_path.exists():
            from tracecase.ui.db import get_execution_run
            try:
                run_rec = get_execution_run(run_id, self.db_path)
                if run_rec and run_rec.get("status") in {"passed", "completed"}:
                    return True
                if run_rec and run_rec.get("status") in {"failed", "error", "flaky"}:
                    return False
            except Exception:
                pass

        # Default to False (safe approach: do not prune unless certain it passed)
        return False
