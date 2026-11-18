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

Exit codes: `0` passed, `1` assertion failed, `2` infrastructure error.

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

- Replay supports derived assertions and heuristic selector healing; AI-driven self-healing and visual comparison are not included yet.
- Desktop web only; mobile apps and API-only testing are not covered.
- Visual comparison between runs is not included.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
