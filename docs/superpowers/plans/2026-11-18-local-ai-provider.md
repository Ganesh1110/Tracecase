# Local AI Provider and Analyze Implementation Plan (Phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local-first AI and heuristic analysis layer to QA Auto (`qa_auto.ai`), providing flow summaries, risk flagging, assertion suggestions, negative test scenarios, and a new `qa_auto analyze` CLI command outputting `analysis.json`.

**Architecture:** Add `qa_auto.ai` package with provider abstractions (`NullProvider`, `OllamaProvider`, `OpenAICompatProvider`), heuristic analyzers, prompt management, and `AnalysisResult` serialization.

**Tech Stack:** Python 3.13, Pydantic v2, Typer, Rich, Jinja2, pytest.

## Global Constraints

- Python `>=3.13`, Ruff `target-version = "py313"`, line length 100.
- Offline by default: AI is strictly opt-in (`--ai` or explicit provider).
- `NullProvider` is always available without network or background daemon.
- `testcase.json` schema is NEVER mutated; output goes to `analysis.json`.
- AI assertions must carry `source="ai"`, `confidence: float`, and `enforced=False`.
- Tests must use local mock HTTP endpoints (`127.0.0.1`), never external APIs.
- AI tests needing real models marked `@pytest.mark.llm` (skipped by default).
- Ruff rules: `E`, `F`, `I`, `UP`, `B`, `SIM`. Type annotations required (`disallow_untyped_defs`).

---

### Task 1: AI models and provider protocol

**Files:**
- Create: `src/qa_auto/ai/__init__.py`
- Create: `src/qa_auto/ai/models.py`
- Create: `src/qa_auto/ai/provider.py`
- Test: `tests/test_ai_provider.py`

**Interfaces:**
- Produces:
  - `Message(role, content)`, `Annotation`, `AnalysisResult`.
  - Protocol `Provider`: `name: str`, `chat(messages, schema=None) -> dict[str, Any]`.
  - `NullProvider`, `OllamaProvider(base_url, model)`, `OpenAICompatProvider(base_url, model, api_key)`.
  - Factory: `get_provider(name, base_url=None, model=None) -> Provider`.

- [ ] **Step 1: Write the failing provider tests**

Create `tests/test_ai_provider.py`:

```python
"""Tests for AI provider abstraction and implementations."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from qa_auto.ai.models import Message
from qa_auto.ai.provider import (
    NullProvider,
    OllamaProvider,
    OpenAICompatProvider,
    get_provider,
)


class _MockLLMHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        content_len = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(content_len).decode("utf-8")) if content_len else {}

        if self.path == "/api/chat":  # Ollama endpoint
            resp = {
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"summary": "Ollama response"}),
                }
            }
            self._send(200, resp)
        elif self.path == "/v1/chat/completions":  # OpenAI compatible
            resp = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({"summary": "OpenAI response"}),
                        }
                    }
                ]
            }
            self._send(200, resp)
        else:
            self.send_response(404)
            self.end_headers()

    def _send(self, status: int, data: dict) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def mock_llm_server() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockLLMHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_null_provider_returns_empty_content() -> None:
    provider = NullProvider()
    assert provider.name == "null"
    resp = await provider.chat([Message(role="user", content="hello")])
    assert resp == {}


@pytest.mark.asyncio
async def test_ollama_provider_chats(mock_llm_server: str) -> None:
    provider = OllamaProvider(base_url=mock_llm_server, model="llama3")
    resp = await provider.chat([Message(role="user", content="hello")])
    assert resp == {"summary": "Ollama response"}


@pytest.mark.asyncio
async def test_openai_compat_provider_chats(mock_llm_server: str) -> None:
    provider = OpenAICompatProvider(base_url=f"{mock_llm_server}/v1", model="gpt-4o")
    resp = await provider.chat([Message(role="user", content="hello")])
    assert resp == {"summary": "OpenAI response"}


def test_get_provider_factory() -> None:
    assert isinstance(get_provider("null"), NullProvider)
    assert isinstance(get_provider("ollama"), OllamaProvider)
    assert isinstance(get_provider("openai"), OpenAICompatProvider)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ai_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'qa_auto.ai'`.

- [ ] **Step 3: Implement AI models and provider**

Create `src/qa_auto/ai/models.py`:

```python
"""Data models for AI-assisted QA analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field

from qa_auto.replay.models import Assertion


class Message(BaseModel):
    """Chat message for LLM interactions."""

    role: Literal["system", "user", "assistant"]
    content: str


class Annotation(BaseModel):
    """An analytical insight, warning, or risk note."""

    type: Literal["assertion_suggestion", "risk", "test_idea", "bug_report", "summary"]
    message: str
    severity: Literal["info", "warning", "error"] = "info"
    step_number: int | None = None
    provider: str | None = None
    model: str | None = None


class AnalysisResult(BaseModel):
    """Complete analysis artifact stored in analysis.json."""

    testcase_id: str
    testcase_name: str
    generated_at: datetime = Field(default_factory=datetime.now)
    provider: str
    model: str | None = None
    summary: str
    annotations: list[Annotation] = Field(default_factory=list)
    suggested_assertions: list[Assertion] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    negative_scenarios: list[str] = Field(default_factory=list)
```

Create `src/qa_auto/ai/provider.py`:

```python
"""AI provider protocol and implementations."""

from __future__ import annotations

import asyncio
import json
import urllib.request
import urllib.error
from typing import Any, Protocol, runtime_checkable

from qa_auto.ai.models import Message


@runtime_checkable
class Provider(Protocol):
    """Protocol for AI language model providers."""

    name: str
    model: str | None

    async def chat(
        self,
        messages: list[Message],
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send chat messages and return parsed JSON payload."""
        ...


class NullProvider:
    """Offline heuristic provider returning empty structures."""

    name = "null"
    model = None

    async def chat(
        self,
        messages: list[Message],
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {}


class OllamaProvider:
    """Provider connecting to local Ollama server."""

    name = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "llama3") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def _sync_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/api/chat"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data.get("message", {}).get("content", "{}")
                if isinstance(content, str):
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return {"content": content}
                return content if isinstance(content, dict) else {}
        except Exception:
            return {}

    async def chat(
        self,
        messages: list[Message],
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
        }
        if schema:
            payload["format"] = "json"
        return await asyncio.to_thread(self._sync_request, payload)


class OpenAICompatProvider:
    """Provider connecting to OpenAI-compatible inference servers."""

    name = "openai"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000/v1",
        model: str = "default",
        api_key: str = "none",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def _sync_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "{}")
                    if isinstance(content, str):
                        try:
                            return json.loads(content)
                        except json.JSONDecodeError:
                            return {"content": content}
                    return content if isinstance(content, dict) else {}
                return {}
        except Exception:
            return {}

    async def chat(
        self,
        messages: list[Message],
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        return await asyncio.to_thread(self._sync_request, payload)


def get_provider(
    name: str = "null",
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> Provider:
    """Factory creating an AI provider by name."""
    name_clean = name.lower().strip()
    if name_clean == "ollama":
        url = base_url or "http://127.0.0.1:11434"
        mdl = model or "llama3"
        return OllamaProvider(base_url=url, model=mdl)
    elif name_clean in {"openai", "vllm", "lmstudio"}:
        url = base_url or "http://127.0.0.1:8000/v1"
        mdl = model or "default"
        key = api_key or "none"
        return OpenAICompatProvider(base_url=url, model=mdl, api_key=key)
    return NullProvider()
```

- [ ] **Step 4: Run provider tests to verify they pass**

Run: `pytest tests/test_ai_provider.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run lint and types**

Run: `ruff check src/qa_auto/ai tests/test_ai_provider.py && mypy src/qa_auto/ai --ignore-missing-imports`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/qa_auto/ai/ tests/test_ai_provider.py
git commit -m "Add AI models and provider abstractions"
```

---

### Task 2: Heuristic and AI Analyst

**Files:**
- Create: `src/qa_auto/ai/analyst.py`
- Test: `tests/test_ai_analyst.py`

**Interfaces:**
- Consumes: `TestCase`, `Provider`, `AnalysisResult`.
- Produces:
  - `analyze_testcase(testcase: TestCase, provider: Provider) -> AnalysisResult`
  - `write_analysis_result(result: AnalysisResult, output_dir: Path) -> Path`

- [ ] **Step 1: Write failing analyst tests**

Create `tests/test_ai_analyst.py`:

```python
"""Tests for testcase analysis (heuristics and AI enrichment)."""

from datetime import datetime
from pathlib import Path

import pytest

from qa_auto.ai.analyst import analyze_testcase, write_analysis_result
from qa_auto.ai.models import Message
from qa_auto.ai.provider import NullProvider
from qa_auto.models import ElementInfo, NetworkRequest, PageError, Step, TestCase


def _step(number: int, action: str = "click", value: str | None = None) -> Step:
    return Step(
        number=number,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type=action,
        element=ElementInfo(
            selector="#btn",
            xpath="//*[@id='btn']",
            tag_name="button",
            text="Save",
            attributes={},
            bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
        ),
        input_value=value,
        description_short=f"Step {number}",
        description_detailed=f"Step {number}",
    )


def _testcase(steps: list[Step], errors: list[PageError] | None = None) -> TestCase:
    return TestCase(
        id="tc_analyst",
        name="Profile Update",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url="https://example.com/profile",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=steps,
        console_logs=[],
        network_requests=[],
        page_errors=errors or [],
        total_duration=1.0,
        total_steps=len(steps),
    )


@pytest.mark.asyncio
async def test_heuristic_detects_empty_inputs_and_errors() -> None:
    steps = [
        _step(1, action="input", value=""),  # empty input risk
        _step(2, action="click"),
    ]
    err = PageError(message="TypeError: cannot read property", timestamp=datetime(2025, 1, 1, 12, 0, 0))
    tc = _testcase(steps, errors=[err])

    result = await analyze_testcase(tc, provider=NullProvider())

    assert result.testcase_id == "tc_analyst"
    assert "Profile Update" in result.summary
    assert any("empty input" in a.message.lower() for a in result.annotations)
    assert any("TypeError" in r for r in result.risks)


@pytest.mark.asyncio
async def test_ai_enrichment_integrates_suggestions() -> None:
    class FakeAIProvider:
        name = "mock_ai"
        model = "test-model"

        async def chat(self, messages: list[Message], schema=None) -> dict:
            return {
                "summary": "Enriched test summary",
                "risks": ["Potential SQL injection"],
                "negative_scenarios": ["Submit without authentication token"],
                "suggested_assertions": [
                    {
                        "kind": "visible",
                        "target": ".alert-success",
                        "expected": True,
                        "step_number": 1,
                        "confidence": 0.9,
                    }
                ],
            }

    tc = _testcase([_step(1)])
    result = await analyze_testcase(tc, provider=FakeAIProvider())

    assert result.summary == "Enriched test summary"
    assert "Potential SQL injection" in result.risks
    assert len(result.suggested_assertions) == 1
    assert result.suggested_assertions[0].source == "ai"
    assert result.suggested_assertions[0].enforced is False


def test_write_analysis_result(temp_dir: Path) -> None:
    tc = _testcase([_step(1)])
    result = analyze_testcase(tc, provider=NullProvider())
    import asyncio
    res = asyncio.run(result)
    path = write_analysis_result(res, temp_dir)

    assert path.exists()
    assert path.name == "analysis.json"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ai_analyst.py -v`
Expected: FAIL with `ImportError: cannot import name 'analyze_testcase'`.

- [ ] **Step 3: Implement `src/qa_auto/ai/analyst.py`**

Create `src/qa_auto/ai/analyst.py`:

```python
"""Analysis engine: heuristics first, optional AI enrichment."""

from __future__ import annotations

import json
from pathlib import Path

from qa_auto.ai.models import AnalysisResult, Annotation, Message
from qa_auto.ai.provider import Provider
from qa_auto.models import TestCase
from qa_auto.replay.models import Assertion


async def analyze_testcase(testcase: TestCase, provider: Provider) -> AnalysisResult:
    """Analyze a test case with deterministic heuristics and optional AI."""
    annotations: list[Annotation] = []
    risks: list[str] = []
    negative_scenarios: list[str] = []
    suggested_assertions: list[Assertion] = []

    # 1. Heuristic: Uncaught page errors
    for err in testcase.page_errors:
        risks.append(f"Recorded page error: {err.message}")
        annotations.append(
            Annotation(
                type="bug_report",
                message=f"Page error observed: {err.message}",
                severity="error",
                provider="heuristics",
            )
        )

    # 2. Heuristic: Empty input actions
    for step in testcase.steps:
        if step.action_type == "input" and not step.input_value:
            msg = f"Step {step.number} submitted an empty input value."
            annotations.append(
                Annotation(
                    type="risk",
                    message=msg,
                    severity="warning",
                    step_number=step.number,
                    provider="heuristics",
                )
            )

    summary = f"Recorded {len(testcase.steps)} steps for '{testcase.name}' starting at {testcase.start_url}."

    # 3. Optional AI enrichment
    if provider.name != "null":
        prompt = (
            f"Analyze this UI test flow:\n"
            f"Name: {testcase.name}\n"
            f"URL: {testcase.start_url}\n"
            f"Steps: {[s.description_short for s in testcase.steps]}\n"
            f"Errors: {[e.message for e in testcase.page_errors]}\n\n"
            "Respond in JSON with keys: summary, risks (list of str), negative_scenarios (list of str), "
            "suggested_assertions (list of {kind, target, expected, step_number, confidence})."
        )
        ai_resp = await provider.chat([Message(role="user", content=prompt)], schema={})
        if ai_resp:
            if "summary" in ai_resp:
                summary = str(ai_resp["summary"])
            if "risks" in ai_resp and isinstance(ai_resp["risks"], list):
                risks.extend(str(r) for r in ai_resp["risks"])
            if "negative_scenarios" in ai_resp and isinstance(ai_resp["negative_scenarios"], list):
                negative_scenarios.extend(str(s) for s in ai_resp["negative_scenarios"])
            if "suggested_assertions" in ai_resp and isinstance(ai_resp["suggested_assertions"], list):
                for item in ai_resp["suggested_assertions"]:
                    if isinstance(item, dict):
                        suggested_assertions.append(
                            Assertion(
                                kind=item.get("kind", "visible"),
                                target=item.get("target"),
                                expected=item.get("expected"),
                                step_number=item.get("step_number"),
                                source="ai",
                                confidence=float(item.get("confidence", 0.8)),
                                enforced=False,
                            )
                        )

    return AnalysisResult(
        testcase_id=testcase.id,
        testcase_name=testcase.name,
        provider=provider.name,
        model=provider.model,
        summary=summary,
        annotations=annotations,
        suggested_assertions=suggested_assertions,
        risks=risks,
        negative_scenarios=negative_scenarios,
    )


def write_analysis_result(result: AnalysisResult, output_dir: Path) -> Path:
    """Save analysis report to analysis.json in target directory."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "analysis.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path
```

- [ ] **Step 4: Run analyst tests to verify they pass**

Run: `pytest tests/test_ai_analyst.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run lint and types**

Run: `ruff check src/qa_auto/ai tests/test_ai_analyst.py && mypy src/qa_auto/ai --ignore-missing-imports`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/qa_auto/ai/ tests/test_ai_analyst.py
git commit -m "Implement heuristic and AI analyst"
```

---

### Task 3: CLI `analyze` command integration

**Files:**
- Modify: `src/qa_auto/cli.py`
- Test: `tests/test_cli_analyze.py`

**Interfaces:**
- CLI command: `qa_auto analyze <testcase> [--ai] [--provider <name>] [--base-url <url>] [--model <model>] [-o <output>]`
- Outputs Rich panels with summary, risks, negative test scenarios, and assertion suggestions. Writes `analysis.json`.

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli_analyze.py`:

```python
"""Tests for CLI analyze command."""

from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from qa_auto.cli import app
from qa_auto.models import TestCase

runner = CliRunner()


def _write_testcase(path: Path) -> Path:
    testcase = TestCase(
        id="tc_cli_analyze",
        name="Cart Checkout",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url="https://example.com/cart",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=[],
        console_logs=[],
        network_requests=[],
        page_errors=[],
        total_duration=0.0,
        total_steps=0,
    )
    path.write_text(testcase.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_analyze_help() -> None:
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "testcase" in result.stdout.lower()
    assert "--ai" in result.stdout
    assert "--provider" in result.stdout


def test_analyze_runs_heuristics_default(temp_dir: Path) -> None:
    tc_path = _write_testcase(temp_dir / "testcase.json")
    result = runner.invoke(app, ["analyze", str(tc_path)])

    assert result.exit_code == 0
    assert "Analysis Results" in result.stdout
    assert (temp_dir / "analysis.json").exists()


def test_analyze_missing_file_exits_2(temp_dir: Path) -> None:
    result = runner.invoke(app, ["analyze", str(temp_dir / "missing.json")])
    assert result.exit_code == 2
```

- [ ] **Step 2: Run CLI tests to verify they fail**

Run: `pytest tests/test_cli_analyze.py -v`
Expected: FAIL because `analyze` is not registered.

- [ ] **Step 3: Register `analyze` command in `src/qa_auto/cli.py`**

Add `analyze` command to `src/qa_auto/cli.py`:

```python
@app.command()
def analyze(
    testcase: Annotated[
        Path,
        typer.Argument(help="Path to a testcase.json file"),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Directory to save analysis.json (defaults to test case directory)",
        ),
    ] = None,
    ai: Annotated[
        bool,
        typer.Option("--ai", help="Enable local AI model enrichment"),
    ] = False,
    provider: Annotated[
        str,
        typer.Option(
            "--provider",
            help="AI provider to use (null, ollama, openai)",
        ),
    ] = "null",
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="Base URL for the AI provider endpoint"),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Model name (e.g. llama3, qwen2.5)"),
    ] = None,
) -> None:
    """Analyze recorded user flow with heuristics and optional local AI."""
    from qa_auto.ai.analyst import analyze_testcase, write_analysis_result
    from qa_auto.ai.provider import get_provider
    from qa_auto.models import TestCase as RecordedTestCase

    if not testcase.exists():
        console.print(f"[red]✗ Test case not found:[/red] {testcase}")
        raise typer.Exit(2)

    try:
        case = RecordedTestCase.model_validate_json(testcase.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[red]✗ Invalid test case:[/red] {exc}")
        raise typer.Exit(2) from None

    chosen_provider = provider
    if ai and chosen_provider == "null":
        chosen_provider = "ollama"

    prov = get_provider(chosen_provider, base_url=base_url, model=model)
    console.print(f"[bold cyan]Analyzing '{case.name}' with provider: {prov.name}[/bold cyan]")

    result = asyncio.run(analyze_testcase(case, prov))

    # Print summary panel
    table = Table(title="Analysis Results")
    table.add_column("Category", style="cyan")
    table.add_column("Details")
    table.add_row("Summary", result.summary)
    table.add_row("Risks Identified", str(len(result.risks)))
    table.add_row("Suggested Assertions", str(len(result.suggested_assertions)))
    table.add_row("Negative Scenarios", str(len(result.negative_scenarios)))
    console.print(table)

    if result.risks:
        console.print("\n[bold yellow]Identified Risks:[/bold yellow]")
        for risk in result.risks:
            console.print(f"  • {risk}")

    if result.negative_scenarios:
        console.print("\n[bold magenta]Negative Test Scenarios to consider:[/bold magenta]")
        for scenario in result.negative_scenarios:
            console.print(f"  • {scenario}")

    out_dir = output or testcase.parent
    path = write_analysis_result(result, out_dir)
    console.print(f"\n[green]✓[/green] Analysis report saved to: {path}")
```

- [ ] **Step 4: Run CLI tests to verify they pass**

Run: `pytest tests/test_cli_analyze.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run lint and types**

Run: `ruff check src/qa_auto/ai src/qa_auto/cli.py tests/test_cli_analyze.py && mypy src/qa_auto --ignore-missing-imports`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/qa_auto/cli.py tests/test_cli_analyze.py
git commit -m "Add analyze CLI command"
```

---

### Task 4: Documentation and Phase verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document `qa_auto analyze` in `README.md`**

Add documentation and options table for `qa_auto analyze` in `README.md`.

- [ ] **Step 2: Run full test suite and quality gate**

Run:
```bash
pytest tests/ -m "not slow" -q
pytest tests/integration/ -m "integration and slow" -q
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/qa_auto --ignore-missing-imports
```
Expected: all tests pass, zero errors.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document analyze CLI command"
```
