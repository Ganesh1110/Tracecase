# Tracecase

**Record once, test everywhere.**

Tracecase turns real browser interactions into structured, reusable QA assets. Open a URL,
perform a user flow once, and Tracecase writes a complete test case with screenshots, network
activity, console output, and JavaScript errors. Replay it, analyze it with AI, generate
Playwright automation, and run it in CI.

Tracecase comes in two forms:

- **Tracecase Studio** — a full web application for recording, analyzing, and managing tests.
- **Tracecase CLI** — a scriptable command-line tool for automation and CI pipelines.

[![CI](https://github.com/Ganesh1110/Tracecase/actions/workflows/ci.yml/badge.svg)](https://github.com/Ganesh1110/Tracecase/actions/workflows/ci.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

---

## Table of contents

- [Why Tracecase](#why-tracecase)
- [Feature highlights](#feature-highlights)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start: Tracecase Studio](#quick-start-tracecase-studio)
- [Quick start: CLI](#quick-start-cli)
- [Tracecase Studio modules](#tracecase-studio-modules)
- [AI configuration](#ai-configuration)
- [How recording works](#how-recording-works)
- [Output artifacts](#output-artifacts)
- [CLI reference](#cli-reference)
- [What gets captured](#what-gets-captured)
- [Project structure](#project-structure)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Documentation](#documentation)
- [License](#license)

---

## Why Tracecase

- **Zero manual documentation.** Perform a flow once and get a structured, replayable test case.
- **Visual evidence.** Every step includes a screenshot with the target element highlighted.
- **Full context.** Network requests, console logs, and JavaScript errors are attached to steps.
- **Three formats.** JSON for automation, Markdown for tickets, HTML for reviews and demos.
- **AI-assisted QA.** Suggested assertions, selector audits, coverage gaps, and risk analysis.
- **Automation ready.** Export standalone `pytest` + Playwright tests.
- **Cross-browser.** Record and replay with Chromium, Firefox, or WebKit.
- **Multi-tab support.** Captures and replays actions across new tabs, pop-ups, and
  `target="_blank"` windows.
- **Local and private.** Recordings stay on your machine. AI is optional and configurable.

Tracecase is built for:

- QA engineers documenting and automating manual test scenarios
- Developers reporting bugs with full reproduction context
- Teams building regression suites and test datasets for automation or AI tooling

---

## Feature highlights

### Record and document

- Capture clicks, inputs, selects, checkboxes, key presses, and navigation
- Screenshot per step with the target element outlined
- Element metadata: CSS selector, XPath, text, placeholder, attributes, bounding box
- Export to JSON, Markdown, and self-contained HTML

### Replay and validate

- Deterministic replay with Playwright
- Derived assertions from captured DOM, HTTP statuses, and console output
- Multi-tier self-healing locators: ID, name, CSS, text, and XPath fallbacks
- Pixel-accurate visual regression diffing
- HAR-based offline network mocking
- Multi-tab and pop-up synchronization

### AI QA intelligence

- Assertion recommendations from recorded evidence
- Selector fragility audit with resilient locator suggestions
- Corpus coverage insights and test-gap analysis
- Workflow risk audit
- Failure diagnosis with root cause and remediation advice
- Natural-language test assistant over your repository

### Automation and CI

- Standalone `pytest` + Playwright code generation
- Negative test generation: boundary values, injection probes, network faults
- Smart regression selection with explainable decisions
- CI quality gate with regression drift classification
- Markdown and JSON manifests for PRs and pipelines

### Corpus and integrations

- SQLite FTS5 full-text search with BM25 ranking
- Coverage analytics across domains, routes, and endpoints
- MCP server for Claude Desktop, Cursor, and other AI tools
- Storage inspection and artifact pruning

---

## Requirements

- Python 3.13 or newer
- [Playwright](https://playwright.dev/python/) and a Playwright browser
- Node.js 18+ only if you want to rebuild the Studio web UI

---

## Installation

### From PyPI

```bash
pip install tracecase
playwright install chromium
```

### From source

```bash
git clone https://github.com/Ganesh1110/Tracecase.git
cd Tracecase

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
playwright install chromium
```

### Verify the installation

```bash
tracecase check
tracecase version
```

---

## Quick start: Tracecase Studio

Studio is the recommended starting point. It provides a web UI for recording, replaying,
analyzing, and managing tests.

```bash
tracecase ui
```

This starts the Studio at `http://127.0.0.1:8000` and opens your browser automatically.

```bash
tracecase ui --port 8080        # use a different port
tracecase ui --no-browser       # do not open a browser automatically
tracecase ui --host 0.0.0.0     # allow access from other machines on the network
```

The web UI is prebuilt and included with the package. Rebuild it only if you change frontend
code:

```bash
cd frontend
npm install
npm run build
```

For a guided walkthrough, see the [QA Demo Guide](docs/DEMO_GUIDE.md).

---

## Quick start: CLI

Record a flow:

```bash
tracecase record https://example.com --output ./my_test
```

With options:

```bash
tracecase record https://example.com -o ./tests -n "Login Flow" -b firefox
```

A browser opens with a control panel. Click **Start**, perform your actions, then click **Stop**.
Tracecase saves the test case and closes the session.

---

## Tracecase Studio modules

| Module | What it does |
|--------|--------------|
| **Overview** | Workspace dashboard for tests, runs, and quality signals |
| **Projects** | Group test assets by product or team |
| **Test Cases** | Browse, inspect, and replay recorded tests |
| **Test Suites** | Organize tests into suites |
| **Browser Recorder** | Record a live flow into a test case |
| **Test Executions** | Run and monitor replay batches and browser matrices |
| **Execution History** | Review past runs and outcomes |
| **Reports** | Generate and download execution reports |
| **Visual Regression** | Compare screenshots and inspect visual diffs |
| **CI Quality Gate** | Review CI runs, gate status, and regression drift |
| **Smart Regression** | Select the highest-value tests within a time budget |
| **Autonomous Exploration** | Crawl a site, map a navigation graph, and plan requirements |
| **AI Test Assistant** | Chat with an assistant connected to your test repository |
| **Test Analysis** | Assertion suggestions, selector audit, coverage, and risk audit |
| **Negative Test Generation** | Generate edge-case and security-style variations |
| **Test Repository** | Full-text search across indexed tests |
| **Code Generator** | Produce ready-to-run pytest + Playwright scripts |
| **Network Inspector** | Inspect recorded network activity |
| **MCP Integrations** | Connect the corpus to AI coding tools |
| **Settings** | Configure browser defaults, AI provider, and theme |
| **Storage Management** | Inspect usage and prune artifacts |

---

## AI configuration

AI features are optional. Heuristic analysis, replay, search, code generation, and visual
diffing work fully offline.

Configure the provider in **Settings → AI Intelligence Provider**:

| Provider | Use case | Default endpoint | Default model |
|----------|----------|------------------|---------------|
| `openai` | Hosted or local OpenAI-compatible server (vLLM, LM Studio, llama.cpp) | `http://127.0.0.1:8000/v1` | `default` |
| `ollama` | Local Ollama server | `http://127.0.0.1:11434` | `llama3` |
| `null` | Deterministic heuristics only | — | — |

For an OpenAI-compatible endpoint, the base URL must include `/v1`, for example:

```text
Provider Type:  OpenAI / Compatible Endpoint (vLLM, LMStudio)
Model:          gemma-4-12b-it
Base URL:       https://chatbot.infospica.in/v1
API Key:        leave blank if the server does not require one
```

Verify the endpoint:

```bash
curl -s https://chatbot.infospica.in/v1/models
```

Privacy: heuristic analysis is local. When a hosted provider is enabled, test metadata such as
step descriptions, URLs, selectors, and error text is sent to that endpoint. Do not record
production secrets or customer data while a hosted AI provider is enabled.

---

## How recording works

1. Run `tracecase record <url> -o <output-dir>`, or use **Browser Recorder** in Studio.
2. A browser window opens with the Tracecase control panel.
3. Click **Start** in the panel.
4. Perform your test actions.
5. Click **Stop**. Tracecase saves the test case and closes the session.

The control panel tracks the number of captured steps and is excluded from every screenshot.

```text
[ Browser interaction ]
          |
          v
   tracecase record  ---> testcase.json + Markdown + HTML + screenshots
          |
          +---> replay    ---> assertions, self-healing, visual diff
          +---> codegen   ---> pytest + Playwright script
          +---> analyze   ---> risks, assertions, negative scenarios
          +---> mutate    ---> negative and edge-case test cases
          +---> index     ---> SQLite FTS5 corpus
          |         |
          |         +---> search / coverage / mcp
          +---> ci        ---> quality gate and regression selection
```

---

## Output artifacts

After a recording, the output directory contains:

```text
output/
├── screenshots/
│   ├── 001_click_login-button.png
│   ├── 002_input_email-field.png
│   └── ...
├── testcase.json    # Machine-readable test case
├── testcase.md      # Markdown documentation
└── testcase.html    # Self-contained visual report
```

The JSON model includes metadata, ordered steps, element details, screenshots, network requests,
console logs, and page errors.

---

## CLI reference

### Core commands

| Command | Description |
|---------|-------------|
| `tracecase record <url> -o <dir>` | Record a browser flow and generate a test case |
| `tracecase ui` | Launch Tracecase Studio |
| `tracecase check` | Verify dependencies and Playwright browsers |
| `tracecase version` | Print version and system information |

### `tracecase record`

Record browser actions and generate a test case.

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--output` | `-o` | Output directory for test case files | required |
| `--name` | `-n` | Test case name | generated from the URL |
| `--browser` | `-b` | Browser: `chromium`, `firefox`, `webkit` | `chromium` |
| `--headless` | | Run without a visible window | `false` |
| `--timeout` | `-t` | Action timeout in milliseconds | `30000` |

### `tracecase ui`

Launch the Tracecase Studio web application.

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--host` | `-h` | Bind host address | `127.0.0.1` |
| `--port` | `-p` | Bind port | `8000` |
| `--browser` / `--no-browser` | | Open a browser window automatically | `true` |

### Replay and validation

#### `tracecase replay`

Replay a recorded test case, evaluate assertions, and optionally heal selectors.

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

```bash
tracecase replay ./recordings/example/testcase.json --headed --heal
tracecase replay ./recordings/example/testcase.json --diff --diff-threshold 0.5 --diff-fail
```

#### `tracecase diff`

Compare two images pixel-by-pixel and optionally save a highlighted diff overlay.

```bash
tracecase diff baseline.png candidate.png
tracecase diff baseline.png candidate.png -o diff.png --threshold 0.5
```

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--output` | `-o` | Path to save the highlighted diff image | none |
| `--threshold` | `-t` | Tolerance percentage | `0.1` |

#### `tracecase export-har`

Export recorded network activity to a HAR file for offline replay.

```bash
tracecase export-har ./recordings/example/testcase.json -o ./recordings/example/network.har
tracecase replay ./recordings/example/testcase.json --from-har ./recordings/example/network.har
```

### Automation

#### `tracecase codegen`

Generate a standalone `pytest` + Playwright test module.

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--output` | `-o` | Output Python test file path | `test_<name>.py` |
| `--har` | | HAR file for offline route mocking | none |

```bash
tracecase codegen ./recordings/example/testcase.json
tracecase codegen ./recordings/example/testcase.json -o ./tests/test_checkout.py --har ./recordings/example/network.har
pytest ./tests/test_checkout.py -v
```

#### `tracecase mutate`

Synthesize negative test cases from a recorded flow.

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--output` | `-o` | Output directory for mutations | `<testcase_dir>/mutations` |
| `--strategy` | `-s` | `all`, `inputs`, `actions`, `network` | `all` |
| `--limit` | `-n` | Maximum number of variations | `20` |

Strategies include empty and boundary inputs, SQL injection and XSS probes, Unicode edge cases,
skipped or repeated actions, and simulated HTTP errors or latency.

```bash
tracecase mutate ./recordings/example/testcase.json -o ./mutations/
tracecase mutate ./recordings/example/testcase.json --strategy inputs --limit 5
```

### AI and intelligence

#### `tracecase analyze`

Analyze a recorded flow with heuristics and optional AI enrichment.

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--output` | `-o` | Directory to save `analysis.json` | test case directory |
| `--ai` | | Enable AI enrichment | `false` |
| `--provider` | | `null`, `ollama`, `openai` | `null` |
| `--base-url` | | Provider endpoint URL | per provider |
| `--model` | `-m` | Model name | per provider |

```bash
# Offline heuristics
tracecase analyze ./recordings/example/testcase.json

# Local Ollama
tracecase analyze ./recordings/example/testcase.json --ai

# OpenAI-compatible endpoint
tracecase analyze ./recordings/example/testcase.json --ai \
  --provider openai \
  --base-url https://chatbot.infospica.in/v1 \
  --model gemma-4-12b-it
```

### Corpus and integrations

#### `tracecase index`

Index a directory of `testcase.json` files into a local SQLite FTS5 database.

| Option | Description | Default |
|--------|-------------|---------|
| `--db` | Path to the SQLite corpus database | local default |
| `--clear` | Wipe the database before indexing | `false` |

```bash
tracecase index ./recordings/
tracecase index ./recordings/ --db ./corpus.db --clear
```

#### `tracecase search`

Search indexed tests and actions with BM25 ranking.

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--db` | | Path to the SQLite corpus database | local default |
| `--limit` | `-n` | Maximum number of results | `10` |

```bash
tracecase search "Payment"
tracecase search "login" --limit 5
```

#### `tracecase coverage`

Analyze coverage across domains, start URLs, and network endpoints.

```bash
tracecase coverage
tracecase coverage --db ./corpus.db
```

#### `tracecase mcp`

Start a stdio Model Context Protocol server exposing the corpus to AI tools.

```bash
tracecase mcp
tracecase mcp --db ./corpus.db
```

Tools exposed: `search_testcases`, `get_testcase`, and `coverage_report`.

Example Claude Desktop configuration:

```json
{
  "mcpServers": {
    "tracecase": {
      "command": "/path/to/.venv/bin/tracecase",
      "args": ["mcp", "--db", "/path/to/.tracecase/corpus.db"]
    }
  }
}
```

### Advanced regression and CI

These commands power the predictive regression and CI workflows. Run
`tracecase <command> --help` for the full option list.

| Command | Description |
|---------|-------------|
| `tracecase changes` | Analyze git changes, diffs, selectors, routes, and symbols |
| `tracecase map` | Map test cases to application routes, selectors, and files |
| `tracecase impact` | Identify tests impacted by code changes with confidence scores |
| `tracecase risk` | Score and rank regression risk per test |
| `tracecase select` | Select tests using change risk and execution constraints |
| `tracecase explain` | Explain why tests were selected, excluded, or flagged |
| `tracecase report` | Generate a Markdown report or CI/PR JSON manifest |
| `tracecase run` | Execute tests with intelligent regression selection |
| `tracecase ci` | Run the CI quality gate with regression selection and reporting |
| `tracecase ci-upload` | Upload an exported CI manifest to Tracecase Studio |
| `tracecase benchmark` | Benchmark sequential, parallel, and pooled execution |
| `tracecase storage` | Inspect storage usage and prune execution artifacts |

```bash
tracecase ci --base origin/main --budget 180s --gate standard
tracecase ci --base HEAD~1 --target HEAD --concurrency 4 --browser chromium
```

### Maintenance

#### `tracecase clean`

Wipe the local corpus database and/or recorded artifacts.

| Option | Description | Default |
|--------|-------------|---------|
| `--db` / `--no-db` | Clear the local SQLite corpus database | enabled |
| `--recordings` / `--no-recordings` | Remove the local `./recordings` directory | disabled |
| `--all` / `-a` | Remove both the database and recordings | disabled |
| `--db-path` | Path to a custom corpus database | local default |

```bash
tracecase clean --db
tracecase clean --all
```

Warning: `--all` deletes local recordings.

#### `tracecase storage`

Inspect disk usage and prune replay artifacts.

```bash
tracecase storage
tracecase storage --diffs --dry-run
tracecase storage --older-than 14 --keep-latest 10
tracecase storage --failures-only --max-mb 500
```

---

## What gets captured

- Clicks and double-clicks
- Text input, debounced
- Select, checkbox, and radio changes
- Special key presses such as Enter, Escape, and Tab
- CSS selector, XPath, tag name, text, placeholder, and bounding box per element
- One screenshot per step with the target element outlined
- Network requests and responses with headers, bodies, status, and timing
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
│   ├── ai/                # Heuristic and LLM flow analysis
│   ├── index/             # SQLite FTS5 corpus index and search
│   ├── mcp/               # Stdio Model Context Protocol server
│   ├── mutation/          # Negative scenario generator
│   ├── ui/                # FastAPI backend and prebuilt Studio frontend
│   └── templates/         # Jinja2 report templates
├── frontend/              # React + Vite source for Tracecase Studio
├── docs/                  # User guide and demo guide
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
pytest                   # all tests
pytest -m "not slow"     # skip slow tests
pytest --cov=tracecase   # with coverage
```

### Linting and type checking

```bash
ruff check src/ tests/
ruff format src/ tests/
mypy src/tracecase --ignore-missing-imports
```

### Frontend development

```bash
cd frontend
npm install
npm run dev      # Vite dev server on http://localhost:3000, proxies /api to port 8000
npm run build    # rebuild the bundled UI into src/tracecase/ui/static
```

Run `tracecase ui --no-browser` in another terminal while using the Vite dev server.

---

## Troubleshooting

### The Studio page is blank or shows "Static UI not found"

Rebuild the frontend:

```bash
cd frontend
npm install
npm run build
cd ..
tracecase ui
```

### Port 8000 is already in use

```bash
tracecase ui --port 8080
```

### Playwright browser fails to launch

```bash
playwright install --with-deps chromium
```

### AI returns heuristic results only

1. Confirm the endpoint is reachable with `curl`.
2. Confirm the provider is `openai` or `ollama` in **Settings**.
3. Confirm the base URL includes `/v1` for OpenAI-compatible servers.
4. Switch to `null` (heuristics only) if the network is restricted.

### A replay step cannot find an element

```bash
tracecase replay ./recordings/example/testcase.json --timeout 60000 --heal
```

For more, see the [Comprehensive User Guide](docs/USER_GUIDE.md).

---

## Limitations

- Desktop web only. Mobile apps and API-only testing are not covered.
- AI output is advisory. Assertions and test drafts require human review.
- Hosted AI providers receive test metadata; use heuristics-only mode for sensitive data.

---

## Documentation

- [Comprehensive User Guide](docs/USER_GUIDE.md)
- [QA Demo Guide](docs/DEMO_GUIDE.md)
- [Changelog](CHANGELOG.md)

---

## License

MIT License. See [LICENSE](LICENSE) for details.
