"""SQLite persistence layer for Tracecase Studio (Projects, Suites, Executions, Settings)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tracecase.models import TestCase

DEFAULT_STUDIO_DB_PATH = Path(".tracecase") / "studio.db"


def get_db_path(custom_path: Path | str | None = None) -> Path:
    """Resolve database path, ensuring parent directory exists."""
    if custom_path:
        p = Path(custom_path)
    else:
        p = DEFAULT_STUDIO_DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create a SQLite connection configured with WAL and dict-like row factory."""
    path = get_db_path(db_path)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_studio_db(db_path: Path | str | None = None) -> None:
    """Initialize database schema with tables for projects, suites, executions, and settings."""
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                settings_json TEXT DEFAULT '{}'
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_suites (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                testcase_ids_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS testcases_meta (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                start_url TEXT NOT NULL,
                browser TEXT NOT NULL DEFAULT 'chromium',
                total_steps INTEGER NOT NULL DEFAULT 0,
                total_duration REAL NOT NULL DEFAULT 0.0,
                folder_path TEXT NOT NULL,
                file_path TEXT NOT NULL,
                tags_json TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )

        try:
            cursor = conn.execute("PRAGMA table_info(testcases_meta)")
            cols = [row["name"] for row in cursor.fetchall()]
            if "approval_status" not in cols:
                conn.execute(
                    "ALTER TABLE testcases_meta ADD COLUMN approval_status TEXT NOT NULL DEFAULT 'approved'"
                )
            if "provenance_json" not in cols:
                conn.execute(
                    "ALTER TABLE testcases_meta ADD COLUMN provenance_json TEXT DEFAULT '{}'"
                )
        except Exception:
            pass

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_runs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                suite_id TEXT,
                testcase_id TEXT NOT NULL,
                testcase_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                browser TEXT NOT NULL DEFAULT 'chromium',
                headed INTEGER NOT NULL DEFAULT 0,
                heal INTEGER NOT NULL DEFAULT 1,
                assertions INTEGER NOT NULL DEFAULT 1,
                visual_diff INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                duration_ms REAL DEFAULT 0.0,
                passed_steps INTEGER DEFAULT 0,
                failed_steps INTEGER DEFAULT 0,
                total_steps INTEGER DEFAULT 0,
                exit_code INTEGER DEFAULT 0,
                error_message TEXT,
                report_path TEXT,
                logs_json TEXT DEFAULT '[]'
            )
            """
        )

        try:
            cursor = conn.execute("PRAGMA table_info(execution_runs)")
            cols = [row["name"] for row in cursor.fetchall()]
            if "batch_id" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN batch_id TEXT")
            if "worker_id" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN worker_id TEXT")
            if "concurrency" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN concurrency INTEGER DEFAULT 1")
            if "matrix_id" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN matrix_id TEXT")
            if "retries" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN retries INTEGER DEFAULT 0")
            if "attempt_count" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN attempt_count INTEGER DEFAULT 1")
            if "retry_history_json" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN retry_history_json TEXT DEFAULT '[]'")
            if "failure_step" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN failure_step INTEGER")
            if "failure_selector" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN failure_selector TEXT")
            if "queue_wait_ms" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN queue_wait_ms REAL DEFAULT 0.0")
            if "browser_startup_ms" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN browser_startup_ms REAL DEFAULT 0.0")
            if "execution_duration_ms" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN execution_duration_ms REAL DEFAULT 0.0")
            if "teardown_ms" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN teardown_ms REAL DEFAULT 0.0")
            if "memory_rss_mb" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN memory_rss_mb REAL DEFAULT 0.0")
            if "cpu_percent" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN cpu_percent REAL DEFAULT 0.0")
            if "load_average" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN load_average REAL DEFAULT 0.0")
            if "artifact_size_bytes" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN artifact_size_bytes INTEGER DEFAULT 0")
        except Exception:
            pass

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_attempts (
                id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                duration_ms REAL DEFAULT 0.0,
                error_message TEXT,
                failed_step INTEGER,
                failed_selector TEXT,
                report_path TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (execution_id) REFERENCES execution_runs(id) ON DELETE CASCADE
            )
            """
        )

        try:
            a_cursor = conn.execute("PRAGMA table_info(execution_attempts)")
            a_cols = [row["name"] for row in a_cursor.fetchall()]
            if "browser_startup_ms" not in a_cols:
                conn.execute("ALTER TABLE execution_attempts ADD COLUMN browser_startup_ms REAL DEFAULT 0.0")
            if "execution_duration_ms" not in a_cols:
                conn.execute("ALTER TABLE execution_attempts ADD COLUMN execution_duration_ms REAL DEFAULT 0.0")
            if "teardown_ms" not in a_cols:
                conn.execute("ALTER TABLE execution_attempts ADD COLUMN teardown_ms REAL DEFAULT 0.0")
            if "memory_rss_mb" not in a_cols:
                conn.execute("ALTER TABLE execution_attempts ADD COLUMN memory_rss_mb REAL DEFAULT 0.0")
            if "artifact_size_bytes" not in a_cols:
                conn.execute("ALTER TABLE execution_attempts ADD COLUMN artifact_size_bytes INTEGER DEFAULT 0")
        except Exception:
            pass

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_batches (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                suite_id TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                concurrency INTEGER NOT NULL DEFAULT 2,
                total_tests INTEGER NOT NULL DEFAULT 0,
                passed_tests INTEGER NOT NULL DEFAULT 0,
                failed_tests INTEGER NOT NULL DEFAULT 0,
                cancelled_tests INTEGER NOT NULL DEFAULT 0,
                flaky_tests INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                duration_ms REAL DEFAULT 0.0,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )

        try:
            b_cursor = conn.execute("PRAGMA table_info(execution_batches)")
            b_cols = [row["name"] for row in b_cursor.fetchall()]
            if "flaky_tests" not in b_cols:
                conn.execute("ALTER TABLE execution_batches ADD COLUMN flaky_tests INTEGER DEFAULT 0")
            if "queue_wait_ms" not in b_cols:
                conn.execute("ALTER TABLE execution_batches ADD COLUMN queue_wait_ms REAL DEFAULT 0.0")
            if "avg_startup_ms" not in b_cols:
                conn.execute("ALTER TABLE execution_batches ADD COLUMN avg_startup_ms REAL DEFAULT 0.0")
            if "artifact_size_bytes" not in b_cols:
                conn.execute("ALTER TABLE execution_batches ADD COLUMN artifact_size_bytes INTEGER DEFAULT 0")
        except Exception:
            pass

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_matrices (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                suite_id TEXT,
                name TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                concurrency INTEGER NOT NULL DEFAULT 2,
                browsers_json TEXT NOT NULL DEFAULT '["chromium"]',
                total_executions INTEGER NOT NULL DEFAULT 0,
                passed_executions INTEGER NOT NULL DEFAULT 0,
                failed_executions INTEGER NOT NULL DEFAULT 0,
                cancelled_executions INTEGER NOT NULL DEFAULT 0,
                flaky_executions INTEGER NOT NULL DEFAULT 0,
                divergence_count INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                duration_ms REAL DEFAULT 0.0,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )

        try:
            m_cursor = conn.execute("PRAGMA table_info(execution_matrices)")
            m_cols = [row["name"] for row in m_cursor.fetchall()]
            if "flaky_executions" not in m_cols:
                conn.execute("ALTER TABLE execution_matrices ADD COLUMN flaky_executions INTEGER DEFAULT 0")
            if "queue_wait_ms" not in m_cols:
                conn.execute("ALTER TABLE execution_matrices ADD COLUMN queue_wait_ms REAL DEFAULT 0.0")
            if "avg_startup_ms" not in m_cols:
                conn.execute("ALTER TABLE execution_matrices ADD COLUMN avg_startup_ms REAL DEFAULT 0.0")
            if "artifact_size_bytes" not in m_cols:
                conn.execute("ALTER TABLE execution_matrices ADD COLUMN artifact_size_bytes INTEGER DEFAULT 0")
        except Exception:
            pass

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_step_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT NOT NULL,
                step_number INTEGER NOT NULL,
                action_type TEXT,
                status TEXT NOT NULL,
                duration_ms REAL DEFAULT 0.0,
                selector_used TEXT,
                healed_from TEXT,
                error TEXT,
                screenshot_path TEXT,
                visual_diff_json TEXT,
                assertions_json TEXT DEFAULT '[]',
                FOREIGN KEY (execution_id) REFERENCES execution_runs(id) ON DELETE CASCADE
            )
            """
        )

        try:
            cursor = conn.execute("PRAGMA table_info(execution_step_logs)")
            cols = [row["name"] for row in cursor.fetchall()]
            if "assertions_json" not in cols:
                conn.execute("ALTER TABLE execution_step_logs ADD COLUMN assertions_json TEXT DEFAULT '[]'")
        except Exception:
            pass

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_analyses (
                id TEXT PRIMARY KEY,
                testcase_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                model_used TEXT,
                summary TEXT,
                risk_score INTEGER DEFAULT 0,
                raw_analysis_json TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exploration_runs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                start_url TEXT NOT NULL,
                allowed_origins_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'running',
                max_depth INTEGER NOT NULL DEFAULT 3,
                max_pages INTEGER NOT NULL DEFAULT 20,
                max_interactions INTEGER NOT NULL DEFAULT 50,
                execution_timeout REAL NOT NULL DEFAULT 120.0,
                created_at TEXT NOT NULL,
                finished_at TEXT,
                pages_discovered INTEGER NOT NULL DEFAULT 0,
                transitions_discovered INTEGER NOT NULL DEFAULT 0,
                forms_discovered INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                config_json TEXT DEFAULT '{}',
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exploration_pages (
                id TEXT PRIMARY KEY,
                exploration_id TEXT NOT NULL,
                url TEXT NOT NULL,
                normalized_url TEXT NOT NULL,
                title TEXT,
                depth INTEGER NOT NULL DEFAULT 0,
                state_fingerprint TEXT NOT NULL,
                status_code INTEGER DEFAULT 200,
                forms_json TEXT DEFAULT '[]',
                interactive_elements_json TEXT DEFAULT '[]',
                links_json TEXT DEFAULT '[]',
                screenshot_path TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (exploration_id) REFERENCES exploration_runs(id) ON DELETE CASCADE
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS synthesized_drafts (
                id TEXT PRIMARY KEY,
                exploration_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                journey_type TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'medium',
                start_url TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                approved_testcase_id TEXT,
                rejection_reason TEXT,
                requires_human_input INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                FOREIGN KEY (exploration_id) REFERENCES exploration_runs(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )

        # Test-to-Code Mapping Table (Phase 7.5.2)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_code_mappings (
                id TEXT PRIMARY KEY,
                testcase_id TEXT NOT NULL,
                testcase_name TEXT NOT NULL DEFAULT '',
                project_id TEXT NOT NULL DEFAULT 'default_project',
                file_path TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                matched_entity TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                evidence_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tc_mappings_testcase ON test_code_mappings(testcase_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tc_mappings_file ON test_code_mappings(file_path)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tc_mappings_relation ON test_code_mappings(relation_type)"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exploration_transitions (
                id TEXT PRIMARY KEY,
                exploration_id TEXT NOT NULL,
                source_url TEXT NOT NULL,
                target_url TEXT NOT NULL,
                action_type TEXT NOT NULL,
                selector TEXT,
                element_text TEXT,
                is_safe INTEGER NOT NULL DEFAULT 1,
                duration_ms REAL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (exploration_id) REFERENCES exploration_runs(id) ON DELETE CASCADE
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS synthesized_drafts (
                id TEXT PRIMARY KEY,
                exploration_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                journey_type TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'medium',
                start_url TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                approved_testcase_id TEXT,
                rejection_reason TEXT,
                requires_human_input INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                FOREIGN KEY (exploration_id) REFERENCES exploration_runs(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )

        # Predictive Risk Snapshots Table (Phase 7.5.3)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_risk_snapshots (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL DEFAULT 'default_project',
                commit_hash TEXT,
                branch TEXT,
                testcase_id TEXT NOT NULL,
                testcase_name TEXT NOT NULL DEFAULT '',
                risk_score REAL NOT NULL,
                risk_tier TEXT NOT NULL,
                mapping_confidence REAL NOT NULL,
                primary_driver TEXT NOT NULL,
                breakdown_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_risk_snapshots_commit ON test_risk_snapshots(commit_hash)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_risk_snapshots_tc ON test_risk_snapshots(testcase_id)"
        )

        # Ensure default project exists
        default_proj = conn.execute(
            "SELECT id FROM projects WHERE id = 'default_project'"
        ).fetchone()
        if not default_proj:
            now = datetime.now().isoformat()
            conn.execute(
                """
                INSERT INTO projects (id, name, description, created_at, updated_at, settings_json)
                VALUES ('default_project', 'Tracecase', 'Default testing workspace', ?, ?, '{}')
                """,
                (now, now),
            )

        # Set default settings if not populated
        default_settings = {
            "default_browser": "chromium",
            "default_timeout": "30000",
            "ai_provider": "ollama",
            "ai_model": "llama3",
            "ai_api_base": "http://localhost:11434/v1",
            "ai_api_key": "",
            "theme": "dark",
            "artifact_retention_mode": "all",
            "artifact_keep_latest_runs": "10",
            "artifact_max_age_days": "14",
            "artifact_max_storage_mb": "500",
            "artifact_auto_prune_on_complete": "true",
        }
        for k, v in default_settings.items():
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
                (k, v),
            )
    conn.close()


# ---------------------------------------------------------------------------
# Project Operations
# ---------------------------------------------------------------------------

def list_projects(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """List all projects with test case counts."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT p.*,
                   (SELECT COUNT(*) FROM testcases_meta tm WHERE tm.project_id = p.id) AS testcase_count,
                   (SELECT COUNT(*) FROM test_suites ts WHERE ts.project_id = p.id) AS suite_count
            FROM projects p
            ORDER BY p.created_at ASC
            """
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["settings"] = json.loads(d.get("settings_json") or "{}")
            result.append(d)
        return result
    finally:
        conn.close()


def get_project(project_id: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    """Fetch project by ID."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["settings"] = json.loads(d.get("settings_json") or "{}")
        return d
    finally:
        conn.close()


def create_project(
    name: str,
    description: str = "",
    settings: dict[str, Any] | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Create a new project workspace."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    project_id = f"proj_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    settings_json = json.dumps(settings or {})
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, description, created_at, updated_at, settings_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, name, description, now, now, settings_json),
            )
        return {
            "id": project_id,
            "name": name,
            "description": description,
            "created_at": now,
            "updated_at": now,
            "settings": settings or {},
            "testcase_count": 0,
            "suite_count": 0,
        }
    finally:
        conn.close()


def update_project(
    project_id: str,
    name: str | None = None,
    description: str | None = None,
    settings: dict[str, Any] | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Update project details."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    try:
        existing = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not existing:
            return None
        new_name = name if name is not None else existing["name"]
        new_desc = description if description is not None else existing["description"]
        new_settings = (
            json.dumps(settings)
            if settings is not None
            else existing["settings_json"]
        )
        with conn:
            conn.execute(
                """
                UPDATE projects
                SET name = ?, description = ?, settings_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_name, new_desc, new_settings, now, project_id),
            )
        return get_project(project_id, db_path)
    finally:
        conn.close()


def delete_project(
    project_id: str,
    force: bool = False,
    db_path: Path | str | None = None,
) -> bool:
    """Delete a project workspace and related metadata (except default_project).

    Raises ValueError if project contains test cases/suites and force is False.
    """
    if project_id == "default_project":
        return False
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        existing = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not existing:
            return False

        tc_count = conn.execute(
            "SELECT COUNT(*) FROM testcases_meta WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
        suite_count = conn.execute(
            "SELECT COUNT(*) FROM test_suites WHERE project_id = ?", (project_id,)
        ).fetchone()[0]

        if (tc_count > 0 or suite_count > 0) and not force:
            raise ValueError(
                f"Project contains {tc_count} test case(s) and {suite_count} suite(s). Pass force=true to confirm deletion."
            )

        with conn:
            conn.execute("DELETE FROM testcases_meta WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM test_suites WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM execution_runs WHERE project_id = ?", (project_id,))
            res = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            return res.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test Suite Operations
# ---------------------------------------------------------------------------

def list_suites(project_id: str | None = None, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """List test suites optionally filtered by project."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        if project_id:
            rows = conn.execute(
                "SELECT * FROM test_suites WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM test_suites ORDER BY created_at DESC").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["testcase_ids"] = json.loads(d.get("testcase_ids_json") or "[]")
            d["total_cases"] = len(d["testcase_ids"])
            result.append(d)
        return result
    finally:
        conn.close()


def get_suite(suite_id: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    """Get single test suite by ID, including aggregated execution metrics."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM test_suites WHERE id = ?", (suite_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["testcase_ids"] = json.loads(d.get("testcase_ids_json") or "[]")
        d["total_cases"] = len(d["testcase_ids"])

        # Aggregated execution summary
        exec_rows = conn.execute(
            """
            SELECT status, started_at FROM execution_runs
            WHERE suite_id = ?
            ORDER BY started_at DESC
            """,
            (suite_id,),
        ).fetchall()
        total_runs = len(exec_rows)
        passed_runs = sum(1 for r in exec_rows if r["status"] == "passed")
        failed_runs = sum(1 for r in exec_rows if r["status"] in ("failed", "error"))
        d["total_runs"] = total_runs
        d["passed_runs"] = passed_runs
        d["failed_runs"] = failed_runs
        d["last_run_at"] = exec_rows[0]["started_at"] if exec_rows else None
        d["pass_rate"] = round((passed_runs / total_runs * 100), 1) if total_runs > 0 else None
        return d
    finally:
        conn.close()


def create_suite(
    name: str,
    project_id: str = "default_project",
    description: str = "",
    testcase_ids: list[str] | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Create a new test suite with deduplicated test case IDs."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    suite_id = f"suite_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    # Deduplicate testcase_ids preserving insertion order
    tc_ids = list(dict.fromkeys(testcase_ids or []))
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO test_suites (id, project_id, name, description, testcase_ids_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (suite_id, project_id, name, description, json.dumps(tc_ids), now, now),
            )
        return {
            "id": suite_id,
            "project_id": project_id,
            "name": name,
            "description": description,
            "testcase_ids": tc_ids,
            "total_cases": len(tc_ids),
            "created_at": now,
            "updated_at": now,
        }
    finally:
        conn.close()


def update_suite(
    suite_id: str,
    name: str | None = None,
    description: str | None = None,
    testcase_ids: list[str] | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Update test suite details or included test case IDs with deduplication."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    try:
        existing = conn.execute("SELECT * FROM test_suites WHERE id = ?", (suite_id,)).fetchone()
        if not existing:
            return None
        new_name = name if name is not None else existing["name"]
        new_desc = description if description is not None else existing["description"]
        if testcase_ids is not None:
            deduped = list(dict.fromkeys(testcase_ids))
            new_tc_ids = json.dumps(deduped)
        else:
            new_tc_ids = existing["testcase_ids_json"]
        with conn:
            conn.execute(
                """
                UPDATE test_suites
                SET name = ?, description = ?, testcase_ids_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_name, new_desc, new_tc_ids, now, suite_id),
            )
        return get_suite(suite_id, db_path)
    finally:
        conn.close()


def get_testcase_meta(
    testcase_id: str, db_path: Path | str | None = None
) -> dict[str, Any] | None:
    """Retrieve metadata record for a testcase."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM testcases_meta WHERE id = ?", (testcase_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["tags"] = json.loads(d.get("tags_json") or "[]")
        d["provenance"] = json.loads(d.get("provenance_json") or "{}")
        return d
    finally:
        conn.close()


def add_testcase_to_suite(
    suite_id: str,
    testcase_id: str,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Add a testcase to a suite, preventing duplicates and blocking unapproved drafts."""
    meta = get_testcase_meta(testcase_id, db_path)
    if meta and meta.get("approval_status") == "draft":
        raise ValueError(f"Cannot add unapproved draft testcase '{testcase_id}' to a suite.")

    suite = get_suite(suite_id, db_path)
    if not suite:
        return None
    ids = suite.get("testcase_ids", [])
    if testcase_id not in ids:
        ids.append(testcase_id)
        return update_suite(suite_id=suite_id, testcase_ids=ids, db_path=db_path)
    return suite


def remove_testcase_from_suite(
    suite_id: str,
    testcase_id: str,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Remove a testcase from a suite."""
    suite = get_suite(suite_id, db_path)
    if not suite:
        return None
    ids = [i for i in suite.get("testcase_ids", []) if i != testcase_id]
    return update_suite(suite_id=suite_id, testcase_ids=ids, db_path=db_path)


def delete_suite(suite_id: str, db_path: Path | str | None = None) -> bool:
    """Delete a test suite."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            res = conn.execute("DELETE FROM test_suites WHERE id = ?", (suite_id,))
            return res.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test Case Metadata Synchronization
# ---------------------------------------------------------------------------

def sync_testcase_meta(
    testcase: TestCase,
    file_path: Path | str,
    project_id: str = "default_project",
    tags: list[str] | None = None,
    approval_status: str = "approved",
    provenance: dict[str, Any] | None = None,
    db_path: Path | str | None = None,
) -> None:
    """Upsert testcase metadata into testcases_meta."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    fpath = Path(file_path).resolve()
    folder_path = str(fpath.parent)
    tags_json = json.dumps(tags or [])
    prov_json = json.dumps(provenance or {})
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO testcases_meta (
                    id, project_id, name, description, start_url, browser,
                    total_steps, total_duration, folder_path, file_path, tags_json,
                    approval_status, provenance_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    start_url = excluded.start_url,
                    browser = excluded.browser,
                    total_steps = excluded.total_steps,
                    total_duration = excluded.total_duration,
                    folder_path = excluded.folder_path,
                    file_path = excluded.file_path,
                    approval_status = excluded.approval_status,
                    provenance_json = excluded.provenance_json,
                    updated_at = excluded.updated_at
                """,
                (
                    testcase.id,
                    project_id,
                    testcase.name,
                    getattr(testcase, "description", ""),
                    testcase.start_url,
                    testcase.browser,
                    testcase.total_steps,
                    testcase.total_duration,
                    folder_path,
                    str(fpath),
                    tags_json,
                    approval_status,
                    prov_json,
                    testcase.created_at.isoformat() if hasattr(testcase.created_at, "isoformat") else str(testcase.created_at),
                    now,
                ),
            )
    finally:
        conn.close()


def sync_all_testcases_from_disk(
    search_paths: list[Path] | None = None,
    db_path: Path | str | None = None,
) -> int:
    """Scan disk for testcase.json files and sync their metadata into SQLite."""
    if search_paths is None:
        search_paths = [Path("recordings"), Path(".")]

    synced_count = 0
    seen_ids: set[str] = set()

    for base in search_paths:
        if not base.exists():
            continue
        for p in base.glob("**/testcase.json"):
            try:
                content = p.read_text(encoding="utf-8")
                tc = TestCase.model_validate_json(content)
                if tc.id not in seen_ids:
                    seen_ids.add(tc.id)
                    sync_testcase_meta(tc, p, project_id="default_project", db_path=db_path)
                    synced_count += 1
            except Exception:
                continue
    return synced_count


# ---------------------------------------------------------------------------
# Execution Runs & Step Logs
# ---------------------------------------------------------------------------

def create_execution_run(
    testcase_id: str,
    testcase_name: str,
    project_id: str = "default_project",
    suite_id: str | None = None,
    browser: str = "chromium",
    headed: bool = False,
    heal: bool = True,
    assertions: bool = True,
    visual_diff: bool = False,
    batch_id: str | None = None,
    worker_id: str | None = None,
    concurrency: int = 1,
    matrix_id: str | None = None,
    retries: int = 0,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Register a new test execution run in queued status."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    exec_id = f"run_{uuid.uuid4().hex[:10]}"
    now = datetime.now().isoformat()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO execution_runs (
                    id, project_id, suite_id, testcase_id, testcase_name, status,
                    browser, headed, heal, assertions, visual_diff, started_at,
                    batch_id, worker_id, concurrency, matrix_id, retries, attempt_count
                )
                VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    exec_id,
                    project_id,
                    suite_id,
                    testcase_id,
                    testcase_name,
                    browser,
                    1 if headed else 0,
                    1 if heal else 0,
                    1 if assertions else 0,
                    1 if visual_diff else 0,
                    now,
                    batch_id,
                    worker_id,
                    concurrency,
                    matrix_id,
                    retries,
                ),
            )
        return get_execution_run(exec_id, db_path) or {}
    finally:
        conn.close()


def update_execution_run_status(
    execution_id: str,
    status: str,
    finished_at: str | None = None,
    duration_ms: float | None = None,
    passed_steps: int | None = None,
    failed_steps: int | None = None,
    total_steps: int | None = None,
    exit_code: int | None = None,
    error_message: str | None = None,
    report_path: str | None = None,
    logs: list[str] | None = None,
    worker_id: str | None = None,
    batch_id: str | None = None,
    matrix_id: str | None = None,
    attempt_count: int | None = None,
    retry_history: list[dict[str, Any]] | None = None,
    failure_step: int | None = None,
    failure_selector: str | None = None,
    queue_wait_ms: float | None = None,
    browser_startup_ms: float | None = None,
    execution_duration_ms: float | None = None,
    teardown_ms: float | None = None,
    memory_rss_mb: float | None = None,
    cpu_percent: float | None = None,
    load_average: float | None = None,
    artifact_size_bytes: int | None = None,
    db_path: Path | str | None = None,
) -> None:
    """Update execution run results."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        updates = ["status = ?"]
        params: list[Any] = [status]

        if finished_at is not None:
            updates.append("finished_at = ?")
            params.append(finished_at)
        if duration_ms is not None:
            updates.append("duration_ms = ?")
            params.append(duration_ms)
        if passed_steps is not None:
            updates.append("passed_steps = ?")
            params.append(passed_steps)
        if failed_steps is not None:
            updates.append("failed_steps = ?")
            params.append(failed_steps)
        if total_steps is not None:
            updates.append("total_steps = ?")
            params.append(total_steps)
        if exit_code is not None:
            updates.append("exit_code = ?")
            params.append(exit_code)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        if report_path is not None:
            updates.append("report_path = ?")
            params.append(report_path)
        if logs is not None:
            updates.append("logs_json = ?")
            params.append(json.dumps(logs))
        if worker_id is not None:
            updates.append("worker_id = ?")
            params.append(worker_id)
        if batch_id is not None:
            updates.append("batch_id = ?")
            params.append(batch_id)
        if matrix_id is not None:
            updates.append("matrix_id = ?")
            params.append(matrix_id)
        if attempt_count is not None:
            updates.append("attempt_count = ?")
            params.append(attempt_count)
        if retry_history is not None:
            updates.append("retry_history_json = ?")
            params.append(json.dumps(retry_history))
        if failure_step is not None:
            updates.append("failure_step = ?")
            params.append(failure_step)
        if failure_selector is not None:
            updates.append("failure_selector = ?")
            params.append(failure_selector)
        if queue_wait_ms is not None:
            updates.append("queue_wait_ms = ?")
            params.append(queue_wait_ms)
        if browser_startup_ms is not None:
            updates.append("browser_startup_ms = ?")
            params.append(browser_startup_ms)
        if execution_duration_ms is not None:
            updates.append("execution_duration_ms = ?")
            params.append(execution_duration_ms)
        if teardown_ms is not None:
            updates.append("teardown_ms = ?")
            params.append(teardown_ms)
        if memory_rss_mb is not None:
            updates.append("memory_rss_mb = ?")
            params.append(memory_rss_mb)
        if cpu_percent is not None:
            updates.append("cpu_percent = ?")
            params.append(cpu_percent)
        if load_average is not None:
            updates.append("load_average = ?")
            params.append(load_average)
        if artifact_size_bytes is not None:
            updates.append("artifact_size_bytes = ?")
            params.append(artifact_size_bytes)

        params.append(execution_id)
        with conn:
            conn.execute(
                f"UPDATE execution_runs SET {', '.join(updates)} WHERE id = ?",
                params,
            )
    finally:
        conn.close()


def log_execution_step(
    execution_id: str,
    step_number: int,
    action_type: str | None,
    status: str,
    duration_ms: float = 0.0,
    selector_used: str | None = None,
    healed_from: str | None = None,
    error: str | None = None,
    screenshot_path: str | None = None,
    visual_diff: dict[str, Any] | None = None,
    assertions: list[dict[str, Any]] | None = None,
    db_path: Path | str | None = None,
) -> None:
    """Log individual step result into execution_step_logs."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    vdiff_json = json.dumps(visual_diff) if visual_diff else None
    asserts_json = json.dumps(assertions or [])
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO execution_step_logs (
                    execution_id, step_number, action_type, status, duration_ms,
                    selector_used, healed_from, error, screenshot_path, visual_diff_json,
                    assertions_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    step_number,
                    action_type,
                    status,
                    duration_ms,
                    selector_used,
                    healed_from,
                    error,
                    screenshot_path,
                    vdiff_json,
                    asserts_json,
                ),
            )
    finally:
        conn.close()


def get_execution_run(execution_id: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    """Fetch complete execution run with step logs, attempts, and retry history."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM execution_runs WHERE id = ?", (execution_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["logs"] = json.loads(d.get("logs_json") or "[]")
        d["retry_history"] = json.loads(d.get("retry_history_json") or "[]")
        # Fetch step logs
        step_rows = conn.execute(
            """
            SELECT * FROM execution_step_logs
            WHERE execution_id = ?
            ORDER BY step_number ASC
            """,
            (execution_id,),
        ).fetchall()
        steps = []
        for sr in step_rows:
            sd = dict(sr)
            sd["visual_diff"] = json.loads(sd.get("visual_diff_json") or "null")
            sd["assertions"] = json.loads(sd.get("assertions_json") or "[]")
            steps.append(sd)
        d["step_logs"] = steps

        # Fetch execution attempts
        attempt_rows = conn.execute(
            """
            SELECT * FROM execution_attempts
            WHERE execution_id = ?
            ORDER BY attempt_number ASC
            """,
            (execution_id,),
        ).fetchall()
        d["attempts"] = [dict(ar) for ar in attempt_rows]

        return d
    finally:
        conn.close()


def list_execution_runs(
    project_id: str | None = None,
    testcase_id: str | None = None,
    suite_id: str | None = None,
    status: str | None = None,
    batch_id: str | None = None,
    worker_id: str | None = None,
    matrix_id: str | None = None,
    limit: int = 50,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """List execution runs with optional filters."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        query = "SELECT * FROM execution_runs WHERE 1=1"
        params: list[Any] = []
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if testcase_id:
            query += " AND testcase_id = ?"
            params.append(testcase_id)
        if suite_id:
            query += " AND suite_id = ?"
            params.append(suite_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        if batch_id:
            query += " AND batch_id = ?"
            params.append(batch_id)
        if worker_id:
            query += " AND worker_id = ?"
            params.append(worker_id)
        if matrix_id:
            query += " AND matrix_id = ?"
            params.append(matrix_id)

        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["logs"] = json.loads(d.get("logs_json") or "[]")
            d["retry_history"] = json.loads(d.get("retry_history_json") or "[]")
            result.append(d)
        return result
    finally:
        conn.close()


def record_execution_attempt(
    execution_id: str,
    attempt_number: int,
    status: str,
    duration_ms: float = 0.0,
    error_message: str | None = None,
    failed_step: int | None = None,
    failed_selector: str | None = None,
    report_path: str | None = None,
    browser_startup_ms: float = 0.0,
    execution_duration_ms: float = 0.0,
    teardown_ms: float = 0.0,
    memory_rss_mb: float = 0.0,
    artifact_size_bytes: int = 0,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Record an individual execution attempt permanently with telemetry metrics."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    attempt_id = f"att_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO execution_attempts (
                    id, execution_id, attempt_number, status, duration_ms,
                    error_message, failed_step, failed_selector, report_path, created_at,
                    browser_startup_ms, execution_duration_ms, teardown_ms, memory_rss_mb, artifact_size_bytes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    execution_id,
                    attempt_number,
                    status,
                    duration_ms,
                    error_message,
                    failed_step,
                    failed_selector,
                    report_path,
                    now_iso,
                    browser_startup_ms,
                    execution_duration_ms,
                    teardown_ms,
                    memory_rss_mb,
                    artifact_size_bytes,
                ),
            )
        return {
            "id": attempt_id,
            "execution_id": execution_id,
            "attempt_number": attempt_number,
            "status": status,
            "duration_ms": duration_ms,
            "error_message": error_message,
            "failed_step": failed_step,
            "failed_selector": failed_selector,
            "report_path": report_path,
            "browser_startup_ms": browser_startup_ms,
            "execution_duration_ms": execution_duration_ms,
            "teardown_ms": teardown_ms,
            "memory_rss_mb": memory_rss_mb,
            "artifact_size_bytes": artifact_size_bytes,
            "created_at": now_iso,
        }
    finally:
        conn.close()


def get_execution_attempts(execution_id: str, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """Fetch all recorded attempts for an execution run."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT * FROM execution_attempts
            WHERE execution_id = ?
            ORDER BY attempt_number ASC
            """,
            (execution_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_testcase_flakiness_stats(
    testcase_id: str,
    limit: int = 30,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Calculate flakiness rate, first-attempt pass rate, final pass rate, failure rate,
    stability score, and per-browser breakdown across historical runs."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, status, browser, attempt_count, retries, duration_ms,
                   error_message, failure_step, failure_selector, started_at, finished_at
            FROM execution_runs
            WHERE testcase_id = ? AND status IN ('passed', 'flaky', 'failed', 'error')
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (testcase_id, limit),
        ).fetchall()

        runs = [dict(r) for r in rows]
        total_runs = len(runs)
        flaky_runs = sum(1 for r in runs if r["status"] == "flaky")
        passed_runs = sum(1 for r in runs if r["status"] == "passed")
        failed_runs = sum(1 for r in runs if r["status"] == "failed")
        error_runs = sum(1 for r in runs if r["status"] == "error")

        # 1. Flakiness rate: Percentage of runs that recover after retry
        flakiness_rate = round((flaky_runs / total_runs) * 100, 1) if total_runs > 0 else 0.0
        flakiness_score = flakiness_rate  # Backward compatibility alias

        # 2. First-attempt pass rate: Percentage passing without retries
        first_attempt_pass_rate = round((passed_runs / total_runs) * 100, 1) if total_runs > 0 else 0.0

        # 3. Final pass rate: Percentage passing after all retries
        final_pass_rate = round(((passed_runs + flaky_runs) / total_runs) * 100, 1) if total_runs > 0 else 0.0

        # 4. Failure rate: Percentage ultimately failing
        failure_rate = round(((failed_runs + error_runs) / total_runs) * 100, 1) if total_runs > 0 else 0.0

        # 5. Stability score: Consistency of outcomes across repeated runs
        # Measures modal outcome dominance across terminal outcomes ('passed', 'flaky', 'failed', 'error')
        max_outcome_count = max(passed_runs, flaky_runs, failed_runs, error_runs) if total_runs > 0 else 0
        stability_score = round((max_outcome_count / total_runs) * 100, 1) if total_runs > 0 else 100.0

        # Reliability score: Failure-free operation without retries (first-attempt pass rate)
        # Never defined as 100 - flakiness_score (a consistently failing test has 0% reliability).
        reliability_score = first_attempt_pass_rate

        if total_runs == 0:
            rating = "untested"
        elif final_pass_rate == 0.0:
            rating = "failing"
        elif flakiness_rate == 0.0:
            rating = "stable"
        elif flakiness_rate <= 15.0:
            rating = "low"
        elif flakiness_rate <= 40.0:
            rating = "moderate"
        else:
            rating = "high"

        # Per-browser breakdown
        browsers: dict[str, dict[str, Any]] = {}
        for r in runs:
            b = r.get("browser") or "chromium"
            if b not in browsers:
                browsers[b] = {
                    "total": 0,
                    "flaky": 0,
                    "passed": 0,
                    "failed": 0,
                    "error": 0,
                    "flakiness_rate": 0.0,
                    "flakiness_score": 0.0,
                    "first_attempt_pass_rate": 0.0,
                    "final_pass_rate": 0.0,
                    "failure_rate": 0.0,
                    "stability_score": 100.0,
                    "reliability_score": 0.0,
                }
            browsers[b]["total"] += 1
            st = r["status"]
            if st in browsers[b]:
                browsers[b][st] += 1

        for b, data in browsers.items():
            t = data["total"]
            f = data["flaky"]
            p = data["passed"]
            fail = data["failed"]
            err = data["error"]
            data["flakiness_rate"] = round((f / t) * 100, 1) if t > 0 else 0.0
            data["flakiness_score"] = data["flakiness_rate"]
            data["first_attempt_pass_rate"] = round((p / t) * 100, 1) if t > 0 else 0.0
            data["final_pass_rate"] = round(((p + f) / t) * 100, 1) if t > 0 else 0.0
            data["failure_rate"] = round(((fail + err) / t) * 100, 1) if t > 0 else 0.0
            max_b = max(p, f, fail, err) if t > 0 else 0
            data["stability_score"] = round((max_b / t) * 100, 1) if t > 0 else 100.0
            data["reliability_score"] = data["first_attempt_pass_rate"]

        return {
            "testcase_id": testcase_id,
            "total_runs": total_runs,
            "flaky_runs": flaky_runs,
            "passed_runs": passed_runs,
            "failed_runs": failed_runs,
            "error_runs": error_runs,
            "flakiness_rate": flakiness_rate,
            "flakiness_score": flakiness_score,
            "first_attempt_pass_rate": first_attempt_pass_rate,
            "final_pass_rate": final_pass_rate,
            "failure_rate": failure_rate,
            "stability_score": stability_score,
            "reliability_score": reliability_score,
            "rating": rating,
            "flakiness_by_browser": browsers,
            "recent_runs": runs,
        }
    finally:
        conn.close()


def create_execution_batch(
    batch_id: str,
    project_id: str = "default_project",
    suite_id: str | None = None,
    concurrency: int = 2,
    total_tests: int = 0,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Register a new batch execution in queued status."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO execution_batches (
                    id, project_id, suite_id, status, concurrency,
                    total_tests, passed_tests, failed_tests, cancelled_tests, started_at
                )
                VALUES (?, ?, ?, 'queued', ?, ?, 0, 0, 0, ?)
                """,
                (batch_id, project_id, suite_id, concurrency, total_tests, now),
            )
        return get_execution_batch(batch_id, db_path) or {}
    finally:
        conn.close()


def update_execution_batch(
    batch_id: str,
    status: str | None = None,
    passed_tests: int | None = None,
    failed_tests: int | None = None,
    cancelled_tests: int | None = None,
    flaky_tests: int | None = None,
    finished_at: str | None = None,
    duration_ms: float | None = None,
    queue_wait_ms: float | None = None,
    avg_startup_ms: float | None = None,
    artifact_size_bytes: int | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Update execution batch state."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        updates = []
        params: list[Any] = []
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if passed_tests is not None:
            updates.append("passed_tests = ?")
            params.append(passed_tests)
        if failed_tests is not None:
            updates.append("failed_tests = ?")
            params.append(failed_tests)
        if cancelled_tests is not None:
            updates.append("cancelled_tests = ?")
            params.append(cancelled_tests)
        if flaky_tests is not None:
            updates.append("flaky_tests = ?")
            params.append(flaky_tests)
        if finished_at is not None:
            updates.append("finished_at = ?")
            params.append(finished_at)
        if duration_ms is not None:
            updates.append("duration_ms = ?")
            params.append(duration_ms)
        if queue_wait_ms is not None:
            updates.append("queue_wait_ms = ?")
            params.append(queue_wait_ms)
        if avg_startup_ms is not None:
            updates.append("avg_startup_ms = ?")
            params.append(avg_startup_ms)
        if artifact_size_bytes is not None:
            updates.append("artifact_size_bytes = ?")
            params.append(artifact_size_bytes)

        if updates:
            params.append(batch_id)
            with conn:
                conn.execute(
                    f"UPDATE execution_batches SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
        return get_execution_batch(batch_id, db_path)
    finally:
        conn.close()


def get_execution_batch(batch_id: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    """Fetch execution batch by ID with its child runs."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM execution_batches WHERE id = ?", (batch_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        # Fetch runs belonging to this batch
        run_rows = conn.execute(
            "SELECT * FROM execution_runs WHERE batch_id = ? ORDER BY started_at ASC",
            (batch_id,),
        ).fetchall()
        runs = []
        for rr in run_rows:
            rd = dict(rr)
            rd["logs"] = json.loads(rd.get("logs_json") or "[]")
            rd["retry_history"] = json.loads(rd.get("retry_history_json") or "[]")
            runs.append(rd)
        d["runs"] = runs
        return d
    finally:
        conn.close()


def list_execution_batches(
    project_id: str | None = None,
    suite_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """List execution batches."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        query = "SELECT * FROM execution_batches WHERE 1=1"
        params: list[Any] = []
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if suite_id:
            query += " AND suite_id = ?"
            params.append(suite_id)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Cross-Browser Execution Matrices
# ---------------------------------------------------------------------------

def create_execution_matrix(
    matrix_id: str,
    project_id: str = "default_project",
    suite_id: str | None = None,
    name: str | None = None,
    concurrency: int = 2,
    browsers: list[str] | None = None,
    total_executions: int = 0,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Register a new cross-browser execution matrix in queued status."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    target_browsers = browsers or ["chromium"]
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO execution_matrices (
                    id, project_id, suite_id, name, status, concurrency,
                    browsers_json, total_executions, passed_executions, failed_executions,
                    cancelled_executions, divergence_count, started_at
                )
                VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, 0, 0, 0, 0, ?)
                """,
                (
                    matrix_id,
                    project_id,
                    suite_id,
                    name or f"Matrix Run ({', '.join(target_browsers)})",
                    concurrency,
                    json.dumps(target_browsers),
                    total_executions,
                    now,
                ),
            )
        return get_execution_matrix(matrix_id, db_path) or {}
    finally:
        conn.close()


def update_execution_matrix(
    matrix_id: str,
    status: str | None = None,
    passed_executions: int | None = None,
    failed_executions: int | None = None,
    cancelled_executions: int | None = None,
    flaky_executions: int | None = None,
    divergence_count: int | None = None,
    finished_at: str | None = None,
    duration_ms: float | None = None,
    queue_wait_ms: float | None = None,
    avg_startup_ms: float | None = None,
    artifact_size_bytes: int | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Update execution matrix state."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        updates = []
        params: list[Any] = []
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if passed_executions is not None:
            updates.append("passed_executions = ?")
            params.append(passed_executions)
        if failed_executions is not None:
            updates.append("failed_executions = ?")
            params.append(failed_executions)
        if cancelled_executions is not None:
            updates.append("cancelled_executions = ?")
            params.append(cancelled_executions)
        if flaky_executions is not None:
            updates.append("flaky_executions = ?")
            params.append(flaky_executions)
        if divergence_count is not None:
            updates.append("divergence_count = ?")
            params.append(divergence_count)
        if finished_at is not None:
            updates.append("finished_at = ?")
            params.append(finished_at)
        if duration_ms is not None:
            updates.append("duration_ms = ?")
            params.append(duration_ms)
        if queue_wait_ms is not None:
            updates.append("queue_wait_ms = ?")
            params.append(queue_wait_ms)
        if avg_startup_ms is not None:
            updates.append("avg_startup_ms = ?")
            params.append(avg_startup_ms)
        if artifact_size_bytes is not None:
            updates.append("artifact_size_bytes = ?")
            params.append(artifact_size_bytes)

        if updates:
            params.append(matrix_id)
            with conn:
                conn.execute(
                    f"UPDATE execution_matrices SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
        return get_execution_matrix(matrix_id, db_path)
    finally:
        conn.close()


def get_execution_matrix(matrix_id: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    """Fetch execution matrix by ID with child runs, consolidated grid, and divergence metrics."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM execution_matrices WHERE id = ?", (matrix_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        browsers = json.loads(d.get("browsers_json") or '["chromium"]')
        d["browsers"] = browsers

        # Fetch runs belonging to this matrix
        run_rows = conn.execute(
            "SELECT * FROM execution_runs WHERE matrix_id = ? ORDER BY started_at ASC",
            (matrix_id,),
        ).fetchall()
        runs = []
        for rr in run_rows:
            rd = dict(rr)
            rd["logs"] = json.loads(rd.get("logs_json") or "[]")
            rd["retry_history"] = json.loads(rd.get("retry_history_json") or "[]")
            runs.append(rd)
        d["runs"] = runs

        # Build consolidated grid: Test Cases x Browsers
        tc_map: dict[str, dict[str, Any]] = {}
        for r in runs:
            t_id = r["testcase_id"]
            if t_id not in tc_map:
                tc_map[t_id] = {
                    "testcase_id": t_id,
                    "testcase_name": r.get("testcase_name") or t_id,
                    "browsers": {},
                }
            tc_map[t_id]["browsers"][r["browser"]] = {
                "run_id": r["id"],
                "status": r["status"],
                "attempt_count": r.get("attempt_count", 1),
                "retries": r.get("retries", 0),
                "duration_ms": r.get("duration_ms", 0.0),
                "error_message": r.get("error_message"),
                "artifacts_path": r.get("artifacts_path"),
                "worker_id": r.get("worker_id"),
            }

        grid = []
        divergent_testcases = 0

        for t_id, tc_info in tc_map.items():
            browser_statuses = {
                b: info["status"]
                for b, info in tc_info["browsers"].items()
                if info["status"] in ("passed", "failed", "error", "flaky")
            }
            # Divergence exists if different terminal statuses appear among completed browsers
            terminal_statuses = set(browser_statuses.values())
            is_divergent = len(terminal_statuses) > 1

            divergence_notes = None
            if is_divergent:
                divergent_testcases += 1
                parts = [f"{b}: {st}" for b, st in browser_statuses.items()]
                divergence_notes = f"Divergence detected ({', '.join(parts)})"

            grid.append({
                "testcase_id": t_id,
                "testcase_name": tc_info["testcase_name"],
                "browsers": tc_info["browsers"],
                "is_divergent": is_divergent,
                "divergence_notes": divergence_notes,
            })

        total_tc = len(grid)
        parity_pct = (
            round(100.0 * (total_tc - divergent_testcases) / total_tc, 1)
            if total_tc > 0
            else 100.0
        )

        # Calculate granular rates per browser: first-attempt, final pass, and flakiness
        browser_pass_rates: dict[str, float] = {}
        browser_first_attempt_pass_rates: dict[str, float] = {}
        browser_final_pass_rates: dict[str, float] = {}
        browser_flakiness_rates: dict[str, float] = {}

        for b in browsers:
            b_runs = [r for r in runs if r.get("browser") == b and r.get("status") in ("passed", "failed", "error", "flaky")]
            if b_runs:
                clean_passed = sum(1 for r in b_runs if r["status"] == "passed")
                flaky_b = sum(1 for r in b_runs if r["status"] == "flaky")
                total_b = len(b_runs)
                browser_first_attempt_pass_rates[b] = round(100.0 * clean_passed / total_b, 1)
                browser_final_pass_rates[b] = round(100.0 * (clean_passed + flaky_b) / total_b, 1)
                browser_flakiness_rates[b] = round(100.0 * flaky_b / total_b, 1)
                browser_pass_rates[b] = browser_final_pass_rates[b]
            else:
                browser_first_attempt_pass_rates[b] = 0.0
                browser_final_pass_rates[b] = 0.0
                browser_flakiness_rates[b] = 0.0
                browser_pass_rates[b] = 0.0

        d["grid"] = grid
        d["total_testcases"] = total_tc
        d["divergent_testcases_count"] = divergent_testcases
        d["cross_browser_parity_pct"] = parity_pct
        d["browser_pass_rates"] = browser_pass_rates
        d["browser_first_attempt_pass_rates"] = browser_first_attempt_pass_rates
        d["browser_final_pass_rates"] = browser_final_pass_rates
        d["browser_flakiness_rates"] = browser_flakiness_rates
        return d
    finally:
        conn.close()


def list_execution_matrices(
    project_id: str | None = None,
    suite_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """List execution matrices."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        query = "SELECT * FROM execution_matrices WHERE 1=1"
        params: list[Any] = []
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if suite_id:
            query += " AND suite_id = ?"
            params.append(suite_id)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["browsers"] = json.loads(d.get("browsers_json") or '["chromium"]')
            result.append(d)
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Aggregated Metrics for Overview Dashboard
# ---------------------------------------------------------------------------

def get_dashboard_metrics(
    project_id: str | None = None,
    days: int = 7,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Calculate real aggregated metrics for the overview dashboard."""
    init_studio_db(db_path)
    # Ensure testcases from disk are synced
    sync_all_testcases_from_disk(db_path=db_path)

    conn = get_connection(db_path)
    try:
        total_projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]

        if project_id:
            suite_count = conn.execute(
                "SELECT COUNT(*) FROM test_suites WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0]
            tc_count = conn.execute(
                "SELECT COUNT(*) FROM testcases_meta WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0]
            exec_query = "FROM execution_runs WHERE project_id = ?"
            exec_params: list[Any] = [project_id]
        else:
            suite_count = conn.execute("SELECT COUNT(*) FROM test_suites").fetchone()[0]
            tc_count = conn.execute("SELECT COUNT(*) FROM testcases_meta").fetchone()[0]
            exec_query = "FROM execution_runs WHERE 1=1"
            exec_params = []

        total_runs = conn.execute(f"SELECT COUNT(*) {exec_query}", exec_params).fetchone()[0]
        passed_runs = conn.execute(
            f"SELECT COUNT(*) {exec_query} AND status = 'passed'", exec_params
        ).fetchone()[0]
        failed_runs = conn.execute(
            f"SELECT COUNT(*) {exec_query} AND (status = 'failed' OR status = 'error')",
            exec_params,
        ).fetchone()[0]
        running_runs = conn.execute(
            f"SELECT COUNT(*) {exec_query} AND (status = 'running' OR status = 'queued')",
            exec_params,
        ).fetchone()[0]

        completed_runs = passed_runs + failed_runs
        pass_rate = round((passed_runs / completed_runs * 100), 1) if completed_runs > 0 else 100.0
        fail_rate = round((failed_runs / completed_runs * 100), 1) if completed_runs > 0 else 0.0

        avg_dur_ms = conn.execute(
            f"SELECT AVG(duration_ms) {exec_query} AND status IN ('passed', 'failed', 'error') AND duration_ms > 0",
            exec_params,
        ).fetchone()[0] or 0.0
        avg_duration_sec = round(avg_dur_ms / 1000.0, 2)

        # Recent executions with project name
        p_filter = "WHERE e.project_id = ?" if project_id else "WHERE 1=1"
        recent_rows = conn.execute(
            f"""
            SELECT e.id, e.project_id, COALESCE(p.name, 'Tracecase') AS project_name,
                   e.suite_id, e.testcase_id, e.testcase_name, e.status, e.browser,
                   e.started_at, e.duration_ms, e.passed_steps, e.total_steps
            FROM execution_runs e
            LEFT JOIN projects p ON e.project_id = p.id
            {p_filter}
            ORDER BY e.started_at DESC LIMIT 8
            """,
            exec_params,
        ).fetchall()
        recent_executions = [dict(r) for r in recent_rows]

        # Failed tests list
        failed_filter = f"{p_filter} AND (e.status = 'failed' OR e.status = 'error')"
        failed_rows = conn.execute(
            f"""
            SELECT e.id, e.project_id, COALESCE(p.name, 'Tracecase') AS project_name,
                   e.testcase_id, e.testcase_name, e.status, e.error_message, e.started_at, e.duration_ms
            FROM execution_runs e
            LEFT JOIN projects p ON e.project_id = p.id
            {failed_filter}
            ORDER BY e.started_at DESC LIMIT 5
            """,
            exec_params,
        ).fetchall()
        failed_tests = [dict(r) for r in failed_rows]

        # Recently modified test cases
        tc_p_filter = "WHERE project_id = ?" if project_id else "WHERE 1=1"
        recent_tc_rows = conn.execute(
            f"""
            SELECT id, project_id, name, description, start_url, browser, total_steps, updated_at
            FROM testcases_meta
            {tc_p_filter}
            ORDER BY updated_at DESC LIMIT 5
            """,
            exec_params,
        ).fetchall()
        recent_testcases = [dict(r) for r in recent_tc_rows]

        # Execution activity / trends by date over requested days
        from datetime import date, timedelta
        today = date.today()
        date_map = {}
        for i in range(days - 1, -1, -1):
            d_str = (today - timedelta(days=i)).isoformat()
            date_map[d_str] = {"exec_date": d_str, "passed": 0, "failed": 0, "total": 0}

        min_date = (today - timedelta(days=days - 1)).isoformat()
        trend_params = [min_date] + exec_params
        trend_rows = conn.execute(
            f"""
            SELECT SUBSTR(started_at, 1, 10) AS exec_date,
                   SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) AS passed,
                   SUM(CASE WHEN status IN ('failed', 'error') THEN 1 ELSE 0 END) AS failed
            FROM execution_runs
            WHERE SUBSTR(started_at, 1, 10) >= ?
            {"AND project_id = ?" if project_id else ""}
            GROUP BY exec_date
            ORDER BY exec_date ASC
            """,
            trend_params,
        ).fetchall()

        for r in trend_rows:
            d_str = r["exec_date"]
            if d_str in date_map:
                date_map[d_str]["passed"] = r["passed"] or 0
                date_map[d_str]["failed"] = r["failed"] or 0
                date_map[d_str]["total"] = (r["passed"] or 0) + (r["failed"] or 0)

        trends = list(date_map.values())

        return {
            "total_projects": total_projects,
            "total_suites": suite_count,
            "total_testcases": tc_count,
            "total_executions": total_runs,
            "passed_executions": passed_runs,
            "failed_executions": failed_runs,
            "running_executions": running_runs,
            "success_rate": pass_rate,
            "failure_rate": fail_rate,
            "avg_duration_sec": avg_duration_sec,
            "recent_executions": recent_executions,
            "failed_tests": failed_tests,
            "recent_testcases": recent_testcases,
            "execution_trends": trends,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# App Settings Operations
# ---------------------------------------------------------------------------

def get_settings(db_path: Path | str | None = None) -> dict[str, str]:
    """Retrieve all application settings."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


def update_settings(new_settings: dict[str, str], db_path: Path | str | None = None) -> dict[str, str]:
    """Update application settings."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            for k, v in new_settings.items():
                conn.execute(
                    "INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (k, str(v)),
                )
        return get_settings(db_path)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# AI Analysis Persistence
# ---------------------------------------------------------------------------

def save_ai_analysis(
    testcase_id: str,
    summary: str,
    risk_score: int,
    raw_analysis: dict[str, Any],
    model_used: str = "default",
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Persist AI analysis results."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    analysis_id = f"ai_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO ai_analyses (id, testcase_id, created_at, model_used, summary, risk_score, raw_analysis_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis_id,
                    testcase_id,
                    now,
                    model_used,
                    summary,
                    risk_score,
                    json.dumps(raw_analysis),
                ),
            )
        return {
            "id": analysis_id,
            "testcase_id": testcase_id,
            "created_at": now,
            "model_used": model_used,
            "summary": summary,
            "risk_score": risk_score,
            "raw_analysis": raw_analysis,
        }
    finally:
        conn.close()


def get_ai_analyses_for_testcase(
    testcase_id: str, db_path: Path | str | None = None
) -> list[dict[str, Any]]:
    """Retrieve historical AI analysis records for a test case."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM ai_analyses WHERE testcase_id = ? ORDER BY created_at DESC",
            (testcase_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["raw_analysis"] = json.loads(d.get("raw_analysis_json") or "{}")
            result.append(d)
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Autonomous Exploration Operations
# ---------------------------------------------------------------------------

def create_exploration_run(
    exploration_id: str,
    project_id: str,
    start_url: str,
    config: dict[str, Any],
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Create a new exploration run record in the database."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO exploration_runs (
                    id, project_id, start_url, allowed_origins_json, status,
                    max_depth, max_pages, max_interactions, execution_timeout,
                    created_at, config_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exploration_id,
                    project_id,
                    start_url,
                    json.dumps(config.get("allowed_origins", [])),
                    "running",
                    config.get("max_depth", 3),
                    config.get("max_pages", 20),
                    config.get("max_interactions", 50),
                    config.get("execution_timeout", 120.0),
                    now,
                    json.dumps(config),
                ),
            )
        return {
            "id": exploration_id,
            "project_id": project_id,
            "start_url": start_url,
            "status": "running",
            "created_at": now,
            "config": config,
            "pages_discovered": 0,
            "transitions_discovered": 0,
            "forms_discovered": 0,
        }
    finally:
        conn.close()


def update_exploration_run_status(
    exploration_id: str,
    status: str,
    pages_discovered: int | None = None,
    transitions_discovered: int | None = None,
    forms_discovered: int | None = None,
    finished_at: str | None = None,
    error_message: str | None = None,
    db_path: Path | str | None = None,
) -> None:
    """Update execution progress and completion status of an exploration run."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        updates = ["status = ?"]
        params: list[Any] = [status]

        if pages_discovered is not None:
            updates.append("pages_discovered = ?")
            params.append(pages_discovered)
        if transitions_discovered is not None:
            updates.append("transitions_discovered = ?")
            params.append(transitions_discovered)
        if forms_discovered is not None:
            updates.append("forms_discovered = ?")
            params.append(forms_discovered)
        if finished_at is not None:
            updates.append("finished_at = ?")
            params.append(finished_at)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)

        params.append(exploration_id)
        sql = f"UPDATE exploration_runs SET {', '.join(updates)} WHERE id = ?"

        with conn:
            conn.execute(sql, tuple(params))
    finally:
        conn.close()


def save_exploration_page(
    exploration_id: str,
    page_data: dict[str, Any],
    db_path: Path | str | None = None,
) -> None:
    """Save or update a discovered page node in the exploration database."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    node_id = page_data.get("id") or f"node_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO exploration_pages (
                    id, exploration_id, url, normalized_url, title, depth,
                    state_fingerprint, status_code, forms_json,
                    interactive_elements_json, links_json, screenshot_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_id,
                    exploration_id,
                    page_data.get("url", ""),
                    page_data.get("normalized_url", ""),
                    page_data.get("title", ""),
                    page_data.get("depth", 0),
                    page_data.get("state_fingerprint", ""),
                    page_data.get("status_code", 200),
                    json.dumps(page_data.get("forms", [])),
                    json.dumps(page_data.get("interactive_elements", [])),
                    json.dumps(page_data.get("links", [])),
                    page_data.get("screenshot_path"),
                    now,
                ),
            )
    finally:
        conn.close()


def save_exploration_transition(
    exploration_id: str,
    trans_data: dict[str, Any],
    db_path: Path | str | None = None,
) -> None:
    """Save a transition edge between exploration states."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    trans_id = trans_data.get("id") or f"trans_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO exploration_transitions (
                    id, exploration_id, source_url, target_url, action_type,
                    selector, element_text, is_safe, duration_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trans_id,
                    exploration_id,
                    trans_data.get("source_url", ""),
                    trans_data.get("target_url", ""),
                    trans_data.get("action_type", "navigate"),
                    trans_data.get("selector"),
                    trans_data.get("element_text"),
                    1 if trans_data.get("is_safe", True) else 0,
                    trans_data.get("duration_ms", 0.0),
                    now,
                ),
            )
    finally:
        conn.close()


def get_exploration_run(
    exploration_id: str, db_path: Path | str | None = None
) -> dict[str, Any] | None:
    """Get metadata and summary of a specific exploration run."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM exploration_runs WHERE id = ?", (exploration_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["allowed_origins"] = json.loads(d.get("allowed_origins_json") or "[]")
        d["config"] = json.loads(d.get("config_json") or "{}")
        return d
    finally:
        conn.close()


def list_exploration_runs(
    project_id: str | None = None, db_path: Path | str | None = None
) -> list[dict[str, Any]]:
    """List exploration runs, optionally scoped to a project."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        if project_id:
            rows = conn.execute(
                "SELECT * FROM exploration_runs WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM exploration_runs ORDER BY created_at DESC"
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["allowed_origins"] = json.loads(d.get("allowed_origins_json") or "[]")
            d["config"] = json.loads(d.get("config_json") or "{}")
            result.append(d)
        return result
    finally:
        conn.close()


def get_exploration_graph(
    exploration_id: str, db_path: Path | str | None = None
) -> dict[str, Any]:
    """Retrieve full navigation graph (nodes, transitions, forms) for an exploration run."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        run = conn.execute(
            "SELECT * FROM exploration_runs WHERE id = ?", (exploration_id,)
        ).fetchone()
        if not run:
            return {"nodes": {}, "transitions": []}

        page_rows = conn.execute(
            "SELECT * FROM exploration_pages WHERE exploration_id = ? ORDER BY depth ASC, created_at ASC",
            (exploration_id,),
        ).fetchall()
        nodes = {}
        for pr in page_rows:
            pd = dict(pr)
            pd["forms"] = json.loads(pd.get("forms_json") or "[]")
            pd["interactive_elements"] = json.loads(pd.get("interactive_elements_json") or "[]")
            pd["links"] = json.loads(pd.get("links_json") or "[]")
            nodes[pd["normalized_url"]] = pd

        trans_rows = conn.execute(
            "SELECT * FROM exploration_transitions WHERE exploration_id = ? ORDER BY created_at ASC",
            (exploration_id,),
        ).fetchall()
        transitions = [dict(tr) for tr in trans_rows]

        return {
            "exploration_id": exploration_id,
            "start_url": run["start_url"],
            "status": run["status"],
            "nodes": nodes,
            "transitions": transitions,
            "total_pages": len(nodes),
            "total_transitions": len(transitions),
        }
    finally:
        conn.close()


def delete_exploration_run(
    exploration_id: str, db_path: Path | str | None = None
) -> bool:
    """Delete an exploration run and cascade delete its pages and transitions."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM exploration_runs WHERE id = ?", (exploration_id,)
            )
            return cursor.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test-to-Code Mapping Persistence (Phase 7.5.2)
# ---------------------------------------------------------------------------

def save_test_code_mappings(
    mappings: list[Any],
    db_path: Path | str | None = None,
) -> int:
    """Save or update test-to-code mapping records into SQLite."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    saved = 0
    now = datetime.now().isoformat()
    try:
        with conn:
            for m in mappings:
                m_id = getattr(m, "id", None) or m.get("id")
                tc_id = getattr(m, "testcase_id", None) or m.get("testcase_id")
                tc_name = getattr(m, "testcase_name", None) or m.get("testcase_name", "")
                proj_id = getattr(m, "project_id", None) or m.get("project_id", "default_project")
                f_path = getattr(m, "file_path", None) or m.get("file_path")
                rel_type = getattr(m, "relation_type", None) or m.get("relation_type")
                matched = getattr(m, "matched_entity", None) or m.get("matched_entity")
                conf = getattr(m, "confidence", 1.0) or m.get("confidence", 1.0)
                ev = getattr(m, "evidence", {}) or m.get("evidence", {})
                ev_str = json.dumps(ev) if isinstance(ev, dict) else str(ev)

                conn.execute(
                    """
                    INSERT INTO test_code_mappings (
                        id, testcase_id, testcase_name, project_id, file_path,
                        relation_type, matched_entity, confidence, evidence_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        confidence = excluded.confidence,
                        evidence_json = excluded.evidence_json,
                        updated_at = excluded.updated_at
                    """,
                    (m_id, tc_id, tc_name, proj_id, f_path, rel_type, matched, float(conf), ev_str, now),
                )
                saved += 1
        return saved
    finally:
        conn.close()


def get_test_code_mappings(
    testcase_id: str | None = None,
    file_path: str | None = None,
    relation_type: str | None = None,
    project_id: str | None = None,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve test-to-code mappings with optional filters."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        query = "SELECT * FROM test_code_mappings WHERE 1=1"
        params: list[Any] = []

        if testcase_id:
            query += " AND testcase_id = ?"
            params.append(testcase_id)
        if file_path:
            query += " AND file_path = ?"
            params.append(file_path)
        if relation_type:
            query += " AND relation_type = ?"
            params.append(relation_type)
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        query += " ORDER BY confidence DESC, file_path ASC"
        rows = conn.execute(query, params).fetchall()
        results: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            try:
                d["evidence"] = json.loads(d.get("evidence_json") or "{}")
            except Exception:
                d["evidence"] = {}
            results.append(d)
        return results
    finally:
        conn.close()


def clear_test_code_mappings(
    project_id: str = "default_project",
    db_path: Path | str | None = None,
) -> int:
    """Clear test-to-code mappings for a project."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM test_code_mappings WHERE project_id = ?",
                (project_id,),
            )
            return cursor.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test Journey Drafts & Approval Operations
# ---------------------------------------------------------------------------

def save_synthesized_draft(
    draft: dict[str, Any], db_path: Path | str | None = None
) -> dict[str, Any]:
    """Persist a synthesized test journey draft."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    draft_id = draft.get("id") or f"draft_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    steps_json = json.dumps(draft.get("steps", []))
    requires_input = 1 if draft.get("requires_human_input") else 0
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO synthesized_drafts (
                    id, exploration_id, project_id, name, description,
                    journey_type, priority, start_url, steps_json,
                    status, approved_testcase_id, rejection_reason,
                    requires_human_input, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft_id,
                    draft.get("exploration_id", ""),
                    draft.get("project_id", "default_project"),
                    draft.get("name", "Synthesized Journey"),
                    draft.get("description", ""),
                    draft.get("journey_type", "navigation"),
                    draft.get("priority", "medium"),
                    draft.get("start_url", ""),
                    steps_json,
                    draft.get("status", "pending"),
                    draft.get("approved_testcase_id"),
                    draft.get("rejection_reason"),
                    requires_input,
                    draft.get("created_at", now),
                ),
            )
        return get_synthesized_draft(draft_id, db_path) or draft
    finally:
        conn.close()


def get_synthesized_draft(
    draft_id: str, db_path: Path | str | None = None
) -> dict[str, Any] | None:
    """Retrieve a single synthesized test journey draft."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM synthesized_drafts WHERE id = ?", (draft_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["steps"] = json.loads(d.get("steps_json") or "[]")
        d["requires_human_input"] = bool(d.get("requires_human_input", 0))
        return d
    finally:
        conn.close()


def list_synthesized_drafts(
    project_id: str | None = None,
    exploration_id: str | None = None,
    status: str | None = None,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """List test journey drafts with optional filters."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        clauses = []
        params = []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if exploration_id:
            clauses.append("exploration_id = ?")
            params.append(exploration_id)
        if status:
            clauses.append("status = ?")
            params.append(status)

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM synthesized_drafts {where_clause} ORDER BY created_at DESC"
        rows = conn.execute(sql, tuple(params)).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            d["steps"] = json.loads(d.get("steps_json") or "[]")
            d["requires_human_input"] = bool(d.get("requires_human_input", 0))
            result.append(d)
        return result
    finally:
        conn.close()


def update_synthesized_draft(
    draft_id: str,
    name: str | None = None,
    description: str | None = None,
    steps: list[dict[str, Any]] | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """
    Update a draft's name, description, or steps.
    
    Security Guardrail:
    If a draft was previously 'approved', modifying its content automatically
    invalidates approval status, resetting it to 'pending' and requiring re-approval.
    """
    init_studio_db(db_path)
    draft = get_synthesized_draft(draft_id, db_path)
    if not draft:
        return None

    was_approved = draft.get("status") == "approved"
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    try:
        with conn:
            updates = []
            params: list[Any] = []
            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            if steps is not None:
                updates.append("steps_json = ?")
                params.append(json.dumps(steps))

            if was_approved and (steps is not None or name is not None):
                # Security invalidation: reset approval status
                updates.append("status = 'pending'")
                updates.append("approved_testcase_id = NULL")
                updates.append("requires_human_input = 1")

            updates.append("reviewed_at = ?")
            params.append(now)

            params.append(draft_id)
            sql = f"UPDATE synthesized_drafts SET {', '.join(updates)} WHERE id = ?"
            conn.execute(sql, tuple(params))
        return get_synthesized_draft(draft_id, db_path)
    finally:
        conn.close()


def approve_synthesized_draft(
    draft_id: str,
    custom_name: str | None = None,
    modifications: dict[str, Any] | None = None,
    base_dir: Path | str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Approve a synthesized draft journey and promote it into an executable TestCase."""
    init_studio_db(db_path)
    draft = get_synthesized_draft(draft_id, db_path)
    if not draft:
        raise ValueError(f"Draft '{draft_id}' not found.")

    if draft.get("status") == "approved" and draft.get("approved_testcase_id"):
        return {
            "draft_id": draft_id,
            "testcase_id": draft["approved_testcase_id"],
            "status": "approved",
            "message": "Draft already approved.",
        }

    now = datetime.now()
    tc_id = f"tc_{uuid.uuid4().hex[:8]}"
    name = custom_name or draft.get("name") or "Synthesized Test Case"
    description = draft.get("description", "")
    start_url = draft.get("start_url", "")
    project_id = draft.get("project_id", "default_project")

    # Build steps and custom assertions
    from tracecase.models import ElementInfo, Step, TestCase

    steps_data: list[dict[str, Any]] = (
        (modifications.get("steps") if modifications and "steps" in modifications else draft.get("steps")) or []
    )
    testcase_steps: list[Step] = []
    custom_assertions: list[dict[str, Any]] = []

    for idx, s in enumerate(steps_data, start=1):
        action_type = s.get("action_type", "navigate")
        step_assertions = s.get("assertions", [])

        for a in step_assertions:
            custom_assertions.append({
                "id": f"assert_{uuid.uuid4().hex[:6]}",
                "step_number": idx,
                "assertion_type": a.get("assertion_type", "url_matches"),
                "target_selector": a.get("target_selector"),
                "expected_value": a.get("expected_value"),
                "source": a.get("source", "evidence"),
                "provenance": a.get("evidence_provenance", {}),
            })

        selector = s.get("selector")
        el_info = None
        if selector:
            el_info = ElementInfo(
                selector=selector,
                tag_name="element",
                text=None,
                bounding_box={"x": 0.0, "y": 0.0, "width": 100.0, "height": 30.0},
            )

        testcase_steps.append(
            Step(
                number=idx,
                timestamp=now,
                action_type=action_type,
                url=s.get("url"),
                element=el_info,
                input_value=s.get("input_value"),
                description_short=s.get("description_short") or f"Step {idx}",
                description_detailed=s.get("description_detailed") or f"Execute {action_type}",
            )
        )

    testcase = TestCase(
        id=tc_id,
        name=name,
        description=description,
        created_at=now,
        start_url=start_url,
        browser="chromium",
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 Tracecase",
        steps=testcase_steps,
        custom_assertions=custom_assertions,
        total_duration=round(len(testcase_steps) * 1.5, 2),
        total_steps=len(testcase_steps),
    )

    # Write testcase file to disk
    target_root = Path(base_dir) if base_dir else Path("recordings")
    tc_dir = target_root / tc_id
    tc_dir.mkdir(parents=True, exist_ok=True)
    tc_file = tc_dir / "testcase.json"
    tc_file.write_text(testcase.model_dump_json(indent=2), encoding="utf-8")

    # Upsert into testcases_meta with approval_status="approved"
    sync_testcase_meta(
        testcase=testcase,
        file_path=tc_file,
        project_id=project_id,
        tags=["synthesized", "autonomous", draft.get("journey_type", "navigation")],
        approval_status="approved",
        provenance={"draft_id": draft_id, "exploration_id": draft.get("exploration_id")},
        db_path=db_path,
    )

    # Update draft in database
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                UPDATE synthesized_drafts
                SET status = 'approved',
                    approved_testcase_id = ?,
                    reviewed_at = ?
                WHERE id = ?
                """,
                (tc_id, now.isoformat(), draft_id),
            )
    finally:
        conn.close()

    return {
        "draft_id": draft_id,
        "testcase_id": tc_id,
        "status": "approved",
        "file_path": str(tc_file),
        "testcase": testcase.model_dump(mode="json"),
    }


def reject_synthesized_draft(
    draft_id: str,
    reason: str | None = None,
    db_path: Path | str | None = None,
) -> bool:
    """Reject a synthesized draft with reason."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    try:
        with conn:
            cursor = conn.execute(
                """
                UPDATE synthesized_drafts
                SET status = 'rejected',
                    rejection_reason = ?,
                    reviewed_at = ?
                WHERE id = ?
                """,
                (reason or "Rejected by reviewer", now, draft_id),
            )
            return cursor.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test-to-Code Mapping Persistence (Phase 7.5.2)
# ---------------------------------------------------------------------------

def save_test_code_mappings(
    mappings: list[Any],
    db_path: Path | str | None = None,
) -> int:
    """Save or update test-to-code mapping records into SQLite."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    saved = 0
    now = datetime.now().isoformat()
    try:
        with conn:
            for m in mappings:
                m_id = getattr(m, "id", None) or m.get("id")
                tc_id = getattr(m, "testcase_id", None) or m.get("testcase_id")
                tc_name = getattr(m, "testcase_name", None) or m.get("testcase_name", "")
                proj_id = getattr(m, "project_id", None) or m.get("project_id", "default_project")
                f_path = getattr(m, "file_path", None) or m.get("file_path")
                rel_type = getattr(m, "relation_type", None) or m.get("relation_type")
                matched = getattr(m, "matched_entity", None) or m.get("matched_entity")
                conf = getattr(m, "confidence", 1.0) or m.get("confidence", 1.0)
                ev = getattr(m, "evidence", {}) or m.get("evidence", {})
                ev_str = json.dumps(ev) if isinstance(ev, dict) else str(ev)

                conn.execute(
                    """
                    INSERT INTO test_code_mappings (
                        id, testcase_id, testcase_name, project_id, file_path,
                        relation_type, matched_entity, confidence, evidence_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        confidence = excluded.confidence,
                        evidence_json = excluded.evidence_json,
                        updated_at = excluded.updated_at
                    """,
                    (m_id, tc_id, tc_name, proj_id, f_path, rel_type, matched, float(conf), ev_str, now),
                )
                saved += 1
        return saved
    finally:
        conn.close()


def get_test_code_mappings(
    testcase_id: str | None = None,
    file_path: str | None = None,
    relation_type: str | None = None,
    project_id: str | None = None,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve test-to-code mappings with optional filters."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        query = "SELECT * FROM test_code_mappings WHERE 1=1"
        params: list[Any] = []

        if testcase_id:
            query += " AND testcase_id = ?"
            params.append(testcase_id)
        if file_path:
            query += " AND file_path = ?"
            params.append(file_path)
        if relation_type:
            query += " AND relation_type = ?"
            params.append(relation_type)
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        query += " ORDER BY confidence DESC, file_path ASC"
        rows = conn.execute(query, params).fetchall()
        results: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            try:
                d["evidence"] = json.loads(d.get("evidence_json") or "{}")
            except Exception:
                d["evidence"] = {}
            results.append(d)
        return results
    finally:
        conn.close()


def clear_test_code_mappings(
    project_id: str = "default_project",
    db_path: Path | str | None = None,
) -> int:
    """Clear test-to-code mappings for a project."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM test_code_mappings WHERE project_id = ?",
                (project_id,),
            )
            return cursor.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Predictive Risk Snapshots Persistence (Phase 7.5.3)
# ---------------------------------------------------------------------------

def save_risk_scores_snapshot(
    scores: list[Any],
    commit_hash: str | None = None,
    branch: str | None = None,
    project_id: str = "default_project",
    db_path: Path | str | None = None,
) -> int:
    """Persist a predictive risk scoring snapshot against a git commit."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    saved = 0
    now = datetime.now().isoformat()
    try:
        with conn:
            for s in scores:
                if isinstance(s, dict):
                    tc_id = s.get("testcase_id")
                    tc_name = s.get("testcase_name", "")
                    r_score = s.get("risk_score", 0.0)
                    r_tier = s.get("risk_tier", "low")
                    m_conf = s.get("mapping_confidence", 0.0)
                    driver = s.get("primary_risk_driver", "")
                    bd = s.get("breakdown", {})
                else:
                    tc_id = getattr(s, "testcase_id", "")
                    tc_name = getattr(s, "testcase_name", "")
                    r_score = getattr(s, "risk_score", 0.0)
                    r_tier = getattr(s, "risk_tier", "low")
                    m_conf = getattr(s, "mapping_confidence", 0.0)
                    driver = getattr(s, "primary_risk_driver", "")
                    bd = getattr(s, "breakdown", {})

                bd_dict = bd.model_dump() if hasattr(bd, "model_dump") else bd if isinstance(bd, dict) else {}
                bd_str = json.dumps(bd_dict)

                snap_id = f"risk_{commit_hash or 'dirty'}_{tc_id}_{int(datetime.now().timestamp())}_{saved}"

                conn.execute(
                    """
                    INSERT INTO test_risk_snapshots (
                        id, project_id, commit_hash, branch, testcase_id, testcase_name,
                        risk_score, risk_tier, mapping_confidence, primary_driver,
                        breakdown_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snap_id,
                        project_id,
                        commit_hash,
                        branch,
                        tc_id,
                        tc_name,
                        float(r_score),
                        str(r_tier),
                        float(m_conf),
                        str(driver),
                        bd_str,
                        now,
                    ),
                )
                saved += 1
        return saved
    finally:
        conn.close()


def get_risk_scores_snapshots(
    commit_hash: str | None = None,
    testcase_id: str | None = None,
    project_id: str = "default_project",
    limit: int = 50,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve historical predictive risk snapshots."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        query = "SELECT * FROM test_risk_snapshots WHERE project_id = ?"
        params: list[Any] = [project_id]

        if commit_hash:
            query += " AND commit_hash = ?"
            params.append(commit_hash)
        if testcase_id:
            query += " AND testcase_id = ?"
            params.append(testcase_id)

        query += " ORDER BY created_at DESC, risk_score DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        results: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            try:
                d["breakdown"] = json.loads(d.get("breakdown_json") or "{}")
            except Exception:
                d["breakdown"] = {}
            results.append(d)
        return results
    finally:
        conn.close()
