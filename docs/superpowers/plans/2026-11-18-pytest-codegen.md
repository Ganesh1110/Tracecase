# Pytest Codegen Implementation Plan (Phase 4 Codegen)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit clean, standalone, executable `pytest` + Playwright Python test modules from recorded test cases (`testcase.json`), with actions, assertions, and optional HAR route fulfillment.

**Architecture:** Add `qa_auto.codegen` package with `PytestExporter` and `generate_pytest_code`. The CLI gains `codegen`.

**Tech Stack:** Python 3.13, Typer, Jinja2, Playwright async API, pytest.

## Global Constraints

- Python `>=3.13`, Ruff `target-version = "py313"`, line length 100.
- Core dependencies unchanged: Playwright, Pydantic, Typer, Rich, Jinja2, Pillow.
- Offline by default. Tests must only use `127.0.0.1`; no external network.
- `testcase.json` schema is unchanged.
- Generated code must be valid, well-formatted Python syntax and adhere to standard `pytest` conventions.
- All browser tests must be marked `@pytest.mark.integration` and `@pytest.mark.slow`.
- Exit codes: `0` on success, `2` on invalid testcase/file errors.
- Ruff rules: `E`, `F`, `I`, `UP`, `B`, `SIM`. Type annotations required (`disallow_untyped_defs`).

---

### Task 1: Pytest test code generator

**Files:**
- Create: `src/qa_auto/codegen/__init__.py`
- Create: `src/qa_auto/codegen/pytest_exporter.py`
- Test: `tests/test_codegen.py`

**Interfaces:**
- Consumes: `TestCase`, `Step`, `ElementInfo`, `qa_auto.replay.assertions.derive_assertions`.
- Produces:
  - `generate_pytest_code(testcase: TestCase, *, har_path: str | None = None) -> str`
  - `PytestExporter(BaseExporter).export(testcase: TestCase, output_dir: Path) -> Path`

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_codegen.py`:

```python
"""Tests for pytest Playwright code generator."""

from datetime import datetime
from pathlib import Path

from qa_auto.models import ElementInfo, NetworkRequest, Step, TestCase
from qa_auto.codegen.pytest_exporter import PytestExporter, generate_pytest_code


def _element(selector: str, tag: str = "button", text: str = "Submit") -> ElementInfo:
    return ElementInfo(
        selector=selector,
        xpath=f"//*[@id='{selector.lstrip('#')}']",
        tag_name=tag,
        text=text,
        attributes={"id": selector.lstrip("#")},
        bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
    )


def _testcase(steps: list[Step], name: str = "Sample Test") -> TestCase:
    return TestCase(
        id="tc_codegen",
        name=name,
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url="https://example.com/login",
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=steps,
        console_logs=[],
        network_requests=[],
        page_errors=[],
        total_duration=1.0,
        total_steps=len(steps),
    )


def test_generate_code_has_imports_and_function() -> None:
    step = Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=_element("#btn"),
        description_short="Click button",
        description_detailed="Click button",
    )
    code = generate_pytest_code(_testcase([step], name="User Login Flow"))

    assert "import pytest" in code
    assert "from playwright.async_api import Page, expect" in code
    assert "async def test_user_login_flow(page: Page) -> None:" in code
    assert 'await page.goto("https://example.com/login")' in code
    assert 'await page.locator("#btn").click()' in code


def test_generate_code_all_action_types() -> None:
    steps = [
        Step(
            number=1,
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
            action_type="input",
            element=_element("#username", tag="input"),
            input_value="alice@example.com",
            description_short="Type username",
            description_detailed="Type username",
        ),
        Step(
            number=2,
            timestamp=datetime(2025, 1, 1, 12, 0, 1),
            action_type="select",
            element=_element("#role", tag="select"),
            input_value="admin",
            description_short="Select role",
            description_detailed="Select role",
        ),
        Step(
            number=3,
            timestamp=datetime(2025, 1, 1, 12, 0, 2),
            action_type="check",
            element=_element("#terms", tag="input"),
            description_short="Check terms",
            description_detailed="Check terms",
        ),
        Step(
            number=4,
            timestamp=datetime(2025, 1, 1, 12, 0, 3),
            action_type="uncheck",
            element=_element("#newsletter", tag="input"),
            description_short="Uncheck newsletter",
            description_detailed="Uncheck newsletter",
        ),
        Step(
            number=5,
            timestamp=datetime(2025, 1, 1, 12, 0, 4),
            action_type="hover",
            element=_element("#menu"),
            description_short="Hover menu",
            description_detailed="Hover menu",
        ),
        Step(
            number=6,
            timestamp=datetime(2025, 1, 1, 12, 0, 5),
            action_type="keypress",
            key="Enter",
            description_short="Press Enter",
            description_detailed="Press Enter",
        ),
        Step(
            number=7,
            timestamp=datetime(2025, 1, 1, 12, 0, 6),
            action_type="navigate",
            url="https://example.com/dashboard",
            description_short="Navigate dashboard",
            description_detailed="Navigate dashboard",
        ),
    ]

    code = generate_pytest_code(_testcase(steps))

    assert 'await page.locator("#username").fill("alice@example.com")' in code
    assert 'await page.locator("#role").select_option("admin")' in code
    assert 'await page.locator("#terms").check()' in code
    assert 'await page.locator("#newsletter").uncheck()' in code
    assert 'await page.locator("#menu").hover()' in code
    assert 'await page.keyboard.press("Enter")' in code
    assert 'await page.goto("https://example.com/dashboard")' in code


def test_generate_code_with_har_route() -> None:
    step = Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=_element("#load"),
        description_short="Click",
        description_detailed="Click",
    )
    code = generate_pytest_code(_testcase([step]), har_path="network.har")

    assert 'await page.route_from_har("network.har")' in code


def test_pytest_exporter_writes_file(temp_dir: Path) -> None:
    step = Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=_element("#btn"),
        description_short="Click",
        description_detailed="Click",
    )
    exporter = PytestExporter()
    out_file = exporter.export(_testcase([step], name="My Test"), temp_dir)

    assert out_file.exists()
    assert out_file.name == "test_my_test.py"
    assert "async def test_my_test(page: Page)" in out_file.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_codegen.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'qa_auto.codegen'`.

- [ ] **Step 3: Implement pytest exporter**

Create `src/qa_auto/codegen/__init__.py` and `src/qa_auto/codegen/pytest_exporter.py`:

```python
"""Pytest Playwright code generator for recorded test cases."""

from __future__ import annotations

import re
from pathlib import Path

from qa_auto.exporters.base import BaseExporter
from qa_auto.models import Step, TestCase
from qa_auto.replay.assertions import derive_assertions


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text).strip().lower()
    slug = re.sub(r"[-\s]+", "_", cleaned)
    return slug or "test_case"


def _format_step(step: Step) -> list[str]:
    lines: list[str] = []
    action = step.action_type
    selector = step.element.selector if step.element else ""

    if action == "navigate" and step.url:
        lines.append(f'await page.goto("{step.url}")')
    elif action == "click" and selector:
        lines.append(f'await page.locator("{selector}").click()')
    elif action == "dblclick" and selector:
        lines.append(f'await page.locator("{selector}").dblclick()')
    elif action == "input" and selector:
        val = (step.input_value or "").replace('"', '\\"')
        lines.append(f'await page.locator("{selector}").fill("{val}")')
    elif action == "select" and selector:
        val = (step.input_value or "").replace('"', '\\"')
        lines.append(f'await page.locator("{selector}").select_option("{val}")')
    elif action == "check" and selector:
        lines.append(f'await page.locator("{selector}").check()')
    elif action == "uncheck" and selector:
        lines.append(f'await page.locator("{selector}").uncheck()')
    elif action == "hover" and selector:
        lines.append(f'await page.locator("{selector}").hover()')
    elif action == "keypress":
        key = step.key or "Enter"
        lines.append(f'await page.keyboard.press("{key}")')
    elif action == "wait":
        ms = int(step.input_value or "1000")
        lines.append(f"await page.wait_for_timeout({ms})")

    return lines


def generate_pytest_code(testcase: TestCase, *, har_path: str | None = None) -> str:
    """Generate executable pytest + Playwright Python test source code."""
    fn_name = f"test_{_slugify(testcase.name)}"
    assertions = derive_assertions(testcase)
    assertions_by_step: dict[int, list[str]] = {}

    for assertion in assertions:
        if assertion.step_number is None:
            continue
        step_lines = assertions_by_step.setdefault(assertion.step_number, [])
        if assertion.kind == "url" and assertion.expected:
            step_lines.append(
                f'assert "{assertion.expected}" in page.url'
            )

    body_lines: list[str] = []

    if har_path:
        body_lines.append(f'await page.route_from_har("{har_path}")')

    body_lines.append(f'await page.goto("{testcase.start_url}")')

    for step in testcase.steps:
        body_lines.append(f"# Step {step.number}: {step.description_short}")
        body_lines.extend(_format_step(step))
        for assertion_line in assertions_by_step.get(step.number, []):
            body_lines.append(assertion_line)

    indented_body = "\n    ".join(body_lines)

    code = f'''"""Generated Playwright test for {testcase.name}."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect


@pytest.mark.asyncio
async def {fn_name}(page: Page) -> None:
    """Recorded test flow: {testcase.name}."""
    {indented_body}
'''
    return code


class PytestExporter(BaseExporter):
    """Exports a recorded testcase to a pytest module."""

    def __init__(self, har_path: str | None = None) -> None:
        self.har_path = har_path

    def export(self, testcase: TestCase, output_dir: Path) -> Path:
        """Write the generated pytest code to output_dir."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"test_{_slugify(testcase.name)}.py"
        path = output_dir / filename
        content = generate_pytest_code(testcase, har_path=self.har_path)
        path.write_text(content, encoding="utf-8")
        return path
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_codegen.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run lint and types**

Run: `ruff check src/qa_auto/codegen tests/test_codegen.py && mypy src/qa_auto/codegen --ignore-missing-imports`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/qa_auto/codegen/ tests/test_codegen.py
git commit -m "Add pytest Playwright code generator"
```

---

### Task 2: CLI `codegen` command

**Files:**
- Modify: `src/qa_auto/cli.py`
- Test: `tests/test_cli_codegen.py`

**Interfaces:**
- Consumes: `TestCase`, `PytestExporter`, `generate_pytest_code`.
- Produces: CLI command `qa_auto codegen <testcase> [-o output] [--har har_path]`.

- [ ] **Step 1: Write the failing CLI tests**

Create `tests/test_cli_codegen.py`:

```python
"""Tests for CLI codegen command."""

from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from qa_auto.cli import app
from qa_auto.models import Step, TestCase

runner = CliRunner()


def _write_testcase(path: Path) -> Path:
    testcase = TestCase(
        id="tc_cli_codegen",
        name="Checkout Flow",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url="https://example.com",
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


def test_codegen_help() -> None:
    result = runner.invoke(app, ["codegen", "--help"])
    assert result.exit_code == 0
    assert "testcase" in result.stdout.lower()
    assert "--output" in result.stdout


def test_codegen_creates_python_file(temp_dir: Path) -> None:
    tc_path = _write_testcase(temp_dir / "testcase.json")
    out_file = temp_dir / "test_checkout.py"

    result = runner.invoke(app, ["codegen", str(tc_path), "-o", str(out_file)])

    assert result.exit_code == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "async def test_checkout_flow" in content


def test_codegen_missing_file_exits_2(temp_dir: Path) -> None:
    result = runner.invoke(app, ["codegen", str(temp_dir / "missing.json")])
    assert result.exit_code == 2
```

- [ ] **Step 2: Run CLI tests to verify they fail**

Run: `pytest tests/test_cli_codegen.py -v`
Expected: FAIL because `codegen` is not registered.

- [ ] **Step 3: Register `codegen` in `src/qa_auto/cli.py`**

Add `codegen` command to `src/qa_auto/cli.py`:

```python
@app.command()
def codegen(
    testcase: Annotated[
        Path,
        typer.Argument(help="Path to a testcase.json file"),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output Python test file path (defaults to test_<name>.py)",
        ),
    ] = None,
    har: Annotated[
        str | None,
        typer.Option(
            "--har",
            help="Optional path to HAR file to replay routes offline",
        ),
    ] = None,
) -> None:
    """Generate executable pytest Playwright test code from a testcase."""
    from qa_auto.codegen.pytest_exporter import generate_pytest_code, _slugify
    from qa_auto.models import TestCase as RecordedTestCase

    if not testcase.exists():
        console.print(f"[red]✗ Test case not found:[/red] {testcase}")
        raise typer.Exit(2)

    try:
        case = RecordedTestCase.model_validate_json(testcase.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[red]✗ Invalid test case:[/red] {exc}")
        raise typer.Exit(2) from None

    output_path = output or testcase.with_name(f"test_{_slugify(case.name)}.py")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    code = generate_pytest_code(case, har_path=har)
    output_path.write_text(code, encoding="utf-8")
    console.print(f"[green]✓[/green] Generated pytest test: {output_path}")
```

- [ ] **Step 4: Run CLI tests to verify they pass**

Run: `pytest tests/test_cli_codegen.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run lint and types**

Run: `ruff check src/qa_auto tests/ && mypy src/qa_auto --ignore-missing-imports`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/qa_auto/cli.py tests/test_cli_codegen.py
git commit -m "Add codegen CLI command"
```

---

### Task 3: Integration verification of generated test execution

**Files:**
- Test: `tests/integration/test_codegen_execution.py`

**Interfaces:**
- Consumes: `html_server`, `generate_pytest_code`, `TestCase`.
- Verifies: Generated test file runs and passes under `pytest` subprocess against `html_server`.

- [ ] **Step 1: Write the integration test**

Create `tests/integration/test_codegen_execution.py`:

```python
"""Integration test executing generated pytest code against the local server."""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from qa_auto.codegen.pytest_exporter import generate_pytest_code
from qa_auto.models import ElementInfo, Step, TestCase


@pytest.mark.integration
@pytest.mark.slow
def test_generated_pytest_file_runs_and_passes(html_server: str, temp_dir: Path) -> None:
    element = ElementInfo(
        selector="#load",
        xpath="//*[@id='load']",
        tag_name="button",
        text="Load",
        attributes={"id": "load"},
        bounding_box={"x": 0, "y": 0, "width": 10, "height": 10},
    )
    step = Step(
        number=1,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        action_type="click",
        element=element,
        description_short="Click Load",
        description_detailed="Click Load",
    )
    testcase = TestCase(
        id="tc_exec",
        name="Live Server Flow",
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        start_url=html_server,
        browser="chromium",
        viewport={"width": 1280, "height": 720},
        user_agent="TestAgent/1.0",
        steps=[step],
        console_logs=[],
        network_requests=[],
        page_errors=[],
        total_duration=1.0,
        total_steps=1,
    )

    code = generate_pytest_code(testcase)
    test_file = temp_dir / "test_live_server.py"
    test_file.write_text(code, encoding="utf-8")

    # Execute the generated file with pytest
    res = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-v"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert res.returncode == 0
    assert "1 passed" in res.stdout
```

- [ ] **Step 2: Run the integration test**

Run: `pytest tests/integration/test_codegen_execution.py -v -m "integration and slow"`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_codegen_execution.py
git commit -m "Verify generated pytest code executes cleanly"
```

---

### Task 4: Documentation and Phase verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document `qa_auto codegen` in `README.md`**

Add `qa_auto codegen` to CLI reference and workflow sections.

- [ ] **Step 2: Run the full test suite and quality gate**

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
git commit -m "Document codegen CLI command"
```
