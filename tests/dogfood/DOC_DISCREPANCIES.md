# Documentation Discrepancies (DOC_DISCREPANCIES.md)

This document tracks all discrepancies discovered between the documentation (`README.md`, `docs/USER_GUIDE.md`, `docs/DEMO_GUIDE.md`) and the actual implementation in `src/tracecase/` and `frontend/`.

---

## 1. MCP Tool Naming: `coverage_report` vs `get_coverage`
- **Location**: `src/tracecase/mcp/server.py` vs `docs/USER_GUIDE.md` vs `README.md`
- **Docs**:
  - `docs/USER_GUIDE.md` (line 398) states available tools: `search_testcases`, `get_testcase`, `get_coverage`.
  - `README.md` (line 500) states available tools: `search_testcases`, `get_testcase`, and `coverage_report`.
- **Code**:
  - `src/tracecase/mcp/server.py` (lines 81, 149) registers tool named `"coverage_report"`.
  - Calling `get_coverage` returns an error (`Method not found: tools/call` or invalid tool name).
- **Resolution for Testing**: Test actual behavior (`coverage_report` succeeds, `get_coverage` returns error).

---

## 2. Root Package Shadowing Bug: `annotated_doc` Stub (BUG-001)
- **Location**: Repository root `./annotated_doc/__init__.py`
- **Docs**: Unmentioned in documentation.
- **Code**:
  - Tracked in git commit `687543898b814f6f6f41ee4931becfec6071d801`.
  - The repository root contains `./annotated_doc/__init__.py` with `class Doc: pass`.
  - When Python runs in the repository root without isolation, `sys.path[0]` loads the local empty `Doc` class instead of the installed `annotated-doc` package in `.venv/lib/python3.14/site-packages/annotated_doc/`.
  - When FastAPI (`fastapi.security.http`) executes `Doc("The HTTP Basic password.")`, it crashes with `TypeError: Doc() takes no arguments`.
- **Resolution for Testing**:
  - Tests running FastAPI / Studio must isolate `sys.path` (or run with `src` in `PYTHONPATH` without `.` in front).
  - Regression test verifies this reproduces from root.

---

## 3. Healing Tier Ordering & Candidate Selectors (BUG-002)
- **Location**: `src/tracecase/replay/healing.py` vs `docs/USER_GUIDE.md` (Section 4)
- **Docs**:
  `docs/USER_GUIDE.md` lists the fallback order as:
  1. Exact CSS Selector
  2. Element ID (`#id`)
  3. Name attribute (`[name="..."]`)
  4. Role + accessible name (`role=button[name="..."]`)
  5. Text content (`text="..."`)
  6. XPath
- **Code**:
  `src/tracecase/replay/healing.py` `candidate_selectors()` implements:
  1. `element.selector` (Original CSS)
  2. `xpath={element.xpath}` (XPath is Tier 2 in code, but Tier 6 in docs!)
  3. `[data-testid=...]` (Tier 3 in code; missing from docs)
  4. `#{element.id}` (Tier 4 in code; Tier 2 in docs)
  5. `tag[name=...]` and `[name=...]` (Tier 5 in code; Tier 3 in docs)
  6. `[placeholder=...]` (Tier 6 in code; missing from docs)
  7. `[aria-label=...]` (Tier 7 in code; missing from docs)
  8. Clean selector (stripped focus/hover pseudo-classes)
  9. `role=...[name=...]` (Tier 9 in code; Tier 4 in docs)
  10. `text=...` (Tier 10 in code; Tier 5 in docs)
- **Risk**: Stale absolute XPath can match unintended DOM elements following layout shifts. Tested in `test_c10_healing_order.py`.

---

## 4. Mutation Strategies: Documented vs Implemented
- **Location**: `src/tracecase/mutation/` (`actions.py`, `network.py`, `inputs.py`) vs `docs/`
- **Docs**:
  - `docs/USER_GUIDE.md` and spec plans promise:
    - Action mutations: `skip_action`, `rapid double click`, `reorder inputs`.
    - Network mutations: `HTTP 500`, `HTTP 403`, `HTTP 429`, and `high latency` delays.
- **Code**:
  - `src/tracecase/mutation/actions.py` ONLY implements `double_click`. There is no implementation of `skip_action` or `reorder_inputs`.
  - `src/tracecase/mutation/network.py` ONLY injects HTTP 500 (`network_error`). There is no implementation of HTTP 403, HTTP 429, or latency delay injection.
  - `src/tracecase/mutation/models.py` defines `MutationType = Literal["empty", "boundary_long", "special_chars", "unicode", "invalid_format", "double_click", "network_error"]`.
- **Resolution for Testing**: Test actual behavior in code (`double_click`, `network_error` 500, input probes); assert graceful failure / rejection if non-implemented strategies are requested.

---

## 5. ActionTypes: Code Enum vs Docs
- **Location**: `src/tracecase/models.py`, `src/tracecase/events.py`, `src/tracecase/replay/engine.py` vs `docs/USER_GUIDE.md`
- **Docs**:
  - `docs/USER_GUIDE.md` explicitly lists `scroll`, `radio`, `checkbox` as captured browser actions.
- **Code & Actual Behavior**:
  - `ActionType` enum in `src/tracecase/models.py` defines 11 types: `Literal["click", "dblclick", "input", "select", "check", "uncheck", "navigate", "scroll", "hover", "keypress", "wait"]`.
  - **Scroll is never recorded and crashes replay (BUG-010)**: `events.py` does not attach `scroll` event listeners in `EVENT_LISTENER_JS`, so user scrolling is never emitted. If a testcase with `action_type="scroll"` is fed to `ReplayEngine._perform`, it crashes with `ValueError: Unsupported action type: scroll`.
  - **Hover and wait are modeled but unrecordable**: `hover` and `wait` are first-class enum values in `ActionType`, but `events.py` has no `mouseenter`/`mouseover` listeners for hover, and `wait` is purely a synthetic construct. They cannot be recorded interactively from the browser.
  - Radios and checkboxes are recorded as `click` or `check`/`uncheck`.

---

## 6. CLI Options Present in Code but Omitted from Docs
- **`replay`**:
  - `--browser` / `-b` option exists in `src/tracecase/cli.py` (`chromium|firefox|webkit`), allowing cross-browser replay from the CLI, but is omitted from several summary tables in the docs.
- **`analyze`**:
  - `--api-key` option is supported in `cli.py` to pass OpenAI API keys directly, but docs only mention environment variables.
- **`run` & `select`**:
  - Undocumented options: `--include-critical`, `--count-budget`, `--risk-coverage`, `--pareto_optimal` strategy.
- **`ci`**:
  - `--baseline-ref`, `--auto-run-baseline`, `--allow-preexisting`, `--upload-url`, `--upload-token` are implemented in CLI but not fully documented in `USER_GUIDE.md`.

---

## 7. Leftover Legacy Name Strings (`qa_auto` / `__qa_`)
- **Location**: `src/tracecase/control_panel.py` and `docs/superpowers/plans/`
- **Evidence**:
  - Control panel injected DOM IDs use `__qa_` prefixes:
    `__qa_start_btn__`, `__qa_stop_btn__`, `__qa_status_dot__`, `__qa_status_text__`, `__qa_steps_count__`, `__qa_message__`, `__qa_pulse`.

---

## 8. Replay Exit Code Contract: Action Error vs Assertion Failure
- **Location**: `src/tracecase/replay/engine.py` (lines 156-167) vs `docs/USER_GUIDE.md`
- **Docs**: Docs imply exit code 0 = pass, 1 = test failure, 2 = CLI infrastructure error.
- **Code**:
  - In `ReplayEngine.run()`:
    - If any step status is `"error"` (e.g., target element not found, action timeout): `status = "error"`, `exit_code = 2`.
    - If any step status is `"failed"` (e.g., derived assertion or visual diff failed): `status = "failed"`, `exit_code = 1`.
    - If all steps pass: `status = "passed"`, `exit_code = 0`.
- **Resolution for Testing**: Tests assert exit code 2 for action/selector errors, exit code 1 for assertion failures, and exit code 0 for passing replays.

---

## 9. Visual Diff Dimension Mismatch Behavior
- **Location**: `src/tracecase/replay/visual.py` (lines 60-69) vs `docs/USER_GUIDE.md`
- **Docs**: Docs indicate that comparing images with mismatched dimensions causes a comparison failure/error.
- **Code**:
  - `compare_images()` does not raise an exception or abort on dimension mismatches.
  - It automatically normalizes both images to the bounding box `(max(w1, w2), max(h1, h2))` by padding with transparent pixels `(0, 0, 0, 0)`.
  - The padded difference area is counted toward `diff_pixels`, producing an accurate diff percentage and returning `passed = False` (which causes `tracecase diff` CLI to exit with code 1, not exit code 2).
- **Resolution for Testing**: Tests assert graceful canvas padding and exit code 1 on dimension mismatches.

---

## 10. Codegen Asynchronous Fixture vs Sync Playwright Documentation (BUG-007)
- **Location**: `src/tracecase/codegen/pytest_exporter.py` vs `docs/USER_GUIDE.md` / Playwright docs
- **Docs**: Documentation suggests running generated tests directly via standard `pytest` / Playwright runner.
- **Code**:
  - `pytest_exporter.py` generates `import pytest_asyncio` and `async def test_*(page: Page): ...`.
  - In environments without `pytest-asyncio` installed, pytest fails at collection with `ModuleNotFoundError: No module named 'pytest_asyncio'`. Standard `pytest-playwright` tests use synchronous test functions (`def test_*(page: Page): ...`).
- **Resolution for Testing**: Documented as BUG-007; characterized in test suite and tracked with strict xfail.

---

## 11. Browser Disconnect Handling During Active Recording (BUG-012)
- **Location**: `src/tracecase/recorder.py` and `src/tracecase/cli.py` vs User Guide
- **Docs**: Documentation implies user workflows are preserved and saved when recording completes.
- **Code**:
  - Closing the browser window without pressing "Stop" in the control panel triggers browser disconnect, which causes the CLI to exit 0 with "Browser closed".
  - However, `export()` is never called, silently dropping all recorded steps with zero files written and no warning to the user.
- **Resolution for Testing**: Documented as BUG-012; tracked with strict xfail `test_b14_close_browser_without_stop_saves_or_warns`.
