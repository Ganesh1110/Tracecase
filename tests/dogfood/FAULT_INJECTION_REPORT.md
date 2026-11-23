# Tracecase Fault Injection Sensitivity Report

This report proves that dogfood test assertions are genuinely sensitive to application faults and regressions.
8 synthetic faults were injected into an isolated, throwaway copy of the codebase (`/tmp/tc_fault_injection/src`).

| Fault ID | Description | Injected In | Target Test | Result | Detail |
|---|---|---|---|---|---|
| `FAULT-1` | Replay always exits 0 (suppresses exit code 2 on missing/corrupt testcase files) | `tracecase/cli.py` | `test_c4_exit_codes` | **CAUGHT (PASS)** | Test failed as expected when fault was injected. |
| `FAULT-2` | Healing disabled completely (candidate resolution skips fallbacks) | `tracecase/replay/healing.py` | `test_c9_replay_with_heal_version_b` | **CAUGHT (PASS)** | Test failed as expected when fault was injected. |
| `FAULT-3` | Codegen drops the last recorded step | `tracecase/codegen/pytest_exporter.py` | `test_f1_default_codegen` | **CAUGHT (PASS)** | Test failed as expected when fault was injected. |
| `FAULT-4` | Mutate ignores --limit flag and produces default pool | `tracecase/cli.py` | `test_g5_limit_flag` | **CAUGHT (PASS)** | Test failed as expected when fault was injected. |
| `FAULT-5` | Corpus search query matching forced to match all rows | `tracecase/index/search.py` | `test_i8_search_no_results` | **CAUGHT (PASS)** | Test failed as expected when fault was injected. |
| `FAULT-6` | Export-har writes empty entries list | `tracecase/replay/har.py` | `test_e1_export_har_with_output_flag` | **CAUGHT (PASS)** | Test failed as expected when fault was injected. |
| `FAULT-7` | Heuristic analyzer drops all detected risks from analysis output | `tracecase/ai/analyst.py` | `test_h8_heuristic_risk_detection` | **CAUGHT (PASS)** | Test failed as expected when fault was injected. |
| `FAULT-8` | Clean --no-db deletes database anyway | `tracecase/cli.py` | `test_i15_clean_selective_flags` | **CAUGHT (PASS)** | Test failed as expected when fault was injected. |

✓ **Verdict**: All 8 synthetic faults were successfully detected and caught by the dogfood test suite.