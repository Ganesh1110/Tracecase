"""Predictive Risk Scoring Engine for Tracecase (Phase 7.5.3).

Calculates a multidimensional failure risk score for each test case following a code change:
Risk = 0.30*I + 0.25*B + 0.20*F + 0.15*H + 0.10*C

Where:
- I = Change Impact (0-100): Directness and confidence of code-to-test mapping
- B = Selector / Route Breakage (0-100): Whether selectors or routes were deleted or edited
- F = Historical Failure Rate (0-100): Failure frequency from SQLite execution history
- H = Flakiness & Recency (0-100): Retry flakiness rate and recent failure patterns
- C = Change Magnitude (0-100): Size of relevant code modifications

Classifies tests into:
- Critical (85-100)
- High (70-84)
- Medium (40-69)
- Low (0-39)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from tracecase.intelligence.code_mapper import (
    TestReferenceExtractor,
    TestToCodeGraph,
)
from tracecase.intelligence.models import (
    ChangedFile,
    GitChangeSet,
    PredictiveRiskReport,
    RiskFactorBreakdown,
    RiskScoringWeights,
    RiskTier,
    TestCoverageProfile,
    TestRiskScore,
)
from tracecase.models import TestCase
from tracecase.ui.db import (
    get_testcase_flakiness_stats,
    save_risk_scores_snapshot,
)

logger = logging.getLogger(__name__)


class PredictiveRiskScorer:
    """Calculates deterministic, evidence-based predictive risk scores for regression tests."""

    def __init__(
        self,
        weights: RiskScoringWeights | None = None,
        db_path: Path | str | None = None,
        project_id: str = "default_project",
    ) -> None:
        self.weights = weights or RiskScoringWeights()
        self.db_path = db_path
        self.project_id = project_id

    # -----------------------------------------------------------------------
    # Factor Computation (All Normalized 0 - 100)
    # -----------------------------------------------------------------------

    def compute_change_impact(
        self,
        testcase_id: str,
        graph: TestToCodeGraph,
        changed_files: list[ChangedFile],
        profile: TestCoverageProfile | None = None,
    ) -> tuple[float, float, list[str]]:
        """
        Compute Signal I: Change Impact (0-100) and return (score, max_mapping_confidence, explanations).
        
        Mapping confidence is strictly tracked separately from risk.
        """
        mappings = graph.get_mappings_for_test(testcase_id)

        changed_paths = {f.path for f in changed_files}
        old_changed_paths = {f.old_path for f in changed_files if f.old_path}

        best_score = 0.0
        max_conf = 0.0
        explanations: list[str] = []

        # Check direct graph mappings
        for m in mappings:
            if m.file_path in changed_paths or (old_changed_paths and m.file_path in old_changed_paths):
                max_conf = max(max_conf, m.confidence)
                score = 0.0
                if m.relation_type == "exact_route":
                    score = 100.0
                    explanations.append(f"Direct route match: '{m.matched_entity}' in changed file '{m.file_path}'")
                elif m.relation_type == "exact_selector":
                    score = 95.0
                    explanations.append(f"Direct selector match: '{m.matched_entity}' in changed file '{m.file_path}'")
                elif m.relation_type == "api_endpoint":
                    score = 90.0
                    explanations.append(f"API endpoint match: '{m.matched_entity}' in changed file '{m.file_path}'")
                elif m.relation_type == "route_prefix":
                    score = 80.0
                    explanations.append(f"Route prefix match: '{m.matched_entity}' in changed file '{m.file_path}'")
                elif m.relation_type == "dependency_import":
                    score = 65.0
                    explanations.append(f"Transitive dependency match: '{m.matched_entity}' in changed file '{m.file_path}'")
                else:
                    score = 40.0

                best_score = max(best_score, score)

        # Check if changed files have deleted selectors or routes that this test uses
        test_sels = {s.lower() for s in profile.selectors_used} if profile else set()
        test_rts = {r.lower() for r in profile.page_routes} if profile else set()

        for cf in changed_files:
            matched_deleted = any(s.lower() in test_sels for s in cf.removed_selectors)
            matched_deleted_rt = any(r.lower() in test_rts for r in cf.removed_routes)
            if matched_deleted or matched_deleted_rt:
                best_score = 100.0
                max_conf = max(max_conf, 0.98)
                explanations.append(f"Direct code breakage: Deleted entity in '{cf.path}' covers test.")

        if not explanations:
            return 0.0, max_conf, ["Test files are unaffected by the current code modifications."]

        return best_score, max_conf, explanations

    def compute_selector_breakage(
        self,
        profile: TestCoverageProfile,
        changed_files: list[ChangedFile],
    ) -> tuple[float, int, int, list[str]]:
        """
        Compute Signal B: Selector / Route Breakage (0-100).
        
        Returns (score, broken_count, modified_count, explanations).
        """
        test_selectors = {s.lower() for s in profile.selectors_used}
        test_routes = {r.lower() for r in profile.page_routes}

        broken_count = 0
        modified_count = 0
        explanations: list[str] = []

        for cf in changed_files:
            # Check removed selectors (Critical)
            for r_sel in cf.removed_selectors:
                if r_sel.lower() in test_selectors:
                    broken_count += 1
                    explanations.append(
                        f"CRITICAL: Interacted selector '{r_sel}' was deleted in '{cf.path}'"
                    )

            # Check removed routes (Critical)
            for r_rt in cf.removed_routes:
                if r_rt.lower() in test_routes:
                    broken_count += 1
                    explanations.append(
                        f"CRITICAL: Test route '{r_rt}' was removed in '{cf.path}'"
                    )

            # Check modified selectors (Non-breaking or edited)
            for m_sel in cf.changed_selectors:
                if m_sel not in cf.removed_selectors and m_sel.lower() in test_selectors:
                    modified_count += 1
                    explanations.append(f"Selector '{m_sel}' was modified in '{cf.path}'")

            # Check modified routes
            for m_rt in cf.changed_routes:
                if m_rt not in cf.removed_routes and m_rt.lower() in test_routes:
                    modified_count += 1
                    explanations.append(f"Route '{m_rt}' was modified in '{cf.path}'")

        if broken_count > 0:
            score = 100.0
        elif modified_count > 0:
            score = min(80.0, 50.0 + (modified_count * 10.0))
        else:
            score = 0.0

        return score, broken_count, modified_count, explanations

    def compute_historical_failure(
        self,
        stats: dict[str, Any],
    ) -> tuple[float, bool, int, list[str]]:
        """
        Compute Signal F: Historical Failure Rate (0-100).
        
        Handles insufficient history safely: Untested tests receive a neutral baseline
        score of 40.0 with explicit uncertainty notation.
        """
        total_runs = stats.get("total_runs", 0)
        explanations: list[str] = []

        if total_runs == 0:
            explanations.append("Insufficient history: Test has 0 recorded runs (baseline failure risk 40.0 applied)")
            return 40.0, False, 0, explanations

        fail_rate = float(stats.get("failure_rate", 0.0))

        if total_runs < 3:
            # Blend baseline with observed rate for low-sample tests
            blended = (40.0 * (3 - total_runs) + fail_rate * total_runs) / 3.0
            explanations.append(f"Low sample history ({total_runs} runs): failure rate {fail_rate:.1f}% blended to {blended:.1f}")
            return round(blended, 1), True, total_runs, explanations

        explanations.append(f"Historical failure rate: {fail_rate:.1f}% across {total_runs} recorded executions")
        return round(fail_rate, 1), True, total_runs, explanations

    def compute_flakiness_and_recency(
        self,
        stats: dict[str, Any],
    ) -> tuple[float, bool, list[str]]:
        """
        Compute Signal H: Flakiness & Failure Recency (0-100).
        
        Returns (score, recent_failure_detected, explanations).
        """
        total_runs = stats.get("total_runs", 0)
        explanations: list[str] = []

        if total_runs == 0:
            explanations.append("Insufficient history: baseline flakiness risk 30.0 applied")
            return 30.0, False, explanations

        base_flakiness = float(stats.get("flakiness_rate", 0.0))
        recent_failure = False
        recency_boost = 0.0

        recent_runs = stats.get("runs", [])
        if recent_runs:
            # Check latest run
            latest_status = recent_runs[0].get("status", "")
            if latest_status in ("failed", "error"):
                recent_failure = True
                recency_boost += 30.0
                explanations.append("Recency alert: The most recent execution of this test failed (+30 risk)")

            # Check last 3 runs
            last_3 = recent_runs[:3]
            failed_in_3 = sum(1 for r in last_3 if r.get("status") in ("failed", "error"))
            if failed_in_3 >= 2:
                recent_failure = True
                recency_boost += 20.0
                explanations.append(f"Recency alert: Failed in {failed_in_3} of the last 3 executions (+20 risk)")

        score = min(100.0, base_flakiness + recency_boost)
        if base_flakiness > 0:
            explanations.append(f"Flakiness rate: {base_flakiness:.1f}% requires retries")

        return round(score, 1), recent_failure, explanations

    def compute_change_magnitude(
        self,
        testcase_id: str,
        graph: TestToCodeGraph,
        changed_files: list[ChangedFile],
    ) -> tuple[float, int, list[str]]:
        """
        Compute Signal C: Change Magnitude (0-100) based on code volume in mapped files.
        """
        mappings = graph.get_mappings_for_test(testcase_id)
        mapped_paths = {m.file_path for m in mappings}

        lines_changed = 0
        for cf in changed_files:
            if cf.path in mapped_paths or (cf.old_path and cf.old_path in mapped_paths):
                lines_changed += (cf.additions + cf.deletions)

        score = min(100.0, lines_changed * 1.5)
        explanation = [f"Code change volume in covered files: {lines_changed} lines modified (score: {score:.1f}/100)"]
        return round(score, 1), lines_changed, explanation

    # -----------------------------------------------------------------------
    # Comprehensive Test Risk Scoring
    # -----------------------------------------------------------------------

    def score_test(
        self,
        tc: TestCase,
        profile: TestCoverageProfile,
        graph: TestToCodeGraph,
        changed_files: list[ChangedFile],
    ) -> TestRiskScore:
        """Calculate the composite predictive risk score and classify tier for a test case."""
        # 1. Fetch execution history from SQLite
        stats = get_testcase_flakiness_stats(tc.id, limit=30, db_path=self.db_path)

        # 2. Compute individual signals (all 0 - 100)
        s_impact, max_conf, exp_impact = self.compute_change_impact(tc.id, graph, changed_files, profile=profile)
        s_breakage, broken_cnt, mod_cnt, exp_breakage = self.compute_selector_breakage(profile, changed_files)
        s_failure, has_hist, run_cnt, exp_failure = self.compute_historical_failure(stats)
        s_flakiness, rec_fail, exp_flakiness = self.compute_flakiness_and_recency(stats)
        s_magnitude, lines_chg, exp_magnitude = self.compute_change_magnitude(tc.id, graph, changed_files)

        # 3. Apply configurable weighted formula
        w = self.weights
        w_imp = w.weight_impact * s_impact
        w_brk = w.weight_breakage * s_breakage
        w_fail = w.weight_failure_rate * s_failure
        w_flk = w.weight_flakiness_recency * s_flakiness
        w_mag = w.weight_change_magnitude * s_magnitude

        raw_score = w_imp + w_brk + w_fail + w_flk + w_mag
        composite_score = round(max(0.0, min(100.0, raw_score)), 1)

        # 4. Classify risk tier
        if composite_score >= 85.0:
            tier: RiskTier = "critical"
        elif composite_score >= 70.0:
            tier = "high"
        elif composite_score >= 40.0:
            tier = "medium"
        else:
            tier = "low"

        # 5. Formulate primary driver
        if broken_cnt > 0:
            primary_driver = f"Critical DOM selector or route breakage ({broken_cnt} deleted entities)"
        elif s_impact >= 80.0 and rec_fail:
            primary_driver = "High change impact combined with recent execution failure"
        elif s_impact >= 80.0:
            primary_driver = "Direct code modification to covered route/component"
        elif rec_fail:
            primary_driver = "Recent test failure pattern requires verification"
        elif s_failure >= 50.0:
            primary_driver = f"Historically failure-prone testcase ({s_failure:.1f}% failure rate)"
        elif s_impact > 0:
            primary_driver = f"Indirect dependency impact ({s_impact:.1f}/100)"
        else:
            primary_driver = "Low risk: test is decoupled from current modifications"

        # Collect explanations
        all_explanations = exp_impact + exp_breakage + exp_failure + exp_flakiness + exp_magnitude

        # Associated files, selectors, and routes
        mappings = graph.get_mappings_for_test(tc.id)
        test_sels = {s.lower() for s in profile.selectors_used}
        test_rts = {r.lower() for r in profile.page_routes}
        aff_files = sorted(
            {m.file_path for m in mappings if any(m.file_path == cf.path for cf in changed_files)}
            | {cf.path for cf in changed_files if any(s.lower() in test_sels for s in cf.removed_selectors) or any(r.lower() in test_rts for r in cf.removed_routes)}
        )
        matched_sels = sorted({m.matched_entity for m in mappings if m.relation_type == "exact_selector"})
        matched_rts = sorted({m.matched_entity for m in mappings if m.relation_type in ("exact_route", "api_endpoint")})

        breakdown = RiskFactorBreakdown(
            change_impact_score=s_impact,
            selector_breakage_score=s_breakage,
            historical_failure_score=s_failure,
            flakiness_recency_score=s_flakiness,
            change_magnitude_score=s_magnitude,
            weighted_impact=round(w_imp, 2),
            weighted_breakage=round(w_brk, 2),
            weighted_failure=round(w_fail, 2),
            weighted_flakiness=round(w_flk, 2),
            weighted_magnitude=round(w_mag, 2),
            has_history=has_hist,
            history_run_count=run_cnt,
            recent_failure_detected=rec_fail,
            broken_selectors_count=broken_cnt,
            modified_selectors_count=mod_cnt,
            lines_changed=lines_chg,
        )

        return TestRiskScore(
            testcase_id=tc.id,
            testcase_name=tc.name,
            project_id=self.project_id,
            risk_score=composite_score,
            risk_tier=tier,
            mapping_confidence=max_conf,
            primary_risk_driver=primary_driver,
            explanation=all_explanations,
            breakdown=breakdown,
            affected_files=aff_files,
            matched_selectors=matched_sels,
            matched_routes=matched_rts,
        )

    # -----------------------------------------------------------------------
    # Suite Risk Evaluation
    # -----------------------------------------------------------------------

    def evaluate_suite_risk(
        self,
        testcases: list[TestCase],
        graph: TestToCodeGraph,
        changeset: GitChangeSet,
        persist: bool = True,
    ) -> PredictiveRiskReport:
        """Score all test cases in the suite and compile a ranked PredictiveRiskReport."""
        scores: list[TestRiskScore] = []

        for tc in testcases:
            prof = TestReferenceExtractor.extract_profile(tc)
            score_item = self.score_test(tc, prof, graph, changeset.files)
            scores.append(score_item)

        # Sort descending by risk score
        scores.sort(key=lambda s: s.risk_score, reverse=True)

        critical_c = sum(1 for s in scores if s.risk_tier == "critical")
        high_c = sum(1 for s in scores if s.risk_tier == "high")
        med_c = sum(1 for s in scores if s.risk_tier == "medium")
        low_c = sum(1 for s in scores if s.risk_tier == "low")

        # Persist snapshot against git commit
        if persist:
            save_risk_scores_snapshot(
                scores=scores,
                commit_hash=changeset.current_commit,
                branch=changeset.current_branch,
                project_id=self.project_id,
                db_path=self.db_path,
            )

        return PredictiveRiskReport(
            changeset_commit=changeset.current_commit,
            changeset_branch=changeset.current_branch,
            weights=self.weights,
            total_tests_evaluated=len(scores),
            critical_count=critical_c,
            high_count=high_c,
            medium_count=med_c,
            low_count=low_c,
            scores=scores,
        )
