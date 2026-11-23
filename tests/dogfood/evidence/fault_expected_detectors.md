# Fault Injection Expected Detectors Mapping

| Fault ID | Injected Regression | Intended Primary Detectors | Detection Rationale |
|---|---|---|---|
| **FAULT-1** | Replay CLI always exits 0 even on failure | `test_cli_c_replay_healing.py::test_c4_exit_codes`<br>`test_cli_c_replay_healing.py::test_c7_timeout_sensitivity` | Tests expect non-zero exit code (1 or 2) when replaying invalid/missing testcases or timing out. |
| **FAULT-2** | Healing candidate resolution returns first element without verifying text/role | `test_cli_c_replay_healing.py::test_c10_healing_tiers_and_false_positive_audit`<br>`test_cli_c_replay_healing.py::test_c9_replay_with_heal_version_b` | Asserts exact candidate selector order, text/role matching, and false-positive DOM shift rejection. |
| **FAULT-3** | Codegen pytest exporter drops the final recorded step | `test_cli_f_codegen.py::test_f1_default_codegen`<br>`test_cli_f_codegen.py::test_f8_all_recorded_steps_emitted` | Compares number of generated test steps against recorded step count in testcase.json. |
| **FAULT-4** | Mutate CLI ignores `--limit` flag | `test_cli_g_mutate.py::test_g6_limit_flag` | Generates mutations with `--limit 3` and strictly asserts `len(mutations) == 3`. |
| **FAULT-5** | Corpus search ignores query and matches everything | `test_cli_i_corpus_mcp.py::test_i8_search_no_results` | Searches for nonexistent query `totally_absent_phrase_999` and asserts 0 results returned. |
| **FAULT-6** | HAR exporter writes empty entries list | `test_cli_e_export_har.py::test_e1_export_har_with_output_flag`<br>`test_cli_e_export_har.py::test_e2_entry_fields` | Asserts `len(har["log"]["entries"]) > 0` and inspects entry request/response fields. |
| **FAULT-7** | Analysis engine labels heuristic output as LLM | `test_cli_h_analyze.py::test_h7_schema_validation`<br>`test_cli_h_analyze.py::test_h1_offline_heuristics` | Runs `--provider null` and asserts `analysis["provider"] in ("null", "heuristics")`. |
| **FAULT-8** | `clean --db` also deletes `./recordings` | `test_cli_i_corpus_mcp.py::test_i13_clean_db_flag` | Creates `./recordings` directory, runs `clean --db`, and asserts `./recordings` still exists. |
| **FAULT-9** | Replay engine swallows assertion failures | `test_cli_c_replay_healing.py::test_c4_exit_codes`<br>`test_cli_c_replay_healing.py::test_c5_derived_assertions_flag`<br>`test_cli_c_replay_healing.py::test_c6_url_assertion_evaluation` | Executes replay with assertion checking and asserts replay fails (status="failed", exit 1). |
| **FAULT-10** | Recorder listener drops all network capture | `test_cli_b_record.py::test_b19_network_capture` | Asserts `len(tc.network_requests) > 0` and checks request method/URL. |
| **FAULT-11** | MCP `get_testcase` tool returns wrong testcase | `test_cli_i_corpus_mcp.py::test_i19_mcp_get_testcase_tool` | Calls `get_testcase` for `tc_mcp19` and asserts returned ID is `tc_mcp19`. |
| **FAULT-12** | `replay.json` stops recording healed tier (`healed_from=None`) | `test_cli_c_replay_healing.py::test_c9_replay_with_heal_version_b` | Asserts `report["steps"][1]["healed_from"]` is present and matches original selector. |
