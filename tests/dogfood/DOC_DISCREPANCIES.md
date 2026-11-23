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

## 2. Root Package Shadowing Bug: `annotated_doc` Stub
- **Location**: Repository root `./annotated_doc/__init__.py`
- **Docs**: Does not document `annotated_doc`.
- **Code**:
  - The repository root contains `./annotated_doc/__init__.py` with `class Doc: pass`.
  - When Python runs in the repository root without isolation, `sys.path[0]` loads the local empty `Doc` class instead of the installed `annotated-doc` package in `.venv/lib/python3.14/site-packages/annotated_doc/`.
  - When FastAPI (`fastapi.security.http`) executes `Doc("The HTTP Basic password.")`, it crashes with `TypeError: Doc() takes no arguments`.
- **Resolution for Testing**:
  - Tests running FastAPI / Studio must isolate `sys.path` (or run with `src` in `PYTHONPATH` without `.` in front) to prevent shadowing until the user approves removing the stub.

---

## 3. Healing Tier Ordering & Candidate Selectors
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
- **Resolution for Testing**: Test candidate generation and resolution against the real code ordering, documenting that XPath and data-testid take precedence before `#id` in the current implementation.

---

## 4. `tracecase clean` Default Flag Behavior
- **Location**: `src/tracecase/cli.py` vs `README.md` / `docs/USER_GUIDE.md`
- **Docs**: Some descriptions suggest `tracecase clean` cleans all artifacts or requests interactive confirmation.
- **Code**:
  - `clean` command default options: `--db` is `True`, `--recordings` is `False`, `--all` is `False`.
  - Running bare `tracecase clean` only wipes the corpus SQLite database, leaving recording directories untouched.
- **Resolution for Testing**: Validate that bare `tracecase clean` wipes corpus database while preserving `./recordings/`.

---

## 5. Pytest Codegen Structure: Async Fixtures & Output
- **Location**: `src/tracecase/codegen/pytest_exporter.py` vs `docs/USER_GUIDE.md`
- **Docs**: Notes that generated tests use pytest-asyncio with Playwright async API and fixtures.
- **Code**:
  - `generate_pytest_code()` generates `@pytest_asyncio.fixture async def page() -> AsyncGenerator[Page]`, with context closing and browser launch.
  - When `--har` is specified, it sets up route interception with HAR replaying via Playwright's `route_from_har`.
- **Resolution for Testing**: Execute generated code with `pytest` in subprocess and confirm it passes.

---

## 6. CLI Command Nomenclature: `version` vs `--version`
- **Location**: `tracecase --help`
- **Docs**: Often mentions `tracecase --version`.
- **Code**:
  - Typer CLI defines `tracecase version` as a subcommand.
  - `tracecase --version` triggers unknown option error.
- **Resolution for Testing**: Test `tracecase version` as subcommand, and verify error handling for `--version`.
