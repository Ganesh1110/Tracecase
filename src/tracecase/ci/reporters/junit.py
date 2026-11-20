"""JUnit XML Reporter for CI/CD test results and summaries."""

from __future__ import annotations

from typing import Any
import xml.etree.ElementTree as ET


def generate_junit_xml(
    runs: list[dict[str, Any]],
    suite_name: str = "Tracecase Regression Suite",
    time_budget_s: float | None = None,
) -> str:
    """Generate standard JUnit XML formatted output from test execution runs."""
    total_tests = len(runs)
    failures = sum(1 for r in runs if r.get("status") == "failed")
    errors = sum(1 for r in runs if r.get("status") == "error")
    skipped = sum(1 for r in runs if r.get("status") in ("skipped", "cancelled"))
    total_time_s = sum(float(r.get("duration_ms") or 0.0) for r in runs) / 1000.0

    testsuites_el = ET.Element("testsuites", {
        "name": "Tracecase CI",
        "tests": str(total_tests),
        "failures": str(failures),
        "errors": str(errors),
        "time": f"{total_time_s:.3f}",
    })

    testsuite_el = ET.SubElement(testsuites_el, "testsuite", {
        "name": suite_name,
        "tests": str(total_tests),
        "failures": str(failures),
        "errors": str(errors),
        "skipped": str(skipped),
        "time": f"{total_time_s:.3f}",
    })

    for r in runs:
        tc_id = r.get("testcase_id") or "test"
        tc_name = r.get("testcase_name") or tc_id
        dur_s = float(r.get("duration_ms") or 0.0) / 1000.0
        status = r.get("status", "passed")

        tc_el = ET.SubElement(testsuite_el, "testcase", {
            "id": tc_id,
            "name": tc_name,
            "classname": f"tracecase.{tc_id}",
            "time": f"{dur_s:.3f}",
        })

        if status == "failed":
            msg = r.get("error_message") or "Test assertion or step failed."
            fail_el = ET.SubElement(tc_el, "failure", {
                "message": msg,
                "type": "AssertionError",
            })
            logs = "\n".join(r.get("logs") or [])
            fail_el.text = f"{msg}\n\nExecution Logs:\n{logs}"

        elif status == "error":
            msg = r.get("error_message") or "Infrastructure or execution error."
            err_el = ET.SubElement(tc_el, "error", {
                "message": msg,
                "type": "RuntimeError",
            })
            err_el.text = msg

        elif status in ("skipped", "cancelled"):
            skip_el = ET.SubElement(tc_el, "skipped", {
                "message": r.get("error_message") or "Test skipped or cancelled.",
            })

        # Add properties for flakiness / retries
        props_el = ET.SubElement(tc_el, "properties")
        if r.get("status") == "flaky":
            ET.SubElement(props_el, "property", {"name": "flaky", "value": "true"})
        attempts = r.get("attempt_count") or 1
        ET.SubElement(props_el, "property", {"name": "attempts", "value": str(attempts)})

    return ET.tostring(testsuites_el, encoding="utf-8", xml_declaration=True).decode("utf-8")
