"""Quality Gate Evaluator enforcing strict, unambiguous policy checks."""

from __future__ import annotations

from typing import Any
from tracecase.ci.models import (
    QualityGateResult,
    QualityGateRuleViolation,
    QualityGateStatus,
)
from tracecase.ci.policy import QualityGatePolicy, get_policy
from tracecase.intelligence.models import (
    GitChangeSet,
    PrioritizationReport,
    RegressionSelectionResult,
)


class QualityGateEvaluator:
    """Evaluates CI execution outcomes against configured quality policies."""

    def __init__(self, policy: QualityGatePolicy | str | None = None) -> None:
        self.policy = get_policy(policy)

    def evaluate(
        self,
        selection: RegressionSelectionResult | None = None,
        report: PrioritizationReport | None = None,
        batch_record: dict[str, Any] | None = None,
        execution_runs: list[dict[str, Any]] | None = None,
        changeset: GitChangeSet | None = None,
    ) -> QualityGateResult:
        """Evaluate all policy rules against the test execution and selection metrics."""
        violations: list[QualityGateRuleViolation] = []
        policy = self.policy

        # Collect runs
        runs = list(execution_runs or [])
        if batch_record and not runs:
            runs = list(batch_record.get("runs") or [])

        # 1. Compute execution metrics
        total_runs = len(runs)
        passed_runs = [r for r in runs if r.get("status") == "passed"]
        failed_runs = [r for r in runs if r.get("status") == "failed"]
        flaky_runs = [r for r in runs if r.get("status") == "flaky"]
        error_runs = [r for r in runs if r.get("status") == "error"]
        cancelled_runs = [r for r in runs if r.get("status") == "cancelled"]

        completed_count = len(passed_runs) + len(failed_runs) + len(flaky_runs) + len(error_runs)

        # Risk tier lookup per testcase
        risk_tier_map: dict[str, str] = {}
        if selection:
            for t in selection.tests:
                risk_tier_map[t.testcase_id] = t.risk_tier.lower()

        # Rule 1: Critical Breakage Check
        critical_failures: list[dict[str, Any]] = []
        if policy.fail_on_critical_breakage:
            for r in failed_runs + error_runs:
                tid = r.get("testcase_id", "")
                tier = risk_tier_map.get(tid, "low")
                if tier == "critical":
                    critical_failures.append(r)
                    violations.append(
                        QualityGateRuleViolation(
                            rule_name="critical_breakage",
                            severity="critical",
                            message=(
                                f"Critical-risk test '{r.get('testcase_name') or tid}' ({tid}) "
                                f"failed execution with status '{r.get('status')}': {r.get('error_message') or 'Test assertions failed.'}"
                            ),
                            actual_value=r.get("status"),
                            threshold_value="passed",
                        )
                    )

        # Rule 2: Maximum Failure Rate
        failure_rate = (len(failed_runs) / max(1, completed_count)) * 100.0 if completed_count > 0 else 0.0
        if completed_count > 0 and failure_rate > policy.max_failure_rate_pct:
            violations.append(
                QualityGateRuleViolation(
                    rule_name="max_failure_rate",
                    severity="high",
                    message=(
                        f"Execution failure rate {failure_rate:.1f}% ({len(failed_runs)}/{completed_count} tests) "
                        f"exceeds policy limit of {policy.max_failure_rate_pct:.1f}%."
                    ),
                    actual_value=round(failure_rate, 1),
                    threshold_value=policy.max_failure_rate_pct,
                )
            )

        # Rule 3: Maximum Flakiness Rate
        flakiness_rate = (len(flaky_runs) / max(1, completed_count)) * 100.0 if completed_count > 0 else 0.0
        if completed_count > 0 and flakiness_rate > policy.max_flakiness_pct:
            violations.append(
                QualityGateRuleViolation(
                    rule_name="max_flakiness",
                    severity="medium",
                    message=(
                        f"Flakiness rate {flakiness_rate:.1f}% ({len(flaky_runs)}/{completed_count} tests) "
                        f"exceeds tolerance of {policy.max_flakiness_pct:.1f}%."
                    ),
                    actual_value=round(flakiness_rate, 1),
                    threshold_value=policy.max_flakiness_pct,
                )
            )

        # Rule 4: Execution / Infrastructure Errors
        if policy.fail_on_execution_errors and error_runs:
            for err_r in error_runs:
                violations.append(
                    QualityGateRuleViolation(
                        rule_name="execution_errors",
                        severity="critical",
                        message=(
                            f"Infrastructure or runtime execution error in '{err_r.get('testcase_id')}': "
                            f"{err_r.get('error_message') or 'Worker error'}"
                        ),
                        actual_value="error",
                        threshold_value="none",
                    )
                )

        # Rule 5: Budget Exceptions (Critical tests skipped without approval)
        budget_exceptions_count = (
            selection.budget_exception_count
            or len(selection.budget_exception_test_ids)
            or len(getattr(selection, "budget_exceptions", []))
        ) if selection else 0
        if policy.block_on_budget_exceptions and budget_exceptions_count > 0:
            violations.append(
                QualityGateRuleViolation(
                    rule_name="budget_exceptions",
                    severity="high",
                    message=(
                        f"{budget_exceptions_count} Critical-risk test(s) exceeded the time budget and "
                        "were skipped. Explicit approval is required to merge with unexecuted critical tests."
                    ),
                    actual_value=budget_exceptions_count,
                    threshold_value=0,
                )
            )

        # Rule 6: Minimum Surface Coverage
        surface_coverage = report.functional_surface_coverage_pct if report else (
            100.0 if not changeset or len(changeset.files) == 0 else 0.0
        )
        total_impacted_files = report.total_impacted_files_count if report else (
            len(changeset.files) if changeset else 0
        )
        if total_impacted_files > 0 and surface_coverage < policy.min_surface_coverage_pct:
            violations.append(
                QualityGateRuleViolation(
                    rule_name="min_surface_coverage",
                    severity="medium",
                    message=(
                        f"Surface file mapping coverage {surface_coverage:.1f}% is below required "
                        f"{policy.min_surface_coverage_pct:.1f}% ({report.covered_files_count if report else 0}/{total_impacted_files} changed files mapped to tests). "
                        "Note: surface coverage is a static file-mapping metric, not dynamic runtime branch coverage."
                    ),
                    actual_value=round(surface_coverage, 1),
                    threshold_value=policy.min_surface_coverage_pct,
                )
            )

        # Rule 7: Unmapped Code Changes
        if policy.fail_on_unmapped_changes and changeset and len(changeset.files) > 0:
            considered = selection.total_tests_considered if selection else 0
            if considered == 0:
                violations.append(
                    QualityGateRuleViolation(
                        rule_name="unmapped_changes",
                        severity="medium",
                        message=(
                            f"Repository has {len(changeset.files)} changed file(s), but 0 tests were mapped "
                            "or available in the test suite."
                        ),
                        actual_value=0,
                        threshold_value=1,
                    )
                )

        # Determine Gate Status
        if not violations:
            status: QualityGateStatus = "PASSED"
            passed = True
            summary = (
                f"Quality Gate PASSED ({policy.name.upper()} policy): All {completed_count} tests satisfied "
                f"quality criteria (0 critical failures, {failure_rate:.1f}% failure rate)."
            )
        else:
            has_critical_or_high = any(v.severity in ("critical", "high") for v in violations)
            if has_critical_or_high or policy.name == "strict":
                status = "FAILED"
                passed = False
                summary = (
                    f"Quality Gate FAILED ({policy.name.upper()} policy): {len(violations)} rule violation(s) detected. "
                    f"Merge is blocked."
                )
            else:
                status = "WARNING"
                passed = True
                summary = (
                    f"Quality Gate PASSED WITH WARNINGS ({policy.name.upper()} policy): "
                    f"{len(violations)} non-blocking advisory violation(s)."
                )

        metrics = {
            "total_runs": total_runs,
            "completed_runs": completed_count,
            "passed_count": len(passed_runs),
            "failed_count": len(failed_runs),
            "flaky_count": len(flaky_runs),
            "error_count": len(error_runs),
            "cancelled_count": len(cancelled_runs),
            "critical_failures_count": len(critical_failures),
            "failure_rate_pct": round(failure_rate, 1),
            "flakiness_rate_pct": round(flakiness_rate, 1),
            "surface_coverage_pct": round(surface_coverage, 1),
            "budget_exceptions_count": budget_exceptions_count,
        }

        return QualityGateResult(
            status=status,
            passed=passed,
            policy_name=policy.name,
            summary=summary,
            violations=violations,
            metrics=metrics,
        )
