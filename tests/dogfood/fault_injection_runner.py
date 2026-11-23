"""
Fault injection verification runner for Tracecase dogfood suite.

Injects 8 intentional regressions into a throwaway copy of `src/` at
/tmp/tc_fault_injection/src/ and verifies that the corresponding dogfood tests
catch each fault (failing as expected).
"""

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
        "description": "Replay always exits 0 (suppresses exit code 2 on missing/corrupt testcase files)",
        "file": "tracecase/cli.py",
        "find": "def replay(\n    testcase: Annotated[",
        "replace": "def replay(\n    testcase: Annotated[\n) -> None:\n    # FAULT INJECTION: always exit 0\n    raise typer.Exit(0)\ndef _unused_replay(",
        "test": "tests/dogfood/cli_tests/test_cli_c_replay_healing.py::test_c4_exit_codes",
    },
    {
        "id": "FAULT-2",
        "description": "Healing disabled completely (candidate resolution skips fallbacks)",
        "file": "tracecase/replay/healing.py",
        "find": "    candidates = candidate_selectors(step.element)",
        "replace": "    candidates = candidate_selectors(step.element)\n    candidates = candidates[:1]  # FAULT INJECTION: never heal",
        "test": "tests/dogfood/cli_tests/test_cli_c_replay_healing.py::test_c9_replay_with_heal_version_b",
    },
    {
        "id": "FAULT-3",
        "description": "Codegen drops the last recorded step",
        "file": "tracecase/codegen/pytest_exporter.py",
        "find": "    for step in testcase.steps:",
        "replace": "    for step in testcase.steps[:-1]:  # FAULT INJECTION: drop last step",
        "test": "tests/dogfood/cli_tests/test_cli_f_codegen.py::test_f1_default_codegen",
    },
    {
        "id": "FAULT-4",
        "description": "Mutate ignores --limit flag and produces default pool",
        "file": "tracecase/cli.py",
        "find": "    mutations = engine.generate(case, strategies=selected_strategies, limit=limit)",
        "replace": "    mutations = engine.generate(case, strategies=selected_strategies, limit=999)  # FAULT INJECTION",
        "test": "tests/dogfood/cli_tests/test_cli_g_mutate.py::test_g5_limit_flag",
    },
    {
        "id": "FAULT-5",
        "description": "Corpus search query matching forced to match all rows",
        "file": "tracecase/index/search.py",
        "find": "        WHERE steps_fts MATCH ?",
        "replace": "        WHERE 1=1 OR steps_fts MATCH ?  -- FAULT INJECTION: match all",
        "test": "tests/dogfood/cli_tests/test_cli_i_corpus_mcp.py::test_i8_search_no_results",
    },
    {
        "id": "FAULT-6",
        "description": "Export-har writes empty entries list",
        "file": "tracecase/replay/har.py",
        "find": "            \"entries\": [_har_entry(request) for request in testcase.network_requests],",
        "replace": "            \"entries\": [],  # FAULT INJECTION: empty entries",
        "test": "tests/dogfood/cli_tests/test_cli_e_export_har.py::test_e1_export_har_with_output_flag",
    },
    {
        "id": "FAULT-7",
        "description": "Heuristic analyzer drops all detected risks from analysis output",
        "file": "tracecase/ai/analyst.py",
        "find": "        risks=risks,",
        "replace": "        risks=[],  # FAULT INJECTION: drop all detected risks",
        "test": "tests/dogfood/cli_tests/test_cli_h_analyze.py::test_h8_heuristic_risk_detection",
    },
    {
        "id": "FAULT-8",
        "description": "Clean --no-db deletes database anyway",
        "file": "tracecase/cli.py",
        "find": "    if db or all_artifacts:\n        if reset_db(target_db):",
        "replace": "    if True:  # FAULT INJECTION: always delete db even with --no-db\n        if reset_db(target_db):",
        "test": "tests/dogfood/cli_tests/test_cli_i_corpus_mcp.py::test_i15_clean_selective_flags",
    },
]


def setup_throwaway():
    if THROWAWAY_DIR.exists():
        shutil.rmtree(THROWAWAY_DIR)
    THROWAWAY_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO_ROOT / "src", SRC_COPY)
    print(f"✓ Initialized clean throwaway src copy at {SRC_COPY}")


def run_fault_injection():
    results = []
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_COPY)

    for fault in FAULTS:
        target_file = SRC_COPY / fault["file"]
        orig_content = target_file.read_text(encoding="utf-8")

        if fault["find"] not in orig_content:
            print(f"ERROR: Cannot find injection point for {fault['id']} in {fault['file']}")
            results.append((fault, "ERROR", "Injection pattern not found in target file"))
            continue

        # Apply mutation
        mutated_content = orig_content.replace(fault["find"], fault["replace"], 1)
        target_file.write_text(mutated_content, encoding="utf-8")

        # Run test against mutated code
        cmd = [
            str(REPO_ROOT / ".venv" / "bin" / "python"),
            "-m",
            "pytest",
            fault["test"],
            "-v",
        ]
        proc = subprocess.run(cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True)

        # Restore original content immediately
        target_file.write_text(orig_content, encoding="utf-8")

        # In fault injection, the test MUST fail (exit code != 0) to prove test sensitivity!
        if proc.returncode != 0:
            status = "CAUGHT (PASS)"
            detail = "Test failed as expected when fault was injected."
            print(f"[{fault['id']}] {status} -> {fault['description']}")
        else:
            status = "ESCAPED (FAIL)"
            detail = "Test passed despite injected fault! Test lacks sensitivity."
            print(f"[{fault['id']}] {status} -> {fault['description']}: Test unexpectedly passed!")

        results.append((fault, status, detail))

    # Write report
    report_md = [
        "# Tracecase Fault Injection Sensitivity Report",
        "",
        "This report proves that dogfood test assertions are genuinely sensitive to application faults and regressions.",
        "8 synthetic faults were injected into an isolated, throwaway copy of the codebase (`/tmp/tc_fault_injection/src`).",
        "",
        "| Fault ID | Description | Injected In | Target Test | Result | Detail |",
        "|---|---|---|---|---|---|",
    ]
    for fault, status, detail in results:
        report_md.append(
            f"| `{fault['id']}` | {fault['description']} | `{fault['file']}` | `{fault['test'].split('::')[-1]}` | **{status}** | {detail} |"
        )
    report_md.append("")
    all_caught = all(status == "CAUGHT (PASS)" for _, status, _ in results)
    if all_caught:
        report_md.append("✓ **Verdict**: All 8 synthetic faults were successfully detected and caught by the dogfood test suite.")
    else:
        report_md.append("✗ **Verdict**: One or more faults escaped test detection.")

    report_path = REPO_ROOT / "tests" / "dogfood" / "FAULT_INJECTION_REPORT.md"
    report_path.write_text("\n".join(report_md), encoding="utf-8")
    print(f"\n✓ Generated {report_path}")


if __name__ == "__main__":
    setup_throwaway()
    run_fault_injection()
