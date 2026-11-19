"""SQLite persistence layer for QA Auto Studio (Projects, Suites, Executions, Settings)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from qa_auto.models import TestCase

DEFAULT_STUDIO_DB_PATH = Path(".qa_auto") / "studio.db"


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

        # Ensure default project exists
        default_proj = conn.execute(
            "SELECT id FROM projects WHERE id = 'default_project'"
        ).fetchone()
        if not default_proj:
            now = datetime.now().isoformat()
            conn.execute(
                """
                INSERT INTO projects (id, name, description, created_at, updated_at, settings_json)
                VALUES ('default_project', 'Default Project', 'Default testing workspace', ?, ?, '{}')
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


def add_testcase_to_suite(
    suite_id: str,
    testcase_id: str,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Add a testcase to a suite, preventing duplicates."""
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
    db_path: Path | str | None = None,
) -> None:
    """Upsert testcase metadata into testcases_meta."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    fpath = Path(file_path).resolve()
    folder_path = str(fpath.parent)
    tags_json = json.dumps(tags or [])
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO testcases_meta (
                    id, project_id, name, description, start_url, browser,
                    total_steps, total_duration, folder_path, file_path, tags_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    start_url = excluded.start_url,
                    browser = excluded.browser,
                    total_steps = excluded.total_steps,
                    total_duration = excluded.total_duration,
                    folder_path = excluded.folder_path,
                    file_path = excluded.file_path,
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
                    browser, headed, heal, assertions, visual_diff, started_at
                )
                VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?)
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
    """Fetch complete execution run with step logs."""
    init_studio_db(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM execution_runs WHERE id = ?", (execution_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["logs"] = json.loads(d.get("logs_json") or "[]")
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
        return d
    finally:
        conn.close()


def list_execution_runs(
    project_id: str | None = None,
    testcase_id: str | None = None,
    suite_id: str | None = None,
    status: str | None = None,
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

        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["logs"] = json.loads(d.get("logs_json") or "[]")
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
            SELECT e.id, e.project_id, COALESCE(p.name, 'Default Project') AS project_name,
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
            SELECT e.id, e.project_id, COALESCE(p.name, 'Default Project') AS project_name,
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
