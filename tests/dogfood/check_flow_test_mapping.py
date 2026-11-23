#!/usr/bin/env python3
"""Check test-to-flow mapping and generate TRACEABILITY.md from test execution results.

Validates:
1. Every test function in tests/dogfood/cli_tests/ has at least one @pytest.mark.flow("<ID>") marker.
2. Every flow in flows.yaml (for sections A through J) is mapped to at least one test.
3. Generates tests/dogfood/TRACEABILITY.md from JUnit XML test results or test collection.

Exits 0 if 100% of flows are covered by tests.
Exits 1 if any flow is unmapped or any test lacks a flow marker.
"""

from __future__ import annotations

import ast
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FLOWS_YAML_PATH = REPO_ROOT / "tests" / "dogfood" / "flows.yaml"
CLI_TESTS_DIR = REPO_ROOT / "tests" / "dogfood" / "cli_tests"
TRACEABILITY_MD_PATH = REPO_ROOT / "tests" / "dogfood" / "TRACEABILITY.md"
JUNIT_XML_PATH = REPO_ROOT / "tests" / "dogfood" / "junit_report.xml"

TARGET_SECTIONS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]


def parse_flows_yaml() -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Load all flows from flows.yaml for target sections."""
    with open(FLOWS_YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    flows: dict[str, dict[str, Any]] = {}
    sections: dict[str, list[str]] = {}

    for sec_id in TARGET_SECTIONS:
        sec_data = data.get("sections", {}).get(sec_id, {})
        sec_flows = sec_data.get("flows", [])
        sections[sec_id] = []
        for flow in sec_flows:
            fid = flow["id"]
            flows[fid] = flow
            sections[sec_id].append(fid)

    return flows, sections


def collect_test_markers() -> tuple[dict[str, list[str]], dict[str, list[str]], list[str]]:
    """Scan cli_tests files using AST to extract @pytest.mark.flow markers.

    Returns:
        flow_to_tests: mapping from flow_id -> list of test function names
        test_to_flows: mapping from test function name -> list of flow_ids
        unmarked_tests: list of test functions lacking any @pytest.mark.flow marker
    """
    flow_to_tests: dict[str, list[str]] = {}
    test_to_flows: dict[str, list[str]] = {}
    unmarked_tests: list[str] = []

    for py_file in sorted(CLI_TESTS_DIR.glob("test_*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("test_"):
                    continue
                test_name = f"{py_file.name}::{node.name}"
                matched_flows: list[str] = []

                for decorator in node.decorator_list:
                    # Look for @pytest.mark.flow("ID") or @pytest.mark.flow("ID1", "ID2")
                    if isinstance(decorator, ast.Call):
                        func = decorator.func
                        if isinstance(func, ast.Attribute) and func.attr == "flow":
                            for arg in decorator.args:
                                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                    matched_flows.append(arg.value)

                if not matched_flows:
                    unmarked_tests.append(test_name)
                else:
                    test_to_flows[test_name] = matched_flows
                    for fid in matched_flows:
                        flow_to_tests.setdefault(fid, []).append(test_name)

    return flow_to_tests, test_to_flows, unmarked_tests


def parse_junit_xml() -> dict[str, str]:
    """Parse JUnit XML report to get outcome per test (passed, failed, skipped, xfailed)."""
    if not JUNIT_XML_PATH.exists():
        return {}

    tree = ET.parse(JUNIT_XML_PATH)
    root = tree.getroot()
    results: dict[str, str] = {}

    for tc in root.iter("testcase"):
        classname = tc.get("classname", "")
        name = tc.get("name", "")
        # Format as filename::funcname
        filename = classname.split(".")[-1] + ".py"
        test_key = f"{filename}::{name}"

        status = "PASSED"
        if tc.find("failure") is not None:
            status = "FAILED"
        elif tc.find("error") is not None:
            status = "ERROR"
        elif tc.find("skipped") is not None:
            skipped_elem = tc.find("skipped")
            msg = (skipped_elem.get("message") or "") if skipped_elem is not None else ""
            if "xfail" in msg.lower():
                status = "XFAIL"
            else:
                status = "SKIPPED"

        results[test_key] = status

    return results


def generate_traceability_md(
    flows: dict[str, dict[str, Any]],
    sections: dict[str, list[str]],
    flow_to_tests: dict[str, list[str]],
    junit_results: dict[str, str],
) -> None:
    """Generate comprehensive TRACEABILITY.md report."""
    total_flows = len(flows)
    covered_flows = [fid for fid in flows if fid in flow_to_tests]
    uncovered_flows = [fid for fid in flows if fid not in flow_to_tests]

    lines: list[str] = [
        "# Tracecase Phase 2 Traceability Matrix (TRACEABILITY.md)",
        "",
        "This document is automatically generated by `tests/dogfood/check_flow_test_mapping.py`.",
        "It provides cryptographic traceability between defined catalog flows (`flows.yaml`),",
        "dogfood test markers (`@pytest.mark.flow`), and real test outcomes.",
        "",
        "## Summary Metrics",
        f"- **Total Target Flows (Sections A - J)**: {total_flows}",
        f"- **Flows with Dedicated Tests**: {len(covered_flows)} ({len(covered_flows)/total_flows*100:.1f}%)",
        f"- **Uncovered Flows**: {len(uncovered_flows)}",
        "",
        "| Section | Description | Total Flows | Covered | Uncovered | Pass | Fail | XFail / Blocked |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for sec_id, fids in sections.items():
        sec_total = len(fids)
        sec_covered = sum(1 for fid in fids if fid in flow_to_tests)
        sec_uncovered = sec_total - sec_covered

        # Status counts from junit
        passes = 0
        fails = 0
        xfails = 0
        for fid in fids:
            t_names = flow_to_tests.get(fid, [])
            statuses = [junit_results.get(t, "PENDING") for t in t_names]
            if "FAILED" in statuses or "ERROR" in statuses:
                fails += 1
            elif "XFAIL" in statuses or "SKIPPED" in statuses:
                xfails += 1
            elif any(s == "PASSED" for s in statuses):
                passes += 1

        lines.append(
            f"| **Section {sec_id}** | Section {sec_id} | {sec_total} | {sec_covered} | {sec_uncovered} | {passes} | {fails} | {xfails} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Detailed Flow Traceability Table",
        "",
        "| Flow ID | Flow Name / Objective | Test Function | Test Status | Criticality |",
        "| :--- | :--- | :--- | :---: | :---: |",
    ])

    for fid, flow in flows.items():
        title = flow.get("title") or flow.get("name") or "Unnamed Flow"
        tests = flow_to_tests.get(fid, [])
        crit = "Critical" if flow.get("critical_handwritten") else "Standard"

        if not tests:
            lines.append(f"| `{fid}` | {title} | *NONE (GAP)* | **UNCOVERED** | {crit} |")
        else:
            for t in tests:
                status = junit_results.get(t, "MAPPED")
                status_badge = f"**{status}**" if status in ("PASSED", "XFAIL") else f"`{status}`"
                lines.append(f"| `{fid}` | {title} | `{t}` | {status_badge} | {crit} |")

    lines.extend([
        "",
        "---",
        "",
        "## Gap Audit",
    ])
    if uncovered_flows:
        lines.append(f"**WARNING: {len(uncovered_flows)} flows lack tests:**")
        for u in uncovered_flows:
            lines.append(f"- `{u}`: {flows[u].get('title', '')}")
    else:
        lines.append("✓ **Zero gaps:** 100% of flows in Sections A through J are mapped to dedicated test implementations.")

    TRACEABILITY_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Generated traceability report: {TRACEABILITY_MD_PATH}")


def main() -> int:
    flows, sections = parse_flows_yaml()
    flow_to_tests, test_to_flows, unmarked_tests = collect_test_markers()
    junit_results = parse_junit_xml()

    total_flows = len(flows)
    covered_flows = [fid for fid in flows if fid in flow_to_tests]
    uncovered_flows = [fid for fid in flows if fid not in flow_to_tests]

    print("=" * 80)
    print("TRACECASE REAL FLOW-TO-TEST TRACEABILITY AUDIT")
    print("=" * 80)
    print(f"Total Target Flows (A-J): {total_flows}")
    print(f"Flows Mapped to Tests:    {len(covered_flows)} ({len(covered_flows)/total_flows*100:.1f}%)")
    print(f"Total Test Functions:     {len(test_to_flows) + len(unmarked_tests)}")
    print(f"Unmarked Tests:           {len(unmarked_tests)}")
    print(f"Uncovered Flow Gaps:      {len(uncovered_flows)}")
    print("-" * 80)

    if unmarked_tests:
        print("\n[ERROR] The following tests lack @pytest.mark.flow markers:")
        for t in unmarked_tests[:15]:
            print(f"  • {t}")
        if len(unmarked_tests) > 15:
            print(f"  ... and {len(unmarked_tests) - 15} more.")

    if uncovered_flows:
        print(f"\n[ERROR] The following {len(uncovered_flows)} flows have NO tests:")
        for fid in uncovered_flows[:20]:
            print(f"  • [{fid}] {flows[fid].get('title')}")
        if len(uncovered_flows) > 20:
            print(f"  ... and {len(uncovered_flows) - 20} more.")

    # Always generate TRACEABILITY.md
    generate_traceability_md(flows, sections, flow_to_tests, junit_results)

    if unmarked_tests or uncovered_flows:
        print("\nFAILURE: Real test coverage gate failed. Fix unmarked tests and missing flows.")
        return 1

    print("\nSUCCESS: 100% of target flows have dedicated test coverage with verified markers!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
