"""SARIF 2.1.0 Reporter for static analysis and regression findings."""

from __future__ import annotations

from typing import Any
from tracecase.ci.models import QualityGateResult
from tracecase.intelligence.models import RegressionSelectionResult


def generate_sarif_report(
    gate_result: QualityGateResult,
    runs: list[dict[str, Any]],
    selection: RegressionSelectionResult | None = None,
    repo_path: str = ".",
) -> dict[str, Any]:
    """Generate SARIF 2.1.0 compliant JSON report for GitHub Code Scanning / GitLab SAST widgets."""
    rules = [
        {
            "id": "TRACECASE-CRITICAL-FAIL",
            "name": "CriticalRegressionFailure",
            "shortDescription": {"text": "A critical-risk test case failed during regression verification."},
            "fullDescription": {"text": "A test classified as Critical due to code/locator modifications failed."},
            "defaultConfiguration": {"level": "error"},
        },
        {
            "id": "TRACECASE-TEST-FAIL",
            "name": "RegressionTestFailure",
            "shortDescription": {"text": "A regression test case failed assertions or expectations."},
            "fullDescription": {"text": "Test execution encountered failure or assertion error."},
            "defaultConfiguration": {"level": "warning"},
        },
        {
            "id": "TRACECASE-BUDGET-EXC",
            "name": "CriticalBudgetException",
            "shortDescription": {"text": "Critical-risk test skipped due to time budget limit."},
            "fullDescription": {"text": "A high-risk test was not executed because the time budget was exceeded."},
            "defaultConfiguration": {"level": "warning"},
        },
        {
            "id": "TRACECASE-FLAKY",
            "name": "FlakyTestDetected",
            "shortDescription": {"text": "Test failed on attempt 1 but passed after retries."},
            "fullDescription": {"text": "Flaky behavior indicates timing, race condition, or non-deterministic state."},
            "defaultConfiguration": {"level": "note"},
        },
    ]

    results: list[dict[str, Any]] = []

    # Map candidate tests to affected files
    affected_file_map: dict[str, list[str]] = {}
    risk_tier_map: dict[str, str] = {}
    if selection:
        for t in selection.tests:
            affected_file_map[t.testcase_id] = t.affected_files
            risk_tier_map[t.testcase_id] = t.risk_tier.lower()

    for r in runs:
        tid = r.get("testcase_id", "")
        status = r.get("status")
        aff_files = affected_file_map.get(tid, [])
        primary_file = aff_files[0] if aff_files else "tests"
        tier = risk_tier_map.get(tid, "low")

        if status in ("failed", "error"):
            rule_id = "TRACECASE-CRITICAL-FAIL" if tier == "critical" else "TRACECASE-TEST-FAIL"
            level = "error" if tier == "critical" else "warning"
            results.append({
                "ruleId": rule_id,
                "level": level,
                "message": {
                    "text": (
                        f"Regression failure in test '{r.get('testcase_name') or tid}' ({tid}) "
                        f"targeting affected file '{primary_file}': {r.get('error_message') or 'Step failure.'}"
                    )
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": primary_file},
                            "region": {"startLine": 1, "startColumn": 1},
                        }
                    }
                ],
            })

        elif status == "flaky":
            results.append({
                "ruleId": "TRACECASE-FLAKY",
                "level": "note",
                "message": {
                    "text": f"Test '{r.get('testcase_name') or tid}' was unstable and required retry recovery."
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": primary_file},
                            "region": {"startLine": 1, "startColumn": 1},
                        }
                    }
                ],
            })

    # Record budget exceptions in SARIF
    exc_items = (
        (selection.budget_exception_test_ids if selection else [])
        or (getattr(selection, "budget_exceptions", []) if selection else [])
    )
    if selection and (selection.budget_exception_count > 0 or len(exc_items) > 0):
        for exc_id in exc_items:
            aff = affected_file_map.get(exc_id, ["unknown"])[0]
            results.append({
                "ruleId": "TRACECASE-BUDGET-EXC",
                "level": "warning",
                "message": {
                    "text": f"Critical test '{exc_id}' exceeded execution time budget and was skipped."
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": aff},
                            "region": {"startLine": 1, "startColumn": 1},
                        }
                    }
                ],
            })

    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Tracecase Continuous Quality Gate",
                        "informationUri": "https://github.com/tracecase/tracecase",
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }
