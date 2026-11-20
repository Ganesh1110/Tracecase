"""Regression Drift Comparator comparing a test execution batch against a baseline."""

from __future__ import annotations

import logging
from typing import Any

from tracecase.ci.baseline.models import BaselineSnapshot, compute_test_revision_hash
from tracecase.ci.drift.classifier import RegressionDriftClassifier
from tracecase.ci.drift.models import DriftAnalysisResult, DriftClassification, TestDriftItem
from tracecase.models import TestCase

logger = logging.getLogger("tracecase.ci.drift.comparator")


class RegressionDriftComparator:
    """Compares current PR test outcomes against baseline snapshot."""

    @staticmethod
    def compare_batch(
        runs: list[dict[str, Any]],
        baseline: BaselineSnapshot | None,
        run_id: str,
        project_id: str = "default_project",
        base_commit: str | None = None,
        pr_commit: str | None = None,
        browser: str = "chromium",
        testcases_map: dict[str, TestCase] | None = None,
    ) -> DriftAnalysisResult:
        """Analyze test runs against baseline snapshot and produce DriftAnalysisResult."""
        tc_map = testcases_map or {}
        items: list[TestDriftItem] = []

        new_regressions = 0
        pre_existing_failures = 0
        fixed_regressions = 0
        newly_flaky = 0
        persistent_flaky = 0
        stable_passes = 0
        unknown_baseline_failures = 0
        infra_errors = 0
        def_drift_count = 0

        total_base_dur = 0.0
        total_pr_dur = 0.0

        for r in runs:
            tid = r.get("testcase_id", "")
            tname = r.get("testcase_name") or tid
            pr_st = r.get("status", "unknown")
            pr_dur = float(r.get("duration_ms") or 0.0)
            pr_err = r.get("error_message")

            tc_obj = tc_map.get(tid)
            pr_rev_hash = compute_test_revision_hash(tc_obj) if tc_obj else ""

            base_outcome = baseline.get_outcome(tid) if baseline else None
            base_st = base_outcome.status if base_outcome else None
            base_dur = base_outcome.duration_ms if base_outcome else None
            base_err = base_outcome.error_message if base_outcome else None

            classification, explanation, test_def_drift = RegressionDriftClassifier.classify(
                pr_status=pr_st,
                base_outcome=base_outcome,
                pr_test_revision_hash=pr_rev_hash,
            )

            dur_delta = (pr_dur - base_dur) if base_dur is not None else None
            if base_dur is not None:
                total_base_dur += base_dur
            total_pr_dur += pr_dur

            # Count categories
            if classification == DriftClassification.NEW_REGRESSION:
                new_regressions += 1
            elif classification == DriftClassification.PRE_EXISTING_FAILURE:
                pre_existing_failures += 1
            elif classification == DriftClassification.FIXED_REGRESSION:
                fixed_regressions += 1
            elif classification == DriftClassification.NEWLY_FLAKY:
                newly_flaky += 1
            elif classification == DriftClassification.PERSISTENT_FLAKY:
                persistent_flaky += 1
            elif classification == DriftClassification.STABLE_PASS:
                stable_passes += 1
            elif classification == DriftClassification.UNKNOWN_BASELINE_FAILURE:
                unknown_baseline_failures += 1
            elif classification == DriftClassification.INFRASTRUCTURE_ERROR:
                infra_errors += 1

            if test_def_drift:
                def_drift_count += 1

            items.append(
                TestDriftItem(
                    testcase_id=tid,
                    testcase_name=tname,
                    classification=classification,
                    pr_status=pr_st,
                    base_status=base_st,
                    test_definition_drift=test_def_drift,
                    base_duration_ms=base_dur,
                    pr_duration_ms=pr_dur,
                    duration_delta_ms=dur_delta,
                    pr_error_message=pr_err,
                    base_error_message=base_err,
                    explanation=explanation,
                )
            )

        duration_delta = total_pr_dur - total_base_dur
        dur_drift_pct = (
            round((duration_delta / total_base_dur) * 100.0, 1)
            if total_base_dur > 0
            else 0.0
        )

        return DriftAnalysisResult(
            run_id=run_id,
            project_id=project_id,
            base_commit=base_commit or (baseline.commit_hash if baseline else None),
            pr_commit=pr_commit,
            browser=browser,
            baseline_found=baseline is not None,
            baseline_match_type="exact" if (baseline and base_commit and baseline.commit_hash.startswith(base_commit[:7])) else ("branch" if baseline else "none"),
            total_compared=len(items),
            new_regressions_count=new_regressions,
            pre_existing_failures_count=pre_existing_failures,
            fixed_regressions_count=fixed_regressions,
            newly_flaky_count=newly_flaky,
            persistent_flaky_count=persistent_flaky,
            stable_passes_count=stable_passes,
            unknown_baseline_failures_count=unknown_baseline_failures,
            infrastructure_errors_count=infra_errors,
            tests_with_definition_drift_count=def_drift_count,
            total_base_duration_ms=total_base_dur,
            total_pr_duration_ms=total_pr_dur,
            duration_delta_ms=duration_delta,
            duration_drift_pct=dur_drift_pct,
            items=items,
        )
