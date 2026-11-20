# Tracecase Demo Guide for QA Teams

This guide explains how to set up and demo Tracecase to a QA team lead. It is written to be
understandable even if you have only about two years of QA experience.

You do not need to know Python or AI to follow the demo. You only need to be able to run a few
commands in a terminal and use a web browser.

---

## Table of contents

1. [What Tracecase is](#1-what-tracecase-is)
2. [What you will show in the demo](#2-what-you-will-show-in-the-demo)
3. [Before the demo: setup checklist](#3-before-the-demo-setup-checklist)
4. [Start Tracecase Studio](#4-start-tracecase-studio)
5. [Connect the AI model (one-time setup)](#5-connect-the-ai-model-one-time-setup)
6. [The 20-minute demo script](#6-the-20-minute-demo-script)
7. [CLI cheat sheet for Q&A](#7-cli-cheat-sheet-for-qa)
8. [Key messages to leave with the team lead](#8-key-messages-to-leave-with-the-team-lead)
9. [Troubleshooting during the demo](#9-troubleshooting-during-the-demo)
10. [Reset and cleanup](#10-reset-and-cleanup)
11. [Plain-language glossary](#11-plain-language-glossary)

---

## 1. What Tracecase is

**Tracecase turns a manual browser test into reusable QA assets.**

You open a website, perform a user flow once (for example: log in, search, add to cart, check out),
and Tracecase records:

- Every click and every value typed
- A screenshot of each step
- The network calls made by the page
- Browser console messages and JavaScript errors

It then gives you:

- A readable test case (Markdown and HTML)
- A replayable test (re-run the same flow automatically)
- Optional AI suggestions for missing assertions and risks
- An exportable Playwright/pytest automation script

In one sentence for the team lead:

> "Record a manual flow once, then replay it, generate automation code, and let AI point out
> missing checks and risky steps."

---

## 2. What you will show in the demo

Recommended demo flow (about 20 minutes):

| # | Feature | What the team lead sees |
|---|---------|-------------------------|
| 1 | Overview dashboard | One place for tests, runs, and quality signals |
| 2 | Browser Recorder | A manual flow becomes a structured test case |
| 3 | Replay and self-healing | The same flow runs automatically; broken selectors can recover |
| 4 | Test Analysis (AI) | Suggested assertions, fragile selectors, coverage gaps, risk audit |
| 5 | AI Test Assistant | A chat assistant that understands your test repository |
| 6 | Autonomous Exploration | The tool crawls a site and maps a navigation graph |
| 7 | Requirements Planner | A plain-English user story is mapped to observed pages |
| 8 | Negative Test Generation | Automatic edge-case and security-style variations |
| 9 | Code Generator | A ready-to-run pytest + Playwright script |
| 10 | Smart Regression and CI gate | Which tests to run for a change, and pass/fail gate results |

You do not have to show all of them. Items 1 to 4 are the core story. Add 5 to 10 if time allows.

---

## 3. Before the demo: setup checklist

Do this at least one day before the demo, on the same machine you will present from.

### 3.1 Requirements

- Python 3.13 or newer
- Node.js 18 or newer (only needed if you must rebuild the web UI)
- A Chromium browser installed through Playwright
- Internet access to the AI endpoint (optional; heuristics work offline)

### 3.2 Install Tracecase from source

```bash
git clone https://github.com/Ganesh1110/Tracecase.git
cd Tracecase

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
playwright install chromium
```

### 3.3 Verify the installation

```bash
tracecase check
tracecase version
```

`tracecase check` should report that the required packages and browsers are available.

### 3.4 Confirm the web UI is present

The web UI is prebuilt and shipped inside the package. Confirm this file exists:

```bash
ls src/tracecase/ui/static/index.html
```

If the file is missing, build the UI once:

```bash
cd frontend
npm install
npm run build
cd ..
```

You do not need to rebuild the UI for normal use or after Python code changes.

### 3.5 Prepare a demo website

Use a stable public demo site so the demo does not depend on your product environment:

- `https://demo.playwright.dev/todomvc/` (recommended: simple, fast, no login)
- `https://example.com` (very simple, fewer actions)
- Your own staging site if network access is reliable

Avoid sites that require real credentials, CAPTCHA, or one-time passwords during a live demo.

---

## 4. Start Tracecase Studio

From the project folder, with the virtual environment activated:

```bash
tracecase ui
```

This starts the Studio at `http://127.0.0.1:8000` and opens your browser automatically.

Useful options:

```bash
tracecase ui --port 8080              # use a different port
tracecase ui --no-browser             # do not open the browser automatically
tracecase ui --host 0.0.0.0           # allow other machines to connect (demo over LAN)
```

Leave the terminal running during the demo. Press `Ctrl+C` to stop the server.

---

## 5. Connect the AI model (one-time setup)

Tracecase works without AI, but the AI features are more impressive. If your team already has an
OpenAI-compatible endpoint, configure it here. Otherwise, skip to the offline fallback.

### 5.1 Configure in the UI

1. Open Studio.
2. Click **Settings** in the left sidebar.
3. Under **AI Intelligence Provider**, set:

| Field | Value |
|-------|-------|
| Provider Type | `OpenAI / Compatible Endpoint (vLLM, LMStudio)` |
| Model Identifier | `<your-model-name>` |
| API Endpoint Base URL | `https://<your-llm-host>/v1` |
| API Key | `<your-api-key, or blank if not required>` |

4. Click **Save Settings**.

Get the exact endpoint and model name from your platform or infrastructure team. Do not commit
internal endpoints or keys to the repository.

### 5.2 Verify the endpoint before the demo

```bash
curl -s https://<your-llm-host>/v1/models
```

You should see your model in the response.

Quick chat test:

```bash
curl -s https://<your-llm-host>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"<your-model-name>","messages":[{"role":"user","content":"Say OK"}]}'
```

### 5.3 Offline fallback

If the endpoint is unreachable during the demo, change **Provider Type** to:

> `Deterministic Heuristics Only (Offline)`

All heuristic features still work. Only the LLM-enhanced summaries and chat will be limited.

### 5.4 Privacy note

Heuristic analysis runs fully on your machine. When the hosted AI provider is enabled, test
metadata (step descriptions, URLs, selectors, error text) is sent to that endpoint. Do not record
real customer data or production secrets during a demo.

---

## 6. The 20-minute demo script

Follow this order. Each section includes what to click and what to say.

### Step 1: Overview (2 minutes)

1. Open `http://127.0.0.1:8000`.
2. Land on **Overview**.

**Say:**
> "This is the workspace dashboard. It gives the team one place to see recorded tests, recent
> executions, and quality signals instead of scattered spreadsheets and manual notes."

Point out the left sidebar groups: test assets, execution, intelligence, and settings.

---

### Step 2: Record a manual flow (5 minutes)

1. Click **Browser Recorder** in the sidebar.
2. Fill in:
   - **Target Application URL:** `https://demo.playwright.dev/todomvc/`
   - **Test Case Name:** `Demo - Add and Complete Todo`
   - **Browser Engine:** `Chromium`
   - **Window Mode:** `Headed (Interactive Window)`
3. Click **Start Recording**.
4. A browser window opens. In that window:
   - Type `Buy milk` in the input and press Enter.
   - Type `Call QA lead` and press Enter.
   - Click the checkbox next to `Buy milk`.
5. Return to the Studio tab and click **Stop & Save Test Case**.

**Say:**
> "I performed the flow once, exactly like a manual tester would. Tracecase captured each action,
> a screenshot, the network calls, and any console errors."

6. Open **Test Cases** and select the new test.
7. On the test detail page, show:
   - The ordered steps
   - Screenshots for each step
   - Network and console context
   - The generated Markdown and HTML report options

**Key point:** the QA team does not have to write the steps manually.

---

### Step 3: Replay and self-healing (3 minutes)

1. On the test detail page, click **Execute Replay**.
2. Choose the browser and enable **self-healing** if the option is shown.
3. Run the replay.
4. Open **Test Executions** to show the live result.
5. Point out any step marked as healed.

**Say:**
> "Replay runs the recorded flow automatically. If a developer changes a CSS selector, the
> self-healing engine tries alternative locators such as ID, name, text, or XPath, so small UI
> refactors do not automatically break the test."

If time allows, show the same result from the terminal:

```bash
tracecase replay ./recordings/<your_test_folder>/testcase.json --headed --heal
```

---

### Step 4: AI Test Analysis (4 minutes)

1. Click **Test Analysis** in the sidebar.
2. Select the demo test case at the top.
3. Show the four tabs:

   **a. Automatic Assertion Generation**
   - Click **Suggest Assertions**.
   - Point out the recommended URL, visibility, text, and status assertions.
   - Click **Attach All** to add them to the test.

   **b. Selector Intelligence & Healing**
   - Click **Audit Selectors**.
   - Show fragile selectors (dynamic IDs, hashed classes, absolute XPaths) and the recommended
     resilient locator.

   **c. Corpus Coverage Intelligence**
   - Click **Refresh Insights**.
   - Show coverage score, risk level, unique routes, and assertion density.

   **d. Workflow Risk Analysis**
   - Click **Run Risk Audit**.
   - Show the risk score, summary, and identified risks.

**Say:**
> "The AI does not replace the tester. It reviews the evidence the tester already captured and
> points out missing checks, fragile locators, and risky steps. The tester still approves every
> suggestion."

**Important credibility point:** suggested assertions are attached as drafts and require review.
The tool reports whether a result came from heuristics or the LLM, so it never pretends a
heuristic result was AI-generated.

---

### Step 5: AI Test Assistant (2 minutes)

1. Click **AI Test Assistant** in the sidebar.
2. Ask one of the sample questions, for example:
   - "Suggest boundary and negative assertions for login inputs."
   - "What test coverage gaps exist across my recorded flows?"
3. Send the message and show the reply.

**Say:**
> "This is a chat interface over the same test repository. A QA engineer can ask questions in
> plain English instead of searching through folders."

If the hosted model is unavailable, skip this step and continue with heuristics.

---

### Step 6: Autonomous Exploration (4 minutes)

1. Click **Autonomous Exploration** in the sidebar.
2. In the exploration form, enter a safe start URL, for example
   `https://demo.playwright.dev/todomvc/`.
3. Set a small depth and page limit (for example depth `2`, pages `10`).
4. Click **Start Exploring**.
5. When finished, show the discovered navigation graph.
6. Click **Synthesize Journeys** to generate draft test journeys from the graph.
7. Open the **Requirements Planner** section.
8. Use a sample requirement:
   > "As a user, I want to add a todo and mark it complete."
9. Click **Map & Plan Test**.
10. Show the coverage score, covered concepts, missing evidence, and the synthesized draft.
11. Open the draft in the review queue and show the provenance evidence attached to each step.

**Say:**
> "Tracecase can explore a site on its own and build a map of pages and actions. The requirements
> planner then checks whether a user story is actually supported by observed evidence. If evidence
> is missing, it says so instead of inventing steps."

Safety note to mention: exploration is restricted to the target origin, and destructive actions
such as payment, delete, or publish are flagged and skipped.

---

### Step 7: Negative Test Generation (2 minutes)

1. Click **Negative Test Generation** in the sidebar.
2. Select the demo test case.
3. Click **Synthesize Negative Tests**.
4. Show the generated variations:
   - Empty input
   - Boundary-length input
   - SQL injection and XSS style payloads
   - Simulated HTTP 500 or timeout

**Say:**
> "Instead of manually writing dozens of negative cases, the tool derives them from the happy-path
> recording. Each generated case can be replayed like any other test."

---

### Step 8: Code Generator (2 minutes)

1. Click **Code Generator** in the sidebar.
2. Select the demo test case.
3. Show the generated pytest + Playwright code.
4. Click **Copy Pytest Script**.

**Say:**
> "When the team is ready to move a manual or recorded test into automation, this gives them a
> standard pytest and Playwright script. They can review it, commit it, and run it in CI."

Run it from the terminal if time allows:

```bash
tracecase codegen ./recordings/<your_test_folder>/testcase.json
pytest ./recordings/<your_test_folder>/test_*.py -v
```

---

### Step 9: Smart Regression and CI gate (3 minutes)

1. Click **Smart Regression** in the sidebar.
2. Choose a strategy, for example **Time Budget** with `120s`.
3. Click **Compute Intelligent Regression Set**.
4. Show selected tests, estimated duration, risk coverage, and the reasons for each decision.
5. Open **CI Quality Gate** and show run history, gate status, and regression drift.

**Say:**
> "For every change, the team gets a prioritized set of tests to run within a time budget, with
> an explanation for why each test was selected. The CI gate then blocks new regressions while
> tolerating known pre-existing failures."

---

### Step 10: Test Repository search (1 minute)

1. Click **Test Repository** in the sidebar.
2. Search for a keyword such as `todo` or a selector such as `input`.
3. Show the matched test cases and highlighted snippets.

**Say:**
> "All recorded tests are indexed locally with full-text search, so finding an existing test is
> fast even when the suite grows."

---

## 7. CLI cheat sheet for Q&A

The Studio covers the main workflows. These commands are useful if the team lead asks about
scripting or CI.

```bash
# Record a flow
tracecase record https://example.com -o ./recordings/example -n "Example Flow"

# Replay with self-healing and assertions
tracecase replay ./recordings/example/testcase.json --headed --heal

# Visual comparison of two screenshots
tracecase diff baseline.png candidate.png -o diff.png --threshold 0.5

# Export recorded network traffic for offline replay
tracecase export-har ./recordings/example/testcase.json -o ./recordings/example/network.har

# Generate a pytest + Playwright test
tracecase codegen ./recordings/example/testcase.json

# Analyze a flow with heuristics only (offline)
tracecase analyze ./recordings/example/testcase.json

# Analyze with an OpenAI-compatible endpoint
tracecase analyze ./recordings/example/testcase.json --ai \
  --provider openai \
  --base-url https://<your-llm-host>/v1 \
  --model <your-model-name>

# Generate negative tests
tracecase mutate ./recordings/example/testcase.json -o ./mutations/

# Index recordings for search and coverage
tracecase index ./recordings/

# Search the indexed corpus
tracecase search "checkout"

# Coverage summary
tracecase coverage

# Start the MCP server for AI coding assistants
tracecase mcp
```

---

## 8. Key messages to leave with the team lead

Use these points in the closing summary:

1. **Record once, reuse many times.**
   A manual flow becomes a test case, a replayable test, and automation code.

2. **Evidence first.**
   Steps, screenshots, network calls, and console errors are captured together, so failures are
   easier to diagnose.

3. **AI assists, it does not invent.**
   Suggestions require human review. The tool clearly reports whether output came from
   heuristics or an LLM.

4. **Works offline.**
   Heuristic analysis, replay, search, and code generation do not need an LLM or internet.

5. **Fits existing workflows.**
   Exports standard pytest + Playwright code and supports CI quality gates.

6. **Local and private by default.**
   Recordings and the database stay on the machine. Only the optional hosted AI provider sends
   test metadata externally.

7. **Low learning curve.**
   A QA engineer can start with the Recorder, then add replay, analysis, and code generation as
   the team matures.

Suggested closing line:

> "Tracecase gives us a single pipeline from manual exploration to automated regression, with
> evidence at every step and AI as an assistant rather than a replacement."

---

## 9. Troubleshooting during the demo

### The Studio page is blank or shows "Static UI not found"

The prebuilt UI is missing. Rebuild it:

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

Then open `http://127.0.0.1:8080`.

### The browser does not open automatically

Open `http://127.0.0.1:8000` manually, or start with:

```bash
tracecase ui --no-browser
```

### Recording does not start or the browser fails to launch

```bash
playwright install --with-deps chromium
```

On macOS, `playwright install chromium` is usually enough.

### AI features return heuristic results only

1. Confirm the endpoint is reachable:

   ```bash
   curl -s https://<your-llm-host>/v1/models
   ```

2. In **Settings**, confirm:
   - Provider Type is `OpenAI / Compatible Endpoint (vLLM, LMStudio)`
   - Base URL ends with `/v1`
   - Model matches the value provided by your platform team

3. If the network is restricted, switch to `Deterministic Heuristics Only (Offline)` and continue
   the demo. All non-chat features still work.

### A replay step cannot find an element

- Increase the timeout:

  ```bash
  tracecase replay ./recordings/<test>/testcase.json --timeout 60000
  ```

- Enable self-healing with `--heal`.

### The demo site is slow or unreachable

Switch to `https://demo.playwright.dev/todomvc/` or `https://example.com`. Avoid demoing against
a flaky staging environment.

---

## 10. Reset and cleanup

After the demo, you can remove generated artifacts.

Warning: the following command deletes local recordings and the local corpus database.

```bash
tracecase clean --all
```

To remove only the search database:

```bash
tracecase clean --db
```

The Studio workspace database lives in `.tracecase/studio.db`. Delete that file only if you want a
completely fresh Studio state.

---

## 11. Plain-language glossary

| Term | Simple meaning |
|------|----------------|
| **Test case** | The recorded steps of one user flow |
| **Replay** | Running the recorded steps again automatically |
| **Selector** | The address the tool uses to find an element on the page, such as `#login-button` |
| **Self-healing** | Trying other ways to find an element when the original selector no longer works |
| **Assertion** | A check that proves the result is correct, such as "the success banner is visible" |
| **Heuristic** | A rule-based check that works without AI |
| **LLM** | Large Language Model, the AI model used for summaries and suggestions |
| **OpenAI-compatible endpoint** | A server that accepts the same request format as OpenAI's chat API |
| **HAR** | A standard file that records network requests and responses |
| **FTS5** | SQLite's full-text search feature, used for fast test search |
| **MCP** | Model Context Protocol, a way to expose test data to AI coding tools |
| **Regression** | A previously working feature that breaks after a change |
| **CI gate** | An automated pass/fail check in the CI pipeline |

---

## Quick reference card

```text
Start Studio:      tracecase ui
Studio URL:        http://127.0.0.1:8000
Demo site:         https://demo.playwright.dev/todomvc/
AI provider:       OpenAI / Compatible Endpoint
AI base URL:       https://<your-llm-host>/v1
AI model:          <your-model-name>
Offline mode:      Deterministic Heuristics Only
Docs:              docs/USER_GUIDE.md and README.md
```

For deeper details on every feature, see [USER_GUIDE.md](USER_GUIDE.md).
