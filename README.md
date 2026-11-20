# Tracecase

**Record once, test everywhere.**

Tracecase is an open-source command-line tool that turns real browser interactions into structured, shareable test cases. Open a URL, hit **Start**, exercise your application, hit **Stop**, and Tracecase writes a complete test case with screenshots, network activity, console output, and JavaScript errors.

The generated reports are readable by QA engineers, developers, and AI agents, and are available as JSON, Markdown, and HTML.

[![CI](https://github.com/Ganesh1110/Tracecase/actions/workflows/ci.yml/badge.svg)](https://github.com/Ganesh1110/Tracecase/actions/workflows/ci.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

---

## Table of contents

- [Why Tracecase](#why-tracecase)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Comprehensive User Guide](docs/USER_GUIDE.md)
- [QA Demo Guide](docs/DEMO_GUIDE.md)
- [How it works](#how-it-works)
- [Output](#output)
- [CLI reference](#cli-reference)
- [What gets captured](#what-gets-captured)
- [Project structure](#project-structure)
- [Development](#development)
- [Limitations](#limitations)
- [License](#license)

---

## Why Tracecase

- **Zero manual documentation.** Perform a flow once and get a step-by-step test case.
- **Visual evidence.** Every captured step includes a screenshot with the target element highlighted.
- **Full context.** Network requests, console logs, and JavaScript errors are attached to the relevant steps.
- **Three formats.** JSON for automation, Markdown for tickets and docs, HTML for reviews and demos.
- **Cross-browser.** Record with Chromium, Firefox, or WebKit.
- **Multi-tab & pop-up support.** Seamlessly captures and replays actions across newly opened tabs, pop-ups, and `target="_blank"` windows.
- **Local and private.** Recordings run on your machine and stay there.
- **Clean screenshots.** The Tracecase control panel is automatically hidden while screenshots are taken.

Tracecase is useful for:

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
pip install tracecase
playwright install chromium
```

From source:

```bash
git clone https://github.com/Ganesh1110/Tracecase.git
cd Tracecase
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

---

## Quick start

```bash
tracecase record https://example.com --output ./my_test
```

With options:

```bash
tracecase record https://example.com -o ./tests -n "Login Flow" -b firefox
```

Check your environment:

```bash
tracecase check
```

Show version and installed dependencies:

```bash
tracecase version
```

---

## How it works

1. Run `tracecase record <url> -o <output-dir>`.
2. A browser window opens with the Tracecase control panel in the top-right corner.
3. Click **Start** in the panel.
4. Perform your test actions in the browser.
5. Click **Stop**. Tracecase saves the test case and closes the session.

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

### `tracecase record`

Record browser actions and generate a test case.

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--output` | `-o` | Output directory for test case files | required |
| `--name` | `-n` | Test case name | generated from the URL |
| `--browser` | `-b` | Browser: `chromium`, `firefox`, `webkit` | `chromium` |
| `--headless` | | Run the browser without a visible window | `false` |
| `--timeout` | `-t` | Action timeout in milliseconds | `30000` |

### `tracecase ui`

Launch the Tracecase Studio interactive web application.

```bash
tracecase ui
# or specify host/port
tracecase ui --host 127.0.0.1 --port 8000
```

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--host` | `-h` | Server host address | `127.0.0.1` |
| `--port` | `-p` | Server port | `8000` |
| `--browser` / `--no-browser` | | Automatically open browser window | `true` |

### `tracecase check`

Verify that Python packages and Playwright browsers are installed correctly.

### `tracecase version`

Print the Tracecase version along with Python, Playwright, and Pydantic versions.

### `tracecase replay`

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

### `tracecase diff`

Compare two screenshots or images pixel-by-pixel, compute diff metrics, and optionally save a highlighted diff overlay image.

```bash
# Compare two images with default 0.1% threshold
tracecase diff baseline.png candidate.png

# Specify custom tolerance threshold and save highlighted diff image
tracecase diff baseline.png candidate.png -o diff.png --threshold 0.5
```

### `tracecase export-har`

Write recorded network activity to a HAR file for offline replay.

```bash
tracecase export-har ./my_test/testcase.json -o ./my_test/network.har
tracecase replay ./my_test/testcase.json --from-har ./my_test/network.har
```

### `tracecase codegen`

Generate standalone, executable `pytest` + Playwright Python test modules from recorded test cases.

```bash
# Generate test_<name>.py in the same folder
tracecase codegen ./my_test/testcase.json

# Specify an output path and optional HAR for offline mock routing
tracecase codegen ./my_test/testcase.json -o ./tests/test_checkout.py --har ./my_test/network.har

# Run the generated test with pytest
pytest ./tests/test_checkout.py -v
```

### `tracecase analyze`

Analyze recorded flows with deterministic heuristics and optional local AI enrichment (Ollama, OpenAI-compatible). Generates flow summaries, risk flagging, negative test scenarios, and assertion suggestions in `analysis.json`.

```bash
# Run deterministic heuristics (offline, no LLM required)
tracecase analyze ./my_test/testcase.json

# Enrich with local Ollama (default http://127.0.0.1:11434, llama3)
tracecase analyze ./my_test/testcase.json --ai

# Enrich with custom local OpenAI-compatible endpoint or model
tracecase analyze ./my_test/testcase.json --provider openai --base-url http://127.0.0.1:8000/v1 --model qwen2.5
```

| Option | Description | Default |
|--------|-------------|---------|
| `--output` / `-o` | Directory to save `analysis.json` | test case dir |
| `--ai` | Enable local AI enrichment | `false` |
| `--provider` | AI provider (`null`, `ollama`, `openai`) | `null` |
| `--base-url` | Provider endpoint URL | default per provider |
| `--model` / `-m` | Model name | default per provider |

### `tracecase mutate`

Synthesize realistic negative test cases from a recorded user flow. Generates variations covering empty inputs, boundary strings (2048 chars), special characters / injection probes, unicode edge cases, rapid double clicks, and simulated HTTP 500 network errors.

```bash
# Generate negative test variations
tracecase mutate ./my_test/testcase.json -o ./my_test/mutations/

# Filter by strategy (inputs, actions, network, or all)
tracecase mutate ./my_test/testcase.json --strategy inputs --limit 5

# Replay any synthesized negative test
tracecase replay ./my_test/mutations/tc_order_mut_1_empty/testcase.json
```

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--output` | `-o` | Output directory for mutated test cases | `<testcase_dir>/mutations` |
| `--strategy` | `-s` | Strategy filter: `all`, `inputs`, `actions`, `network` | `all` |
| `--limit` | `-n` | Maximum number of variations to synthesize | `20` |

### `tracecase index`

Index directories of `testcase.json` recordings into a local SQLite database with full-text search (FTS5).

```bash
# Index recordings in a directory
tracecase index ./my_test/

# Specify a custom corpus database location
tracecase index ./tests/recordings/ --db ./corpus.db
```

### `tracecase search`

Search indexed test cases and actions using fast FTS5 BM25 relevance ranking and matched text snippets.

```bash
# Search for actions or flows mentioning "checkout" or "Payment"
tracecase search "Payment"

# Limit the number of search results
tracecase search "login" --limit 5
```

### `tracecase coverage`

Analyze test corpus coverage across tested domains, start URLs, network endpoints, and flag potential duplicate test flows.

```bash
tracecase coverage
tracecase coverage --db ./corpus.db
```

### `tracecase mcp`

Start the Model Context Protocol (MCP) server over stdio, exposing your indexed test corpus (`search_testcases`, `get_testcase`, `coverage_report`) to local LLM agents and IDE assistants.

```bash
tracecase mcp
tracecase mcp --db ./corpus.db
```

### `tracecase clean`

Wipe the local SQLite corpus database and/or recorded session artifacts when they are no longer needed:

```bash
# Wipe the local SQLite corpus database
tracecase clean --db

# Wipe both the local corpus database and all recorded test cases in ./recordings/
tracecase clean --all
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
- Multi-tab tracking (`page_id`) across pop-ups and new windows

---

## Project structure

```text
tracecase/
├── src/tracecase/
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
│   ├── mutation/          # Negative scenario generator and mutator
│   └── templates/         # Jinja2 report templates
└── tests/                 # Unit and integration tests
```

---

## Development

### Setup

```bash
git clone https://github.com/Ganesh1110/Tracecase.git
cd Tracecase
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

### Tests

```bash
pytest                 # All tests
pytest -m "not slow"   # Skip slow tests
pytest --cov=tracecase   # With coverage
```

### Linting and type checking

```bash
ruff check src/ tests/
ruff format src/ tests/
mypy src/tracecase --ignore-missing-imports
```

---

## Limitations

- Replay supports derived assertions, heuristic selector healing, and pixel-accurate visual regression diffing.
- Desktop web only; mobile apps and API-only testing are not covered.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
