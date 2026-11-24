"""
Fault injection verification runner for Tracecase dogfood suite.

Injects intentional regressions into a throwaway copy of `src/` at
/tmp/tc_fault_injection/src/ and runs the ENTIRE CLI dogfood test suite
against each fault. Reports all failing tests, diffs, and verbatim assertion
failure traces per fault.
"""

import difflib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
THROWAWAY_DIR = Path("/tmp/tc_fault_injection")
SRC_COPY = THROWAWAY_DIR / "src"
EVIDENCE_DIR = REPO_ROOT / "tests" / "dogfood" / "evidence"

FAULTS = [
    {
        "id": "FAULT-1",
        "name": "Replay always exits 0",
        "description": "Replay CLI command always exits 0 even on test failure or error",
        "file": "tracecase/cli.py",
        "find": "    raise typer.Exit(result.exit_code)",
        "replace": "    raise typer.Exit(0)  # FAULT-1: always exit 0",
    },
    {
        "id": "FAULT-2",
        "name": "Healing returns first element matching ANY element",
        "description": "Candidate loop accepts the first candidate matching ANY element, skipping text/role/visibility checks",
        "file": "tracecase/replay/healing.py",
        "find": "        if await _is_single_visible(locator, wait_ms=wait_ms):",
        "replace": "        if await locator.count() > 0:  # FAULT-2: accept first candidate matching ANY element, skipping checks",
    },
    {
        "id": "FAULT-2b",
        "name": "Crude healing returns first body element",
        "description": "Crude fallback returns first generic element on page (body *) with healed_from set",
        "file": "tracecase/replay/healing.py",
        "find": "    for index, selector in enumerate(candidates):",
        "replace": "    if heal and len(candidates) > 1:\n        result.selector = 'body *'\n        result.healed_from = step.element.selector\n        return page.locator('button, a, input, div').first, result\n    for index, selector in enumerate(candidates):",
    },
    {
        "id": "FAULT-3",
        "name": "Codegen drops last step",
        "description": "Codegen pytest exporter drops the final recorded step",
        "file": "tracecase/codegen/pytest_exporter.py",
        "find": "    for step in testcase.steps:",
        "replace": "    for step in testcase.steps[:-1]:  # FAULT-3: drop last step",
    },
    {
        "id": "FAULT-4",
        "name": "Mutate ignores --limit",
        "description": "Mutate CLI command ignores --limit flag and always produces default unconstrained pool",
        "file": "tracecase/cli.py",
        "find": "    mutations = engine.generate(case, strategies=selected_strategies, limit=limit)",
        "replace": "    mutations = engine.generate(case, strategies=selected_strategies, limit=999)  # FAULT-4",
    },
    {
        "id": "FAULT-5",
        "name": "Search ignores query",
        "description": "Corpus search ignores query and matches all testcases in the database",
        "file": "tracecase/index/search.py",
        "find": "        WHERE steps_fts MATCH ?",
        "replace": "        WHERE 1=1 OR steps_fts MATCH ?  -- FAULT-5: match everything",
    },
    {
        "id": "FAULT-6",
        "name": "Export-har writes empty entries list",
        "description": "HAR exporter writes empty entries list: {'log': {'entries': []}}",
        "file": "tracecase/replay/har.py",
        "find": "            \"entries\": [_har_entry(request) for request in testcase.network_requests],",
        "replace": "            \"entries\": [],  # FAULT-6: empty entries",
    },
    {
        "id": "FAULT-7",
        "name": "Analyze labels heuristic output as LLM-generated",
        "description": "Analysis engine labels heuristic output with provider='openai' / LLM",
        "file": "tracecase/ai/analyst.py",
        "find": "        provider=provider.name,",
        "replace": "        provider='openai' if provider.name == 'null' else provider.name,  # FAULT-7",
    },
    {
        "id": "FAULT-8",
        "name": "clean --db also deletes recordings",
        "description": "tracecase clean --db deletes ./recordings even when --recordings is false",
        "file": "tracecase/cli.py",
        "find": "    if db or all_artifacts:\n        if reset_db(target_db):",
        "replace": "    if db or all_artifacts:\n        rec_dir = Path('./recordings')\n        if rec_dir.exists():\n            shutil.rmtree(rec_dir)\n        if reset_db(target_db):",
    },
    {
        "id": "FAULT-9",
        "name": "Replay swallows assertion failures",
        "description": "Replay engine ignores failed assertions and marks step as passed",
        "file": "tracecase/replay/engine.py",
        "find": "        failed = any(not result.passed for result in assertion_results)",
        "replace": "        failed = False  # FAULT-9: swallow assertion failures",
    },
    {
        "id": "FAULT-10",
        "name": "Record drops all network capture",
        "description": "Recorder listener drops all network requests and leaves network_requests empty",
        "file": "tracecase/recorder.py",
        "find": "    def _on_request(self, request: Request) -> None:\n        \"\"\"Handle network request start.\"\"\"",
        "replace": "    def _on_request(self, request: Request) -> None:\n        return  # FAULT-10: drop all network capture",
    },
    {
        "id": "FAULT-11",
        "name": "MCP get_testcase returns wrong testcase",
        "description": "MCP get_testcase tool returns wrong testcase or payload for valid ID",
        "file": "tracecase/mcp/server.py",
        "find": "            return tc_data",
        "replace": "            tc_data['id'] = 'wrong_mutated_id'  # FAULT-11\n            return tc_data",
    },
    {
        "id": "FAULT-12",
        "name": "replay.json stops recording healed tier",
        "description": "Healing resolves successfully, but replay.json omits healed_from",
        "file": "tracecase/replay/engine.py",
        "find": "        elif healed_from is not None:\n            step_status = \"healed\"",
        "replace": "        elif healed_from is not None:\n            step_status = \"healed\"\n            healed_from = None  # FAULT-12: omit healed_from",
    },
]


def verify_detector_mapping():
    """Verify that every detector in fault_expected_detectors.md is present in pytest --collect-only -q."""
    detector_md = EVIDENCE_DIR / "fault_expected_detectors.md"
    if not detector_md.exists():
        raise RuntimeError(f"Detector mapping missing: {detector_md}")

    # Collect all available test node IDs
    res = subprocess.run(
        [str(REPO_ROOT / ".venv" / "bin" / "pytest"), "tests/dogfood/cli_tests/", "--collect-only", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    collected = set(line.strip() for line in res.stdout.splitlines() if "::" in line)

    # Extract detector node IDs from markdown table
    md_content = detector_md.read_text(encoding="utf-8")
    listed_detectors = set(re.findall(r"`(test_cli_[^`]+::test_[^`]+)`", md_content))
    # Prepend directory prefix if needed
    normalized_listed = set()
    for d in listed_detectors:
        if not d.startswith("tests/dogfood/cli_tests/"):
            normalized_listed.add(f"tests/dogfood/cli_tests/{d}")
        else:
            normalized_listed.add(d)

    missing = [d for d in normalized_listed if d not in collected]
    if missing:
        print("\n❌ FATAL: Detector mapping references tests that are NOT collected by pytest:")
        for m in sorted(missing):
            print(f"  - {m}")
        sys.exit(1)
    print(f"✓ Detector mapping validated: all {len(normalized_listed)} listed detectors are collected!")


def reset_throwaway_src():
    if THROWAWAY_DIR.exists():
        shutil.rmtree(THROWAWAY_DIR)
    THROWAWAY_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO_ROOT / "src", SRC_COPY)


def verify_throwaway_env():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_COPY)
    proc = subprocess.run(
        [str(REPO_ROOT / ".venv" / "bin" / "python"), "-c", "import tracecase; print(tracecase.__file__)"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    imported_path = proc.stdout.strip()
    assert str(SRC_COPY) in imported_path, f"Throwaway environment failed to import from {SRC_COPY}: got {imported_path}"
    out_file = EVIDENCE_DIR / "throwaway_env_paths.txt"
    out_file.write_text(f"PYTHONPATH: {SRC_COPY}\ntracecase.__file__: {imported_path}\n", encoding="utf-8")
    print(f"Verified throwaway module import: {imported_path}")


def apply_fault(fault: dict) -> str:
    target_path = SRC_COPY / fault["file"]
    orig_content = target_path.read_text(encoding="utf-8")
    if fault["find"] not in orig_content:
        raise ValueError(f"Could not find patch target in {target_path}:\n{fault['find']}")
    patched_content = orig_content.replace(fault["find"], fault["replace"], 1)
    target_path.write_text(patched_content, encoding="utf-8")

    diff_lines = list(difflib.unified_diff(
        orig_content.splitlines(keepends=True),
        patched_content.splitlines(keepends=True),
        fromfile=f"a/{fault['file']}",
        tofile=f"b/{fault['file']}",
    ))
    diff_text = "".join(diff_lines)
    if not diff_text.strip():
        raise RuntimeError(f"FATAL: Generated diff for {fault['id']} is empty!")

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    diff_path = EVIDENCE_DIR / f"fault_{fault['id'].lower().replace('-', '_')}.diff"
    diff_path.write_text(diff_text, encoding="utf-8")
    return diff_text


def run_full_suite() -> dict:
    """Runs the full CLI suite with fixed seed / no randomly. Returns execution results and parsed failure details."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_COPY)

    cmd = [
        str(REPO_ROOT / ".venv" / "bin" / "pytest"),
        "tests/dogfood/cli_tests/",
        "-q",
        "--tb=short",
        "-p", "no:randomly",
    ]
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    raw_output = proc.stdout + proc.stderr

    # Parse failing test nodes
    failing_nodes = []
    for line in raw_output.splitlines():
        if line.startswith("FAILED "):
            parts = line.split()
            if len(parts) >= 2:
                failing_nodes.append(parts[1])

    # Extract first assertion or exception line per failure
    failure_traces = {}
    current_test = None
    collecting_trace = False
    for line in raw_output.splitlines():
        if line.startswith("___") and line.endswith("___"):
            current_test = line.strip("_ ")
            collecting_trace = True
            continue
        if collecting_trace and current_test:
            if line.startswith("E   ") or line.startswith(">   "):
                failure_traces[current_test] = line.strip()
                collecting_trace = False

    # Extract verbatim summary line
    summary_lines = [l for l in raw_output.splitlines() if ("passed" in l or "failed" in l or "error" in l)]
    summary_line = summary_lines[-1] if summary_lines else "NO SUMMARY OUTPUT"

    # Treat exit code other than 0 or 1, collection errors, or timeouts as INFRA FAILURE
    is_infra_failure = proc.returncode not in (0, 1) or "collection error" in raw_output.lower() or "interrupted" in raw_output.lower()

    return {
        "exit_code": proc.returncode,
        "summary_line": summary_line,
        "failing_nodes": failing_nodes,
        "failure_traces": failure_traces,
        "is_infra_failure": is_infra_failure,
        "raw_output": raw_output,
    }


def get_expected_detectors(fault_id: str) -> list[str]:
    detector_md = EVIDENCE_DIR / "fault_expected_detectors.md"
    if not detector_md.exists():
        return []
    content = detector_md.read_text(encoding="utf-8")
    pattern = rf"\|\s*\*\*{fault_id}\*\*\s*\|\s*[^|]+\|\s*([^|]+)\|"
    match = re.search(pattern, content)
    if not match:
        return []
    cell = match.group(1)
    nodes = re.findall(r"`(test_cli_[^`]+)`", cell)
    return [f"tests/dogfood/cli_tests/{n}" if not n.startswith("tests/dogfood/cli_tests/") else n for n in nodes]


def run_single_fault(fault_key: str):
    norm_key = fault_key.upper().strip()
    if not norm_key.startswith("FAULT-"):
        norm_key = f"FAULT-{norm_key}"

    target_fault = None
    for f in FAULTS:
        if f["id"].upper() == norm_key:
            target_fault = f
            break
    if not target_fault:
        print(f"❌ Unknown fault ID: {fault_key} (expected one of: {[f['id'] for f in FAULTS]})")
        sys.exit(1)

    print("=" * 80)
    print(f"FAULT INJECTION: {target_fault['id']} ({target_fault['name']})")
    print("=" * 80)
    reset_throwaway_src()
    verify_throwaway_env()
    diff_text = apply_fault(target_fault)

    expected = get_expected_detectors(target_fault["id"])
    run_res = run_full_suite()

    has_expected_caught = any(
        any(exp in node for exp in expected) for node in run_res["failing_nodes"]
    )
    if run_res["is_infra_failure"]:
        verdict = "INFRA FAILURE"
    elif len(run_res["failing_nodes"]) == 0:
        verdict = "NOT DETECTED"
    elif has_expected_caught:
        verdict = "DETECTED"
    else:
        verdict = "COLLATERAL ONLY"

    print(f"Command:              .venv/bin/pytest tests/dogfood/cli_tests/ -q --tb=short -p no:randomly")
    print(f"Pytest Exit Code:     {run_res['exit_code']}")
    print(f"Final Summary Line:   {run_res['summary_line']}")
    print(f"Verdict:              {verdict}")
    print(f"Failing Tests Count:  {len(run_res['failing_nodes'])}")
    print("\nFailing Tests & First Assertion Line:")
    if run_res["failing_nodes"]:
        for node in run_res["failing_nodes"]:
            func_name = node.split("::")[-1]
            trace = run_res["failure_traces"].get(func_name, "Assertion failed")
            print(f"  - {node}")
            print(f"    {trace}")
    else:
        print("  *None*")

    print("\nUnified Diff:")
    print("```diff")
    print(diff_text.strip())
    print("```")
    print("\n" + "-" * 80 + "\n")

    reset_throwaway_src()


def run_baseline():
    print("=" * 80)
    print("FAULT INJECTION BASELINE (CLEAN THROWAWAY SRC)")
    print("=" * 80)
    reset_throwaway_src()
    verify_throwaway_env()

    res = run_full_suite()
    print("Command:              .venv/bin/pytest tests/dogfood/cli_tests/ -q --tb=short -p no:randomly")
    print(f"Pytest Exit Code:     {res['exit_code']}")
    print(f"Final Summary Line:   {res['summary_line']}")
    print(f"Failing Tests Count:  {len(res['failing_nodes'])}")
    print(f"Verdict:              {'BASELINE CLEAN' if len(res['failing_nodes']) == 0 and res['exit_code'] == 0 else 'BASELINE FAILED'}")
    print("\n" + "-" * 80 + "\n")

    out_file = EVIDENCE_DIR / "fault_baseline.txt"
    out_file.write_text(
        f"Exit Code: {res['exit_code']}\n"
        f"{res['summary_line']}\n",
        encoding="utf-8",
    )

    if res["is_infra_failure"] or len(res["failing_nodes"]) > 0:
        print(f"\n❌ BASELINE NOT CLEAN! Failing nodes: {res['failing_nodes']}")
        sys.exit(1)
    print(f"✓ Baseline Clean: 0 failing tests ({res['summary_line']})")


def run_all_faults():
    print("================================================================================")
    print("STRICT 12-FAULT INJECTION BENCHMARK (WHOLE CLI SUITE PER FAULT)")
    print("================================================================================")

    verify_detector_mapping()
    run_baseline()

    report_sections = []
    report_sections.append("="*80)
    report_sections.append("TRACECASE 12-FAULT INJECTION DETAILED BENCHMARK REPORT")
    report_sections.append("="*80 + "\n")

    summary_rows = []
    for fault in FAULTS:
        print(f"\n[{fault['id']}] {fault['name']}...", flush=True)
        reset_throwaway_src()
        diff_text = apply_fault(fault)

        run_res = run_full_suite()
        status = "INFRA FAILURE" if run_res["is_infra_failure"] else ("CAUGHT" if len(run_res["failing_nodes"]) > 0 else "MISSED")

        print(f"  Result: {status} (Exit Code: {run_res['exit_code']}, {len(run_res['failing_nodes'])} failing tests)", flush=True)
        print(f"  Summary: {run_res['summary_line']}", flush=True)

        # Build detailed fault section
        section = [
            f"### {fault['id']}: {fault['name']}",
            f"**Description**: {fault['description']}",
            f"**Target**: `{fault['file']}`",
            f"**Exit Code**: `{run_res['exit_code']}`",
            f"**Verbatim Pytest Summary**: `{run_res['summary_line']}`",
            f"**Status**: **{status}** ({len(run_res['failing_nodes'])} failing test(s))",
            "",
            "**Unified Diff**:",
            "```diff",
            diff_text.strip(),
            "```",
            "",
            "**Failing Tests & Failure Traces**:",
        ]
        if run_res["failing_nodes"]:
            for node in run_res["failing_nodes"]:
                func_name = node.split("::")[-1]
                trace = run_res["failure_traces"].get(func_name, "Assertion failed (see raw output)")
                section.append(f"- `{node}`:\n  `{trace}`")
        else:
            section.append("*None (No tests caught this regression)*")
        section.append("\n" + "-"*80 + "\n")
        report_sections.append("\n".join(section))

        summary_rows.append({
            "id": fault["id"],
            "name": fault["name"],
            "description": fault["description"],
            "failing_nodes": run_res["failing_nodes"],
            "status": status,
            "exit_code": run_res["exit_code"],
            "summary": run_res["summary_line"],
        })

    # Restore clean throwaway
    reset_throwaway_src()

    # Markdown Summary Table
    md_lines = [
        "| Fault ID | Injected Regression | Tests Detecting Regression | Status | Exit Code | Summary |",
        "|---|---|---|---|---|---|",
    ]
    for r in summary_rows:
        tests_str = "<br>".join([f"`{t.split('::')[-1]}`" for t in r["failing_nodes"][:4]])
        if len(r["failing_nodes"]) > 4:
            tests_str += f"<br>*(+{len(r['failing_nodes']) - 4} more)*"
        if not tests_str:
            tests_str = "*None*"
        md_lines.append(f"| **{r['id']}** | {r['description']} | {tests_str} | **{r['status']}** ({len(r['failing_nodes'])}) | `{r['exit_code']}` | `{r['summary']}` |")

    table_md = "\n".join(md_lines)
    print("\n" + "="*80)
    print("FAULT INJECTION RESULTS SUMMARY")
    print("="*80)
    print(table_md)

    full_report_text = "\n".join(report_sections) + "\n\n## Summary Table\n\n" + table_md + "\n"
    report_file = EVIDENCE_DIR / "fault_injection_report.txt"
    report_file.write_text(full_report_text, encoding="utf-8")

    out_file = REPO_ROOT / "tests" / "dogfood" / "FAULT_INJECTION_REPORT.md"
    out_file.write_text(table_md + "\n", encoding="utf-8")
    summary_file = EVIDENCE_DIR / "fault_injection_summary.txt"
    summary_file.write_text(table_md + "\n", encoding="utf-8")

    print(f"\n✓ Full report written to: {report_file}")
    print(f"✓ Summary written to:     {out_file} and {summary_file}")

    all_caught = all(r["status"] == "CAUGHT" for r in summary_rows)
    if not all_caught:
        print("\n❌ ERROR: One or more faults were NOT caught!")
        sys.exit(1)
    else:
        print("\n✓ SUCCESS: All 12 faults caught by the full test suite!")


if __name__ == "__main__":
    if "--baseline" in sys.argv:
        run_baseline()
    elif "--fault" in sys.argv:
        idx = sys.argv.index("--fault")
        if idx + 1 < len(sys.argv):
            run_single_fault(sys.argv[idx + 1])
        else:
            print("Error: --fault requires an argument (e.g. 1, 2, 2b, 3...)")
            sys.exit(1)
    else:
        run_all_faults()
