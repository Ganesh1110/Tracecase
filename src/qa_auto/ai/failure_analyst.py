"""Failure Analysis & Root Cause Explanation Engine for QA Auto.

Examines failed execution runs, step logs, assertion mismatches, console errors,
and network responses to diagnose the exact root cause and recommend actionable fixes.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from qa_auto.ai.models import Message
from qa_auto.ai.provider import Provider

FailureCategory = Literal[
    "APPLICATION_BUG",
    "SELECTOR_DRIFT",
    "ASSERTION_FAILURE",
    "TIMEOUT_ENVIRONMENT",
    "AUTH_EXPIRY",
    "UNKNOWN",
]


class FailureAnalysisResult(BaseModel):
    """Structured root cause diagnosis of an execution failure."""

    execution_id: str
    testcase_name: str
    failed_step_number: int | None = None
    step_number_failed: int | None = None
    failure_category: FailureCategory
    category: str = ""
    root_cause: str
    remediation_advice: str
    remediation: str = ""
    confidence: float = 0.9
    error_summary: str = ""
    selector_drift_detected: bool = False
    console_errors_observed: list[str] = Field(default_factory=list)
    failed_assertions: list[dict[str, Any]] = Field(default_factory=list)


def analyze_failure_heuristics(execution: dict[str, Any]) -> FailureAnalysisResult:
    """Perform deterministic root cause analysis using execution logs and error patterns."""
    exec_id = execution.get("id", "")
    tc_name = execution.get("testcase_name", "")
    error_msg = execution.get("error_message") or ""
    step_logs = execution.get("step_logs") or execution.get("steps") or []

    failed_step = next((s for s in step_logs if s.get("status") in ("failed", "error")), None)
    failed_step_num = (
        failed_step.get("step_number") if failed_step else None
    ) or execution.get("step_number_failed")
    failed_step_error = (failed_step.get("error") if failed_step else "") or error_msg

    # Extract failed assertions
    failed_assertions = []
    if failed_step and failed_step.get("assertions"):
        for a in failed_step["assertions"]:
            if not a.get("passed"):
                failed_assertions.append(a)

    # Extract console logs if present
    logs = execution.get("logs") or []
    console_errors = [l for l in logs if "Error" in l or "500" in l or "failed" in l.lower()]

    def _build_result(
        category: FailureCategory,
        root_cause: str,
        remediation: str,
        confidence: float = 0.9,
        selector_drift: bool = False,
    ) -> FailureAnalysisResult:
        return FailureAnalysisResult(
            execution_id=exec_id,
            testcase_name=tc_name,
            failed_step_number=failed_step_num,
            step_number_failed=failed_step_num,
            failure_category=category,
            category=category,
            root_cause=root_cause,
            remediation_advice=remediation,
            remediation=remediation,
            confidence=confidence,
            error_summary=failed_step_error or root_cause,
            selector_drift_detected=selector_drift,
            console_errors_observed=console_errors,
            failed_assertions=failed_assertions,
        )

    # Pattern 1: Assertion Failure
    if failed_assertions or "assertion" in failed_step_error.lower():
        if failed_assertions:
            first_ast = failed_assertions[0]
            kind = first_ast.get("kind", "")
            exp = first_ast.get("expected")
            act = first_ast.get("actual")
            target = first_ast.get("target")
            root_cause = (
                f"Assertion [{kind}] failed on step {failed_step_num or 1}: "
                f"expected '{exp}', but observed '{act}'" + (f" on {target}." if target else ".")
            )
        else:
            root_cause = f"Assertion verification failed on step {failed_step_num or 1}: {failed_step_error}"

        remediation = (
            f"Inspect the application state at step {failed_step_num or 1}. If the application behavior is correct, "
            f"update the assertion expected value. If the application output is incorrect, file a bug for the development team."
        )
        return _build_result("ASSERTION_FAILURE", root_cause, remediation, confidence=0.95)

    # Pattern 2: Selector Drift (Element not found / timeout on locator)
    if any(
        kw in failed_step_error.lower()
        for kw in (
            "element not found",
            "waiting for locator",
            "waiting for selector",
            "timed out",
            "timeout",
            "could not locate",
            "no element matched",
        )
    ):
        sel = (failed_step.get("selector_used") or failed_step.get("selector")) if failed_step else ""
        root_cause = (
            f"Selector Drift: The target DOM element '{sel or 'unspecified'}' could not be resolved during replay."
        )
        remediation = (
            "The frontend DOM structure or CSS class names may have updated. "
            "Use the Selector Intelligence tab to select a resilient locator such as data-testid or accessible role."
        )
        return _build_result(
            "SELECTOR_DRIFT", root_cause, remediation, confidence=0.9, selector_drift=True
        )

    # Pattern 3: Application Bug (500 or uncaught runtime exceptions)
    if any(kw in failed_step_error.lower() for kw in ("500 internal server error", "uncaught error", "exception")):
        root_cause = f"Application Runtime Bug: The backend or frontend threw an unhandled error: {failed_step_error}"
        remediation = "Investigate backend server logs or frontend console exceptions for stack trace details."
        return _build_result("APPLICATION_BUG", root_cause, remediation, confidence=0.9)

    # Pattern 4: Network / Environment Timeout
    if any(kw in failed_step_error.lower() for kw in ("net::", "econnrefused", "connection refused", "socket hang up")):
        root_cause = f"Environment / Network Failure: Connection error detected: {failed_step_error}"
        remediation = "Verify that the target application test server is up, healthy, and accessible from the test runner."
        return _build_result("TIMEOUT_ENVIRONMENT", root_cause, remediation, confidence=0.85)

    # Fallback
    root_cause = f"Test execution terminated with error: {failed_step_error or 'Unknown failure'}"
    remediation = "Review step execution logs and replay screenshots in the Execution Report."
    return _build_result("UNKNOWN", root_cause, remediation, confidence=0.7)


async def analyze_execution_failure(
    execution: dict[str, Any], provider: Provider | None = None
) -> FailureAnalysisResult:
    """Analyze execution failure with heuristics and optional LLM enrichment."""
    base_result = analyze_failure_heuristics(execution)

    if provider and provider.name != "null":
        try:
            prompt = (
                f"Diagnose this automated test failure:\n"
                f"Testcase: {base_result.testcase_name}\n"
                f"Failed Step: {base_result.failed_step_number}\n"
                f"Error: {base_result.error_summary}\n"
                f"Failed Assertions: {base_result.failed_assertions}\n"
                f"Console Errors: {base_result.console_errors_observed}\n\n"
                "Return a JSON object with keys: failure_category ('APPLICATION_BUG'|'SELECTOR_DRIFT'|'ASSERTION_FAILURE'|'TIMEOUT_ENVIRONMENT'|'AUTH_EXPIRY'), "
                "root_cause (str), remediation_advice (str), confidence (float)."
            )
            ai_data = await provider.chat([Message(role="user", content=prompt)], schema={})
            if ai_data and "root_cause" in ai_data:
                base_result.root_cause = str(ai_data["root_cause"])
            if ai_data and "remediation_advice" in ai_data:
                base_result.remediation_advice = str(ai_data["remediation_advice"])
            if ai_data and "failure_category" in ai_data:
                cat = str(ai_data["failure_category"])
                if cat in ("APPLICATION_BUG", "SELECTOR_DRIFT", "ASSERTION_FAILURE", "TIMEOUT_ENVIRONMENT", "AUTH_EXPIRY"):
                    base_result.failure_category = cat  # type: ignore[assignment]
        except Exception:
            pass

    return base_result
