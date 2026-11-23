# Tracecase Test-Edit Audit Log (TEST_EDIT_LOG.md)

This document tracks all modifications made to test assertions during Phase 2, recording the original assertion, updated assertion, and classification:
- **TEST BUG**: The test expectation or implementation was flawed, not the system under test.
- **APP BEHAVIOR CHANGED TO MATCH DOCS**: Source code or configuration was updated to match specification.
- **APP BUG**: The system under test violates specification/contract. The test is maintained with strict assertion, marked `@pytest.mark.xfail(strict=True)`, and tracked in `BUGS.md`.

---

## Audit Entries

### Entry 1: Zero-Step Recording Assertion (`test_b13_stop_with_zero_steps`)
- **File**: `tests/dogfood/cli_tests/test_cli_b_record.py`
- **Original Assertion**:
  ```python
  assert (out_dir / "testcase.json").exists()
  ```
- **New Assertion**:
  ```python
  assert not (out_dir / "testcase.json").exists()
  ```
- **Classification**: **TEST BUG**
- **Rationale**: `Recorder` is intentionally designed with the rule: *"No steps recorded. Nothing to export."* When a user starts and stops without recording any interactions, creating an empty testcase file is suppressed. The initial test expectation that an empty file would be written was incorrect.

---

### Entry 2: Mutation Directory Structure (`test_g1_default_mutate`, `test_g6`, `test_g7`, `test_g8`, `test_g11`)
- **File**: `tests/dogfood/cli_tests/test_cli_g_mutate.py`
- **Original Assertion**:
  ```python
  mutations = list(mut_dir.glob("*.json"))
  assert len(mutations) > 0
  ```
- **New Assertion**:
  ```python
  mutations = list(mut_dir.glob("*/testcase.json"))
  assert len(mutations) > 0
  ```
- **Classification**: **TEST BUG**
- **Rationale**: `MutationEngine.export_mutations()` exports each synthesized variation into its own directory: `base_dir / m.testcase.id / "testcase.json"`, accompanied by `mutation_meta.json`. The initial test incorrectly looked for flat JSON files in the root mutations folder (`*.json`), which failed to find the files in subdirectories.

---

### Entry 3: MCP Stdio JSON-RPC Error Contract (`test_i22_mcp_nonexistent_testcase`)
- **File**: `tests/dogfood/cli_tests/test_cli_i_corpus_mcp.py`
- **Original Assertion**:
  ```python
  assert missing_call["result"]["isError"] is True
  ```
- **New Assertion**:
  ```python
  assert "error" in missing_call
  assert missing_call["error"]["code"] == -32603
  ```
- **Classification**: **TEST BUG**
- **Rationale**: In the standard JSON-RPC 2.0 specification, an unhandled exception or missing resource during a method call produces an `{"error": {"code": -32603, "message": "..."}}` response, with no `"result"` key. The initial test assumed the response would have `"result.isError"`, which is an MCP tool return payload format, not a top-level RPC response format.

---

### Entry 4: Corpus FTS5 Endpoint URL Indexing (`test_i7_search_by_selector_and_url`)
- **File**: `tests/dogfood/cli_tests/test_cli_i_corpus_mcp.py`
- **Original Query**: Looked for `/api/search` when network request was placed on root `TestCase.network_requests`.
- **Updated Implementation**: Attached `NetworkRequest` to `step.network_requests` (which is what `index_testcase` iterates over to build the `steps_fts.network_urls` column) and searched for `"api"`.
- **Classification**: **TEST BUG**
- **Rationale**: `index_testcase()` indexes `step.network_requests` on each step. The test fixture builder originally attached requests only to the top-level testcase object, leaving the step's network list empty. Fixing the test fixture resolved the indexing.

---

### Entry 5: CI Intelligence CLI Parameter Shapes (`test_cli_j_ci_intelligence.py`)
- **File**: `tests/dogfood/cli_tests/test_cli_j_ci_intelligence.py`
- **Original Invocations**:
  - `run_tracecase(["map", str(repo), "--db", str(db_path)])`
  - `run_tracecase(["explain", str(repo), "--base", base])`
  - `run_tracecase(["ci", str(repo), "--base", base])`
- **Updated Invocations**:
  - `run_tracecase(["map", str(repo)])` (map has `-p / --project`, not `--db`)
  - `run_tracecase(["explain"])` (explain takes `[selection_id]`, not `--base`)
  - `run_tracecase(["ci", "--repo", str(repo), "--base", base])` (ci takes `--repo <path>`, not positional argument)
- **Classification**: **TEST BUG**
- **Rationale**: The initial test drafted CLI invocations from conceptual documentation rather than the actual Typer command definitions in `src/tracecase/cli.py`. The test was corrected to use the exact Click/Typer options.

---

### Entry 6: Replay Exit Code Contract on Missing Selector (`test_c4_exit_codes`, `test_c8_replay_without_heal_version_b`)
- **File**: `tests/dogfood/cli_tests/test_cli_c_replay_healing.py`
- **Original Assertion**:
  ```python
  assert res_no_heal.returncode == 1  # Expected test failure
  ```
- **Intermediate Relaxation**:
  ```python
  assert res_no_heal.returncode == 2  # Relaxed to match code returning status='error'
  ```
- **Hardened Final Assertion**:
  ```python
  @pytest.mark.xfail(strict=True, reason="APP BUG-003: Replay exits 2 instead of 1 on missing selector without --heal")
  def test_c8_replay_without_heal_version_b(...):
      assert res_no_heal.returncode == 1
  ```
- **Classification**: **APP BUG (BUG-003)**
- **Rationale**: The documented contract states `0 = pass`, `1 = test/assertion failure`, and `2 = infrastructure crash / environment error`. When a selector is missing and `--heal` is not enabled, the test has legitimately failed. Returning exit code 2 causes CI pipelines (GitHub Actions, GitLab CI) to treat the run as an infrastructure failure (rerunning or failing the runner job) rather than a normal test failure. The test has been restored to the strict assertion `assert returncode == 1` and marked `xfail(strict=True)`.

---

### Entry 7: Visual Diff Canvas Padding & Dimension Mismatch Warning (`test_d4_dimension_mismatch_warning_reported`)
- **File**: `tests/dogfood/cli_tests/test_cli_d_diff.py`
- **Original Expectation**: Mismatched image sizes would either raise an error or report a clear warning to the user.
- **Hardened Final Assertion**:
  ```python
  @pytest.mark.xfail(strict=True, reason="APP BUG-004: Dimension mismatch is hidden inside diff percentage without explicit warning")
  def test_d4_dimension_mismatch_warning_reported(...):
      assert "dimension mismatch" in res.stdout.lower() or "dimensions differ" in res.stdout.lower()
  ```
- **Classification**: **APP BUG (BUG-004)**
- **Rationale**: When images have differing dimensions, `compare_images` silently pads both canvases with transparent pixels. The user is presented with a diff percentage (e.g. 50.00%) without any warning that the image sizes differed. Reviewers would assume pixels changed rather than dimensions shifting. Marked `xfail(strict=True)`.

---

### Entry 8: Missing Documented Mutation Strategies (`test_g3_missing_skip_action`, `test_g3_missing_reorder_inputs`, `test_g4_missing_latency`)
- **File**: `tests/dogfood/cli_tests/test_cli_g_mutate.py`
- **Hardened Final Assertions**:
  ```python
  @pytest.mark.xfail(strict=True, reason="APP BUG-005: skip_action mutation promised in docs is missing in code")
  def test_g3_missing_skip_action_mutation(...): ...

  @pytest.mark.xfail(strict=True, reason="APP BUG-005: reorder_inputs mutation promised in docs is missing in code")
  def test_g3_missing_reorder_inputs_mutation(...): ...

  @pytest.mark.xfail(strict=True, reason="APP BUG-005: latency fault mutation promised in docs is missing in code")
  def test_g4_missing_latency_fault_mutation(...): ...
  ```
- **Classification**: **APP BUG (BUG-005)**
- **Rationale**: `docs/USER_GUIDE.md` promises `skip_action`, `reorder_inputs`, and `high latency` negative variations. `MutationEngine` only implements `double_click` and HTTP 500. Marked `xfail(strict=True)` to ensure the gap remains visible.

---

### Entry 9: Unhandled Traceback on Unreachable Record URL (`test_b11_unreachable_url`)
- **File**: `tests/dogfood/cli_tests/test_cli_b_record.py`
- **Hardened Final Assertion**:
  ```python
  @pytest.mark.xfail(strict=True, reason="BUG-008: Unhandled connection exception dumps Python traceback on unreachable URL")
  def test_b11_unreachable_url(isolated_workspace: Path, isolated_env: dict[str, str]):
      assert res.returncode != 0
      assert "Traceback" not in res.stderr
  ```
- **Classification**: **APP BUG (BUG-008)**
- **Rationale**: Flow A6 and user documentation specify that CLI command errors should be user-friendly without unhandled Python tracebacks. When `tracecase record` targets an unreachable host/port, it crashes with an unhandled Playwright `net::ERR_CONNECTION_REFUSED` traceback printed directly to stderr.

---

### Entry 10: Control Panel Container Selector (`test_b12_control_panel_lifecycle`)
- **File**: `tests/dogfood/cli_tests/test_cli_b_record.py`
- **Original Assertion**:
  ```python
  panel = await page.wait_for_selector("#__qa_control_panel__")
  ```
- **New Assertion**:
  ```python
  panel = await page.wait_for_selector("#__tracecase_panel__", timeout=5000)
  ```
- **Classification**: **TEST BUG**
- **Rationale**: In `src/tracecase/control_panel.py`, the outer panel `div` has `id="__tracecase_panel__"`, whereas internal buttons use `#__qa_start_btn__`. The test erroneously assumed the container ID was `#__qa_control_panel__`. Corrected to match the actual element ID.

---

### Entry 11: Fixture Exception Message in JS Error Capture (`test_b21_page_uncaught_js_error_capture`)
- **File**: `tests/dogfood/cli_tests/test_cli_b_record.py`
- **Original Assertion**:
  ```python
  assert "Playground Simulated Uncaught Error" in tc.page_errors[0].message
  ```
- **New Assertion**:
  ```python
  assert "Uncaught Playground Exception: boom!" in tc.page_errors[0].message
  ```
- **Classification**: **TEST BUG**
- **Rationale**: The playground fixture `console_errors.html` throws `throw new Error("Uncaught Playground Exception: boom!")`. The test incorrectly asserted an older draft text string rather than the exact string emitted by the fixture.

---

### Entry 12: Password Credential Masking Audit (`test_b27_password_masking_audit`)
- **File**: `tests/dogfood/cli_tests/test_cli_b_record.py`
- **Hardened Final Assertion**:
  ```python
  @pytest.mark.xfail(strict=True, reason="BUG-009: Password input values stored in plaintext without credential masking")
  def test_b27_password_masking_audit(isolated_workspace: Path, playground_server_url: str):
      ...
      assert pwd_step.input_value != secret
      assert all(c == "*" for c in (pwd_step.input_value or ""))
  ```
- **Classification**: **APP BUG (BUG-009)**
- **Rationale**: `src/tracecase/requirements/validation/sandbox.py:73` requires credential masking for recorded traces and artifacts. However, `src/tracecase/events.py` captures raw `el.value` regardless of input type, writing plaintext passwords directly to `testcase.json`. The test asserts masking and is marked strict `xfail`.

---

### Entry 13: Storage Retention Policy Option Shape (`test_j16_storage_retention_policy_older_than`)
- **File**: `tests/dogfood/cli_tests/test_cli_j_ci_intelligence.py`
- **Original Assertion**:
  ```python
  res = run_tracecase(["storage", "--dry-run", "--older-than", "30d"], env=isolated_env)
  ```
- **New Assertion**:
  ```python
  res = run_tracecase(["storage", "--dry-run", "--older-than", "30"], env=isolated_env)
  ```
- **Classification**: **TEST BUG**
- **Rationale**: Typer option `--older-than` takes an integer representing the number of days (`<int>`), not a duration string with suffix (`"30d"`). Corrected to pass integer argument `"30"`.

---

### Entry 14: ActionType `scroll` Unhandled in ReplayEngine (`test_b16_action_types_replay_scroll_bug`)
- **File**: `tests/dogfood/cli_tests/test_cli_b_record.py`
- **Hardened Final Assertion**:
  ```python
  @pytest.mark.xfail(strict=True, reason="BUG-010: ReplayEngine._perform raises ValueError for action_type='scroll'")
  def test_b16_action_types_replay_scroll_bug(...):
      ...
      res = asyncio.run(engine.run())
      assert res.status == "passed"
  ```
- **Classification**: **APP BUG (BUG-010)**
- **Rationale**: ActionType `scroll` is defined in `tracecase.models.ActionType`, but `ReplayEngine._perform` lacks a handler for it and raises `ValueError: Unsupported action type: scroll`. Test explicitly tests replaying a scroll step and is marked strict `xfail`.

---

### Entry 15: Rich Output Destination in Image Diff Error Handling (`test_d5_corrupt_file`)
- **File**: `tests/dogfood/cli_tests/test_cli_d_diff.py`
- **Original Assertion**:
  ```python
  assert "not found" in res_missing.stderr.lower()
  ```
- **New Assertion**:
  ```python
  assert "not found" in (res_missing.stdout + res_missing.stderr).lower()
  ```
- **Classification**: **TEST BUG**
- **Rationale**: `tracecase diff` outputs error messages via Rich console `console.print(f"[red]✗ Baseline not found:[/red] ...")` which streams to `stdout` rather than `stderr`. Checking only `stderr` caused a false failure when the error message was correctly rendered to stdout.

---

### Entry 16: Elimination of Returncode-Only Asserts Across CLI Test Suite
- **Files**: `test_cli_b_record.py`, `test_cli_c_replay_healing.py`, `test_cli_d_diff.py`, `test_cli_g_mutate.py`, `test_cli_h_analyze.py`, `test_cli_i_corpus_mcp.py`, `test_cli_j_ci_intelligence.py`
- **Original Assertion**: `assert res.returncode == 0` without verifying output text or side-effect files.
- **Updated Assertions**: Replaced with assertions on process output, generated artifact schema, or database state.
- **Classification**: **TEST QUALITY HARDENING**
- **Rationale**: Enforces that tests do not merely check process exit status, but rigorously assert on the observable output, file system side-effects, and database content. Verified via `tests/dogfood/check_assertion_quality.py`.

---

### Entry 17: Full Disclosure and Root Cause Remediation of Seed 1049281 Failures
- **Context**: During initial random order testing with `--randomly-seed=1049281`, four tests failed, and parallel `-n 2` suffered port collisions. Every failure was triaged and resolved as follows:
- **Remediations**:
  1. `test_b16_action_types_capture`:
     - **Root Cause**: Action sequence performed `await page.select_option("#role-select", "admin")`, but `#role-select` element was missing from fixture HTML.
     - **Fix**: Added `<select id="role-select">` with options to `tests/dogfood/fixtures/playground_app/pages/actions.html`.
  2. `test_b14_close_browser_without_stop`:
     - **Root Cause**: Closing browser early without clicking Stop triggers clean shutdown without export. Test incorrectly asserted `assert (out_dir / "testcase.json").exists()`.
     - **Fix**: Corrected to `assert not (out_dir / "testcase.json").exists()`.
  3. `test_i4_reindex_idempotency`:
     - **Root Cause**: Queried SQLite for `SELECT count(*) FROM test_cases`, but the Tracecase database table is named `testcases`.
     - **Fix**: Changed query to `SELECT count(*) FROM testcases`.
  4. `test_i9_search_special_fts5_characters`:
     - **Root Cause**: Mismatch in phrase quote escaping for FTS5 queries.
     - **Fix**: Synchronized quote escaping in query and assertion.
  5. Pytest-xdist port collisions (`-n 2`):
     - **Root Cause**: Multiple workers collided on fixed ports 9010/9110 (`[Errno 48] Address already in use`).
     - **Fix**: Added `_get_worker_offset()` in `conftest.py` allocating isolated port bands (`9010 + offset * 10`, `9110 + offset * 10`).


