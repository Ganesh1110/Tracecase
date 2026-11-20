"""SARIF 2.1.0 Reporter for static analysis and regression findings.

Compliant with GitHub Code Scanning SARIF ingestion specifications:
- OASIS SARIF 2.1.0 JSON schema
- Unique rule IDs with markdown-formatted help descriptions
- %SRCROOT% base URI identifier and normalized relative file paths
- Strict distinction between application test failures and infrastructure errors
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from tracecase.ci.models import QualityGateResult
from tracecase.intelligence.models import RegressionSelectionResult


def normalize_repo_relative_path(file_path: str, repo_path: str = ".") -> str:
    """Normalize file path to a relative path suitable for SARIF %SRCROOT% mapping."""
    clean = file_path.replace("\\", "/").strip()
    if clean.startswith("file://"):
        clean = clean[len("file://"):]
    
    p = Path(clean)
    repo_p = Path(repo_path).resolve()
    try:
        if p.is_absolute() and p.is_relative_to(repo_p):
            clean = str(p.relative_to(repo_p))
    except Exception:
        pass

    # Strip leading ./ or /
    clean = clean.lstrip("./").lstrip("/")
    return clean or "unknown"


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
            "help": {
                "text": "Inspect the failure logs and update the application code or selector.",
                "markdown": "### Critical Regression Failure\nA test classified as **Critical** due to modified routes or selectors failed.\n\n**Action:** Inspect step failure logs, locators, and update assertions.",
            },
            "defaultConfiguration": {"level": "error"},
            "properties": {"tags": ["quality-gate", "regression", "critical"]},
        },
        {
            "id": "TRACECASE-TEST-FAIL",
            "name": "RegressionTestFailure",
            "shortDescription": {"text": "A regression test case failed assertions or expectations."},
            "fullDescription": {"text": "Test execution encountered failure or assertion error."},
            "help": {
                "text": "Review failed assertions and verify application behavior.",
                "markdown": "### Regression Test Failure\nTest assertion failed during execution.\n\n**Action:** Review expectations and API responses.",
            },
            "defaultConfiguration": {"level": "warning"},
            "properties": {"tags": ["quality-gate", "regression"]},
        },
        {
            "id": "TRACECASE-INFRA-ERROR",
            "name": "InfrastructureExecutionError",
            "shortDescription": {"text": "Internal runner or browser process crashed or encountered an execution fault."},
            "fullDescription": {"text": "A browser crash, disconnection, or runner exception aborted test execution."},
            "help": {
                "text": "Check browser binaries, memory limits, and host environment dependencies.",
                "markdown": "### Infrastructure Execution Error\nThe test runner could not complete execution due to a browser crash or host resource error.\n\n**Action:** Check host resources, Playwright browser dependencies, or increase runner memory.",
            },
            "defaultConfiguration": {"level": "error"},
            "properties": {"tags": ["quality-gate", "infrastructure"]},
        },
        {
            "id": "TRACECASE-BUDGET-EXC",
            "name": "CriticalBudgetException",
            "shortDescription": {"text": "Critical-risk test skipped due to time budget limit."},
            "fullDescription": {"text": "A high-risk test was not executed because the time budget was exceeded."},
            "help": {
                "text": "Increase CI time budget or pass --include-critical-exceptions to run skipped critical tests.",
                "markdown": "### Critical Test Budget Exception\nA test classified as Critical was omitted to respect the pipeline time budget.\n\n**Action:** Increase `--budget` or use `--include-critical-exceptions`.",
            },
            "defaultConfiguration": {"level": "warning"},
            "properties": {"tags": ["quality-gate", "budget"]},
        },
        {
            "id": "TRACECASE-FLAKY",
            "name": "FlakyTestDetected",
            "shortDescription": {"text": "Test failed on attempt 1 but passed after retries."},
            "fullDescription": {"text": "Flaky behavior indicates timing, race condition, or non-deterministic state."},
            "help": {
                "text": "Investigate race conditions, network latency, or asynchronous timing in the test.",
                "markdown": "### Flaky Test Detected\nTest succeeded on retry after initial failure.\n\n**Action:** Stabilize selectors and add explicit readiness waits.",
            },
            "defaultConfiguration": {"level": "note"},
            "properties": {"tags": ["quality-gate", "flaky"]},
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
        raw_file = aff_files[0] if aff_files else "tests"
        primary_file = normalize_repo_relative_path(raw_file, repo_path=repo_path)
        tier = risk_tier_map.get(tid, "low")

        if status == "error":
            # Infrastructure / browser crash error
            results.append({
                "ruleId": "TRACECASE-INFRA-ERROR",
                "level": "error",
                "message": {
                    "text": (
                        f"Infrastructure or browser crash in test '{r.get('testcase_name') or tid}' ({tid}): "
                        f"{r.get('error_message') or 'Browser or runner process terminated unexpectedly.'}"
                    )
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": primary_file,
                                "uriBaseId": "%SRCROOT%",
                            },
                            "region": {"startLine": 1, "startColumn": 1},
                        }
                    }
                ],
            })

        elif status == "failed":
            # Application test failure
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
                            "artifactLocation": {
                                "uri": primary_file,
                                "uriBaseId": "%SRCROOT%",
                            },
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
                            "artifactLocation": {
                                "uri": primary_file,
                                "uriBaseId": "%SRCROOT%",
                            },
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
            raw_aff = affected_file_map.get(exc_id, ["unknown"])[0]
            aff = normalize_repo_relative_path(raw_aff, repo_path=repo_path)
            results.append({
                "ruleId": "TRACECASE-BUDGET-EXC",
                "level": "warning",
                "message": {
                    "text": f"Critical test '{exc_id}' exceeded execution time budget and was skipped."
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": aff,
                                "uriBaseId": "%SRCROOT%",
                            },
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
                        "semanticVersion": "0.2.0",
                        "informationUri": "https://github.com/tracecase/tracecase",
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }
