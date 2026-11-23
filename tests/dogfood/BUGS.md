# Tracecase Bug Tracker (BUGS.md)

This document tracks all defects, inconsistencies, and functional regressions discovered during Tracecase dogfood testing.

---

## BUG-001: Root `annotated_doc` Stub Shadows Package and Crashes FastAPI on Launch
- **Severity**: High (Blocks `uvicorn`, `pytest`, and `tracecase ui` when launched from repository root)
- **Component**: Python Environment / Root Namespace (`./annotated_doc/__init__.py`)
- **Found in Git**: Tracked in commit `687543898b814f6f6f41ee4931becfec6071d801` (added as dummy module)
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

## BUG-003: Replay Exits with Code 2 Instead of Code 1 on Missing Element Without Heal
- **Severity**: Medium (Conflates test failure with infrastructure error in CI pipelines)
- **Component**: `src/tracecase/cli.py` & `src/tracecase/replay/engine.py`
- **Observed Behavior**:
  When an element is missing on replay without `--heal`, `ReplayEngine` raises `ReplayError("Element not found")`. `cli.py` catches this as a fatal command error and exits with `code 2` (status="error") rather than `code 1` (status="failed").
- **Documentation Contract**:
  The CLI contract states:
  - Exit code 0: Replay passed successfully.
  - Exit code 1: Replay failed (assertion failure or missing element).
  - Exit code 2: Infrastructure / CLI command error (syntax, missing file, browser crash).
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

## BUG-005: Incomplete Mutation Strategies in MutationEngine
- **Severity**: Medium (Missing documented mutation capabilities)
- **Component**: `src/tracecase/engines/mutation.py`
- **Observed Behavior**:
  `MutationEngine` currently only generates:
  - `double_click` for actions
  - `500` status error for network requests
  Strategies promised in documentation (`skip_action`, `reorder_inputs`, `latency`, `403`, `429`) are unimplemented.
- **Test Target**:
  Marked `@pytest.mark.xfail(strict=True)` in:
  - `tests/dogfood/cli_tests/test_cli_g_mutate.py::test_g3_missing_skip_action_mutation`
  - `tests/dogfood/cli_tests/test_cli_g_mutate.py::test_g3_missing_reorder_inputs_mutation`
  - `tests/dogfood/cli_tests/test_cli_g_mutate.py::test_g4_missing_latency_fault_mutation`

---

## BUG-006: Legacy `__qa_` DOM Identifiers in Injected Control Panel
- **Severity**: Low (Branding / Code Hygiene Inconsistency)
- **Component**: `src/tracecase/control_panel.py`
- **Observed Behavior**:
  The control panel container uses `#__tracecase_panel__`, but internal elements retain legacy naming: `#__qa_start_btn__`, `#__qa_stop_btn__`, `#__qa_status_dot__`, `#__qa_steps_count__`, and CSS `@keyframes __qa_pulse`. Leftover artifacts from the previous `qa_auto` product name.

---

## BUG-007: Codegen Generates Asynchronous Playwright Tests (`pytest-asyncio`)
- **Severity**: Info / Documentation Clarification
- **Component**: `src/tracecase/codegen.py`
- **Observed Behavior**:
  Generated tests use `async def test_*(page: Page): ...` and `await ...`. Executing these generated tests requires `pytest-asyncio` installed and active, which is valid and fully functional but not highlighted in user documentation.

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

## BUG-009: Plaintext Credential Leakage in Test Case Recordings
- **Severity**: Critical (Security Vulnerability)
- **Component**: `src/tracecase/events.py` (line 178) & `src/tracecase/recorder.py`
- **Observed Behavior**:
  When recording interactions on password fields (`<input type="password">`), the injected JavaScript event listener reads `lastInputValue[selector] = el.value` without checking the input's `type` attribute. As a result, the recorded `testcase.json` stores the user's plaintext password in `step.input_value`.
- **Contract / Specification**:
  `src/tracecase/requirements/validation/sandbox.py:73` explicitly specifies:
  > "Traces, screenshots, and logs are safely stored with credential masking."
- **Test Target**:
  Marked `@pytest.mark.xfail(strict=True, reason="BUG-009: Password input values stored in plaintext without credential masking")` in `tests/dogfood/cli_tests/test_cli_b_record.py::test_b27_password_masking_audit`.

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
  Marked `@pytest.mark.xfail(strict=True, reason="BUG-010: ReplayEngine._perform raises ValueError for action_type='scroll'")` in `tests/dogfood/cli_tests/test_cli_b_record.py::test_b16_action_types_replay_scroll_bug`.

---

## Tracecase Bug-to-Test Traceability Matrix (BUG-001 to BUG-010)

| Bug ID | Title | Component | Dedicated Test Node ID | Test Marker |
|---|---|---|---|---|
| **BUG-001** | Root `annotated_doc` stub shadows package | `annotated_doc/` | `test_cli_a_help.py::test_a1_root_annotated_doc_shadowing_bug` | `xfail(strict=True)` |
| **BUG-002** | Healing candidate order prioritizes XPath over ID | `replay/healing.py` | `test_cli_c_replay_healing.py::test_c10_healing_tiers_and_false_positive_audit` | Passed (audit assertion) |
| **BUG-003** | Replay exits with code 2 on missing element | `cli.py`, `replay/` | `test_cli_c_replay_healing.py::test_c8_replay_without_heal_version_b` | `xfail(strict=True)` |
| **BUG-004** | Diff pads canvas without warning on dimension mismatch | `replay/visual.py` | `test_cli_d_diff.py::test_d4_dimension_mismatch_warning_reported` | `xfail(strict=True)` |
| **BUG-005** | Incomplete mutation strategies (skip, reorder, latency) | `mutation.py` | `test_cli_g_mutate.py::test_g3_missing_skip_action_mutation`<br>`test_cli_g_mutate.py::test_g3_missing_reorder_inputs_mutation`<br>`test_cli_g_mutate.py::test_g4_missing_latency_fault_mutation` | `xfail(strict=True)` (3 tests) |
| **BUG-006** | Legacy `__qa_` DOM IDs in injected control panel | `control_panel.py` | `test_cli_b_record.py::test_b12_control_panel_legacy_qa_ids_audit` | Passed (audit assertion) |
| **BUG-007** | Codegen generates async test requiring `pytest-asyncio` | `codegen/` | `test_cli_f_codegen.py::test_f11_codegen_requires_pytest_asyncio_audit` | Passed (audit assertion) |
| **BUG-008** | Unhandled connection error dumps raw Python traceback | `cli.py` (record) | `test_cli_b_record.py::test_b11_unreachable_url` | `xfail(strict=True)` |
| **BUG-009** | Plaintext credential leakage in password input | `events.py` | `test_cli_b_record.py::test_b27_password_masking_audit` | `xfail(strict=True)` |
| **BUG-010** | ReplayEngine crashes on action_type `scroll` | `replay/engine.py` | `test_cli_b_record.py::test_b16_action_types_replay_scroll_bug` | `xfail(strict=True)` |

