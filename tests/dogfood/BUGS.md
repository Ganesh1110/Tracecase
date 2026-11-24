# Tracecase Bug Tracker (BUGS.md)

This document tracks all defects, inconsistencies, and functional regressions discovered during Tracecase dogfood testing.

---

## BUG-001: Root `annotated_doc` Stub Shadows Package and Crashes FastAPI on Launch
- **Severity**: Low (Local Environment Issue; outside product code `src/tracecase`)
- **Component**: Python Environment / Root Namespace (`./annotated_doc/__init__.py`)
- **Found in Git**: Tracked in commit `687543898b814f6f6f41ee4931becfec6071d801` (added as dummy module at repository root during early prototyping)
- **Reproduction**:
  ```bash
  cd /path/to/Tracecase
  .venv/bin/python -c "import fastapi"
  ```
- **Error Output**:
  ```
  TypeError: Doc() takes no arguments
  Unable to evaluate type annotation "Annotated[str, Doc('The HTTP Basic username.')]".
  ```
- **Root Cause**:
  `annotated_doc/__init__.py` in repository root defines `class Doc: pass` with zero parameters. Because the workspace root is at the front of `sys.path`, Python loads this empty stub rather than the installed `.venv/lib/python3.14/site-packages/annotated_doc/` (v0.0.6) which defines `Doc(*args, **kwargs)`.
- **Classification & Reclassification**:
  This file is NOT part of the Tracecase package distribution (all production code resides in `src/tracecase/`, and `annotated_doc` is not declared in `pyproject.toml`). It is a stray prototype file committed at the repository root. Reclassified as a Low severity local-environment issue.
- **Expected**:
  `import fastapi` succeeds without errors.
- **Workaround**:
  Dogfood tests run with an isolated `sys.path` where the workspace root is excluded or `src/` is explicitly prepended. A regression test (`test_bug001_annotated_doc_shadowing`) asserts this failure reproduces from the root.

---

## BUG-002: Healing Priority Inverts Fallback Order (XPath Prioritized Over ID and Text)
- **Severity**: Medium-High (Risk of silent incorrect healing onto shifted DOM elements)
- **Component**: `src/tracecase/replay/healing.py` (`candidate_selectors`)
- **Observed Behavior**:
  `candidate_selectors()` places `xpath={element.xpath}` at index 1 (directly after original CSS selector), ahead of `#id`, `[name=...]`, and `text=...`.
- **Risk**:
  When a page undergoes structural redesign or DOM shifts, a stale absolute XPath can resolve to an unintended element (e.g. adjacent table cell or button) and execute silently without error.
- **Test Target**:
  Verified in `tests/dogfood/cli_tests/test_cli_c_replay_healing.py::test_c10_healing_tiers_and_false_positive_audit` with false-positive shift assertions.

---

## BUG-003: Exit Code Contract Ambiguity on Missing Element Without Heal
- **Severity**: Medium (Contract Ambiguity between README documentation and CLI behavior)
- **Component**: `src/tracecase/cli.py` & `src/tracecase/replay/engine.py`
- **Observed Behavior**:
  When an element is missing on replay without `--heal`, `ReplayEngine` raises `ReplayError("Element not found")`. `cli.py` catches this as a fatal command error and exits with `code 2` (status="error") rather than `code 1` (status="failed").
- **Documentation Contract**:
  The README (`README.md#replay`) explicitly defines:
  > `Exit codes: 0 passed, 1 assertion or visual diff failed, 2 infrastructure error.`
  Notice that "missing element" is not explicitly defined in the README. In CI test runners, a failed selector/element lookup is typically classified as a test failure (exit code 1) rather than a tool/infrastructure crash (exit code 2). Currently, `ReplayError` bubbles up to the CLI top-level exception handler, causing exit code 2.
- **Contract Resolution**:
  Contract needs explicit definition: should a missing element be classified under code 1 (test step failed) or code 2 (unhandled selector error)? The dogfood test suite asserts code 1 as the desired behavior for test assertion/locator failures.
- **Test Target**:
  Marked `@pytest.mark.xfail(strict=True, reason="BUG-003: replay exits with code 2 instead of code 1 when element is missing without heal")` in `tests/dogfood/cli_tests/test_cli_c_replay_healing.py::test_c8_replay_without_heal_version_b`.

---

## BUG-004: Visual Diff Automatically Pads Dimension Mismatch Without Warning
- **Severity**: Low-Medium (Hides critical UI layout regressions)
- **Component**: `src/tracecase/replay/visual.py` (`compute_diff`)
- **Observed Behavior**:
  When comparison images differ in dimension (e.g. 100x100 vs 200x200), `compute_diff` silently expands the smaller image by black-padding and computes pixel differences without surfacing a specific dimension mismatch warning or error flag.
- **Expected Behavior**:
  The tool should explicitly warn or flag when viewport or image dimensions do not match baseline dimensions.
- **Test Target**:
  Marked `@pytest.mark.xfail(strict=True, reason="BUG-004: tracecase diff pads canvas without warning on dimension mismatch")` in `tests/dogfood/cli_tests/test_cli_d_diff.py::test_d4_dimension_mismatch_warning_reported`.

---

## BUG-005: Incomplete Mutation Strategies in `tracecase/mutation/`
- **Severity**: Medium (Missing documented mutation capabilities)
- **Component**: `src/tracecase/mutation/network.py` (line 31) and `src/tracecase/mutation/engine.py`
- **Observed Behavior**:
  `src/tracecase/mutation/network.py` line 31 only implements HTTP 500 error mutation:
  ```python
  target_req.status = 500
  target_req.response_body = '{"error": "Simulated Internal Server Error"}'
  ```
  HTTP 403 and 429 error mutations are completely absent from the implementation. Additionally, action-level mutations only support `double_click`. Strategies documented in earlier architectural specs (`skip_action`, `reorder_inputs`, `latency_injection`, `403_forbidden`, `429_rate_limit`) are not implemented.
- **Test Target**:
  Marked `@pytest.mark.xfail(strict=True)` in:
  - `tests/dogfood/cli_tests/test_cli_g_mutate.py::test_g3_missing_skip_action_mutation`
  - `tests/dogfood/cli_tests/test_cli_g_mutate.py::test_g3_missing_reorder_inputs_mutation`
  - `tests/dogfood/cli_tests/test_cli_g_mutate.py::test_g4_missing_latency_fault_mutation`

---

## BUG-006: Legacy `__qa_` DOM Identifiers and Artifacts
- **Severity**: Low (Branding / Code Hygiene Inconsistency)
- **Component**: `src/tracecase/control_panel.py` and `.qa_auto/` legacy directory
- **Observed Behavior**:
  1. The control panel container uses `#__tracecase_panel__`, but internal elements retain legacy naming: `#__qa_start_btn__`, `#__qa_stop_btn__`, `#__qa_status_dot__`, `#__qa_steps_count__`, and CSS `@keyframes __qa_pulse`.
  2. Legacy directory `.qa_auto/` remains at the repository root containing legacy studio database files and exploration screenshots, left over from previous product branding.

---

## BUG-007: Codegen Generates Asynchronous Playwright Tests (`pytest-asyncio`)
- **Severity**: Medium (Breaks documented install-then-run workflow in clean environments lacking `pytest-asyncio`)
- **Component**: `src/tracecase/codegen/` (`pytest_exporter.py`)
- **Observed Behavior**:
  `tracecase codegen` produces tests that use `import pytest_asyncio` and `async def test_*(page: Page): ...`. When users follow standard Playwright documentation (`pip install pytest pytest-playwright`), running `pytest` immediately fails at collection with `ModuleNotFoundError: No module named 'pytest_asyncio'`. Standard `pytest-playwright` tests are synchronous (`def test_*(page: Page): ...`).
- **Reproduction**:
  Verified in a clean virtual environment containing only `pytest` and `pytest-playwright`.
- **Test Target**:
  - Characterization: `tests/dogfood/cli_tests/test_cli_f_codegen.py::test_f11_codegen_requires_pytest_asyncio_audit` (Passed)
  - Strict XFail: Marked `@pytest.mark.xfail(strict=True, reason="BUG-007: Codegen generates async test requiring pytest-asyncio rather than standard pytest-playwright sync fixtures")` in `tests/dogfood/cli_tests/test_cli_f_codegen.py::test_bug007_codegen_clean_playwright_test`.

---

## BUG-008: Unhandled Connection Exception Dumps Raw Python Traceback on Unreachable URL
- **Severity**: Medium (CLI Error Handling Violation)
- **Component**: `src/tracecase/cli.py` (record command)
- **Observed Behavior**:
  Running `tracecase record http://127.0.0.1:19999/unreachable` fails with an unhandled `playwright._impl._errors.Error: net::ERR_CONNECTION_REFUSED` that dumps a full Python / Rich traceback to stderr.
- **Contract**:
  Flow A6 and CLI design specify clean, user-friendly error messages on failure without raw unhandled exception tracebacks.
- **Test Target**:
  Marked `@pytest.mark.xfail(strict=True, reason="BUG-008: Unhandled connection exception dumps Python traceback on unreachable URL")` in `tests/dogfood/cli_tests/test_cli_b_record.py::test_b11_unreachable_url`.

---

## BUG-009A: Plaintext Credential Leakage in `testcase.json`
- **Severity**: Critical (Security Vulnerability)
- **Component**: `src/tracecase/events.py` (line 178) & `src/tracecase/recorder.py`
- **Observed Behavior**:
  When recording interactions on password fields (`<input type="password">`), the injected JavaScript event listener reads `lastInputValue[selector] = el.value` without checking the input's `type` attribute. As a result, the recorded `testcase.json` stores the user's plaintext password in `step.input_value`.
- **Note on API Key vs Password**:
  Masking `type=password` is a mandatory security baseline. Masking fields by name (e.g. `api_key`, `token`) is an architectural design decision currently unaddressed by the recorder.
- **Test Target**:
  Marked `@pytest.mark.xfail(strict=True, reason="BUG-009A: Password input values stored in plaintext in testcase.json")` in `tests/dogfood/cli_tests/test_cli_b_record.py::test_b27_password_masking_json`.

---

## BUG-009B: Plaintext Credential Leakage in Exported Markdown (`testcase.md`)
- **Severity**: Critical (Shareable Artifact Data Leak)
- **Component**: `src/tracecase/recorder.py` (`_generate_short_description`) & Jinja templates
- **Observed Behavior**:
  `_generate_short_description` bakes the raw password into `description_short` (`Type 'password' in #password`). When exported to `testcase.md`, the plaintext secret is rendered in the step documentation table.
- **Test Target**:
  Marked `@pytest.mark.xfail(strict=True, reason="BUG-009B: Plaintext password leaked in exported testcase.md")` in `tests/dogfood/cli_tests/test_cli_b_record.py::test_b27_password_masking_markdown`.

---

## BUG-009C: Plaintext Credential Leakage in Exported HTML (`testcase.html`)
- **Severity**: Critical (Shareable Artifact Data Leak)
- **Component**: `src/tracecase/recorder.py` & `src/tracecase/templates/report.html.j2`
- **Observed Behavior**:
  The HTML test report includes `description_short` and raw input values in rendered table cells, exposing plaintext credentials to anyone viewing the report in a browser.
- **Test Target**:
  Marked `@pytest.mark.xfail(strict=True, reason="BUG-009C: Plaintext password leaked in exported testcase.html")` in `tests/dogfood/cli_tests/test_cli_b_record.py::test_b27_password_masking_html`.

---

## BUG-009D: Plaintext Credential Leakage via MCP `get_testcase` Protocol Response
- **Severity**: Critical (LLM Agent Tool Exposure)
- **Component**: `src/tracecase/mcp/server.py`
- **Observed Behavior**:
  When an AI agent calls the MCP `get_testcase` tool, the server returns the raw `testcase.json` contents without sanitizing passwords, leaking secrets into LLM contexts.
- **Test Target**:
  Marked `@pytest.mark.xfail(strict=True, reason="BUG-009D: MCP get_testcase returns plaintext password credentials")` in `tests/dogfood/cli_tests/test_cli_i_corpus_mcp.py::test_i20_mcp_password_masking`.

---

## BUG-009E: Plaintext Credential Leakage in Exported HAR (`replay/har.py`)
- **Severity**: Critical (Export Artifact Secret Exposure)
- **Component**: `src/tracecase/replay/har.py`
- **Observed Behavior**:
  When replaying and exporting traffic to HAR (`tracecase export-har`), POST request bodies containing passwords (`password=secret`) and authorization headers (`Authorization: Bearer ...`) are serialized verbatim into the `postData` and `headers` sections of `testcase.har` without redaction.
- **Test Target**:
  Detected in credential leak sweep; tracked for sanitization fixture in export engine.

---

## BUG-009F: Mutation Engine Propagates Plaintext Secrets into Generated Mutation Pool
- **Severity**: High (Derived Artifact Secret Proliferation)
- **Component**: `src/tracecase/mutation/` (`engine.py`, `network.py`)
- **Observed Behavior**:
  When `tracecase mutate` generates mutated variants from a baseline test case containing credentials or API keys, those secrets are cloned verbatim into all mutated `testcase.json` files and their metadata descriptions across the entire mutant pool.
- **Test Target**:
  Detected in credential leak sweep.

---

## BUG-009G: Generated Pytest Suite Hardcodes Plaintext API Keys and Secrets
- **Severity**: High (Committed Test Code Secret Leakage)
- **Component**: `src/tracecase/codegen/pytest_exporter.py`
- **Observed Behavior**:
  When exporting recorded sessions to standalone Python tests (`tracecase codegen`), input values for API keys and tokens are emitted as literal python string arguments: `await page.fill("#api-key", "CANARY_APIKEY_...")`, encouraging developers to commit hardcoded secrets into version control.
- **Test Target**:
  Detected in credential leak sweep.

---

## BUG-010: ActionType `scroll` Unhandled in ReplayEngine and Missing Browser Event Listeners
- **Severity**: Medium (Missing Core Action Support in Replay & Recorder)
- **Component**: `src/tracecase/replay/engine.py` (`_perform`) & `src/tracecase/events.py`
- **Observed Behavior**:
  1. `models.py:ActionType` defines 11 action types: `click`, `dblclick`, `input`, `select`, `check`, `uncheck`, `navigate`, `scroll`, `hover`, `keypress`, `wait`.
  2. However, `ReplayEngine._perform` lacks a handler for `"scroll"`. Replaying any test case containing a `scroll` step immediately crashes with `ValueError: Unsupported action type: scroll`.
  3. Furthermore, `events.py:EVENT_LISTENER_JS` contains no event listeners for `scroll` or `mouseenter`/`mouseover`, meaning user scrolling and hover interactions can never be recorded from the browser.
- **Expected Behavior**:
  `ReplayEngine._perform` should support scrolling (e.g. `await page.evaluate("window.scrollBy(...)")` or `page.mouse.wheel`), and `events.py` should attach debounced listeners for page scroll and hover.
- **Test Target**:
  - Characterization: `tests/dogfood/cli_tests/test_cli_b_record.py::test_b16_action_types_unrecordable_gap` (Passed)
  - Strict XFail: Marked `@pytest.mark.xfail(strict=True, reason="BUG-010: ReplayEngine._perform raises ValueError for action_type='scroll'")` in `tests/dogfood/cli_tests/test_cli_b_record.py::test_b16_action_types_replay_scroll_bug`.

---

## Tracecase Bug-to-Test Traceability Matrix (BUG-001 to BUG-010)

| Bug ID | Title | Component | Dedicated Test Node ID | Test Marker |
|---|---|---|---|---|
| **BUG-001** | Root `annotated_doc` stub shadows package | `annotated_doc/` | `test_cli_a_install_env.py::test_bug001_annotated_doc_shadowing_regression`<br>`test_cli_a_install_env.py::test_bug001_annotated_doc_correct_behavior` | Passed (characterization)<br>`xfail(strict=True)` (correct behavior) |
| **BUG-002** | Healing candidate order prioritizes XPath over ID | `replay/healing.py` | `test_cli_c_replay_healing.py::test_c10_healing_tiers_and_false_positive_audit`<br>`test_cli_c_replay_healing.py::test_bug002_healing_order_correct_behavior` | Passed (characterization)<br>`xfail(strict=True)` (correct behavior) |
| **BUG-003** | Replay exits with code 2 on missing element | `cli.py`, `replay/` | `test_cli_c_replay_healing.py::test_c8_replay_without_heal_version_b` | `xfail(strict=True)` |
| **BUG-004** | Diff pads canvas without warning on dimension mismatch | `replay/visual.py` | `test_cli_d_diff.py::test_d4_dimension_mismatch_warning_reported` | `xfail(strict=True)` |
| **BUG-005** | Incomplete mutation strategies (skip, reorder, latency) | `mutation.py` | `test_cli_g_mutate.py::test_g3_missing_skip_action_mutation`<br>`test_cli_g_mutate.py::test_g3_missing_reorder_inputs_mutation`<br>`test_cli_g_mutate.py::test_g4_missing_latency_fault_mutation` | `xfail(strict=True)` (3 tests) |
| **BUG-006** | Legacy `__qa_` DOM IDs in injected control panel | `control_panel.py` | `test_cli_b_record.py::test_b12_control_panel_legacy_qa_ids_audit`<br>`test_cli_b_record.py::test_bug006_control_panel_clean_ids` | Passed (characterization)<br>`xfail(strict=True)` (correct behavior) |
| **BUG-007** | Codegen generates async test requiring `pytest-asyncio` | `codegen/` | `test_cli_f_codegen.py::test_f11_codegen_requires_pytest_asyncio_audit`<br>`test_cli_f_codegen.py::test_bug007_codegen_clean_playwright_test` | Passed (characterization)<br>`xfail(strict=True)` (correct behavior) |
| **BUG-008** | Unhandled connection error dumps raw Python traceback | `cli.py` (record) | `test_cli_b_record.py::test_b11_unreachable_url` | `xfail(strict=True)` |
| **BUG-009A** | Plaintext credential leakage in `testcase.json` | `events.py`, `recorder.py` | `test_cli_b_record.py::test_b27_password_masking_json` | `xfail(strict=True)` |
| **BUG-009B** | Plaintext credential leakage in `testcase.md` | `templates/`, `recorder.py` | `test_cli_b_record.py::test_b27_password_masking_markdown` | `xfail(strict=True)` |
| **BUG-009C** | Plaintext credential leakage in `testcase.html` | `templates/`, `recorder.py` | `test_cli_b_record.py::test_b27_password_masking_html` | `xfail(strict=True)` |
| **BUG-009D** | Plaintext credential leakage via MCP `get_testcase` | `mcp/server.py` | `test_cli_i_corpus_mcp.py::test_i20_mcp_password_masking` | `xfail(strict=True)` |
| **BUG-009E** | Plaintext credential leakage in exported HAR | `replay/har.py` | `credential_leak_sweep.py` (har sweep) | Verified in sweep |
| **BUG-009F** | Mutation engine propagates plaintext secrets | `mutation/` | `credential_leak_sweep.py` (mutations sweep) | Verified in sweep |
| **BUG-009G** | Codegen hardcodes plaintext secrets in python | `codegen/` | `credential_leak_sweep.py` (codegen sweep) | Verified in sweep |
| **BUG-010** | ReplayEngine crashes on action_type `scroll` | `replay/engine.py` | `test_cli_b_record.py::test_b16_action_types_replay_scroll_bug` | `xfail(strict=True)` |
| **BUG-011** | MCP `get_testcase` tool throws JSON-RPC -32603 instead of `result.isError=true` | `mcp/server.py` | `test_cli_i_corpus_mcp.py::test_i19_mcp_missing_testcase_iserror` | `xfail(strict=True)` |
| **BUG-012** | Closing browser without Stop silently drops recording without saving or notice | `recorder.py`, `cli.py` | `test_cli_b_record.py::test_b14_close_browser_without_stop_saves_or_warns` | `xfail(strict=True)` |

---

## BUG-011: MCP `tools/call` for `get_testcase` Returns JSON-RPC -32603 Exception Instead of `result.isError=true`
- **Severity**: Medium (MCP Spec Violation & Client Integration Failure)
- **Component**: `src/tracecase/mcp/server.py` (`_execute_tool`, line 140)
- **Observed Behavior**:
  When a requested testcase ID does not exist in the database, `_execute_tool()` raises `ValueError(f"Testcase '{tc_id}' not found in corpus.")`. The top-level `handle_request()` catches all generic exceptions and returns `{"error": {"code": -32603, "message": "Internal error: ..."}}`.
- **Contract / Spec**:
  The Model Context Protocol (MCP) standard specifies that tool execution failures (such as a requested entity not existing) must be returned inside a normal JSON-RPC `result` structure with `isError: true` and the diagnostic explanation in `content`. Protocol error codes like `-32603` are reserved for server faults and transport failures.
- **Test Target**:
  Marked `@pytest.mark.xfail(strict=True, reason="BUG-011: MCP get_testcase throws -32603 internal exception instead of returning result.isError=True")` in `tests/dogfood/cli_tests/test_cli_i_corpus_mcp.py::test_i19_mcp_missing_testcase_iserror`.

---

## BUG-012: Closing Browser Window Without Clicking Stop Silently Discards Recording
- **Severity**: High (Data Loss)
- **Component**: `src/tracecase/recorder.py`, `src/tracecase/cli.py`
- **Observed Behavior**:
  If a user performs recording actions in the browser and then closes the browser window (or tab) without first pressing "Stop" in the control panel, `BrowserManager` detects the disconnection and sets `_recording_complete`. In the terminal, the user sees:
  ```
  ✓ Browser closed
  ```
  and the CLI process exits cleanly with code 0. However, `export()` is never called, and all recorded steps, screenshots, and logs are silently thrown away with zero files created and no warning displayed.
- **Contract / Expected Behavior**:
  Either the captured recording should be preserved to disk upon browser close (data preservation), or the CLI must emit a prominent warning notice and exit non-zero alerting the user that the recording was aborted.
- **Test Target**:
  Marked `@pytest.mark.xfail(strict=True, reason="BUG-012: Closing browser without clicking Stop silently discards recording without saving or warning user")` in `tests/dogfood/cli_tests/test_cli_b_record.py::test_b14_close_browser_without_stop_saves_or_warns`.



