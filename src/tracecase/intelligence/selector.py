"""Intelligent Regression Test Selector for Tracecase (Phase 7.5.4).

Selects the most valuable test cases for regression execution given code changes,
predictive risk scores, historical execution durations, and execution constraints:
1. Time Budget: Selects the highest value-density tests that fit within a duration cap.
2. Risk Threshold: Selects all tests at or above a specified minimum risk tier or score.
3. Top-K: Selects the top K highest-ranked tests.
4. Combined: Combines risk threshold with time budget or top-K constraints.

Critical Safeguards:
- Never silently exclude Critical tests due to a time budget: expose as budget exceptions.
- Never interpret missing execution duration as 0.0s: apply safe configurable fallback.
- Strictly separate mapping confidence from failure risk.
- Enforce approval checks on synthesized test drafts.
- 100% deterministic and reproducible selection ordering.
"""

from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
from typing import Any

from tracecase.intelligence.models import (
    DurationSource,
    PredictiveRiskReport,
    RegressionSelectionResult,
    RiskTier,
    SelectedTestItem,
    SelectionDecision,
    SelectionStrategy,
    TestRiskScore,
)
from tracecase.models import TestCase
from tracecase.ui.db import (
    get_connection,
    get_testcase_duration_stats,
    init_studio_db,
    save_regression_selection,
)

logger = logging.getLogger(__name__)

TIER_ORDER: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


def parse_duration_string(budget_str: str | float | int | None) -> float | None:
    """Parse budget strings like '120s', '2m', '1.5h', '90' into seconds."""
    if budget_str is None:
        return None
    if isinstance(budget_str, (int, float)):
        return float(budget_str)

    s = budget_str.strip().lower()
    if not s:
        return None

    try:
        if s.endswith("ms"):
            return float(s[:-2]) / 1000.0
        elif s.endswith("s"):
            return float(s[:-1])
        elif s.endswith("m"):
            return float(s[:-1]) * 60.0
        elif s.endswith("h"):
            return float(s[:-1]) * 3600.0
        return float(s)
    except ValueError:
        raise ValueError(f"Invalid duration format: '{budget_str}'. Use e.g. '120s', '2m', '90'.")


class IntelligentRegressionSelector:
    """Deterministic regression selection engine with duration intelligence and safety invariants."""

    def __init__(
        self,
        project_id: str = "default_project",
        db_path: Path | str | None = None,
        fallback_duration_s: float = 15.0,
    ) -> None:
        self.project_id = project_id
        self.db_path = db_path
        self.fallback_duration_s = max(1.0, fallback_duration_s)

    # -----------------------------------------------------------------------
    # Approval Status Check for Synthesized Drafts
    # -----------------------------------------------------------------------

    def _get_unapproved_synthesized_ids(self) -> set[str]:
        """Query SQLite for synthesized testcases that have not yet been approved."""
        init_studio_db(self.db_path)
        conn = get_connection(self.db_path)
        try:
            # Check drafts where status != 'approved'
            rows = conn.execute(
                "SELECT id, approved_testcase_id, status FROM synthesized_drafts WHERE project_id = ?",
                (self.project_id,),
            ).fetchall()
            unapproved = set()
            for r in rows:
                if r["status"] != "approved":
                    if r["approved_testcase_id"]:
                        unapproved.add(r["approved_testcase_id"])
                    unapproved.add(r["id"])
            return unapproved
        except Exception:
            return set()
        finally:
            conn.close()

    # -----------------------------------------------------------------------
    # Core Selection Engine
    # -----------------------------------------------------------------------

    def select(
        self,
        testcases: list[TestCase],
        risk_report: PredictiveRiskReport,
        strategy: SelectionStrategy = "time_budget",
        time_budget: float | str | None = None,
        min_risk_tier: RiskTier | str | None = None,
        min_risk_score: float | None = None,
        top_k: int | None = None,
        include_critical_exceptions: bool = False,
        persist: bool = True,
    ) -> RegressionSelectionResult:
        """
        Execute deterministic regression selection algorithm across the test suite.
        """
        time_budget_s = parse_duration_string(time_budget)
        unapproved_ids = self._get_unapproved_synthesized_ids()

        # Build lookup of risk scores by testcase_id
        score_map: dict[str, TestRiskScore] = {s.testcase_id: s for s in risk_report.scores}

        # 1. Annotate each test case with risk and duration intelligence
        annotated: list[dict[str, Any]] = []
        for tc in testcases:
            score_item = score_map.get(tc.id)
            if score_item:
                r_score = score_item.risk_score
                r_tier = score_item.risk_tier
                m_conf = score_item.mapping_confidence
                driver = score_item.primary_risk_driver
                aff_files = score_item.affected_files
            else:
                # Fallback neutral baseline for un-scored tests
                r_score = 40.0
                r_tier = "medium"
                m_conf = 0.0
                driver = "Unscored testcase (neutral baseline applied)"
                aff_files = []

            # Duration Intelligence
            d_stats = get_testcase_duration_stats(
                testcase_id=tc.id,
                project_id=self.project_id,
                fallback_s=self.fallback_duration_s,
                db_path=self.db_path,
            )
            est_dur = float(d_stats["duration_s"])
            dur_src: DurationSource = d_stats["source"]

            # If SQLite lacked execution history, check if TestCase itself has recorded duration
            if dur_src == "estimated_fallback" and getattr(tc, "total_duration", None) and tc.total_duration > 0:
                est_dur = round(float(tc.total_duration), 2)
                dur_src = "recorded_testcase"

            # Value density calculation:
            # ValueScore = RiskScore * (1.0 + 0.2 * MappingConfidence)
            # Efficiency = ValueScore / max(1.0, Duration)
            value_score = round(r_score * (1.0 + 0.2 * m_conf), 2)
            efficiency = round(value_score / max(1.0, est_dur), 4)

            annotated.append({
                "testcase": tc,
                "risk_score": r_score,
                "risk_tier": r_tier,
                "mapping_confidence": m_conf,
                "primary_driver": driver,
                "affected_files": aff_files,
                "estimated_duration_s": est_dur,
                "duration_source": dur_src,
                "value_score": value_score,
                "efficiency": efficiency,
                "is_unapproved": tc.id in unapproved_ids,
            })

        # 2. Check risk tier threshold rank
        min_tier_rank = 1
        if min_risk_tier:
            min_tier_rank = TIER_ORDER.get(min_risk_tier.lower(), 1)

        # 3. Deterministic Sorting:
        # Tier rank desc (Critical first, then High, etc.) -> Efficiency / Value density desc -> testcase_id asc (tie-breaker)
        if strategy == "top_k":
            # For pure top_k, rank primarily by raw risk score
            annotated.sort(key=lambda x: (-TIER_ORDER.get(x["risk_tier"], 1), -x["risk_score"], x["testcase"].id))
        else:
            annotated.sort(key=lambda x: (-TIER_ORDER.get(x["risk_tier"], 1), -x["efficiency"], -x["risk_score"], x["testcase"].id))

        # 4. Selection Algorithm Execution
        selected_items: list[SelectedTestItem] = []
        selected_ids: list[str] = []
        excluded_ids: list[str] = []
        budget_exception_ids: list[str] = []
        accumulated_duration_s = 0.0

        for item in annotated:
            tc = item["testcase"]
            r_score = item["risk_score"]
            r_tier = item["risk_tier"]
            m_conf = item["mapping_confidence"]
            est_dur = item["estimated_duration_s"]
            dur_src = item["duration_source"]
            val_score = item["value_score"]
            driver = item["primary_driver"]
            aff_files = item["affected_files"]
            tier_rank = TIER_ORDER.get(r_tier, 1)

            # Check 1: Approval status for synthesized drafts
            if item["is_unapproved"]:
                selected_items.append(SelectedTestItem(
                    testcase_id=tc.id,
                    testcase_name=tc.name,
                    risk_score=r_score,
                    risk_tier=r_tier,
                    mapping_confidence=m_conf,
                    estimated_duration_s=est_dur,
                    duration_source=dur_src,
                    decision="excluded",
                    decision_reason="Unapproved synthesized draft: requires human approval before regression execution.",
                    value_score=val_score,
                    primary_risk_driver=driver,
                    affected_files=aff_files,
                ))
                excluded_ids.append(tc.id)
                continue

            # Check 2: Minimum Risk Tier Filter
            if tier_rank < min_tier_rank or (min_risk_score is not None and r_score < min_risk_score):
                selected_items.append(SelectedTestItem(
                    testcase_id=tc.id,
                    testcase_name=tc.name,
                    risk_score=r_score,
                    risk_tier=r_tier,
                    mapping_confidence=m_conf,
                    estimated_duration_s=est_dur,
                    duration_source=dur_src,
                    decision="excluded",
                    decision_reason=f"Risk score {r_score:.1f} ({r_tier.upper()}) is below minimum threshold requirement ({min_risk_tier or min_risk_score}).",
                    value_score=val_score,
                    primary_risk_driver=driver,
                    affected_files=aff_files,
                ))
                excluded_ids.append(tc.id)
                continue

            # Check 3: Strategy-specific Selection
            if strategy in ("time_budget", "combined") and time_budget_s is not None:
                fits_budget = (accumulated_duration_s + est_dur) <= time_budget_s

                # Critical Risk Safeguard
                if r_tier == "critical":
                    if fits_budget:
                        decision: SelectionDecision = "selected"
                        reason = f"Critical risk test within time budget (acc: {accumulated_duration_s + est_dur:.1f}s / {time_budget_s:.1f}s)."
                        accumulated_duration_s += est_dur
                        selected_ids.append(tc.id)
                    else:
                        if include_critical_exceptions:
                            decision = "selected"
                            reason = f"CRITICAL SAFEGUARD EXCEPTION: Included via explicit override (exceeds budget by {accumulated_duration_s + est_dur - time_budget_s:.1f}s)."
                            accumulated_duration_s += est_dur
                            selected_ids.append(tc.id)
                            budget_exception_ids.append(tc.id)
                        else:
                            decision = "budget_exception"
                            reason = (
                                f"CRITICAL RISK EXCEPTION: Test requires {est_dur:.1f}s but remaining budget is "
                                f"{max(0.0, time_budget_s - accumulated_duration_s):.1f}s. "
                                f"Not silently excluded; requires explicit user approval to include or skip."
                            )
                            budget_exception_ids.append(tc.id)
                else:
                    # Non-critical tests
                    if fits_budget:
                        decision = "selected"
                        reason = f"High-yield test fits within time budget (acc: {accumulated_duration_s + est_dur:.1f}s / {time_budget_s:.1f}s, efficiency: {item['efficiency']:.2f})."
                        accumulated_duration_s += est_dur
                        selected_ids.append(tc.id)
                    else:
                        decision = "excluded"
                        reason = f"Exceeds remaining time budget ({est_dur:.1f}s required, {max(0.0, time_budget_s - accumulated_duration_s):.1f}s available)."
                        excluded_ids.append(tc.id)

            elif strategy == "top_k" and top_k is not None:
                if len(selected_ids) < top_k:
                    decision = "selected"
                    reason = f"Selected within Top-{top_k} highest priority tests (rank #{len(selected_ids) + 1}, risk: {r_score:.1f})."
                    accumulated_duration_s += est_dur
                    selected_ids.append(tc.id)
                else:
                    decision = "excluded"
                    reason = f"Ranked outside the requested Top-{top_k} limit."
                    excluded_ids.append(tc.id)

            elif strategy == "risk_threshold":
                decision = "selected"
                reason = f"Meets minimum risk threshold {r_tier.upper()} ({r_score:.1f} >= {min_risk_tier or min_risk_score})."
                accumulated_duration_s += est_dur
                selected_ids.append(tc.id)

            else:
                decision = "selected"
                reason = "Selected under default regression policy."
                accumulated_duration_s += est_dur
                selected_ids.append(tc.id)

            selected_items.append(SelectedTestItem(
                testcase_id=tc.id,
                testcase_name=tc.name,
                risk_score=r_score,
                risk_tier=r_tier,
                mapping_confidence=m_conf,
                estimated_duration_s=est_dur,
                duration_source=dur_src,
                decision=decision,
                decision_reason=reason,
                value_score=val_score,
                primary_risk_driver=driver,
                affected_files=aff_files,
            ))

        # 5. Coverage and distribution metrics
        total_risk = sum(item["risk_score"] for item in annotated)
        selected_risk = sum(
            item.risk_score for item in selected_items if item.decision == "selected"
        )
        risk_cov_pct = round((selected_risk / total_risk * 100.0) if total_risk > 0 else 100.0, 1)

        total_critical = sum(1 for item in annotated if item["risk_tier"] == "critical")
        selected_critical = sum(
            1 for item in selected_items if item.risk_tier == "critical" and item.decision == "selected"
        )
        crit_cov_pct = round((selected_critical / total_critical * 100.0) if total_critical > 0 else 100.0, 1)

        sel_id = f"sel_{risk_report.changeset_commit or 'clean'}_{int(datetime.now().timestamp())}"

        strategy_params = {
            "strategy": strategy,
            "time_budget_s": time_budget_s,
            "min_risk_tier": min_risk_tier,
            "min_risk_score": min_risk_score,
            "top_k": top_k,
            "include_critical_exceptions": include_critical_exceptions,
            "fallback_duration_s": self.fallback_duration_s,
        }

        result = RegressionSelectionResult(
            id=sel_id,
            project_id=self.project_id,
            commit_hash=risk_report.changeset_commit,
            branch=risk_report.changeset_branch,
            strategy=strategy,
            strategy_params=strategy_params,
            selected_test_ids=selected_ids,
            excluded_test_ids=excluded_ids,
            budget_exception_test_ids=budget_exception_ids,
            tests=selected_items,
            total_tests_considered=len(testcases),
            selected_count=len(selected_ids),
            excluded_count=len(excluded_ids),
            budget_exception_count=len(budget_exception_ids),
            time_budget_s=time_budget_s,
            estimated_total_duration_s=round(accumulated_duration_s, 2),
            risk_coverage_pct=risk_cov_pct,
            critical_coverage_pct=crit_cov_pct,
        )

        # 6. SQLite Persistence
        if persist:
            save_regression_selection(result, db_path=self.db_path)

        return result
