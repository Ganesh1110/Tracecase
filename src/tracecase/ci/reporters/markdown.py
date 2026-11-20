"""Markdown Reporter for GitHub Step Summary and PR comment publication."""

from __future__ import annotations

from typing import Any
from tracecase.ci.drift.models import DriftAnalysisResult, DriftClassification
from tracecase.ci.models import CIRunResult, QualityGateResult
from tracecase.intelligence.models import PrioritizationReport, RegressionSelectionResult


def generate_ci_markdown_report(
    run_result: CIRunResult,
    gate_result: QualityGateResult,
    selection: RegressionSelectionResult | None = None,
    report: PrioritizationReport | None = None,
    drift_result: DriftAnalysisResult | None = None,
) -> str:
    """Generate publication-ready Markdown for GitHub Step Summary and PR comments."""
    lines: list[str] = []

    status_badge = (
        "🟢 **QUALITY GATE PASSED**" if gate_result.status == "PASSED" else
        "🔴 **QUALITY GATE FAILED**" if gate_result.status == "FAILED" else
        "🟡 **QUALITY GATE WARNING**"
    )

    lines.append(f"# Tracecase Continuous Quality Gate — {status_badge}")
    lines.append(
        f"> **Policy:** `{gate_result.policy_name.upper()}` | "
        f"**Commit:** `{run_result.commit_hash or 'HEAD'}` | "
        f"**Base:** `{run_result.base_ref or 'main'}` | "
        f"**Duration:** `{run_result.duration_seconds:.1f}s`"
    )
    lines.append("")

    # Summary Table
    m = gate_result.metrics
    failed_cnt = m.get("failed_count", 0)
    error_cnt = m.get("error_count", 0)
    critical_cnt = m.get("critical_failures_count", 0)
    flaky_cnt = m.get("flaky_count", 0)
    surface_pct = m.get("surface_coverage_pct", 0.0)
    budget_exc_cnt = m.get("budget_exceptions_count", 0)

    lines.append("## Executive Summary")
    lines.append("")
    lines.append("| Metric | Result | Target / Threshold | Status |")
    lines.append("| :--- | :--- | :--- | :---: |")
    lines.append(f"| **Tests Executed** | `{m.get('completed_runs', 0)} / {run_result.total_considered}` | Bounded Worker Pool | ℹ |")
    lines.append(f"| **Application Failures** | `{failed_cnt}` ({m.get('failure_rate_pct', 0.0)}%) | `0.0%` max | {'✓' if failed_cnt == 0 else '❌'} |")
    if error_cnt > 0:
        lines.append(f"| **Infrastructure Errors** | `{error_cnt}` | `0` allowed (browser/runner crashes) | 💥 |")
    lines.append(f"| **Critical Breakages** | `{critical_cnt}` | `0` allowed (modified routes/selectors) | {'✓' if critical_cnt == 0 else '❌'} |")
    lines.append(f"| **Flaky Tests** | `{flaky_cnt}` ({m.get('flakiness_rate_pct', 0.0)}%) | Retry recoveries (not counted as failure) | {'✓' if flaky_cnt == 0 else '⚡'} |")
    lines.append(f"| **Surface File Coverage** | `{surface_pct}%` | Static file mapping threshold | {'✓' if surface_pct >= 70.0 else '⚠'} |")
    lines.append(f"| **Budget Exceptions** | `{budget_exc_cnt}` | Skipped critical tests | {'✓' if budget_exc_cnt == 0 else '⚠️'} |")
    lines.append("")

    lines.append("> ℹ️ **Note on Surface Coverage:** Surface coverage measures the percentage of changed application files that have at least one mapped regression test in Tracecase. It is a static test-to-code mapping metric, distinct from dynamic line or branch behavioral coverage.")
    lines.append("")

    # Regression Drift Section (Phase 8.3)
    if drift_result and drift_result.baseline_found:
        lines.append("## 🔍 Baseline & Regression Drift Analysis")
        lines.append("")
        base_sha = (drift_result.base_commit or "unknown")[:8]
        pr_sha = (drift_result.pr_commit or "HEAD")[:8]
        lines.append(
            f"> **Base Commit:** `{base_sha}` | **PR Commit:** `{pr_sha}` | "
            f"**Baseline Match:** `{drift_result.baseline_match_type.upper()}` | "
            f"**Browser:** `{drift_result.browser}`"
        )
        lines.append("")
        lines.append("| Regression Classification | Count | Failure Attribution & Significance | Impact |")
        lines.append("| :--- | :---: | :--- | :---: |")
        lines.append(
            f"| 🚨 **New Regressions** | `{drift_result.new_regressions_count}` | "
            f"Passed on base commit, failed on PR | {'❌ Blocking' if drift_result.new_regressions_count > 0 else '✓ None'} |"
        )
        lines.append(
            f"| 🔧 **Fixed Regressions** | `{drift_result.fixed_regressions_count}` | "
            f"Previously failed on base commit, now passing | {'🎉 Improvement' if drift_result.fixed_regressions_count > 0 else '—'} |"
        )
        lines.append(
            f"| ⏳ **Pre-Existing Failures** | `{drift_result.pre_existing_failures_count}` | "
            f"Already failing on base commit before this PR | {'ℹ Allowed Debt' if gate_result.passed else '⚠ Failing'} |"
        )
        lines.append(
            f"| ⚡ **Newly Flaky Tests** | `{drift_result.newly_flaky_count}` | "
            f"Stable on base commit, required retries on PR | {'⚠ Instability' if drift_result.newly_flaky_count > 0 else '✓ None'} |"
        )
        lines.append(
            f"| 🛡️ **Stable Passes** | `{drift_result.stable_passes_count}` | "
            f"Passed consistently on both base commit and PR | ✓ Verified |"
        )
        delta_s = drift_result.duration_delta_ms / 1000.0
        delta_str = f"{'+' if delta_s >= 0 else ''}{delta_s:.2f}s ({drift_result.duration_drift_pct:+.1f}%)"
        lines.append(
            f"| ⏱️ **Duration Drift (Δ)** | `{delta_str}` | "
            f"Execution time difference vs base commit | ℹ |"
        )
        if drift_result.tests_with_definition_drift_count > 0:
            lines.append(
                f"| 📝 **Test Definition Drift** | `{drift_result.tests_with_definition_drift_count}` | "
                f"Tests whose locators, steps, or assertions were modified in this PR | ℹ |"
            )
        lines.append("")

    # Gate Violations Callout
    if gate_result.violations:
        lines.append("### ⚠️ Quality Gate Violations")
        lines.append("")
        for v in gate_result.violations:
            sev_badge = "🔴" if v.severity == "critical" else "🟠" if v.severity == "high" else "🟡"
            lines.append(f"- {sev_badge} **[{v.severity.upper()}] {v.rule_name}**: {v.message}")
        lines.append("")

    # Test Results Breakdown
    runs = run_result.test_results
    if runs:
        # Build drift classification map if available
        drift_item_map = {item.testcase_id: item for item in (drift_result.items if drift_result else [])}

        lines.append("## Test Results Breakdown")
        lines.append("")
        if drift_result and drift_result.baseline_found:
            lines.append("| Test Case | Status | Attribution | Duration (Δ) | Retries | Details |")
            lines.append("| :--- | :---: | :---: | :---: | :---: | :--- |")
        else:
            lines.append("| Test Case | Status | Duration | Retries | Message |")
            lines.append("| :--- | :---: | :---: | :---: | :--- |")

        for r in runs:
            tid = r.get("testcase_id", "")
            st = r.get("status", "unknown")
            st_icon = (
                "✅ Pass" if st == "passed" else
                "❌ Fail" if st == "failed" else
                "⚡ Flaky" if st == "flaky" else
                "💥 Error" if st == "error" else
                "⚪ Skipped"
            )
            t_name = r.get("testcase_name") or tid
            dur = f"{float(r.get('duration_ms') or 0) / 1000.0:.2f}s"
            retries = len(r.get("retry_history") or [])
            err_msg = (r.get("error_message") or "—").replace("\n", " ")[:70]

            if drift_result and drift_result.baseline_found:
                d_item = drift_item_map.get(tid)
                if d_item:
                    c = d_item.classification
                    attr_badge = (
                        "🚨 **New Regression**" if c == DriftClassification.NEW_REGRESSION else
                        "⏳ Pre-Existing" if c == DriftClassification.PRE_EXISTING_FAILURE else
                        "🔧 **Fixed**" if c == DriftClassification.FIXED_REGRESSION else
                        "⚡ Newly Flaky" if c == DriftClassification.NEWLY_FLAKY else
                        "🛡️ Stable" if c == DriftClassification.STABLE_PASS else
                        "❓ Unknown Base" if c == DriftClassification.UNKNOWN_BASELINE_FAILURE else
                        "✨ New Test" if c == DriftClassification.NEW_TEST_PASS else
                        "💥 Infra Error"
                    )
                    if d_item.test_definition_drift:
                        attr_badge += " 📝"
                    dur_delta_str = f" ({d_item.duration_delta_ms/1000.0:+.2f}s)" if d_item.duration_delta_ms is not None else ""
                    dur_display = f"`{dur}`{dur_delta_str}"
                else:
                    attr_badge = "—"
                    dur_display = f"`{dur}`"

                lines.append(f"| `{t_name}` | {st_icon} | {attr_badge} | {dur_display} | `{retries}` | {err_msg} |")
            else:
                lines.append(f"| `{t_name}` | {st_icon} | `{dur}` | `{retries}` | {err_msg} |")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("_Generated by Tracecase Continuous Quality Gate. Standalone, auditable, evidence-backed._")
    lines.append("")

    return "\n".join(lines)
