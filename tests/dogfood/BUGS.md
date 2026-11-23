# Tracecase Bug Tracker (BUGS.md)

This document tracks all defects, inconsistencies, and functional regressions discovered during Tracecase dogfood testing.

---

## BUG-001: Root `annotated_doc` Stub Shadows Package and Crashes FastAPI on Launch
- **Severity**: High (Blocks `uvicorn`, `pytest`, and `tracecase ui` when launched from repository root)
- **Component**: Python Environment / Root Namespace (`./annotated_doc/__init__.py`)
- **Found in Git**: Tracked in commit `687543898b814f6f6f41ee4931becfec6071d801` (added as dummy module)
- **Reproduction**:
  ```bash
  cd /Users/ganeshjayaprakash/experimental/Tracecase
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
  Verified in `tests/dogfood/cli_tests/test_c10_healing_order.py` with false-positive shift assertions.
