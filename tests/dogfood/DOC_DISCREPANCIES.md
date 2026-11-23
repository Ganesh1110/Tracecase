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
- **Location**: `src/tracecase/models.py` vs `docs/USER_GUIDE.md`
- **Docs**: Mentions recording `radio`, `scroll`, `checkbox`.
- **Code**:
  - `ActionType` enum in `src/tracecase/models.py`:
    `Literal["click", "dblclick", "input", "select", "check", "uncheck", "navigate", "scroll", "hover", "keypress", "wait"]`
  - Radios are recorded under `check` or `click`.
  - `hover`, `wait`, `navigate`, `check`, `uncheck` are first-class action types in code.

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
  - Planning documents in `docs/superpowers/plans/*.md` use `qa_auto` instead of `tracecase` throughout.
- **Resolution for Testing**: Test selectors against real DOM IDs (`#__qa_start_btn__` etc.).
