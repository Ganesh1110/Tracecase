"""
Flakiness & Parallel Ordering Verification Runner (tests/dogfood/flakiness_runner.py)

Runs the Tracecase CLI dogfood suite:
1. Three times with different pytest-randomly seeds
2. Once with pytest-xdist (-n 2) parallel workers

Outputs a concise markdown table with results.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_suite(args: list[str]) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    cmd = [str(REPO_ROOT / ".venv" / "bin" / "pytest"), "tests/dogfood/cli_tests/", "-q"] + args
    proc = subprocess.run(cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True)

    stdout = proc.stdout + proc.stderr
    # Extract seed if randomly was used
    seed_match = re.search(r"--randomly-seed=(\d+)", stdout)
    seed = seed_match.group(1) if seed_match else "N/A"

    # Extract summary line, e.g., "131 passed, 7 xfailed in 45.12s"
    summary_match = re.search(r"(\d+)\s+passed.*?(\d+)\s+xfailed", stdout)
    passed = int(summary_match.group(1)) if summary_match else 0
    xfailed = int(summary_match.group(2)) if summary_match else 0

    failed_match = re.search(r"(\d+)\s+failed", stdout)
    failed = int(failed_match.group(1)) if failed_match else 0

    return {
        "args": " ".join(args),
        "seed": seed,
        "passed": passed,
        "xfailed": xfailed,
        "failed": failed,
        "exit_code": proc.returncode,
    }


def main():
    print("================================================================================")
    print("FLAKINESS & ORDERING VERIFICATION (3 RANDOM RUNS + 1 PARALLEL RUN)")
    print("================================================================================")

    runs = [
        {"name": "Random Run 1", "args": ["--randomly-seed=1049281"]},
        {"name": "Random Run 2", "args": ["--randomly-seed=5820491"]},
        {"name": "Random Run 3", "args": ["--randomly-seed=9301824"]},
        {"name": "Parallel Run (-n 2)", "args": ["-n", "2", "-p", "no:randomly"]},
    ]

    results = []
    for r in runs:
        print(f"\nExecuting {r['name']} ({' '.join(r['args'])})...", flush=True)
        res = run_suite(r["args"])
        res["name"] = r["name"]
        print(f"  Result: {res['passed']} passed, {res['xfailed']} xfailed, {res['failed']} failed", flush=True)
        results.append(res)

    print("\n" + "="*80)
    print("FLAKINESS & CONCURRENCY RESULTS")
    print("="*80)
    md_lines = [
        "| Run | Configuration / Seed | Passed | XFailed | Failed | Status |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        status = "✅ PASS" if r["failed"] == 0 and r["passed"] >= 130 else (f"❌ {r['failed']} FAIL" if r["failed"] > 0 else "⚠️ PASS")
        if "Parallel" in r["name"]:
            cfg = "`-n 2` (2 parallel workers)"
        else:
            cfg = f"Seed `{r['seed']}` (random order)"
        md_lines.append(f"| **{r['name']}** | {cfg} | {r['passed']} | {r['xfailed']} | {r['failed']} | {status} |")

    table_md = "\n".join(md_lines)
    print(table_md)

    out_file = REPO_ROOT / "tests" / "dogfood" / "FLAKINESS_REPORT.md"
    out_file.write_text(table_md + "\n", encoding="utf-8")
    print(f"\nWrote flakiness report to: {out_file}")


if __name__ == "__main__":
    main()
