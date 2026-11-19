"""SQLite and FTS5 test case corpus storage."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from tracecase.models import TestCase

DEFAULT_DB_PATH = Path.home() / ".tracecase" / "corpus.db"


def reset_db(db_path: Path | str | None = None) -> bool:
    """Clear all records from the corpus database or remove the database file."""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    if path.exists():
        path.unlink()
        return True
    return False


def init_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Initialize SQLite database with relational and FTS5 schema."""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    with con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS testcases (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                start_url TEXT NOT NULL,
                browser TEXT NOT NULL,
                created_at TEXT NOT NULL,
                total_steps INTEGER NOT NULL,
                total_duration REAL NOT NULL,
                file_path TEXT NOT NULL,
                indexed_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS steps_fts USING fts5(
                testcase_id UNINDEXED,
                step_number UNINDEXED,
                action_type,
                selector,
                description,
                url,
                network_urls,
                console_logs
            )
            """
        )
    return con


def index_testcase(testcase: TestCase, file_path: Path, db_path: Path | str | None = None) -> None:
    """Index a single test case into relational table and FTS5 index."""
    con = init_db(db_path)
    now = datetime.now().isoformat()

    with con:
        con.execute("DELETE FROM testcases WHERE id = ?", (testcase.id,))
        con.execute("DELETE FROM steps_fts WHERE testcase_id = ?", (testcase.id,))

        con.execute(
            """
            INSERT INTO testcases (
                id, name, start_url, browser, created_at,
                total_steps, total_duration, file_path, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                testcase.id,
                testcase.name,
                testcase.start_url,
                testcase.browser,
                testcase.created_at.isoformat(),
                testcase.total_steps,
                testcase.total_duration,
                str(Path(file_path).resolve()),
                now,
            ),
        )

        # Index overview row so testcase name and start_url are always matched by FTS
        con.execute(
            """
            INSERT INTO steps_fts (
                testcase_id, step_number, action_type,
                selector, description, url, network_urls, console_logs
            ) VALUES (?, 0, 'overview', '', ?, ?, '', '')
            """,
            (
                testcase.id,
                testcase.name,
                testcase.start_url,
            ),
        )

        for step in testcase.steps:
            selector = step.element.selector if step.element else ""
            net_urls = " ".join(r.url for r in step.network_requests)
            logs = " ".join(log.message for log in step.console_logs)

            con.execute(
                """
                INSERT INTO steps_fts (
                    testcase_id, step_number, action_type,
                    selector, description, url, network_urls, console_logs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    testcase.id,
                    step.number,
                    step.action_type,
                    selector,
                    f"{step.description_short} {step.description_detailed}",
                    step.url or "",
                    net_urls,
                    logs,
                ),
            )
    con.close()


def index_directory(directory: Path, db_path: Path | str | None = None) -> int:
    """Recursively search for and index testcase.json files in directory."""
    directory = Path(directory)
    count = 0
    for path in directory.rglob("testcase.json"):
        try:
            tc = TestCase.model_validate_json(path.read_text(encoding="utf-8"))
            index_testcase(tc, path, db_path=db_path)
            count += 1
        except Exception:
            continue
    return count
