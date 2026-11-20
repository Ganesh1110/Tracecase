"""Prioritization Explanation Engine for Tracecase (Phase 7.5.5).

Produces transparent, audit-ready, evidence-backed explanations for every regression
decision made by the selection engine. Strictly maintains:
1. Determinism: Never mutates risk scores or selection decisions during explanation.
2. Evidence Categorization:
   - Observed Evidence (verifiable Git diffs, deleted/modified locators, measured run records)
   - Heuristic Inferences (transitive module imports, prefix locators, value density)
   - Missing Evidence (untested testcases, estimated duration fallbacks)
3. Strict Separation of Mapping Confidence (certainty of link) vs Failure Risk (breakage probability).
4. Dual Reporting:
   - Human-readable Markdown regression reports.
   - Machine-readable JSON regression manifests for CI/PR integration.
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any

from tracecase.intelligence.code_mapper import TestToCodeGraph
from tracecase.intelligence.models import (
    EvidenceCategory,
    EvidenceItem,
    EvidenceType,
    GitChangeSet,
    PredictiveRiskReport,
    PrioritizationReport,
    RegressionSelectionResult,
    SelectedTestItem,
    TestPrioritizationExplanation,
    TestRiskScore,
)
from tracecase.models import TestCase
from tracecase.ui.db import (
    get_regression_selection_by_id,
    save_decision_traces,
    save_regression_selection,
)

logger = logging.getLogger(__name__)


class PrioritizationExplainer:
    """Generates verifiable evidence attribution and audit reports for regression test selection."""

    def __init__(
        self,
        project_id: str = "default_project",
        db_path: Path | str | None = None,
    ) -> None:
        self.project_id = project_id
        self.db_path = db_path

    # -----------------------------------------------------------------------
    # Single Test Explanation
    # -----------------------------------------------------------------------

    def explain_test(
        self,
        item: SelectedTestItem,
        risk_score_item: TestRiskScore | None = None,
        changeset: GitChangeSet | None = None,
        graph: TestToCodeGraph | None = None,
    ) -> TestPrioritizationExplanation:
        """Categorize observed, heuristic, and missing evidence for a single test selection decision."""
        observed: list[EvidenceItem] = []
        heuristic: list[EvidenceItem] = []
        missing: list[EvidenceItem] = []

        # 1. Evidence from Git Changeset and Code Mappings
        if changeset and risk_score_item:
            changed_paths = {cf.path: cf for cf in changeset.files}
            old_paths = {cf.old_path: cf for cf in changeset.files if cf.old_path}

            for aff in risk_score_item.affected_files:
                cf = changed_paths.get(aff) or old_paths.get(aff)
                if cf:
                    diff_info = f"+{cf.additions}/-{cf.deletions} lines modified"
                    observed.append(
                        EvidenceItem(
                            evidence_type="observed",
                            category="git_diff",
                            description=f"Direct code change in covered file '{cf.path}' ({diff_info}, type: {cf.change_type}).",
                            detail={"file": cf.path, "additions": cf.additions, "deletions": cf.deletions},
                        )
                    )

            # Check deleted selectors (Observed Breakage)
            if risk_score_item.breakdown.broken_selectors_count > 0:
                for sel in risk_score_item.matched_selectors:
                    for cf in changeset.files:
                        if sel.lower() in [s.lower() for s in cf.removed_selectors]:
                            observed.append(
                                EvidenceItem(
                                    evidence_type="observed",
                                    category="selector",
                                    description=f"CRITICAL BREAKAGE: Selector '{sel}' was deleted in '{cf.path}'.",
                                    detail={"selector": sel, "file": cf.path, "status": "deleted"},
                                )
                            )

            # Check modified selectors
            if risk_score_item.breakdown.modified_selectors_count > 0:
                for sel in risk_score_item.matched_selectors:
                    for cf in changeset.files:
                        if sel.lower() in [s.lower() for s in cf.changed_selectors] and sel.lower() not in [s.lower() for s in cf.removed_selectors]:
                            observed.append(
                                EvidenceItem(
                                    evidence_type="observed",
                                    category="selector",
                                    description=f"Modified selector: '{sel}' was modified in '{cf.path}'.",
                                    detail={"selector": sel, "file": cf.path, "status": "modified"},
                                )
                            )

        # 2. Historical Execution Evidence
        if risk_score_item:
            b = risk_score_item.breakdown
            if b.has_history:
                observed.append(
                    EvidenceItem(
                        evidence_type="observed",
                        category="history",
                        description=f"Historical failure rate: {b.historical_failure_score:.1f}% across {b.history_run_count} recorded executions.",
                        detail={"failure_rate": b.historical_failure_score, "runs": b.history_run_count},
                    )
                )
                if b.recent_failure_detected:
                    observed.append(
                        EvidenceItem(
                            evidence_type="observed",
                            category="history",
                            description="Recency alert: Recent test execution ended in failure (+30 recency risk applied).",
                            detail={"recent_failure": True},
                        )
                    )
            else:
                missing.append(
                    EvidenceItem(
                        evidence_type="missing",
                        category="history",
                        description="Untested testcase: 0 historical runs recorded in database. Neutral baseline risk (40.0) applied.",
                        detail={"has_history": False},
                    )
                )

        # 3. Duration Attribution
        if item.duration_source == "measured_history":
            observed.append(
                EvidenceItem(
                    evidence_type="observed",
                    category="budget",
                    description=f"Measured execution duration: {item.estimated_duration_s:.1f}s (median across completed test runs).",
                    detail={"duration_s": item.estimated_duration_s, "source": "measured_history"},
                )
            )
        elif item.duration_source == "recorded_testcase":
            observed.append(
                EvidenceItem(
                    evidence_type="observed",
                    category="budget",
                    description=f"Recorded step duration: {item.estimated_duration_s:.1f}s from original testcase recording metadata.",
                    detail={"duration_s": item.estimated_duration_s, "source": "recorded_testcase"},
                )
            )
        else:
            missing.append(
                EvidenceItem(
                    evidence_type="missing",
                    category="budget",
                    description=f"Fallback duration: {item.estimated_duration_s:.1f}s applied due to lack of historical runtime records.",
                    detail={"duration_s": item.estimated_duration_s, "source": "estimated_fallback"},
                )
            )

        # 4. Heuristic Inferences
        if item.mapping_confidence < 0.90 and item.mapping_confidence > 0.0:
            heuristic.append(
                EvidenceItem(
                    evidence_type="heuristic",
                    category="dependency",
                    description=f"Heuristic/Transitive link (confidence: {item.mapping_confidence:.2f}): based on imported module or symbol reference.",
                    detail={"mapping_confidence": item.mapping_confidence},
                )
            )

        if item.value_score > 0:
            heuristic.append(
                EvidenceItem(
                    evidence_type="heuristic",
                    category="budget",
                    description=f"Selection value density: {item.value_score:.1f} value units ({item.value_score / max(1.0, item.estimated_duration_s):.2f} units/sec).",
                    detail={"value_score": item.value_score},
                )
            )

        # Confidence Type
        conf_type = (
            "exact_route" if item.mapping_confidence == 1.0 else
            "exact_selector" if item.mapping_confidence == 0.95 else
            "api_endpoint" if item.mapping_confidence == 0.90 else
            "route_prefix" if item.mapping_confidence == 0.85 else
            "transitive_dependency" if item.mapping_confidence >= 0.70 else
            "heuristic_symbol"
        )

        # Risk Narrative
        risk_narrative = (
            f"Risk score is {item.risk_score:.1f} ({item.risk_tier.upper()}). "
            f"Primary driver: {item.primary_risk_driver}. "
            f"Relationship certainty: {item.mapping_confidence * 100:.0f}% ({conf_type}). "
            f"Note: Mapping confidence measures certainty of code-to-test connection, NOT failure probability."
        )

        # Selection Rationale
        if item.decision == "selected":
            if item.risk_tier == "critical":
                selection_rationale = (
                    f"Selected as top priority due to CRITICAL failure risk ({item.risk_score:.1f}). "
                    f"Fits within allocated execution budget ({item.estimated_duration_s:.1f}s)."
                )
            else:
                selection_rationale = (
                    f"Selected based on high value density ({item.value_score:.1f} score units, "
                    f"{item.estimated_duration_s:.1f}s duration) within available budget."
                )
        elif item.decision == "budget_exception":
            selection_rationale = (
                f"CRITICAL RISK SAFEGUARD: Test failure risk is {item.risk_score:.1f} ({item.risk_tier.upper()}), "
                f"but its estimated duration ({item.estimated_duration_s:.1f}s) exceeds the remaining time budget. "
                f"To prevent silent regression escapes, it has been flagged as a budget exception requiring approval."
            )
        else:
            selection_rationale = f"Excluded from regression set: {item.decision_reason}"

        return TestPrioritizationExplanation(
            testcase_id=item.testcase_id,
            testcase_name=item.testcase_name,
            decision=item.decision,
            decision_summary=f"Decision: {item.decision.upper()} - {item.decision_reason}",
            risk_score=item.risk_score,
            risk_tier=item.risk_tier,
            mapping_confidence=item.mapping_confidence,
            confidence_type=conf_type,
            estimated_duration_s=item.estimated_duration_s,
            duration_source=item.duration_source,
            primary_risk_driver=item.primary_risk_driver or "No code modification impact detected",
            observed_evidence=observed,
            heuristic_inferences=heuristic,
            missing_evidence=missing,
            risk_narrative=risk_narrative,
            selection_rationale=selection_rationale,
            affected_files=item.affected_files,
            matched_selectors=risk_score_item.matched_selectors if risk_score_item else [],
            matched_routes=risk_score_item.matched_routes if risk_score_item else [],
        )

    # -----------------------------------------------------------------------
    # Comprehensive Prioritization Report Generation
    # -----------------------------------------------------------------------

    def build_report(
        self,
        selection: RegressionSelectionResult,
        risk_report: PredictiveRiskReport | None = None,
        changeset: GitChangeSet | None = None,
        graph: TestToCodeGraph | None = None,
        persist: bool = True,
    ) -> PrioritizationReport:
        """Build the full prioritization report, generate markdown, and persist decision traces."""
        score_map: dict[str, TestRiskScore] = {}
        if risk_report:
            score_map = {s.testcase_id: s for s in risk_report.scores}

        explanations: list[TestPrioritizationExplanation] = []
        covered_files: set[str] = set()
        all_impacted_files: set[str] = set()

        if changeset:
            all_impacted_files = {cf.path for cf in changeset.files}

        for item in selection.tests:
            score_item = score_map.get(item.testcase_id)
            exp = self.explain_test(
                item=item,
                risk_score_item=score_item,
                changeset=changeset,
                graph=graph,
            )
            explanations.append(exp)
            if item.decision == "selected":
                covered_files.update(exp.affected_files)

        # Calculate distinct functional surface coverage
        if all_impacted_files:
            surface_cov_pct = round((len(covered_files & all_impacted_files) / len(all_impacted_files)) * 100.0, 1)
        else:
            surface_cov_pct = 100.0 if selection.selected_count > 0 else 0.0

        report = PrioritizationReport(
            selection_id=selection.id,
            project_id=self.project_id,
            commit_hash=selection.commit_hash,
            branch=selection.branch,
            strategy=selection.strategy,
            strategy_params=selection.strategy_params,
            created_at=selection.created_at,
            total_tests=selection.total_tests_considered,
            selected_count=selection.selected_count,
            excluded_count=selection.excluded_count,
            budget_exception_count=selection.budget_exception_count,
            time_budget_s=selection.time_budget_s,
            estimated_total_duration_s=selection.estimated_total_duration_s,
            risk_coverage_pct=selection.risk_coverage_pct,
            critical_coverage_pct=selection.critical_coverage_pct,
            functional_surface_coverage_pct=surface_cov_pct,
            covered_files_count=len(covered_files),
            total_impacted_files_count=len(all_impacted_files),
            explanations=explanations,
        )

        # Generate Markdown representation
        report.markdown_report = self.generate_markdown_report(report)

        # Persist decision traces into SQLite for auditing
        if persist:
            try:
                save_regression_selection(selection, db_path=self.db_path)
            except Exception as e:
                logger.debug("Selection already persisted or save failed: %s", e)
            save_decision_traces(
                selection_id=selection.id,
                traces=explanations,
                commit_hash=selection.commit_hash,
                project_id=self.project_id,
                db_path=self.db_path,
            )

        return report

    # -----------------------------------------------------------------------
    # Markdown Report Generator
    # -----------------------------------------------------------------------

    def generate_markdown_report(self, report: PrioritizationReport) -> str:
        """Render a publication-ready, human-readable Markdown regression decision report."""
        lines: list[str] = []
        commit_str = report.commit_hash or "Working Tree"
        branch_str = report.branch or "local"

        lines.append("# Tracecase Intelligent Regression Decision Report")
        lines.append(f"> **Commit:** `{commit_str}` ({branch_str}) | **Strategy:** `{report.strategy.upper()}` | **Generated:** {report.created_at}")
        lines.append("")

        # Executive Summary Table
        lines.append("## Executive Summary")
        lines.append("")
        lines.append("| Metric | Value | Assessment |")
        lines.append("| :--- | :--- | :--- |")
        lines.append(f"| **Tests Selected** | `{report.selected_count} / {report.total_tests}` | {round(report.selected_count / max(1, report.total_tests) * 100, 1)}% of total suite |")
        lines.append(f"| **Estimated Duration** | `{report.estimated_total_duration_s:.1f}s` | {f'Budget: {report.time_budget_s:.0f}s' if report.time_budget_s else 'Unconstrained'} |")
        lines.append(f"| **Failure Risk Coverage** | `{report.risk_coverage_pct:.1f}%` | Aggregate test risk included |")
        lines.append(f"| **Critical Test Coverage** | `{report.critical_coverage_pct:.1f}%` | Severe breakage scenarios covered |")
        lines.append(f"| **Impacted Surface Coverage** | `{report.functional_surface_coverage_pct:.1f}%` | `{report.covered_files_count} / {report.total_impacted_files_count}` modified files covered |")
        lines.append("")

        # Critical Exceptions Alert
        if report.budget_exception_count > 0:
            lines.append("### ⚠️ Critical Test Budget Exceptions")
            lines.append(
                f"> **Warning:** {report.budget_exception_count} Critical risk test(s) exceeded the time budget. "
                "Tracecase safeguards prevent high-risk tests from being silently omitted. "
                "Explicit approval is required to include or skip them."
            )
            lines.append("")

        # Selected Tests Section
        lines.append("## Selected Regression Tests")
        lines.append("")
        selected_exps = [e for e in report.explanations if e.decision == "selected"]
        if not selected_exps:
            lines.append("_No tests were selected under the current criteria._")
        else:
            for exp in selected_exps:
                lines.append(f"### {exp.testcase_name} (`{exp.testcase_id}`)")
                dur_badge = f"{exp.estimated_duration_s:.1f}s ({exp.duration_source.replace('_', ' ')})"
                lines.append(f"- **Decision:** `SELECTED` | **Risk:** `{exp.risk_score:.1f}` ({exp.risk_tier.upper()}) | **Duration:** `{dur_badge}`")
                lines.append(f"- **Certainty:** `{exp.mapping_confidence * 100:.0f}%` ({exp.confidence_type}) | **Primary Driver:** {exp.primary_risk_driver}")
                lines.append(f"- **Rationale:** {exp.selection_rationale}")

                if exp.observed_evidence:
                    lines.append("- **Observed Evidence:**")
                    for obs in exp.observed_evidence:
                        lines.append(f"  - ✓ {obs.description}")

                if exp.heuristic_inferences:
                    lines.append("- **Heuristic Inferences:**")
                    for heu in exp.heuristic_inferences:
                        lines.append(f"  - ⚡ {heu.description}")

                if exp.missing_evidence:
                    lines.append("- **Missing / Neutral Evidence:**")
                    for mis in exp.missing_evidence:
                        lines.append(f"  - ℹ {mis.description}")

                lines.append("")

        # Budget Exceptions Section
        exceptions_exps = [e for e in report.explanations if e.decision == "budget_exception"]
        if exceptions_exps:
            lines.append("## Budget Exception Candidates (Pending Approval)")
            lines.append("")
            for exp in exceptions_exps:
                lines.append(f"### ⚠️ {exp.testcase_name} (`{exp.testcase_id}`)")
                lines.append(f"- **Status:** `BUDGET EXCEPTION` | **Risk:** `{exp.risk_score:.1f}` ({exp.risk_tier.upper()}) | **Duration Needed:** `{exp.estimated_duration_s:.1f}s`")
                lines.append(f"- **Action Required:** {exp.selection_rationale}")
                if exp.observed_evidence:
                    for obs in exp.observed_evidence:
                        lines.append(f"  - ✓ {obs.description}")
                lines.append("")

        # Excluded Tests Section
        excluded_exps = [e for e in report.explanations if e.decision == "excluded"]
        if excluded_exps:
            lines.append("## Excluded Test Summary")
            lines.append("")
            lines.append("| Test Case | Risk Tier | Risk | Est Duration | Reason for Exclusion |")
            lines.append("| :--- | :--- | :---: | :---: | :--- |")
            for exp in excluded_exps:
                lines.append(f"| `{exp.testcase_id}` | {exp.risk_tier.upper()} | {exp.risk_score:.1f} | {exp.estimated_duration_s:.1f}s | {exp.selection_rationale} |")
            lines.append("")

        # Methodology & Disclaimers
        lines.append("---")
        lines.append(f"_{report.disclaimer}_")
        lines.append("")

        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # Machine-Readable JSON Manifest Generator
    # -----------------------------------------------------------------------

    def generate_json_manifest(self, report: PrioritizationReport) -> dict[str, Any]:
        """Produce a structured manifest suitable for CI/PR pull request automation."""
        return {
            "schema_version": "1.0.0",
            "generator": "Tracecase Intelligent Regression Prioritizer",
            "selection_id": report.selection_id,
            "project_id": report.project_id,
            "commit_hash": report.commit_hash,
            "branch": report.branch,
            "timestamp": report.created_at,
            "strategy": {
                "name": report.strategy,
                "parameters": report.strategy_params,
            },
            "summary": {
                "total_tests_considered": report.total_tests,
                "selected_count": report.selected_count,
                "excluded_count": report.excluded_count,
                "budget_exception_count": report.budget_exception_count,
                "estimated_duration_seconds": report.estimated_total_duration_s,
                "risk_coverage_percentage": report.risk_coverage_pct,
                "critical_coverage_percentage": report.critical_coverage_pct,
                "surface_coverage_percentage": report.functional_surface_coverage_pct,
            },
            "selected_test_ids": [e.testcase_id for e in report.explanations if e.decision == "selected"],
            "budget_exception_test_ids": [e.testcase_id for e in report.explanations if e.decision == "budget_exception"],
            "excluded_test_ids": [e.testcase_id for e in report.explanations if e.decision == "excluded"],
            "tests": [e.model_dump() for e in report.explanations],
        }
