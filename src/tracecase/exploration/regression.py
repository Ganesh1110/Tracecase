"""Intelligent Regression Selector: selects prioritized test subsets based on change impact and failure history."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from tracecase.ui.db import get_connection, init_studio_db
from tracecase.ui.service import find_testcase_files, resolve_testcase_file

logger = logging.getLogger("tracecase.exploration.regression")


def select_intelligent_regression_suite(
    changed_routes: list[str] | None = None,
    changed_selectors: list[str] | None = None,
    project_id: str = "default_project",
    search_paths: list[Path] | None = None,
    db_path: Path | str | None = None,
    max_recommendations: int = 15,
) -> dict[str, Any]:
    """
    Select an optimized subset of regression tests impacted by code, route, or selector changes.
    
    Correlates:
    1. Direct selector modifications (highest risk).
    2. Affected page routes and navigation flows.
    3. Historical execution failure patterns.
    """
    init_studio_db(db_path)
    conn = get_connection(db_path)

    routes_clean = [r.lower().rstrip("/") or "/" for r in (changed_routes or [])]
    selectors_clean = [s.strip().lower() for s in (changed_selectors or [])]

    # 1. Fetch recent execution failure history from SQLite
    failure_history: dict[str, list[dict[str, Any]]] = {}
    try:
        rows = conn.execute(
            """
            SELECT testcase_id, status, error_message, started_at
            FROM execution_runs
            WHERE project_id = ?
            ORDER BY started_at DESC LIMIT 100
            """,
            (project_id,),
        ).fetchall()
        for r in rows:
            tc_id = r["testcase_id"]
            if tc_id not in failure_history:
                failure_history[tc_id] = []
            failure_history[tc_id].append(dict(r))
    finally:
        conn.close()

    # 2. Discover all project test cases from disk
    tc_files = find_testcase_files(search_paths)
    ranked_cases: list[dict[str, Any]] = []

    for f in tc_files:
        try:
            _, tc = resolve_testcase_file(str(f), search_paths)
        except Exception as exc:
            logger.debug("Could not resolve testcase file %s: %s", f, exc)
            continue

        score = 0.0
        reasons: list[str] = []
        affected_steps: list[int] = []

        # Analyze steps in testcase
        for step in tc.steps:
            step_matched = False

            # Check selector match
            if step.element and step.element.selector:
                el_sel = step.element.selector.lower()
                for chg_sel in selectors_clean:
                    if chg_sel and (chg_sel == el_sel or chg_sel in el_sel):
                        score += 50.0
                        step_matched = True
                        reasons.append(f"Step {step.number} directly interacts with modified selector '{chg_sel}'")
                        break

            # Check route match
            step_url = step.url or tc.start_url
            if step_url:
                step_path = urlparse(step_url).path.lower().rstrip("/") or "/"
                for chg_route in routes_clean:
                    if chg_route and (chg_route == step_path or step_path.startswith(chg_route)):
                        score += 35.0
                        step_matched = True
                        reasons.append(f"Step {step.number} operates on modified route '{chg_route}'")
                        break

            if step_matched:
                affected_steps.append(step.number)

        # Check historical execution failures
        tc_hist = failure_history.get(tc.id, [])
        last_status = tc_hist[0]["status"] if tc_hist else None

        if tc_hist and tc_hist[0]["status"] in ("failed", "error"):
            score += 30.0
            reasons.append(f"Most recent execution failed: {tc_hist[0].get('error_message') or 'Assertion failure'}")

        total_fails = sum(1 for h in tc_hist if h["status"] in ("failed", "error"))
        if total_fails >= 2:
            score += 15.0
            reasons.append(f"History of recurring failures ({total_fails} recent failures)")

        # Priority categorization
        if score >= 65.0:
            priority = "critical"
        elif score >= 35.0:
            priority = "high"
        elif score >= 15.0:
            priority = "medium"
        else:
            priority = "low"

        # Deduplicate reasons
        unique_reasons = list(dict.fromkeys(reasons))

        ranked_cases.append({
            "testcase_id": tc.id,
            "testcase_name": tc.name,
            "priority": priority,
            "risk_score": min(round(score, 1), 100.0),
            "reasons": unique_reasons,
            "affected_steps": list(set(affected_steps)),
            "last_status": last_status,
        })

    # Sort by risk score descending
    ranked_cases.sort(key=lambda item: item["risk_score"], reverse=True)

    recommended = [c for c in ranked_cases if c["risk_score"] > 0]
    if not recommended and ranked_cases:
        # If no direct changes matched, recommend top 3 smoke tests
        recommended = ranked_cases[:3]

    recommended_ids = [c["testcase_id"] for c in recommended[:max_recommendations]]

    explanation = (
        f"Analyzed {len(ranked_cases)} test cases against {len(routes_clean)} changed routes and "
        f"{len(selectors_clean)} changed selectors. Identified {len(recommended_ids)} impacted tests."
    )

    return {
        "project_id": project_id,
        "total_testcases_analyzed": len(ranked_cases),
        "recommended_count": len(recommended_ids),
        "ranked_testcases": ranked_cases[:max_recommendations],
        "recommended_suite_testcase_ids": recommended_ids,
        "explanation": explanation,
    }
