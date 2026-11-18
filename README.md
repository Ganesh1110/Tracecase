# QA Auto

**Record once, test everywhere.**

QA Auto is an open-source command-line tool that turns real browser interactions into structured, shareable test cases. Open a URL, hit **Start**, exercise your application, hit **Stop**, and QA Auto writes a complete test case with screenshots, network activity, console output, and JavaScript errors.

The generated reports are readable by QA engineers, developers, and AI agents, and are available as JSON, Markdown, and HTML.

[![CI](https://github.com/Ganesh1110/qa_auto/actions/workflows/ci.yml/badge.svg)](https://github.com/Ganesh1110/qa_auto/actions/workflows/ci.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

---

## Table of contents

- [Why QA Auto](#why-qa-auto)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [How it works](#how-it-works)
- [Output](#output)
- [CLI reference](#cli-reference)
- [What gets captured](#what-gets-captured)
- [Project structure](#project-structure)
- [Development](#development)
- [Limitations](#limitations)
- [License](#license)

---

## Why QA Auto

- **Zero manual documentation.** Perform a flow once and get a step-by-step test case.
- **Visual evidence.** Every captured step includes a screenshot with the target element highlighted.
- **Full context.** Network requests, console logs, and JavaScript errors are attached to the relevant steps.
- **Three formats.** JSON for automation, Markdown for tickets and docs, HTML for reviews and demos.
- **Cross-browser.** Record with Chromium, Firefox, or WebKit.
- **Local and private.** Recordings run on your machine and stay there.
- **Clean screenshots.** The QA Auto control panel is automatically hidden while screenshots are taken.

QA Auto is useful for:

- QA engineers documenting manual test scenarios
- Developers reporting bugs with full reproduction context
- Teams building datasets for test automation and AI tooling

---

## Requirements

- Python 3.13 or newer
- [Playwright](https://playwright.dev/python/) and a Playwright browser

---

## Installation

From PyPI:

```bash
pip install qa_auto
playwright install chromium
```

From source:

```bash
git clone https://github.com/Ganesh1110/qa_auto.git
cd qa_auto
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

---

## Quick start

```bash
qa_auto record https://example.com --output ./my_test
```

With options:

```bash
qa_auto record https://example.com -o ./tests -n "Login Flow" -b firefox
```

Check your environment:

```bash
qa_auto check
```

Show version and installed dependencies:

```bash
qa_auto version
```

---

## How it works

1. Run `qa_auto record <url> -o <output-dir>`.
2. A browser window opens with the QA Auto control panel in the top-right corner.
3. Click **Start** in the panel.
4. Perform your test actions in the browser.
5. Click **Stop**. QA Auto saves the test case and closes the session.

The control panel tracks the number of captured steps. The panel itself is excluded from every screenshot.

---

## Output

After a recording, the output directory contains:

```text
output/
├── screenshots/
│   ├── 001_click_login-button.png
│   ├── 002_input_email-field.png
│   └── ...
├── testcase.json    # Machine-readable test case
├── testcase.md      # Markdown documentation
└── testcase.html    # Visual HTML report
```

The JSON model includes test case metadata, ordered steps, element details, screenshots, network requests, console logs, and page errors.

---

## CLI reference

### `qa_auto record`

Record browser actions and generate a test case.

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--output` | `-o` | Output directory for test case files | required |
| `--name` | `-n` | Test case name | generated from the URL |
| `--browser` | `-b` | Browser: `chromium`, `firefox`, `webkit` | `chromium` |
| `--headless` | | Run the browser without a visible window | `false` |
| `--timeout` | `-t` | Action timeout in milliseconds | `30000` |

### `qa_auto check`

Verify that Python packages and Playwright browsers are installed correctly.

### `qa_auto version`

Print the QA Auto version along with Python, Playwright, and Pydantic versions.

### `qa_auto replay`

Replay a recorded test case, evaluate derived assertions, and optionally heal selectors.

| Option | Description | Default |
|--------|-------------|---------|
| `--output` / `-o` | Directory for `replay.json` and screenshots | none |
| `--heal` | Try fallback selectors when the recorded selector is missing | `false` |
| `--assert` / `--no-assert` | Evaluate derived assertions | enabled |
| `--from-har` | Fulfill network requests from a recorded HAR | none |
| `--headed` | Show the browser window | `false` |
| `--timeout` / `-t` | Action timeout in milliseconds | `30000` |
| `--diff` / `--no-diff` | Perform visual screenshot comparison | `false` |
| `--diff-threshold` | Tolerance percentage for visual diff | `0.1` |
| `--diff-fail` / `--no-diff-fail` | Fail replay if visual diff exceeds threshold | `false` |

Exit codes: `0` passed, `1` assertion or visual diff failed, `2` infrastructure error.

### `qa_auto diff`

Compare two screenshots or images pixel-by-pixel, compute diff metrics, and optionally save a highlighted diff overlay image.

```bash
# Compare two images with default 0.1% threshold
qa_auto diff baseline.png candidate.png

# Specify custom tolerance threshold and save highlighted diff image
qa_auto diff baseline.png candidate.png -o diff.png --threshold 0.5
```

### `qa_auto export-har`

Write recorded network activity to a HAR file for offline replay.

```bash
qa_auto export-har ./my_test/testcase.json -o ./my_test/network.har
qa_auto replay ./my_test/testcase.json --from-har ./my_test/network.har
```

### `qa_auto codegen`

Generate standalone, executable `pytest` + Playwright Python test modules from recorded test cases.

```bash
# Generate test_<name>.py in the same folder
qa_auto codegen ./my_test/testcase.json

# Specify an output path and optional HAR for offline mock routing
qa_auto codegen ./my_test/testcase.json -o ./tests/test_checkout.py --har ./my_test/network.har

# Run the generated test with pytest
pytest ./tests/test_checkout.py -v
```

### `qa_auto analyze`

Analyze recorded flows with deterministic heuristics and optional local AI enrichment (Ollama, OpenAI-compatible). Generates flow summaries, risk flagging, negative test scenarios, and assertion suggestions in `analysis.json`.

```bash
# Run deterministic heuristics (offline, no LLM required)
qa_auto analyze ./my_test/testcase.json

# Enrich with local Ollama (default http://127.0.0.1:11434, llama3)
qa_auto analyze ./my_test/testcase.json --ai

# Enrich with custom local OpenAI-compatible endpoint or model
qa_auto analyze ./my_test/testcase.json --provider openai --base-url http://127.0.0.1:8000/v1 --model qwen2.5
```

| Option | Description | Default |
|--------|-------------|---------|
| `--output` / `-o` | Directory to save `analysis.json` | test case dir |
| `--ai` | Enable local AI enrichment | `false` |
| `--provider` | AI provider (`null`, `ollama`, `openai`) | `null` |
| `--base-url` | Provider endpoint URL | default per provider |
| `--model` / `-m` | Model name | default per provider |

### `qa_auto index`

Index directories of `testcase.json` recordings into a local SQLite database with full-text search (FTS5).

```bash
# Index recordings in a directory
qa_auto index ./my_test/

# Specify a custom corpus database location
qa_auto index ./tests/recordings/ --db ./corpus.db
```

### `qa_auto search`

Search indexed test cases and actions using fast FTS5 BM25 relevance ranking and matched text snippets.

```bash
# Search for actions or flows mentioning "checkout" or "Payment"
qa_auto search "Payment"

# Limit the number of search results
qa_auto search "login" --limit 5
```

### `qa_auto coverage`

Analyze test corpus coverage across tested domains, start URLs, network endpoints, and flag potential duplicate test flows.

```bash
qa_auto coverage
qa_auto coverage --db ./corpus.db
```

### `qa_auto mcp`

Start the Model Context Protocol (MCP) server over stdio, exposing your indexed test corpus (`search_testcases`, `get_testcase`, `coverage_report`) to local LLM agents and IDE assistants.

```bash
qa_auto mcp
qa_auto mcp --db ./corpus.db
```

---

## What gets captured

- Clicks and double-clicks
- Text input (debounced)
- Select, checkbox, and radio changes
- Special key presses (`Enter`, `Escape`, `Tab`)
- CSS selector, XPath, tag name, text, placeholder, and bounding box for each target element
- A screenshot per step, with the target element outlined
- Network requests and responses, including headers, bodies, status, and timing
- Browser console messages
- Uncaught JavaScript errors

---

## Project structure

```text
qa_auto/
├── src/qa_auto/
│   ├── cli.py             # Typer CLI commands
│   ├── recorder.py        # Recording session and export orchestration
│   ├── browser.py         # Playwright browser management
│   ├── events.py          # DOM event capture and element extraction
│   ├── control_panel.py   # In-browser Start/Stop panel
│   ├── screenshot.py      # Screenshot capture, highlighting, panel hiding
│   ├── models.py          # Pydantic data models
│   ├── exporters/         # JSON, Markdown, and HTML exporters
│   ├── replay/            # Replay engine, assertions, HAR, self-healing
│   ├── codegen/           # Pytest Playwright code generator
│   ├── ai/                # Heuristic and local LLM flow analyzer
│   ├── index/             # SQLite FTS5 corpus index and search
│   ├── mcp/               # Stdio Model Context Protocol server
│   └── templates/         # Jinja2 report templates
└── tests/                 # Unit and integration tests
```

---

## Development

### Setup

```bash
git clone https://github.com/Ganesh1110/qa_auto.git
cd qa_auto
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

### Tests

```bash
pytest                 # All tests
pytest -m "not slow"   # Skip slow tests
pytest --cov=qa_auto   # With coverage
```

### Linting and type checking

```bash
ruff check src/ tests/
ruff format src/ tests/
mypy src/qa_auto --ignore-missing-imports
```

---

## Limitations

- Replay supports derived assertions, heuristic selector healing, and pixel-accurate visual regression diffing.
- Desktop web only; mobile apps and API-only testing are not covered.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
