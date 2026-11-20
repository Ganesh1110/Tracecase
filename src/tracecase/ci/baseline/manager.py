"""Baseline Snapshot Manager handling SQLite persistence and historical lookups."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from tracecase.ci.baseline.models import BaselineSnapshot, BaselineTestOutcome
from tracecase.ui.db import get_connection, init_studio_db

logger = logging.getLogger("tracecase.ci.baseline.manager")


def init_baseline_db(db_path: Path | str | None = None) -> None:
    """Ensure ci_baselines and ci_drift_records tables exist in SQLite."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ci_baselines (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL DEFAULT 'default_project',
                commit_hash TEXT NOT NULL,
                branch TEXT,
                browser TEXT NOT NULL,
                testcase_id TEXT NOT NULL,
                testcase_name TEXT NOT NULL,
                test_revision_hash TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                duration_ms REAL NOT NULL DEFAULT 0.0,
                retry_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                run_id TEXT,
                batch_id TEXT,
                environment_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ci_baselines_lookup ON ci_baselines(project_id, commit_hash, browser, testcase_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ci_baselines_branch ON ci_baselines(project_id, branch, browser, testcase_id)"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ci_drift_records (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                project_id TEXT NOT NULL DEFAULT 'default_project',
                base_commit TEXT NOT NULL,
                target_commit TEXT NOT NULL,
                browser TEXT NOT NULL,
                testcase_id TEXT NOT NULL,
                testcase_name TEXT NOT NULL,
                base_status TEXT,
                pr_status TEXT NOT NULL,
                classification TEXT NOT NULL,
                test_definition_drift INTEGER NOT NULL DEFAULT 0,
                base_duration_ms REAL,
                pr_duration_ms REAL,
                duration_delta_ms REAL,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ci_drift_run ON ci_drift_records(run_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ci_drift_tc ON ci_drift_records(testcase_id)"
        )
        conn.commit()
    finally:
        conn.close()


class BaselineManager:
    """Manages storage and retrieval of verified baseline test runs."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = db_path
        init_baseline_db(db_path)

    def save_snapshot(self, snapshot: BaselineSnapshot) -> None:
        """Persist a complete baseline snapshot into SQLite."""
        conn = get_connection(self.db_path)
        env_to_save = dict(snapshot.environment)
        env_to_save["status"] = snapshot.status
        try:
            for outcome in snapshot.outcomes.values():
                record_id = f"base_{snapshot.commit_hash[:10]}_{snapshot.browser}_{outcome.testcase_id}"
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ci_baselines (
                        id, project_id, commit_hash, branch, browser,
                        testcase_id, testcase_name, test_revision_hash,
                        status, duration_ms, retry_count, error_message,
                        run_id, environment_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id,
                        snapshot.project_id,
                        snapshot.commit_hash,
                        snapshot.branch,
                        snapshot.browser,
                        outcome.testcase_id,
                        outcome.testcase_name,
                        outcome.test_revision_hash,
                        outcome.status,
                        outcome.duration_ms,
                        outcome.retry_count,
                        outcome.error_message,
                        outcome.run_id,
                        json.dumps(env_to_save),
                        snapshot.created_at,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def get_snapshot_by_commit(
        self,
        project_id: str,
        commit_hash: str,
        browser: str = "chromium",
    ) -> BaselineSnapshot | None:
        """Fetch baseline snapshot matching a specific commit hash and browser."""
        conn = get_connection(self.db_path)
        try:
            # Match on full or 7+ char short SHA prefix
            query = """
                SELECT * FROM ci_baselines
                WHERE project_id = ? AND (commit_hash = ? OR commit_hash LIKE ? || '%') AND browser = ?
                ORDER BY created_at DESC
            """
            rows = conn.execute(query, (project_id, commit_hash, commit_hash[:7], browser)).fetchall()
            if not rows:
                return None

            outcomes: dict[str, BaselineTestOutcome] = {}
            first = rows[0]
            passed_cnt = 0
            failed_cnt = 0
            flaky_cnt = 0
            error_cnt = 0

            for r in rows:
                d = dict(r)
                st = d["status"]
                if st == "passed":
                    passed_cnt += 1
                elif st == "failed":
                    failed_cnt += 1
                elif st == "flaky":
                    flaky_cnt += 1
                elif st == "error":
                    error_cnt += 1

                outcomes[d["testcase_id"]] = BaselineTestOutcome(
                    testcase_id=d["testcase_id"],
                    testcase_name=d["testcase_name"],
                    status=d["status"],
                    duration_ms=d["duration_ms"],
                    error_message=d["error_message"],
                    retry_count=d["retry_count"],
                    test_revision_hash=d["test_revision_hash"],
                    run_id=d["run_id"],
                    timestamp=d["created_at"],
                )

            env_dict = json.loads(first["environment_json"] or "{}")
            snap_status = env_dict.get("status", "completed")

            return BaselineSnapshot(
                id=f"snap_{first['commit_hash'][:8]}_{browser}",
                project_id=project_id,
                commit_hash=first["commit_hash"],
                branch=first["branch"],
                browser=browser,
                status=snap_status,
                environment=env_dict,
                created_at=first["created_at"],
                total_tests=len(outcomes),
                passed_count=passed_cnt,
                failed_count=failed_cnt,
                flaky_count=flaky_cnt,
                error_count=error_cnt,
                outcomes=outcomes,
            )
        finally:
            conn.close()

    def get_latest_branch_snapshot(
        self,
        project_id: str,
        branch: str,
        browser: str = "chromium",
    ) -> BaselineSnapshot | None:
        """Fetch the most recent baseline snapshot recorded for a base branch (e.g. main)."""
        clean_branch = branch.replace("origin/", "").strip()
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT commit_hash FROM ci_baselines
                WHERE project_id = ? AND (branch = ? OR branch = ?) AND browser = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (project_id, branch, clean_branch, browser),
            ).fetchone()
            if not row:
                return None
            return self.get_snapshot_by_commit(project_id, row["commit_hash"], browser)
        finally:
            conn.close()
