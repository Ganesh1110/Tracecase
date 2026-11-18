# QA Auto — Comprehensive User Guide

Welcome to the **QA Auto** user guide! This manual provides an end-to-end walkthrough of how to record, replay, heal, test, mutate, and manage browser test cases with QA Auto.

---

## Table of Contents

1. [Overview & Core Architecture](#1-overview--core-architecture)
2. [Installation & Setup](#2-installation--setup)
3. [Quick Start: Your First Recording](#3-quick-start-your-first-recording)
4. [Understanding the Generated Artifacts](#4-understanding-the-generated-artifacts)
5. [Replaying Test Cases & Self-Healing](#5-replaying-test-cases--self-healing)
6. [Visual Regression Testing & Screenshot Diffing](#6-visual-regression-testing--screenshot-diffing)
7. [Network Mocking with HAR Files](#7-network-mocking-with-har-files)
8. [Generating Standalone Pytest Test Cases](#8-generating-standalone-pytest-test-cases)
9. [Flow Analysis & Local AI Enrichment](#9-flow-analysis--local-ai-enrichment)
10. [Automated Negative Flow Generator (Mutations)](#10-automated-negative-flow-generator-mutations)
11. [Corpus Search, Indexing & Coverage Analytics](#11-corpus-search-indexing--coverage-analytics)
12. [Model Context Protocol (MCP) Server for AI Assistants](#12-model-context-protocol-mcp-server-for-ai-assistants)
13. [Multi-Tab & Pop-up Handling](#13-multi-tab--pop-up-handling)
14. [Troubleshooting & FAQs](#14-troubleshooting--faqs)

---

## 1. Overview & Core Architecture

QA Auto turns real human or automated browser interactions into structured, maintainable QA assets.

### The QA Auto Workflow

```
[ Browser Interaction ]
         │
         ▼
  qa_auto record          ──► Generates testcase.json, markdown, HTML, screenshots
         │
         ├──► qa_auto replay      ──► Replays actions, verifies assertions & heals selectors
         ├──► qa_auto diff        ──► Detects pixel-level visual UI regressions
         ├──► qa_auto codegen     ──► Exports to zero-dependency pytest-playwright scripts
         ├──► qa_auto mutate      ──► Synthesizes edge-case and negative security tests
         ├──► qa_auto analyze     ──► Evaluates flow risks via heuristics and local LLMs
         └──► qa_auto index       ──► Indexes sessions into FTS5 SQLite database
                   │
                   └──► qa_auto mcp ──► Serves test corpus to AI agents (Cursor, Claude)
```

---

## 2. Installation & Setup

### Requirements
- **Python**: 3.13 or higher
- **Operating System**: macOS, Linux, or Windows

### Installation via Pip

```bash
# 1. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate

# 2. Install QA Auto
pip install qa_auto

# 3. Install browser binaries
playwright install chromium
```

### Installing from Source

```bash
git clone https://github.com/Ganesh1110/qa_auto.git
cd qa_auto
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

### Verifying the Setup

```bash
qa_auto check
qa_auto version
```

---

## 3. Quick Start: Your First Recording

To record a user flow on any website or local web app:

```bash
qa_auto record https://example.com -o ./recordings/example_flow -n "Example Homepage Flow"
```

### During the Recording:
1. A Chromium browser window will open displaying the target URL.
2. Look at the **top-right corner** of the browser window: you will see the floating **QA Auto Control Panel**.
3. Click **Start** in the panel to begin capturing actions.
4. Interact naturally with the page: click buttons, enter form inputs, navigate menus, or open new tabs.
5. When finished, click **Stop** in the control panel.
6. QA Auto will compile the recorded steps, capture network context, save screenshots, and generate documentation.

---

## 4. Understanding the Generated Artifacts

Once a recording session completes, the output directory contains:

```text
recordings/example_flow/
├── screenshots/
│   ├── 001_click_login-btn.png
│   ├── 002_input_username.png
│   └── ...
├── testcase.json       # Pure structured data (Pydantic schema)
├── testcase.md         # Readable Markdown for Jira, GitHub, or docs
└── testcase.html       # Self-contained visual HTML report
```

### Key Data in `testcase.json`
- **Metadata**: Start URL, title, viewport dimensions, duration, timestamp.
- **Steps**: Ordered list of user actions (`click`, `input`, `select_change`, `key_press`, `scroll`).
- **Element Info**: Primary CSS selector, XPath, text content, attributes, tag name, and exact bounding box coordinates.
- **Screenshots**: Filepath to high-res PNG capturing the page state with the target element outlined in red.
- **Context**: HTTP requests/responses (with headers and status codes), browser console messages (`log`, `warn`, `error`), and uncaught exceptions.

---

## 5. Replaying Test Cases & Self-Healing

QA Auto can deterministically execute previously recorded sessions against the same or an updated environment:

```bash
# Basic headless replay
qa_auto replay ./recordings/example_flow/testcase.json

# Headed replay with selector healing enabled
qa_auto replay ./recordings/example_flow/testcase.json --headed --heal

# Save execution results to a custom directory
qa_auto replay ./recordings/example_flow/testcase.json -o ./runs/run_01
```

### Self-Healing Locators (`--heal`)
If your frontend team changes class names, renames CSS selectors, or refactors the DOM structure, standard automated tests break. With `--heal`, QA Auto activates an intelligent fallback resolution engine:
1. **Target ID**: Checks if the original `id` attribute exists.
2. **Name Attribute**: Searches for matching input or field names.
3. **Primary CSS Selector**: Attempts the recorded CSS path.
4. **Normalized Text Content**: Matches elements with identical text or button labels.
5. **Robust XPath**: Resolves via XPath hierarchy.

If the element is successfully resolved via any fallback tier, the step passes and the healed selector is recorded in the replay log.

---

## 6. Visual Regression Testing & Screenshot Diffing

QA Auto includes built-in pixel-accurate and perceptual image comparison to catch unintended styling bugs.

### Standalone Image Comparison (`qa_auto diff`)

Compare any two screenshots and generate a highlighted diff heatmap:

```bash
qa_auto diff baseline.png candidate.png -o diff_output.png --threshold 0.1
```

- **Exit code `0`**: Images match within tolerance.
- **Exit code `1`**: Mismatch exceeds threshold.
- The output image highlights pixel differences in bright magenta.

### Replay with Visual Regression (`qa_auto replay --diff`)

To verify that your UI looks identical to the original recording:

```bash
qa_auto replay ./recordings/example_flow/testcase.json \
  --diff \
  --diff-threshold 0.5 \
  --diff-fail
```

- `--diff`: Takes a screenshot at each step and compares it with the recorded baseline.
- `--diff-threshold <pct>`: Percentage of allowed pixel difference (default `0.1%`).
- `--diff-fail`: Exits with code `1` if visual drift is detected on any step.

---

## 7. Network Mocking with HAR Files

When testing against staging or offline environments where backend APIs may be unstable or unavailable:

### 1. Export HAR from Recorded Test Case

```bash
qa_auto export-har ./recordings/example_flow/testcase.json -o ./recordings/example_flow/network.har
```

### 2. Replay with Network Mocking

```bash
qa_auto replay ./recordings/example_flow/testcase.json --from-har ./recordings/example_flow/network.har
```

Playwright intercepts matching outgoing requests and returns the recorded HTTP headers, status codes, and response payloads directly from the HAR archive, allowing 100% offline replay.

---

## 8. Generating Standalone Pytest Test Cases

Convert your recorded sessions into clean, maintainable `pytest-playwright` test files that can run inside any standard CI/CD runner:

```bash
# Generate test file in the recording directory
qa_auto codegen ./recordings/example_flow/testcase.json

# Specify a custom destination path and attach HAR mocking
qa_auto codegen ./recordings/example_flow/testcase.json \
  -o ./tests/test_checkout_flow.py \
  --har ./recordings/example_flow/network.har
```

### Running the Generated Test

```bash
pytest ./tests/test_checkout_flow.py -v
```

The generated code features:
- Standard async Playwright fixtures (`async def test_*(page: Page): ...`).
- Clear step-by-step comments.
- Explicit selector waits and actions (`await page.click(...)`, `await page.fill(...)`).
- Automatically derived assertions verifying visibility and expected text.

---

## 9. Flow Analysis & Local AI Enrichment

QA Auto can analyze recorded journeys to uncover QA risks, missing assertions, and form validation gaps.

### Deterministic Heuristics (100% Offline)

```bash
qa_auto analyze ./recordings/example_flow/testcase.json
```

Heuristics inspect:
- Form submissions without prior validation steps.
- Password inputs and sensitive credential handling.
- Steps with unhandled network 4xx/5xx errors or console errors.
- Abruptly terminated user flows.

### Local AI Enrichment (Ollama / OpenAI-Compatible)

Enrich findings with an autonomous QA engineer analysis powered by your own local LLM:

```bash
# Using Ollama (default: http://127.0.0.1:11434, llama3)
qa_auto analyze ./recordings/example_flow/testcase.json --ai

# Using custom Ollama model
qa_auto analyze ./recordings/example_flow/testcase.json --ai --model mistral

# Using local OpenAI-compatible server (LM Studio, vLLM, LocalAI)
qa_auto analyze ./recordings/example_flow/testcase.json \
  --ai \
  --provider openai \
  --base-url http://127.0.0.1:8000/v1 \
  --model qwen2.5
```

The output `analysis.json` contains:
- Executive summary of the flow.
- Risk score and identified edge cases.
- Recommended assertions.
- Concrete negative test proposals.

---

## 10. Automated Negative Flow Generator (Mutations)

Rather than manually scripting dozens of negative scenarios, QA Auto synthesizes realistic failure and edge-case test cases from your golden recording:

```bash
# Generate negative test cases
qa_auto mutate ./recordings/example_flow/testcase.json -o ./mutations/

# Filter by strategy
qa_auto mutate ./recordings/example_flow/testcase.json --strategy inputs --limit 10
```

### Mutation Strategies:
- **`inputs`**: Injects empty strings, boundary text (2,048 chars), SQL injection patterns (`' OR '1'='1`), XSS payloads (`<script>alert(1)</script>`), and Unicode zero-width edge cases.
- **`actions`**: Skips critical actions (e.g., clicking accept terms), duplicates clicks (rapid double submits), or reorders sequential inputs.
- **`network`**: Injects simulated backend failures: HTTP 500 Internal Server Error, HTTP 403 Forbidden, HTTP 429 Rate Limited, or artificial high latency.

Each mutated test case is saved as a runnable `testcase.json` that you can directly replay:

```bash
qa_auto replay ./mutations/tc_example_mut_1_empty/testcase.json
```

---

## 11. Corpus Search, Indexing & Coverage Analytics

When maintaining dozens or hundreds of test cases, QA Auto provides a centralized search and analytics engine powered by SQLite FTS5.

### Indexing Recordings

```bash
# Index a single directory of recordings
qa_auto index ./recordings/

# Index multiple projects into a centralized database
qa_auto index ./tests/e2e/ --db ~/.qa_auto/corpus.db
```

### Full-Text Search (BM25)

Search across all recorded steps, input values, button labels, selectors, and URLs:

```bash
qa_auto search "submit payment"
qa_auto search "input[name='email']" --limit 5
```

### Coverage Analytics

Audit which URLs, domains, and interactive elements have test coverage:

```bash
qa_auto coverage
```

Displays:
- Total unique domains and endpoints covered.
- Breakdown of actions per domain.
- Warnings for identical duplicate test flows.

---

## 12. Model Context Protocol (MCP) Server for AI Assistants

QA Auto includes a native Model Context Protocol (MCP) server operating over `stdio`. This allows AI coding tools like **Cursor**, **Claude Desktop**, and **Antigravity** to search, read, and reason over your QA test suite.

### Running the Server

```bash
qa_auto mcp
# Or with a custom corpus database:
qa_auto mcp --db ~/.qa_auto/corpus.db
```

### Claude Desktop Configuration Example

Add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "qa-auto": {
      "command": "/path/to/.venv/bin/qa_auto",
      "args": ["mcp", "--db", "/path/to/.qa_auto/corpus.db"]
    }
  }
}
```

### Cursor IDE Configuration Example

In Cursor settings under **Features > MCP Servers**:
- **Name**: `qa-auto`
- **Type**: `command`
- **Command**: `/path/to/.venv/bin/qa_auto mcp`

### Available MCP Tools:
- `search_testcases`: Search the indexed corpus by keyword or selector.
- `get_testcase`: Retrieve full JSON details for any test case ID.
- `get_coverage`: Obtain corpus coverage metrics and tested domain distributions.

---

## 13. Multi-Tab & Pop-up Handling

QA Auto automatically tracks multiple browser tabs and popup windows.

- **During Recording**: When a link opens a new tab (`target="_blank"`) or JavaScript triggers `window.open()`, QA Auto attaches listeners to the newly created page. All interactions on that page are tagged with their corresponding `page_id`.
- **During Replay**: The replay engine synchronizes popup creation (`expect_popup()`) and automatically switches execution context to the active tab.
- **Backwards Compatibility**: Existing single-page test cases without `page_id` continue to function seamlessly.

---

## 14. Troubleshooting & FAQs

### Q: Browser fails to launch with an error about missing libraries.
**A**: Run `playwright install --with-deps chromium` to ensure all system shared libraries are present on your operating system.

### Q: Replay fails because a dynamic element takes too long to render.
**A**: Increase the action timeout using `--timeout`:
```bash
qa_auto replay ./recordings/example_flow/testcase.json -t 60000
```

### Q: Why does `qa_auto analyze --ai` fail to connect?
**A**: Ensure your local LLM server is running:
- For Ollama: Run `ollama serve` and check `curl http://127.0.0.1:11434/api/tags`.
- For OpenAI-compatible servers: Check that the `--base-url` includes `/v1` (e.g., `http://127.0.0.1:8000/v1`).

### Q: Are my credentials or sensitive data sent to the cloud?
**A**: No. QA Auto is completely local and private by default. Screenshots, HAR files, database records, and AI analyses remain on your machine unless you explicitly point `--base-url` to an external host.
