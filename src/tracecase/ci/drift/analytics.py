"""Drift Analytics and persistence into SQLite for Studio dashboards and historical trends."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from tracecase.ci.baseline.manager import init_baseline_db
from tracecase.ci.drift.models import DriftAnalysisResult
from tracecase.ui.db import get_connection

logger = logging.getLogger("tracecase.ci.drift.analytics")


class DriftAnalytics:
    """Manages persistence and aggregation of regression drift records."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = db_path
        init_baseline_db(db_path)

    def save_drift_result(self, result: DriftAnalysisResult) -> None:
        """Persist individual drift items into the ci_drift_records table."""
        conn = get_connection(self.db_path)
        try:
            for item in result.items:
                rec_id = f"drift_{result.run_id}_{item.testcase_id}"
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ci_drift_records (
                        id, run_id, project_id, base_commit, target_commit,
                        browser, testcase_id, testcase_name, base_status,
                        pr_status, classification, test_definition_drift,
                        base_duration_ms, pr_duration_ms, duration_delta_ms,
                        details_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rec_id,
                        result.run_id,
                        result.project_id,
                        result.base_commit or "unknown",
                        result.pr_commit or "HEAD",
                        result.browser,
                        item.testcase_id,
                        item.testcase_name,
                        item.base_status,
                        item.pr_status,
                        str(item.classification),
                        1 if item.test_definition_drift else 0,
                        item.base_duration_ms,
                        item.pr_duration_ms,
                        item.duration_delta_ms,
                        json.dumps({"explanation": item.explanation}),
                        result.created_at,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def get_drift_records(
        self,
        run_id: str | None = None,
        testcase_id: str | None = None,
        project_id: str = "default_project",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query historical drift records."""
        conn = get_connection(self.db_path)
        try:
            query = "SELECT * FROM ci_drift_records WHERE project_id = ?"
            params: list[Any] = [project_id]
            if run_id:
                query += " AND run_id = ?"
                params.append(run_id)
            if testcase_id:
                query += " AND testcase_id = ?"
                params.append(testcase_id)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
