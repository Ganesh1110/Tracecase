# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-11-18

### Added
- **Replay & Self-Healing Engine (`qa_auto replay`)**:
  - Deterministic replay of recorded browser test cases with Playwright.
  - Automatic assertion derivation from captured DOM state, HTTP statuses, and console output.
  - Multi-tier self-healing locators that automatically recover from UI selector drift (ID -> Name -> CSS -> Text -> XPath).
  - HAR network mocking and recording with `--mock-har` and `--update-har`.
  - Replay execution reports in JSON (`--json-out`) and formatted terminal tables.
- **Standalone Pytest Codegen (`qa_auto codegen`)**:
  - Export recorded sessions directly into standalone `pytest-playwright` test scripts.
  - Clean async Python code generation with Playwright locators, actions, and assertions.
  - Configurable module headers, timeouts, and fixture setup.
- **Local AI & Heuristic Flow Analysis (`qa_auto analyze`)**:
  - Offline heuristic rule engine detecting broken user flows, unasserted actions, and form validation gaps.
  - Local AI provider support for Ollama, LM Studio, and OpenAI-compatible local LLM endpoints.
  - Actionable recommendations and bug risk scoring for QA engineers.
- **Corpus Store, Search & Analytics (`qa_auto index`, `search`, `coverage`)**:
  - SQLite FTS5-backed indexed corpus store for high-speed full-text search across all recorded sessions.
  - BM25 ranked search across selectors, actions, URLs, and text descriptions.
  - URL and selector coverage analytics to pinpoint untested user pathways.
- **Local Model Context Protocol Server (`qa_auto mcp`)**:
  - Stdio-based JSON-RPC 2.0 MCP server for AI coding assistants (Claude Desktop, Cursor, Antigravity).
  - Tools exposed: `search_testcases` and `get_coverage`.
- **Visual Regression Testing (`qa_auto diff`, `qa_auto replay --diff`)**:
  - Pixel-by-pixel and threshold-based image comparison using Pillow.
  - Automated diff heatmap overlay generation highlighting UI shifts and regressions.
  - Native integration with replay via `--diff`, `--diff-threshold`, and `--diff-fail`.
- **Automated Negative Flow Generator (`qa_auto mutate`)**:
  - Systematic mutation engine creating negative and edge-case test suites from recorded baseline sessions.
  - Strategies for boundary input injection (SQLi, XSS, Unicode, buffer overflows), action reordering/dropping, and network fault simulation (500, 403, 429 errors, artificial latency).
- **Multi-Tab & Pop-up Handling**:
  - Automatic tracking of multi-window and pop-up events during recording with `page_id`.
  - Seamless multi-page context management and popup synchronization in the replay engine.
  - Full backwards compatibility with single-page test cases (`page_id=None`).

### Changed
- Refactored `Step` model with optional `page_id` field.
- Refactored `BrowserManager` to expose underlying `BrowserContext` for multi-page event handling.
- Upgraded project CLI with Typer subcommands for replay, codegen, analysis, indexing, search, diffing, and mutations.

---

## [0.1.0] - 2026-11-18

### Added
- Initial release of QA Auto.
- Browser recording with Playwright (`qa_auto record`).
- Automatic screenshot capture on user interactions.
- Network request and response monitoring.
- Console error and page error recording.
- Multi-format test case export (JSON, Markdown, HTML).
- Interactive element metadata extraction (ARIA, CSS, XPath, bounding box).
