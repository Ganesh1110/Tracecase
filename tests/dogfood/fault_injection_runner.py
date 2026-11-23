"""
Fault injection verification runner for Tracecase dogfood suite.

Injects 12 intentional regressions into a throwaway copy of `src/` at
/tmp/tc_fault_injection/src/ and runs the ENTIRE CLI dogfood test suite
against each fault. Reports all failing tests per fault in a markdown table.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
THROWAWAY_DIR = Path("/tmp/tc_fault_injection")
SRC_COPY = THROWAWAY_DIR / "src"

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
        "name": "Healing returns first matching element",
        "description": "Healing candidate resolution returns first element on page without verifying text/role",
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
        "find": "            return json.loads(file_path.read_text(encoding=\"utf-8\"))",
        "replace": "            data = json.loads(file_path.read_text(encoding=\"utf-8\"))\n            data['id'] = 'wrong_mutated_id'  # FAULT-11\n            return data",
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


def reset_throwaway_src():
    if THROWAWAY_DIR.exists():
        shutil.rmtree(THROWAWAY_DIR)
    THROWAWAY_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO_ROOT / "src", SRC_COPY)


def apply_fault(fault: dict) -> None:
    target_path = SRC_COPY / fault["file"]
    content = target_path.read_text(encoding="utf-8")
    if fault["find"] not in content:
        raise ValueError(f"Could not find patch target in {target_path}:\n{fault['find']}")
    patched = content.replace(fault["find"], fault["replace"], 1)
    target_path.write_text(patched, encoding="utf-8")


def run_full_suite() -> list[str]:
    """Runs the whole CLI dogfood suite and returns list of failing test node IDs."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_COPY)
    
    cmd = [
        str(REPO_ROOT / ".venv" / "bin" / "pytest"),
        "tests/dogfood/cli_tests/",
        "-q",
        "--tb=no",
        "--no-header",
        "-p", "no:randomly",
    ]
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    # Parse failing tests from pytest output
    # Lines starting with 'FAILED ' contain the node ID
    failing = []
    for line in proc.stdout.splitlines():
        if line.startswith("FAILED "):
            node = line.split()[1]
            failing.append(node)
    return failing


def main():
    print("================================================================================", flush=True)
    print("STRICT 12-FAULT INJECTION BENCHMARK (WHOLE CLI SUITE PER FAULT)", flush=True)
    print("================================================================================", flush=True)

    results = []
    for fault in FAULTS:
        print(f"\n[Injecting {fault['id']}] {fault['name']}...", flush=True)
        reset_throwaway_src()
        apply_fault(fault)

        failing_tests = run_full_suite()
        status = "CAUGHT" if len(failing_tests) > 0 else "MISSED"
        print(f"  Result: {status} ({len(failing_tests)} failing test(s) detected)", flush=True)
        for t in failing_tests[:5]:
            print(f"    - {t}", flush=True)
        if len(failing_tests) > 5:
            print(f"    ... and {len(failing_tests) - 5} more", flush=True)

        results.append({
            "id": fault["id"],
            "name": fault["name"],
            "description": fault["description"],
            "failing_tests": failing_tests,
            "status": status,
        })

    # Restore clean throwaway
    reset_throwaway_src()

    # Generate Markdown Table
    print("\n" + "="*80)
    print("FAULT INJECTION RESULTS SUMMARY")
    print("="*80)
    md_lines = [
        "| Fault ID | Injected Regression | Tests Detecting Regression | Status |",
        "|---|---|---|---|",
    ]
    for r in results:
        tests_str = "<br>".join([f"`{t.split('::')[-1]}`" for t in r["failing_tests"][:4]])
        if len(r["failing_tests"]) > 4:
            tests_str += f"<br>*(+{len(r['failing_tests']) - 4} more)*"
        if not tests_str:
            tests_str = "*None*"
        md_lines.append(f"| **{r['id']}** | {r['description']} | {tests_str} | **{r['status']}** ({len(r['failing_tests'])}) |")

    table_md = "\n".join(md_lines)
    print(table_md)

    # Save to json/markdown
    out_file = REPO_ROOT / "tests" / "dogfood" / "FAULT_INJECTION_REPORT.md"
    out_file.write_text(table_md + "\n", encoding="utf-8")
    print(f"\nWrote full report to: {out_file}")

    all_caught = all(r["status"] == "CAUGHT" for r in results)
    if not all_caught:
        print("\n❌ ERROR: One or more faults were NOT caught by the test suite!")
        sys.exit(1)
    else:
        print("\n✓ SUCCESS: All 12 faults caught by the full test suite!")


if __name__ == "__main__":
    main()
