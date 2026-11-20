"""Command-line interface for Tracecase."""

import asyncio
import json
import re
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tracecase import __version__
from tracecase.replay.models import ReplayResult


# Browser choices enum for validation
class BrowserType(StrEnum):
    chromium = "chromium"
    firefox = "firefox"
    webkit = "webkit"


app = typer.Typer(
    name="tracecase",
    help="Record browser actions and generate test cases for QA engineers.",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


def validate_url(url: str) -> str:
    """Validate and normalize URL."""
    # Add https:// if no scheme provided
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    # Basic URL validation
    url_pattern = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain
        r"localhost|"  # localhost
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # or IP
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )

    if not url_pattern.match(url):
        console.print(f"[red]✗ Invalid URL:[/red] {url}")
        console.print("  URL should be like: https://example.com or example.com")
        raise typer.Exit(1)

    return url


def validate_output_dir(output: Path) -> Path:
    """Validate output directory path."""
    # Check if parent directory exists or can be created
    try:
        output = output.resolve()

        # If path exists, check if it's a directory
        if output.exists():
            if not output.is_dir():
                console.print(f"[red]✗ Output path is not a directory:[/red] {output}")
                raise typer.Exit(1)
        else:
            # Try to create the directory
            output.mkdir(parents=True, exist_ok=True)
            console.print(f"[dim]Created output directory: {output}[/dim]")

        # Create screenshots subdirectory
        screenshots_dir = output / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)

        return output
    except PermissionError:
        console.print(f"[red]✗ Permission denied:[/red] Cannot create {output}")
        raise typer.Exit(1) from None
    except OSError as e:
        console.print(f"[red]✗ Invalid path:[/red] {e}")
        raise typer.Exit(1) from None


def print_banner() -> None:
    """Print Tracecase banner."""
    banner = Panel(
        "[bold green]Tracecase[/bold green] — Browser Action Recorder\n"
        f"[dim]Version {__version__}[/dim]",
        border_style="green",
        padding=(0, 2),
    )
    console.print(banner)


def print_session_info(
    url: str,
    output: Path,
    name: str,
    browser: str,
    headless: bool,
    timeout: int,
) -> None:
    """Print recording session information."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="dim")
    table.add_column("Value")

    table.add_row("URL", f"[blue]{url}[/blue]")
    table.add_row("Output", f"[yellow]{output}[/yellow]")
    table.add_row("Test Name", f"[cyan]{name}[/cyan]")
    table.add_row("Browser", browser)
    table.add_row("Headless", "Yes" if headless else "No")
    table.add_row("Timeout", f"{timeout}ms")

    console.print("\n[bold]Session Configuration:[/bold]")
    console.print(table)


def generate_testcase_name(url: str) -> str:
    """Generate a default test case name from URL."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    path = parsed.path.strip("/").replace("/", "_")

    if path:
        return f"{domain}_{path}"
    return domain


@app.command()
def record(
    url: Annotated[
        str,
        typer.Argument(
            help="URL to open in the browser (e.g., https://example.com)",
        ),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output directory for test case files",
        ),
    ],
    name: Annotated[
        str | None,
        typer.Option(
            "--name",
            "-n",
            help="Test case name (auto-generated from URL if not provided)",
        ),
    ] = None,
    browser: Annotated[
        BrowserType,
        typer.Option(
            "--browser",
            "-b",
            help="Browser to use",
            case_sensitive=False,
        ),
    ] = BrowserType.chromium,
    headless: Annotated[
        bool,
        typer.Option(
            "--headless",
            help="Run browser in headless mode (no GUI)",
        ),
    ] = False,
    timeout: Annotated[
        int,
        typer.Option(
            "--timeout",
            "-t",
            help="Action timeout in milliseconds",
            min=1000,
            max=300000,
        ),
    ] = 30000,
) -> None:
    """
    Record browser actions and generate a test case.

    Opens a browser window with a control panel. Use the panel buttons to:

    • [green]▶ Start[/green] — Begin recording actions
    • [red]⏹ Stop[/red] — Stop recording and save results

    Output files (JSON, Markdown, HTML) are saved to the specified directory.
    """
    # Print banner
    print_banner()

    # Validate URL
    url = validate_url(url)

    # Validate output directory
    output = validate_output_dir(output)

    # Generate name if not provided
    if name is None:
        name = generate_testcase_name(url)

    # Print session info
    print_session_info(url, output, name, browser.value, headless, timeout)

    # Check if playwright is installed
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        console.print("\n[red]✗ Playwright not installed![/red]")
        console.print("  Run: [cyan]playwright install chromium[/cyan]")
        raise typer.Exit(1) from None

    console.print("\n[bold green]Starting browser...[/bold green]")
    console.print("[dim]Use the control panel in the browser to start/stop recording.[/dim]")
    console.print("[dim]Press Ctrl+C to cancel.[/dim]\n")

    # Run the recorder
    try:
        asyncio.run(
            run_recorder(
                url=url,
                output_dir=output,
                name=name,
                browser_type=browser.value,
                headless=headless,
                timeout=timeout,
            )
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Recording cancelled by user.[/yellow]")
        raise typer.Exit(0) from None


async def run_recorder(
    url: str,
    output_dir: Path,
    name: str,
    browser_type: str,
    headless: bool,
    timeout: int,
) -> None:
    """
    Run the browser recorder.

    Args:
        url: URL to record
        output_dir: Directory to save output files
        name: Test case name
        browser_type: Browser to use
        headless: Run browser without GUI
        timeout: Action timeout in ms
    """
    from tracecase.recorder import Recorder

    recorder = Recorder(
        output_dir=output_dir,
        start_url=url,
        name=name,
        browser_type=browser_type,
        headless=headless,
        viewport=(1280, 720),
        timeout=timeout,
    )

    await recorder.run()


@app.command()
def version() -> None:
    """Show version and system information."""
    print_banner()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Component", style="dim")
    table.add_column("Version")

    table.add_row("Tracecase", __version__)
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    table.add_row("Python", py_ver)

    # Check playwright
    try:
        from playwright._repo_version import version as pw_version

        table.add_row("Playwright", pw_version)
    except ImportError:
        table.add_row("Playwright", "[red]Not installed[/red]")

    # Check pydantic
    try:
        import pydantic

        table.add_row("Pydantic", pydantic.__version__)
    except ImportError:
        table.add_row("Pydantic", "[red]Not installed[/red]")

    console.print("\n[bold]System Information:[/bold]")
    console.print(table)


@app.command()
def check() -> None:
    """Check if all dependencies are properly installed."""
    print_banner()
    console.print("\n[bold]Checking dependencies...[/bold]\n")

    all_ok = True

    # Check Python version
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    console.print(f"[green]✓[/green] Python {py_version}")

    # Check required packages
    packages = [
        ("playwright", "playwright"),
        ("pydantic", "pydantic"),
        ("typer", "typer"),
        ("rich", "rich"),
        ("jinja2", "jinja2"),
        ("PIL", "pillow"),
    ]

    for import_name, package_name in packages:
        try:
            __import__(import_name)
            console.print(f"[green]✓[/green] {package_name}")
        except ImportError:
            console.print(f"[red]✗[/red] {package_name} — [dim]pip install {package_name}[/dim]")
            all_ok = False

    # Check playwright browsers
    console.print("\n[bold]Checking browsers...[/bold]\n")

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            for browser_name in ["chromium", "firefox", "webkit"]:
                try:
                    browser_launcher = getattr(p, browser_name)
                    browser = browser_launcher.launch(headless=True)
                    browser.close()
                    console.print(f"[green]✓[/green] {browser_name}")
                except Exception:
                    install_cmd = f"playwright install {browser_name}"
                    console.print(f"[yellow]○[/yellow] {browser_name} — [dim]{install_cmd}[/dim]")
    except Exception as e:
        console.print(f"[red]✗[/red] Could not check browsers: {e}")
        console.print("[dim]Run: playwright install[/dim]")
        all_ok = False

    # Summary
    console.print()
    if all_ok:
        console.print("[bold green]✓ All checks passed![/bold green]")
    else:
        console.print("[bold yellow]⚠ Some checks failed. See above for details.[/bold yellow]")
        raise typer.Exit(1)


@app.command()
def export_har(
    testcase: Annotated[
        Path,
        typer.Argument(help="Path to a testcase.json file"),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output HAR path (defaults to network.har next to the test case)",
        ),
    ] = None,
) -> None:
    """Export recorded network activity as a HAR file."""
    from tracecase.models import TestCase as RecordedTestCase
    from tracecase.replay.har import export_har as write_har

    if not testcase.exists():
        console.print(f"[red]✗ Test case not found:[/red] {testcase}")
        raise typer.Exit(2)

    try:
        case = RecordedTestCase.model_validate_json(testcase.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[red]✗ Invalid test case:[/red] {exc}")
        raise typer.Exit(2) from None

    output_path = output or testcase.with_name("network.har")
    path = write_har(case, output_path)
    console.print(f"[green]✓[/green] HAR: {path}")


@app.command()
def replay(
    testcase: Annotated[
        Path,
        typer.Argument(help="Path to a testcase.json file"),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Directory for replay.json and failure screenshots",
        ),
    ] = None,
    heal: Annotated[
        bool,
        typer.Option("--heal", help="Enable heuristic selector self-healing"),
    ] = False,
    verify: Annotated[
        bool,
        typer.Option("--assert/--no-assert", help="Evaluate derived assertions"),
    ] = True,
    from_har: Annotated[
        Path | None,
        typer.Option("--from-har", help="Fulfill network requests from a HAR file"),
    ] = None,
    headed: Annotated[
        bool,
        typer.Option("--headed", help="Show the browser window"),
    ] = False,
    timeout: Annotated[
        int,
        typer.Option(
            "--timeout", "-t", help="Action timeout in milliseconds", min=1000, max=300000
        ),
    ] = 30000,
    diff: Annotated[
        bool,
        typer.Option("--diff/--no-diff", help="Perform visual screenshot comparison"),
    ] = False,
    diff_threshold: Annotated[
        float,
        typer.Option(
            "--diff-threshold", help="Tolerance percentage for visual diff", min=0.0, max=100.0
        ),
    ] = 0.1,
    diff_fail: Annotated[
        bool,
        typer.Option(
            "--diff-fail/--no-diff-fail", help="Fail replay if visual diff exceeds threshold"
        ),
    ] = False,
) -> None:
    """Replay a recorded test case and evaluate derived assertions."""
    from tracecase.models import TestCase as RecordedTestCase
    from tracecase.replay.engine import ReplayEngine, write_replay_result
    from tracecase.replay.har import load_har

    print_banner()

    if not testcase.exists():
        console.print(f"[red]✗ Test case not found:[/red] {testcase}")
        raise typer.Exit(2)

    try:
        case = RecordedTestCase.model_validate_json(testcase.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[red]✗ Invalid test case:[/red] {exc}")
        raise typer.Exit(2) from None

    har = None
    if from_har is not None:
        if not from_har.exists():
            console.print(f"[red]✗ HAR not found:[/red] {from_har}")
            raise typer.Exit(2)
        har = load_har(from_har)

    engine = ReplayEngine(
        case,
        headless=not headed,
        timeout=timeout,
        heal=heal,
        har=har,
        output_dir=output,
        assertions_enabled=verify,
        visual_diff=diff,
        diff_threshold=diff_threshold,
        visual_fail=diff_fail,
        testcase_dir=testcase.parent,
    )

    try:
        result = asyncio.run(engine.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Replay cancelled by user.[/yellow]")
        raise typer.Exit(2) from None

    _print_replay_summary(result)

    if output is not None:
        path = write_replay_result(result, output)
        console.print(f"[dim]Replay report: {path}[/dim]")

    raise typer.Exit(result.exit_code)


def _print_replay_summary(result: ReplayResult) -> None:
    table = Table(title="Replay Results")
    table.add_column("Step", style="dim")
    table.add_column("Status")
    table.add_column("Selector")
    table.add_column("Details")

    colors = {
        "passed": "green",
        "healed": "yellow",
        "failed": "red",
        "error": "red",
        "skipped": "dim",
    }
    for step in result.steps:
        color = colors.get(step.status, "white")
        details = step.error or "; ".join(
            assertion.message for assertion in step.assertions if not assertion.passed
        )
        table.add_row(
            str(step.number),
            f"[{color}]{step.status}[/{color}]",
            step.selector_used or "-",
            details or "",
        )

    console.print(table)
    summary_color = {"passed": "green", "failed": "red", "error": "red"}[result.status]
    console.print(f"[{summary_color}]Replay {result.status}[/{summary_color}]")

    if result.status == "error" and any(
        "Element not found" in (s.error or "") for s in result.steps
    ):
        console.print(
            "[dim]Tip: If selectors drifted or the DOM shifted, retry with --heal to enable intelligent fallback locators.[/dim]"
        )

    if result.visual_diffs:
        diff_table = Table(title="Visual Regression Summary")
        diff_table.add_column("Step", style="cyan")
        diff_table.add_column("Diff Pixels")
        diff_table.add_column("Diff %")
        diff_table.add_column("Status")
        for i, vd in enumerate(result.visual_diffs, 1):
            st = "[green]Passed[/green]" if vd.passed else "[red]Failed[/red]"
            diff_table.add_row(str(i), f"{vd.diff_pixels:,}", f"{vd.diff_percentage:.2f}%", st)
        console.print(diff_table)


@app.command()
def diff(
    baseline: Annotated[
        Path,
        typer.Argument(help="Baseline image file"),
    ],
    candidate: Annotated[
        Path,
        typer.Argument(help="Candidate image file"),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Path to save highlighted visual diff image"),
    ] = None,
    threshold: Annotated[
        float,
        typer.Option(
            "--threshold",
            "-t",
            help="Tolerance percentage (e.g. 0.1 for 0.1%)",
            min=0.0,
            max=100.0,
        ),
    ] = 0.1,
) -> None:
    """Compare two images pixel-by-pixel and report differences."""
    from tracecase.replay.visual import compare_images

    if not baseline.exists():
        console.print(f"[red]✗ Baseline not found:[/red] {baseline}")
        raise typer.Exit(2)
    if not candidate.exists():
        console.print(f"[red]✗ Candidate not found:[/red] {candidate}")
        raise typer.Exit(2)

    try:
        res = compare_images(
            baseline,
            candidate,
            diff_output=output,
            threshold_percent=threshold,
        )
    except Exception as exc:
        console.print(f"[red]✗ Comparison error:[/red] {exc}")
        raise typer.Exit(2) from None

    status_str = "[green]Passed[/green]" if res.passed else "[red]Failed[/red]"
    report_table = Table(title="Visual Difference Report")
    report_table.add_column("Metric", style="cyan")
    report_table.add_column("Value")
    report_table.add_row("Baseline", str(baseline))
    report_table.add_row("Candidate", str(candidate))
    report_table.add_row("Total Pixels", f"{res.total_pixels:,}")
    report_table.add_row("Diff Pixels", f"{res.diff_pixels:,}")
    report_table.add_row("Diff Percentage", f"{res.diff_percentage:.2f}%")
    report_table.add_row("Status", status_str)
    if res.diff_path:
        report_table.add_row("Diff Image", res.diff_path)
    console.print(report_table)

    if not res.passed:
        raise typer.Exit(1)


@app.command()
def mutate(
    testcase: Annotated[
        Path,
        typer.Argument(help="Path to a testcase.json file"),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Directory to save synthesized negative test cases",
        ),
    ] = None,
    strategy: Annotated[
        str,
        typer.Option(
            "--strategy",
            "-s",
            help="Mutation strategy to apply: all, inputs, actions, network",
        ),
    ] = "all",
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-n",
            help="Maximum number of mutations to generate",
        ),
    ] = 20,
) -> None:
    """Synthesize negative test case variations from a recorded user flow."""
    from tracecase.models import TestCase as RecordedTestCase
    from tracecase.mutation.engine import MutationEngine

    if not testcase.exists():
        console.print(f"[red]✗ Test case not found:[/red] {testcase}")
        raise typer.Exit(2)

    try:
        case = RecordedTestCase.model_validate_json(testcase.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[red]✗ Invalid test case:[/red] {exc}")
        raise typer.Exit(2) from None

    engine = MutationEngine()
    selected_strategies = (
        [strategy]
        if strategy in ("inputs", "actions", "network")
        else ["inputs", "actions", "network"]
    )
    mutations = engine.generate(case, strategies=selected_strategies, limit=limit)

    if not mutations:
        console.print("[yellow]No mutations generated for this test case.[/yellow]")
        return

    out_dir = output or (testcase.parent / "mutations")
    exported_paths = engine.export_mutations(mutations, out_dir)

    table = Table(title="Synthesized Negative Test Cases")
    table.add_column("ID", style="cyan")
    table.add_column("Strategy")
    table.add_column("Step")
    table.add_column("Type")
    table.add_column("Description")

    for m in mutations:
        table.add_row(
            m.testcase.id,
            m.metadata.strategy,
            str(m.metadata.target_step),
            m.metadata.mutation_type,
            m.metadata.description,
        )

    console.print(table)
    console.print(
        f"\n[green]✓[/green] Synthesized {len(exported_paths)} negative test case(s) into: {out_dir}"
    )
    if exported_paths:
        console.print(
            f"[dim]Tip: Replay an individual variation:[/dim] tracecase replay {exported_paths[0]} --heal"
        )


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
    from tracecase.codegen.pytest_exporter import _slugify, generate_pytest_code
    from tracecase.models import TestCase as RecordedTestCase

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
    from tracecase.ai.analyst import analyze_testcase, write_analysis_result
    from tracecase.ai.provider import (
        DEFAULT_HOSTED_BASE_URL,
        DEFAULT_HOSTED_MODEL,
        get_provider,
    )
    from tracecase.models import TestCase as RecordedTestCase

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
        chosen_provider = "openai"
        base_url = base_url or DEFAULT_HOSTED_BASE_URL
        model = model or DEFAULT_HOSTED_MODEL

    prov = get_provider(chosen_provider, base_url=base_url, model=model)
    console.print(f"[bold cyan]Analyzing '{case.name}' with provider: {prov.name}[/bold cyan]")

    result = asyncio.run(analyze_testcase(case, prov))

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

    if (
        ai
        and prov.name != "null"
        and not result.negative_scenarios
        and not result.suggested_assertions
    ):
        console.print(
            f"\n[dim]Note: Local AI provider '{prov.name}' did not return suggestions. "
            f"Ensure {prov.name} is running (e.g. `ollama serve`) and model '{prov.model}' is downloaded.[/dim]"
        )

    out_dir = output or testcase.parent
    path = write_analysis_result(result, out_dir)
    console.print(f"\n[green]✓[/green] Analysis report saved to: {path}")


@app.command(name="index")
def index_cmd(
    directory: Annotated[
        Path,
        typer.Argument(help="Directory containing testcase.json files to index"),
    ],
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Path to SQLite corpus database"),
    ] = None,
    clear: Annotated[
        bool,
        typer.Option("--clear", help="Wipe database before indexing"),
    ] = False,
) -> None:
    """Index test cases in a directory into the local SQLite/FTS5 store."""
    from tracecase.index.store import index_directory, reset_db

    if not directory.exists() or not directory.is_dir():
        console.print(f"[red]✗ Directory not found:[/red] {directory}")
        raise typer.Exit(2)

    if clear:
        reset_db(db)
        console.print("[dim]Existing corpus database reset.[/dim]")

    count = index_directory(directory, db_path=db)
    console.print(f"[green]✓[/green] Indexed {count} test case(s) into corpus store.")


@app.command()
def search(
    query: Annotated[
        str,
        typer.Argument(help="Search query to match against test cases and actions"),
    ],
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Path to SQLite corpus database"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Maximum number of results to display"),
    ] = 10,
) -> None:
    """Search recorded test cases using full-text FTS5 search."""
    from tracecase.index.search import search_testcases

    results = search_testcases(query, db_path=db, limit=limit)
    if not results:
        console.print(f"[yellow]No test cases found matching:[/yellow] {query}")
        return

    table = Table(title=f"Search Results for '{query}'")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Start URL")
    table.add_column("Matched Snippet")

    for res in results:
        table.add_row(
            res["id"],
            res["name"],
            res["start_url"],
            res.get("snippet") or "-",
        )

    console.print(table)


@app.command()
def coverage(
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Path to SQLite corpus database"),
    ] = None,
) -> None:
    """Analyze corpus coverage across domains, start URLs, and network endpoints."""
    from tracecase.index.search import get_coverage_report

    report = get_coverage_report(db_path=db)

    table = Table(title="Corpus Coverage Report")
    table.add_column("Metric", style="cyan")
    table.add_column("Count / Details")

    table.add_row("Total Test Cases", str(report["total_testcases"]))
    table.add_row("Unique Domains", str(report["unique_domains"]))
    table.add_row("Unique Endpoints", str(len(report["network_endpoints"])))
    table.add_row("Potential Duplicate URLs", str(len(report["potential_duplicates"])))
    console.print(table)

    if report["domains"]:
        console.print("\n[bold]Tested Domains:[/bold]")
        for domain, count in report["domains"].items():
            console.print(f"  • {domain} ({count} test cases)")

    if report["potential_duplicates"]:
        console.print("\n[yellow]Potential Duplicate Test Flows:[/yellow]")
        for dup in report["potential_duplicates"]:
            console.print(f"  • {dup['url']} ({dup['count']} recordings)")


@app.command()
def mcp(
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Path to SQLite corpus database"),
    ] = None,
) -> None:
    """Start local stdio Model Context Protocol (MCP) server."""
    from tracecase.mcp.server import MCPServer

    server = MCPServer(db_path=db)
    asyncio.run(server.run_stdio())


@app.command()
def clean(
    db: Annotated[
        bool,
        typer.Option("--db/--no-db", help="Clear the local SQLite corpus database"),
    ] = True,
    recordings: Annotated[
        bool,
        typer.Option(
            "--recordings/--no-recordings",
            help="Remove local ./recordings directory",
        ),
    ] = False,
    all_artifacts: Annotated[
        bool,
        typer.Option(
            "--all",
            "-a",
            help="Remove both local corpus DB and ./recordings directory",
        ),
    ] = False,
    db_path: Annotated[
        Path | None,
        typer.Option("--db-path", help="Path to custom SQLite corpus database"),
    ] = None,
) -> None:
    """Wipe local corpus SQLite database and/or recorded session artifacts."""
    import shutil

    from tracecase.index.store import DEFAULT_DB_PATH, reset_db

    target_db = Path(db_path) if db_path else DEFAULT_DB_PATH
    wiped_any = False

    if db or all_artifacts:
        if reset_db(target_db):
            console.print(f"[green]✓[/green] Wiped local corpus database: {target_db}")
            wiped_any = True
        else:
            console.print(f"[dim]Corpus database does not exist: {target_db}[/dim]")

    if recordings or all_artifacts:
        rec_dir = Path("./recordings")
        if rec_dir.exists() and rec_dir.is_dir():
            shutil.rmtree(rec_dir)
            console.print(
                f"[green]✓[/green] Removed local recordings directory: {rec_dir.resolve()}"
            )
            wiped_any = True
        else:
            console.print(f"[dim]No local recordings directory found at: {rec_dir}[/dim]")

    if not wiped_any:
        console.print("[yellow]Nothing to wipe.[/yellow]")


@app.command()
def storage(
    prune_diffs: Annotated[
        bool,
        typer.Option("--diffs", help="Prune visual regression diff images"),
    ] = False,
    clean_runs: Annotated[
        bool,
        typer.Option("--clean-runs", help="Prune all old replay run outputs"),
    ] = False,
    failures_only: Annotated[
        bool,
        typer.Option("--failures-only", help="Prune screenshots from passing runs"),
    ] = False,
    older_than: Annotated[
        int | None,
        typer.Option("--older-than", help="Prune replay runs older than N days"),
    ] = None,
    keep_latest: Annotated[
        int | None,
        typer.Option("--keep-latest", help="Keep latest N replay runs per testcase"),
    ] = None,
    max_mb: Annotated[
        int | None,
        typer.Option("--max-mb", help="Enforce target maximum storage quota in MB"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Simulate pruning without deleting files"),
    ] = False,
) -> None:
    """Inspect disk storage usage and prune execution artifacts."""
    from rich.table import Table
    from tracecase.artifact_manager import ArtifactManager, PruneRequest

    mgr = ArtifactManager()

    # If any pruning flag is requested, run pruning
    is_pruning = any([
        prune_diffs,
        clean_runs,
        failures_only,
        older_than is not None,
        keep_latest is not None,
        max_mb is not None,
    ])

    if is_pruning:
        req = PruneRequest(
            clean_diffs=prune_diffs,
            clean_old_runs=clean_runs,
            failures_only=failures_only,
            older_than_days=older_than,
            keep_latest_runs=keep_latest,
            max_storage_mb=max_mb,
            dry_run=dry_run,
        )
        res = mgr.prune_artifacts(req)
        status_prefix = "[yellow][DRY RUN][/yellow] Would free" if dry_run else "[green]✓[/green] Freed"
        console.print(
            f"{status_prefix} [bold]{res.freed_mb} MB[/bold] "
            f"({res.deleted_files} files, {res.deleted_runs} runs pruned). "
            f"Remaining storage: [bold]{res.remaining_storage_mb} MB[/bold]."
        )
        return

    # Default action: print storage summary table
    summary = mgr.get_storage_summary()

    table = Table(title="Tracecase Disk Storage Summary", border_style="cyan")
    table.add_column("Category", style="bold")
    table.add_column("Count / Items", justify="right")
    table.add_column("Size (MB)", justify="right")
    table.add_column("Description", style="dim")

    table.add_row(
        "Baseline Corpus",
        str(summary.recordings_count),
        f"{summary.recordings_size_mb:.2f}",
        "Test case definitions, metadata, baseline screenshots",
    )
    table.add_row(
        "Replay Runs",
        f"{summary.replay_runs_count} runs ({summary.replay_screenshots_count} shots)",
        f"{summary.replay_runs_size_mb:.2f}",
        "Execution logs, step screenshots, run reports",
    )
    table.add_row(
        "Visual Diffs",
        f"{summary.diffs_count} images",
        f"{summary.diffs_size_mb:.2f}",
        "Pixel comparison diff images",
    )
    table.add_row(
        "Explorations",
        f"{summary.explorations_count} runs",
        f"{summary.explorations_size_mb:.2f}",
        "Autonomous exploration sessions & state graphs",
    )
    table.add_row(
        "Studio DB",
        Path(summary.database_path).name,
        f"{summary.database_size_mb:.2f}",
        "SQLite runs, attempts, batches, flakiness metrics",
    )
    table.add_section()
    table.add_row(
        "[bold green]Total Usage[/bold green]",
        "-",
        f"[bold green]{summary.total_size_mb:.2f}[/bold green]",
        "Total disk footprint across all components",
    )

    console.print(table)
    pol = summary.retention_policy
    console.print(
        f"[dim]Active Retention Policy: mode='{pol.retention_mode}', "
        f"keep_latest={pol.keep_latest_runs}, max_age={pol.max_age_days}d, "
        f"max_quota={pol.max_storage_mb}MB[/dim]"
    )


@app.command()
def benchmark(
    iterations: Annotated[
        int,
        typer.Option("--iterations", "-n", help="Number of benchmark test executions per paradigm"),
    ] = 6,
    concurrency: Annotated[
        int,
        typer.Option("--concurrency", "-c", help="Worker concurrency for parallel modes"),
    ] = 3,
    output_md: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Optional markdown file path to save benchmark report"),
    ] = None,
) -> None:
    """Benchmark sequential cold vs parallel cold vs parallel pooled execution."""
    from rich.markdown import Markdown
    from tracecase.benchmark import run_benchmark_suite

    console.print(
        f"[cyan]Running Tracecase Performance Benchmark[/cyan] "
        f"({iterations} runs per mode, concurrency={concurrency})...\n"
    )

    report = asyncio.run(run_benchmark_suite(iterations=iterations, concurrency=concurrency))
    md_content = report.to_markdown()

    console.print(Markdown(md_content))

    if output_md:
        output_md.write_text(md_content)
        console.print(f"\n[green]✓[/green] Saved benchmark report to: {output_md.resolve()}")


@app.command()
def changes(
    repo_path: Annotated[
        Path,
        typer.Argument(help="Path to repository directory (defaults to current dir)"),
    ] = Path("."),
    base: Annotated[
        str | None,
        typer.Option("--base", "-b", help="Base git ref to compare against (e.g. main, HEAD~1)"),
    ] = None,
    staged: Annotated[
        bool,
        typer.Option("--staged", help="Inspect only staged git changes"),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output raw JSON instead of table"),
    ] = False,
) -> None:
    """Analyze git changes, diffs, changed selectors, routes, and symbols (Phase 7.5.1)."""
    from rich.table import Table
    from tracecase.intelligence.git_analyzer import GitChangeAnalyzer

    analyzer = GitChangeAnalyzer(repo_path)
    change_set = analyzer.analyze_repo(base_ref=base, staged_only=staged)

    if as_json:
        console.print_json(change_set.model_dump_json())
        return

    # Header
    branch_str = f"on [bold cyan]{change_set.current_branch or 'detached'}[/bold cyan]"
    commit_str = f"([dim]{change_set.current_commit or 'unknown'}[/dim])"
    status_str = "[yellow]dirty[/yellow]" if change_set.is_dirty else "[green]clean[/green]"
    console.print(f"Git Change Intelligence: {branch_str} {commit_str} - {status_str}\n")

    if not change_set.files:
        console.print("[dim]No changes detected in repository.[/dim]")
        return

    # Files table
    table = Table(title=f"Changed Files ({len(change_set.files)})", border_style="cyan")
    table.add_column("Type", style="bold")
    table.add_column("Path")
    table.add_column("+/-", justify="right")
    table.add_column("Routes", style="magenta")
    table.add_column("Selectors", style="yellow")
    table.add_column("Functions / Classes", style="blue")

    for f in change_set.files:
        t_style = "green" if f.change_type == "added" else "rose" if f.change_type == "deleted" else "cyan"
        diff_str = f"[green]+{f.additions}[/green]/[red]-{f.deletions}[/red]"
        routes_str = ", ".join(f.changed_routes[:2]) if f.changed_routes else "-"
        selectors_str = ", ".join(f.changed_selectors[:2]) if f.changed_selectors else "-"
        syms = (f.changed_functions + f.changed_classes)[:2]
        syms_str = ", ".join(syms) if syms else "-"

        table.add_row(
            f"[{t_style}]{f.change_type.upper()}[/{t_style}]",
            f.path,
            diff_str,
            routes_str,
            selectors_str,
            syms_str,
        )

    console.print(table)

    # Summary
    s = change_set.summary
    console.print(
        f"\n[bold]Summary:[/bold] {s.total_files_changed} files changed "
        f"([green]+{s.total_additions}[/green] / [red]-{s.total_deletions}[/red]). "
        f"Detected [magenta]{len(s.total_changed_routes)} routes[/magenta], "
        f"[yellow]{len(s.total_changed_selectors)} selectors[/yellow], "
        f"[blue]{len(s.total_changed_symbols)} symbols[/blue]."
    )


@app.command(name="map")
def map_code(
    repo_path: Annotated[
        Path,
        typer.Argument(help="Path to repository workspace (defaults to current dir)"),
    ] = Path("."),
    project_id: Annotated[
        str,
        typer.Option("--project", "-p", help="Project identifier"),
    ] = "default_project",
) -> None:
    """Scan codebase and map testcases to application routes, selectors, and files (Phase 7.5.2)."""
    from rich.table import Table
    from tracecase.intelligence.code_mapper import TestToCodeMapper
    from tracecase.models import TestCase
    from tracecase.ui.service import find_testcase_files, resolve_testcase_file

    console.print(f"[cyan]Mapping test cases to codebase in '{repo_path.resolve()}'...[/cyan]")
    mapper = TestToCodeMapper(repo_path=repo_path, project_id=project_id)
    mapper.scan_codebase()

    tc_files = find_testcase_files()
    testcases: list[TestCase] = []
    for f in tc_files:
        try:
            _, tc = resolve_testcase_file(str(f))
            testcases.append(tc)
        except Exception:
            pass

    graph = mapper.build_graph(testcases, persist=True)

    table = Table(title=f"Test-to-Code Mappings ({len(graph.mappings)})", border_style="cyan")
    table.add_column("Test Case", style="bold")
    table.add_column("Relation", style="magenta")
    table.add_column("Confidence", justify="right")
    table.add_column("Matched Entity", style="yellow")
    table.add_column("Application File", style="blue")

    for m in graph.mappings[:20]:
        conf_style = "green" if m.confidence >= 0.9 else "yellow" if m.confidence >= 0.7 else "dim"
        table.add_row(
            m.testcase_name or m.testcase_id,
            m.relation_type,
            f"[{conf_style}]{m.confidence:.2f}[/{conf_style}]",
            m.matched_entity,
            m.file_path,
        )

    console.print(table)
    if len(graph.mappings) > 20:
        console.print(f"[dim]...and {len(graph.mappings) - 20} more mappings indexed in studio.db[/dim]")

    console.print(
        f"\n[green]✓[/green] Successfully indexed [bold]{len(graph.mappings)}[/bold] mappings across "
        f"[bold]{len(testcases)}[/bold] tests and [bold]{len(mapper.file_indices)}[/bold] code files."
    )


@app.command()
def impact(
    repo_path: Annotated[
        Path,
        typer.Argument(help="Path to repository workspace (defaults to current dir)"),
    ] = Path("."),
    base: Annotated[
        str | None,
        typer.Option("--base", "-b", help="Base git ref to compare against (e.g. main, HEAD~1)"),
    ] = None,
    staged: Annotated[
        bool,
        typer.Option("--staged", help="Inspect only staged git changes"),
    ] = False,
    project_id: Annotated[
        str,
        typer.Option("--project", "-p", help="Project identifier"),
    ] = "default_project",
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output raw JSON instead of table"),
    ] = False,
) -> None:
    """Identify regression test cases impacted by git code changes with ranked confidence (Phase 7.5.2)."""
    from rich.table import Table
    from tracecase.intelligence.code_mapper import TestToCodeMapper
    from tracecase.intelligence.git_analyzer import GitChangeAnalyzer
    from tracecase.models import TestCase
    from tracecase.ui.service import find_testcase_files, resolve_testcase_file

    analyzer = GitChangeAnalyzer(repo_path)
    changeset = analyzer.analyze_repo(base_ref=base, staged_only=staged)

    mapper = TestToCodeMapper(repo_path=repo_path, project_id=project_id)
    mapper.scan_codebase()

    tc_files = find_testcase_files()
    testcases: list[TestCase] = []
    test_names: dict[str, str] = {}
    for f in tc_files:
        try:
            _, tc = resolve_testcase_file(str(f))
            testcases.append(tc)
            test_names[tc.id] = tc.name
        except Exception:
            pass

    graph = mapper.build_graph(testcases, persist=False)
    impacted = graph.get_impacted_tests(changeset.files, all_tests=test_names)

    if as_json:
        report = {
            "total_impacted_tests": len(impacted),
            "changeset_summary": changeset.summary.model_dump(),
            "impacted_tests": [t.model_dump() for t in impacted],
        }
        console.print_json(json.dumps(report))
        return

    console.print(f"[bold cyan]Code Change Impact Analysis[/bold cyan] ({len(changeset.files)} files modified)\n")

    if not impacted:
        console.print("[green]✓ No existing test cases impacted by these code changes.[/green]")
        return

    table = Table(title=f"Impacted Regression Tests ({len(impacted)})", border_style="red")
    table.add_column("Test Case", style="bold")
    table.add_column("Confidence", justify="right")
    table.add_column("Primary Reason", style="yellow")
    table.add_column("Affected Files", style="blue")

    for t in impacted:
        conf_style = "bold red" if t.max_confidence >= 0.95 else "yellow" if t.max_confidence >= 0.8 else "dim"
        table.add_row(
            t.testcase_name,
            f"[{conf_style}]{t.max_confidence:.2f}[/{conf_style}]",
            t.primary_reason,
            ", ".join(t.affected_files[:2]),
        )

    console.print(table)
    console.print(f"\n[bold red]Impact:[/bold red] {len(impacted)} tests should be prioritized for regression verification.")


@app.command()
def risk(
    repo_path: Annotated[
        Path,
        typer.Argument(help="Path to repository workspace (defaults to current dir)"),
    ] = Path("."),
    base: Annotated[
        str | None,
        typer.Option("--base", "-b", help="Base git ref to compare against (e.g. main, HEAD~1)"),
    ] = None,
    staged: Annotated[
        bool,
        typer.Option("--staged", help="Inspect only staged git changes"),
    ] = False,
    min_tier: Annotated[
        str | None,
        typer.Option("--min-tier", "-t", help="Minimum risk tier to display: critical, high, medium, low"),
    ] = None,
    project_id: Annotated[
        str,
        typer.Option("--project", "-p", help="Project identifier"),
    ] = "default_project",
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output raw JSON instead of table"),
    ] = False,
) -> None:
    """Evaluate predictive risk scores and priority rankings for regression test cases (Phase 7.5.3)."""
    from rich.table import Table
    from tracecase.intelligence.code_mapper import TestToCodeMapper
    from tracecase.intelligence.git_analyzer import GitChangeAnalyzer
    from tracecase.intelligence.risk_scorer import PredictiveRiskScorer
    from tracecase.models import TestCase
    from tracecase.ui.service import find_testcase_files, resolve_testcase_file

    analyzer = GitChangeAnalyzer(repo_path)
    changeset = analyzer.analyze_repo(base_ref=base, staged_only=staged)

    mapper = TestToCodeMapper(repo_path=repo_path, project_id=project_id)
    mapper.scan_codebase()

    tc_files = find_testcase_files()
    testcases: list[TestCase] = []
    for f in tc_files:
        try:
            _, tc = resolve_testcase_file(str(f))
            testcases.append(tc)
        except Exception:
            pass

    graph = mapper.build_graph(testcases, persist=False)
    scorer = PredictiveRiskScorer(project_id=project_id)
    report = scorer.evaluate_suite_risk(testcases, graph, changeset, persist=True)

    tier_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    min_rank = tier_order.get(min_tier.lower(), 1) if min_tier else 1

    filtered_scores = [s for s in report.scores if tier_order.get(s.risk_tier, 1) >= min_rank]

    if as_json:
        console.print_json(report.model_dump_json())
        return

    branch_str = f"on [bold cyan]{changeset.current_branch or 'detached'}[/bold cyan]"
    commit_str = f"([dim]{changeset.current_commit or 'unknown'}[/dim])"
    console.print(f"[bold]Predictive Risk Analysis[/bold] {branch_str} {commit_str}\n")

    if not filtered_scores:
        console.print("[dim]No test cases meet the selected risk criteria.[/dim]")
        return

    table = Table(title=f"Test Case Risk Rankings ({len(filtered_scores)} displayed)", border_style="cyan")
    table.add_column("Tier", justify="center")
    table.add_column("Test Case", style="bold")
    table.add_column("Risk", justify="right")
    table.add_column("Conf", justify="right")
    table.add_column("Primary Risk Driver", style="yellow")
    table.add_column("Signals (I/B/F/H/C)", style="dim", justify="center")

    tier_styles = {
        "critical": "[bold white on red] CRITICAL [/bold white on red]",
        "high": "[bold red] HIGH [/bold red]",
        "medium": "[bold yellow] MEDIUM [/bold yellow]",
        "low": "[green] LOW [/green]",
    }

    for s in filtered_scores:
        t_badge = tier_styles.get(s.risk_tier, s.risk_tier.upper())
        r_style = "bold red" if s.risk_score >= 85 else "red" if s.risk_score >= 70 else "yellow" if s.risk_score >= 40 else "green"
        conf_str = f"{s.mapping_confidence:.2f}"
        b = s.breakdown
        signals_str = f"{b.change_impact_score:.0f}/{b.selector_breakage_score:.0f}/{b.historical_failure_score:.0f}/{b.flakiness_recency_score:.0f}/{b.change_magnitude_score:.0f}"

        table.add_row(
            t_badge,
            s.testcase_name or s.testcase_id,
            f"[{r_style}]{s.risk_score:.1f}[/{r_style}]",
            conf_str,
            s.primary_risk_driver,
            signals_str,
        )

    console.print(table)
    console.print(
        f"\n[bold]Risk Distribution:[/bold] "
        f"[red]{report.critical_count} Critical[/red], "
        f"[yellow]{report.high_count} High[/yellow], "
        f"[blue]{report.medium_count} Medium[/blue], "
        f"[green]{report.low_count} Low[/green] "
        f"across {report.total_tests_evaluated} evaluated tests."
    )


@app.command()
def select(
    repo_path: Annotated[
        Path,
        typer.Argument(help="Path to repository workspace (defaults to current dir)"),
    ] = Path("."),
    budget: Annotated[
        str | None,
        typer.Option("--budget", "-b", help="Time budget constraint (e.g. 120s, 2m, 90)"),
    ] = None,
    min_tier: Annotated[
        str | None,
        typer.Option("--min-tier", "-t", help="Minimum risk tier (critical, high, medium, low)"),
    ] = None,
    top: Annotated[
        int | None,
        typer.Option("--top", "-k", help="Select top K highest priority tests"),
    ] = None,
    include_critical_exceptions: Annotated[
        bool,
        typer.Option("--include-critical-exceptions", help="Include critical tests that exceed time budget"),
    ] = False,
    base: Annotated[
        str | None,
        typer.Option("--base", help="Base git ref to compare against (e.g. main, HEAD~1)"),
    ] = None,
    staged: Annotated[
        bool,
        typer.Option("--staged", help="Inspect only staged git changes"),
    ] = False,
    project_id: Annotated[
        str,
        typer.Option("--project", "-p", help="Project identifier"),
    ] = "default_project",
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output raw JSON instead of table"),
    ] = False,
) -> None:
    """Intelligently select regression tests based on change risk and execution constraints (Phase 7.5.4)."""
    from rich.table import Table
    from tracecase.intelligence.code_mapper import TestToCodeMapper
    from tracecase.intelligence.git_analyzer import GitChangeAnalyzer
    from tracecase.intelligence.risk_scorer import PredictiveRiskScorer
    from tracecase.intelligence.selector import IntelligentRegressionSelector
    from tracecase.models import TestCase
    from tracecase.ui.service import find_testcase_files, resolve_testcase_file

    # Determine strategy
    if budget and min_tier:
        strategy = "combined"
    elif budget:
        strategy = "time_budget"
    elif top:
        strategy = "top_k"
    elif min_tier:
        strategy = "risk_threshold"
    else:
        strategy = "time_budget"
        budget = "120s"

    analyzer = GitChangeAnalyzer(repo_path)
    changeset = analyzer.analyze_repo(base_ref=base, staged_only=staged)

    mapper = TestToCodeMapper(repo_path=repo_path, project_id=project_id)
    mapper.scan_codebase()

    tc_files = find_testcase_files()
    testcases: list[TestCase] = []
    for f in tc_files:
        try:
            _, tc = resolve_testcase_file(str(f))
            testcases.append(tc)
        except Exception:
            pass

    graph = mapper.build_graph(testcases, persist=False)
    scorer = PredictiveRiskScorer(project_id=project_id)
    risk_report = scorer.evaluate_suite_risk(testcases, graph, changeset, persist=False)

    selector = IntelligentRegressionSelector(project_id=project_id)
    result = selector.select(
        testcases=testcases,
        risk_report=risk_report,
        strategy=strategy,
        time_budget=budget,
        min_risk_tier=min_tier,
        top_k=top,
        include_critical_exceptions=include_critical_exceptions,
        persist=True,
    )

    try:
        from tracecase.intelligence.explainer import PrioritizationExplainer
        explainer = PrioritizationExplainer(project_id=project_id)
        explainer.build_report(
            selection=result,
            risk_report=risk_report,
            changeset=changeset,
            graph=graph,
            persist=True,
        )
    except Exception:
        pass

    if as_json:
        console.print_json(result.model_dump_json())
        return

    branch_str = f"on [bold cyan]{changeset.current_branch or 'detached'}[/bold cyan]"
    commit_str = f"([dim]{changeset.current_commit or 'unknown'}[/dim])"
    strat_str = f"Strategy: [bold magenta]{strategy.upper()}[/bold magenta]"
    if result.time_budget_s:
        strat_str += f" (Budget: [cyan]{result.time_budget_s:.0f}s[/cyan])"
    console.print(f"[bold]Intelligent Regression Selection[/bold] {branch_str} {commit_str} - {strat_str}\n")

    table = Table(title=f"Regression Test Candidates ({len(result.tests)})", border_style="cyan")
    table.add_column("Tier", justify="center")
    table.add_column("Test Case", style="bold")
    table.add_column("Risk", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Decision", justify="center")
    table.add_column("Selection Rationale")

    tier_badges = {
        "critical": "[bold white on red] CRIT [/bold white on red]",
        "high": "[bold red] HIGH [/bold red]",
        "medium": "[bold yellow] MED [/bold yellow]",
        "low": "[green] LOW [/green]",
    }

    decision_styles = {
        "selected": "[bold green] SELECTED [/bold green]",
        "excluded": "[dim] EXCLUDED [/dim]",
        "budget_exception": "[bold white on red] BUDGET EXCEPTION [/bold white on red]",
    }

    src_tags = {
        "measured_history": "[green]hist[/green]",
        "recorded_testcase": "[blue]rec[/blue]",
        "estimated_fallback": "[yellow]est[/yellow]",
    }

    for item in result.tests:
        t_badge = tier_badges.get(item.risk_tier, item.risk_tier.upper())
        d_badge = decision_styles.get(item.decision, item.decision.upper())
        src_tag = src_tags.get(item.duration_source, "")
        dur_str = f"{item.estimated_duration_s:.1f}s {src_tag}"

        table.add_row(
            t_badge,
            item.testcase_name or item.testcase_id,
            f"{item.risk_score:.1f}",
            dur_str,
            d_badge,
            item.decision_reason,
        )

    console.print(table)

    # Budget Exception Alert
    if result.budget_exception_count > 0:
        console.print(
            f"\n[bold red]⚠️ CRITICAL TEST BUDGET EXCEPTION:[/bold red] "
            f"[bold]{result.budget_exception_count}[/bold] critical risk test(s) exceeded the time budget. "
            f"They were NOT silently excluded. Re-run with [bold cyan]--include-critical-exceptions[/bold cyan] to include them."
        )

    # Summary
    console.print(
        f"\n[bold]Selection Summary:[/bold] "
        f"[green]{result.selected_count} Selected[/green] / {result.total_tests_considered} Considered. "
        f"Estimated Duration: [bold cyan]{result.estimated_total_duration_s:.1f}s[/bold cyan]. "
        f"Risk Coverage: [bold green]{result.risk_coverage_pct:.1f}%[/bold green] "
        f"(Critical Coverage: [bold]{result.critical_coverage_pct:.1f}%[/bold])."
    )
    console.print(f"[dim]{result.disclaimer}[/dim]")


@app.command()
def explain(
    selection_id: Annotated[
        str | None,
        typer.Argument(help="ID of regression selection snapshot to explain (defaults to latest)"),
    ] = None,
    project_id: Annotated[
        str,
        typer.Option("--project", "-p", help="Project identifier"),
    ] = "default_project",
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output raw JSON instead of tables"),
    ] = False,
) -> None:
    """Explain why tests were selected, excluded, or flagged as budget exceptions with categorized evidence (Phase 7.5.5)."""
    from rich.table import Table
    from tracecase.intelligence.explainer import PrioritizationExplainer
    from tracecase.intelligence.models import RegressionSelectionResult, SelectedTestItem
    from tracecase.ui.db import get_decision_traces, get_regression_selection_by_id, get_regression_selections

    # 1. Resolve selection ID
    if not selection_id:
        recent = get_regression_selections(project_id=project_id, limit=1)
        if not recent:
            console.print("[bold red]Error:[/bold red] No regression selections found for project.")
            raise typer.Exit(code=1)
        selection_id = recent[0]["id"]

    sel = get_regression_selection_by_id(selection_id)
    if not sel:
        console.print(f"[bold red]Error:[/bold red] Regression selection '{selection_id}' not found.")
        raise typer.Exit(code=1)

    traces = get_decision_traces(selection_id)
    if not traces:
        # Generate explanations dynamically if not precomputed
        tests_data = sel.get("tests") or []
        items = [SelectedTestItem(**t) for t in tests_data]
        selection_obj = RegressionSelectionResult(
            id=sel["id"],
            project_id=sel.get("project_id", project_id),
            commit_hash=sel.get("commit_hash"),
            branch=sel.get("branch"),
            created_at=sel.get("created_at", ""),
            strategy=sel.get("strategy", "time_budget"),
            strategy_params=sel.get("strategy_params") or {},
            time_budget_s=sel.get("time_budget_s"),
            total_tests_considered=sel.get("total_tests_considered", len(items)),
            selected_count=sel.get("selected_count", len(sel.get("selected_test_ids") or [])),
            excluded_count=sel.get("excluded_count", len(sel.get("excluded_test_ids") or [])),
            budget_exception_count=sel.get("budget_exception_count", len(sel.get("budget_exceptions") or [])),
            estimated_total_duration_s=sel.get("estimated_total_duration_s", 0.0),
            risk_coverage_pct=sel.get("risk_coverage_pct", 0.0),
            critical_coverage_pct=sel.get("critical_coverage_pct", 0.0),
            selected_test_ids=sel.get("selected_test_ids") or [],
            excluded_test_ids=sel.get("excluded_test_ids") or [],
            budget_exceptions=sel.get("budget_exceptions") or [],
            tests=items,
        )
        explainer = PrioritizationExplainer(project_id=project_id)
        explainer.build_report(selection_obj, persist=True)
        traces = get_decision_traces(selection_id)

    if as_json:
        console.print_json(json.dumps(traces))
        return

    commit_str = f"([dim]{sel.get('commit_hash') or 'unknown'}[/dim])"
    strat_str = f"Strategy: [bold magenta]{(sel.get('strategy') or 'unknown').upper()}[/bold magenta]"
    console.print(f"[bold]Prioritization Decision Explanation[/bold] ({selection_id}) {commit_str} - {strat_str}\n")

    table = Table(title=f"Decisions & Verifiable Evidence Attribution ({len(traces)} tests)", border_style="cyan")
    table.add_column("Decision", justify="center")
    table.add_column("Tier", justify="center")
    table.add_column("Test Case", style="bold")
    table.add_column("Risk", justify="right")
    table.add_column("Certainty", justify="center")
    table.add_column("Duration", justify="right")
    table.add_column("Evidence Summary")
    table.add_column("Selection Rationale")

    tier_badges = {
        "critical": "[bold white on red] CRIT [/bold white on red]",
        "high": "[bold red] HIGH [/bold red]",
        "medium": "[bold yellow] MED [/bold yellow]",
        "low": "[green] LOW [/green]",
    }

    decision_badges = {
        "selected": "[bold green] SELECTED [/bold green]",
        "excluded": "[dim] EXCLUDED [/dim]",
        "budget_exception": "[bold white on red] EXCEPTION [/bold white on red]",
    }

    for t in traces:
        d_badge = decision_badges.get(t["decision"], t["decision"].upper())
        if t.get("user_override"):
            d_badge += " [yellow](OVERRIDE)[/yellow]"
        t_badge = tier_badges.get(t["risk_tier"], t["risk_tier"].upper())
        conf_pct = f"{t['mapping_confidence'] * 100:.0f}%"
        dur_str = f"{t['estimated_duration_s']:.1f}s"

        ev = t.get("evidence") or {}
        obs_count = len(ev.get("observed") or [])
        heu_count = len(ev.get("heuristic") or [])
        mis_count = len(ev.get("missing") or [])

        ev_summary = f"[green]✓ {obs_count} obs[/green], [yellow]⚡ {heu_count} heu[/yellow], [dim]ℹ {mis_count} mis[/dim]"
        if obs_count > 0 and ev.get("observed"):
            top_obs = ev["observed"][0].get("description", "")
            if len(top_obs) > 40:
                top_obs = top_obs[:37] + "..."
            ev_summary += f"\n[dim]{top_obs}[/dim]"

        rationale = t.get("rationale") or t.get("decision_summary") or ""
        if len(rationale) > 60:
            rationale = rationale[:57] + "..."

        table.add_row(
            d_badge,
            t_badge,
            t.get("testcase_name") or t["testcase_id"],
            f"{t['risk_score']:.1f}",
            conf_pct,
            dur_str,
            ev_summary,
            rationale,
        )

    console.print(table)
    console.print("\n[dim]Note: Mapping confidence measures certainty of code-to-test connection, NOT failure probability.[/dim]")


@app.command()
def report(
    selection_id: Annotated[
        str | None,
        typer.Argument(help="ID of regression selection snapshot to report (defaults to latest)"),
    ] = None,
    project_id: Annotated[
        str,
        typer.Option("--project", "-p", help="Project identifier"),
    ] = "default_project",
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: markdown or json"),
    ] = "markdown",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="File path to write report to (outputs to stdout if omitted)"),
    ] = None,
) -> None:
    """Generate publication-ready Markdown regression report or CI/PR JSON manifest (Phase 7.5.5)."""
    from tracecase.intelligence.explainer import PrioritizationExplainer
    from tracecase.intelligence.models import RegressionSelectionResult, SelectedTestItem
    from tracecase.ui.db import get_regression_selection_by_id, get_regression_selections

    # 1. Resolve selection ID
    if not selection_id:
        recent = get_regression_selections(project_id=project_id, limit=1)
        if not recent:
            console.print("[bold red]Error:[/bold red] No regression selections found for project.")
            raise typer.Exit(code=1)
        selection_id = recent[0]["id"]

    sel = get_regression_selection_by_id(selection_id)
    if not sel:
        console.print(f"[bold red]Error:[/bold red] Regression selection '{selection_id}' not found.")
        raise typer.Exit(code=1)

    tests_data = sel.get("tests") or []
    items = [SelectedTestItem(**t) for t in tests_data]
    selection_obj = RegressionSelectionResult(
        id=sel["id"],
        project_id=sel.get("project_id", project_id),
        commit_hash=sel.get("commit_hash"),
        branch=sel.get("branch"),
        created_at=sel.get("created_at", ""),
        strategy=sel.get("strategy", "time_budget"),
        strategy_params=sel.get("strategy_params") or {},
        time_budget_s=sel.get("time_budget_s"),
        total_tests_considered=sel.get("total_tests_considered", len(items)),
        selected_count=sel.get("selected_count", len(sel.get("selected_test_ids") or [])),
        excluded_count=sel.get("excluded_count", len(sel.get("excluded_test_ids") or [])),
        budget_exception_count=sel.get("budget_exception_count", len(sel.get("budget_exceptions") or [])),
        estimated_total_duration_s=sel.get("estimated_total_duration_s", 0.0),
        risk_coverage_pct=sel.get("risk_coverage_pct", 0.0),
        critical_coverage_pct=sel.get("critical_coverage_pct", 0.0),
        selected_test_ids=sel.get("selected_test_ids") or [],
        excluded_test_ids=sel.get("excluded_test_ids") or [],
        budget_exceptions=sel.get("budget_exceptions") or [],
        tests=items,
    )

    explainer = PrioritizationExplainer(project_id=project_id)
    prioritization_report = explainer.build_report(selection_obj, persist=False)

    if format.lower() == "json":
        manifest = explainer.generate_json_manifest(prioritization_report)
        content = json.dumps(manifest, indent=2)
    else:
        content = prioritization_report.markdown_report

    if output:
        output.write_text(content, encoding="utf-8")
        console.print(f"[bold green]✓ Report successfully saved to {output}[/bold green]")
    else:
        if format.lower() == "json":
            console.print_json(content)
        else:
            console.print(content)


@app.command(name="run")
def run_command(
    target: Annotated[
        Path | None,
        typer.Argument(help="Path to a testcase.json file or folder (optional with --select-smart)"),
    ] = None,
    select_smart: Annotated[
        bool,
        typer.Option("--select-smart", help="Enable intelligent regression test selection"),
    ] = False,
    budget: Annotated[
        str | None,
        typer.Option("--budget", "-b", help="Time budget constraint for smart selection (e.g. 120s, 2m)"),
    ] = None,
    min_tier: Annotated[
        str | None,
        typer.Option("--min-tier", "-t", help="Minimum risk tier (critical, high, medium, low)"),
    ] = None,
    top: Annotated[
        int | None,
        typer.Option("--top", "-k", help="Select top K highest priority tests"),
    ] = None,
    include_critical_exceptions: Annotated[
        bool,
        typer.Option("--include-critical-exceptions", help="Include critical tests that exceed time budget"),
    ] = False,
    concurrency: Annotated[
        int,
        typer.Option("--concurrency", "-c", help="Worker pool concurrency", min=1, max=16),
    ] = 2,
    browser: Annotated[
        str,
        typer.Option("--browser", help="Browser engine (chromium, firefox, webkit)"),
    ] = "chromium",
    retries: Annotated[
        int,
        typer.Option("--retries", help="Configurable attempt retries on failure (0-3)", min=0, max=3),
    ] = 1,
    ci: Annotated[
        bool,
        typer.Option("--ci", "--yes", "-y", help="Non-interactive mode (auto-approves execution)"),
    ] = False,
    repo_path: Annotated[
        Path,
        typer.Option("--repo", help="Repository path for change intelligence"),
    ] = Path("."),
    project_id: Annotated[
        str,
        typer.Option("--project", "-p", help="Project identifier"),
    ] = "default_project",
) -> None:
    """Execute test cases with opt-in intelligent regression selection (Phase 7.5.4)."""
    import asyncio
    from tracecase.intelligence.code_mapper import TestToCodeMapper
    from tracecase.intelligence.git_analyzer import GitChangeAnalyzer
    from tracecase.intelligence.risk_scorer import PredictiveRiskScorer
    from tracecase.intelligence.selector import IntelligentRegressionSelector
    from tracecase.models import TestCase
    from tracecase.ui.executor import orchestrator
    from tracecase.ui.service import find_testcase_files, resolve_testcase_file

    if select_smart:
        console.print("[bold cyan]Tracecase Smart Regression Engine[/bold cyan] analyzing code modifications...")
        strategy = "combined" if (budget and min_tier) else "top_k" if top else "risk_threshold" if min_tier else "time_budget"
        active_budget = budget or "120s"

        analyzer = GitChangeAnalyzer(repo_path)
        changeset = analyzer.analyze_repo()

        mapper = TestToCodeMapper(repo_path=repo_path, project_id=project_id)
        mapper.scan_codebase()

        tc_files = find_testcase_files()
        testcases: list[TestCase] = []
        for f in tc_files:
            try:
                _, tc = resolve_testcase_file(str(f))
                testcases.append(tc)
            except Exception:
                pass

        graph = mapper.build_graph(testcases, persist=False)
        scorer = PredictiveRiskScorer(project_id=project_id)
        risk_report = scorer.evaluate_suite_risk(testcases, graph, changeset, persist=False)

        selector = IntelligentRegressionSelector(project_id=project_id)
        selection = selector.select(
            testcases=testcases,
            risk_report=risk_report,
            strategy=strategy,
            time_budget=active_budget,
            min_risk_tier=min_tier,
            top_k=top,
            include_critical_exceptions=include_critical_exceptions,
            persist=True,
        )

        test_ids_to_run = list(selection.selected_test_ids)
        if not test_ids_to_run:
            console.print("[yellow]No tests met the selection criteria for execution.[/yellow]")
            return

        console.print(
            f"\n[bold]Selected {len(test_ids_to_run)} test case(s)[/bold] "
            f"(Estimated Duration: [cyan]{selection.estimated_total_duration_s:.1f}s[/cyan], "
            f"Risk Coverage: [green]{selection.risk_coverage_pct:.1f}%[/green]):"
        )
        for tid in test_ids_to_run:
            t_item = next((t for t in selection.tests if t.testcase_id == tid), None)
            t_name = t_item.testcase_name if t_item else tid
            t_tier = t_item.risk_tier.upper() if t_item else "N/A"
            console.print(f"  • [{t_tier}] [bold]{t_name}[/bold] ({t_item.estimated_duration_s:.1f}s) - {t_item.decision_reason if t_item else ''}")

        if selection.budget_exception_count > 0 and not include_critical_exceptions:
            console.print(
                f"\n[bold red]Note:[/bold red] {selection.budget_exception_count} critical test(s) exceeded the budget "
                f"and were excluded. Pass --include-critical-exceptions to run them."
            )

        if not ci:
            confirmed = typer.confirm(
                f"\nProceed with parallel execution of these {len(test_ids_to_run)} tests?",
                default=True,
            )
            if not confirmed:
                console.print("[yellow]Execution cancelled by user.[/yellow]")
                return

        console.print(f"\n[bold green]Dispatching batch execution[/bold green] (concurrency={concurrency}, retries={retries})...")
        batch = asyncio.run(
            orchestrator.start_batch_execution(
                testcase_ids=test_ids_to_run,
                concurrency=concurrency,
                project_id=project_id,
                browser=browser,
                retries=retries,
            )
        )
        console.print(f"[green]✓ Batch execution started:[/green] [cyan]{batch.get('id')}[/cyan] ({len(test_ids_to_run)} tests queued)")
        return

    # If --select-smart not provided, target path is required
    if not target:
        console.print("[red]✗ Error:[/red] Please provide a testcase path to run or use [bold]--select-smart[/bold].")
        raise typer.Exit(1)

    from tracecase.cli import replay
    replay(testcase=target, output=None, heal=True, verify=True)




@app.command()
def ui(
    host: Annotated[
        str,
        typer.Option("--host", "-h", help="Bind host address"),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="Bind port number"),
    ] = 8000,
    open_browser: Annotated[
        bool,
        typer.Option("--browser/--no-browser", help="Automatically open browser on launch"),
    ] = True,
) -> None:
    """Launch the Tracecase Studio interactive web application."""
    print_banner()
    console.print(
        f"[bold green]Starting Tracecase Studio[/bold green] on [cyan]http://{host}:{port}[/cyan]"
    )
    console.print("[dim]Press Ctrl+C to stop the studio server.[/dim]\n")

    from tracecase.ui.server import start_server

    try:
        start_server(host=host, port=port, open_browser=open_browser)
    except KeyboardInterrupt:
        console.print("\n[yellow]Tracecase Studio stopped.[/yellow]")


@app.command(name="ci")
def ci_command(
    base: Annotated[
        str | None,
        typer.Option("--base", "-b", help="Base git ref to compare against (e.g. origin/main, HEAD~1)"),
    ] = None,
    target: Annotated[
        str | None,
        typer.Option("--target", help="Target git ref (defaults to HEAD)"),
    ] = None,
    budget: Annotated[
        str | None,
        typer.Option("--budget", help="Time budget constraint (e.g. 180s, 3m)"),
    ] = "180s",
    gate: Annotated[
        str,
        typer.Option("--gate", "-g", help="Named quality gate policy (strict, standard, lenient, permissive)"),
    ] = "standard",
    concurrency: Annotated[
        int,
        typer.Option("--concurrency", "-c", help="Worker pool concurrency (1-16)"),
    ] = 2,
    browser: Annotated[
        str,
        typer.Option("--browser", help="Browser engine (chromium, firefox, webkit)"),
    ] = "chromium",
    retries: Annotated[
        int,
        typer.Option("--retries", help="Attempt retries on failure (0-3)"),
    ] = 1,
    headed: Annotated[
        bool,
        typer.Option("--headed", help="Run browser in headed mode"),
    ] = False,
    include_critical_exceptions: Annotated[
        bool,
        typer.Option("--include-critical-exceptions", help="Force execution of critical tests exceeding time budget"),
    ] = False,
    baseline_ref: Annotated[
        str | None,
        typer.Option("--baseline-ref", help="Explicit base branch/ref to resolve baseline snapshot from"),
    ] = None,
    auto_run_baseline: Annotated[
        bool,
        typer.Option("--auto-run-baseline", help="Auto-execute baseline in isolated worktree if snapshot not found"),
    ] = False,
    allow_preexisting: Annotated[
        bool | None,
        typer.Option("--allow-preexisting/--no-allow-preexisting", help="Allow pre-existing baseline failures"),
    ] = None,
    junit: Annotated[
        Path | None,
        typer.Option("--junit", help="Path to write JUnit XML report"),
    ] = None,
    sarif: Annotated[
        Path | None,
        typer.Option("--sarif", help="Path to write SARIF report"),
    ] = None,
    report: Annotated[
        Path | None,
        typer.Option("--report", help="Path to write Markdown summary report"),
    ] = None,
    manifest: Annotated[
        Path | None,
        typer.Option("--manifest", help="Path to write JSON manifest"),
    ] = None,
    config_file: Annotated[
        Path | None,
        typer.Option("--config", help="Path to YAML configuration file"),
    ] = None,
    repo_path: Annotated[
        Path,
        typer.Option("--repo", help="Repository path"),
    ] = Path("."),
    project_id: Annotated[
        str,
        typer.Option("--project", "-p", help="Project identifier"),
    ] = "default_project",
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Output machine-readable JSON result to stdout"),
    ] = False,
    upload_url: Annotated[
        str | None,
        typer.Option("--upload-url", help="Tracecase Studio URL to upload CI run manifest to"),
    ] = None,
    upload_token: Annotated[
        str | None,
        typer.Option("--upload-token", help="Bearer token for Tracecase Studio upload"),
    ] = None,
) -> None:
    """Run automated CI Quality Gate with predictive regression selection and multi-format reporting."""
    from tracecase.ci.config import CIRunnerConfig
    from tracecase.ci.policy import get_policy
    from tracecase.ci.runner import CIRunner

    # 1. Load base configuration from file if provided, otherwise defaults
    if config_file and Path(config_file).is_file():
        ci_config = CIRunnerConfig.load_from_file(config_file)
    else:
        ci_config = CIRunnerConfig(
            base_ref=base,
            target_ref=target,
            repo_path=str(repo_path),
            project_id=project_id,
            time_budget=budget,
            concurrency=concurrency,
            browser=browser,
            retries=retries,
            headed=headed,
            include_critical_exceptions=include_critical_exceptions,
            gate_policy=get_policy(gate),
            junit_path=str(junit) if junit else None,
            sarif_path=str(sarif) if sarif else None,
            markdown_path=str(report) if report else None,
            json_path=str(manifest) if manifest else None,
        )

    # CLI option overrides if specified explicitly
    if base is not None:
        ci_config.base_ref = base
    if target is not None:
        ci_config.target_ref = target
    if gate != "standard" or ci_config.gate_policy.name != gate:
        ci_config.gate_policy = get_policy(gate)
    if junit:
        ci_config.junit_path = str(junit)
    if sarif:
        ci_config.sarif_path = str(sarif)
    if report:
        ci_config.markdown_path = str(report)
    if manifest:
        ci_config.json_path = str(manifest)
    if baseline_ref:
        ci_config.baseline_ref = baseline_ref
    if auto_run_baseline:
        ci_config.auto_run_baseline = auto_run_baseline
    if allow_preexisting is not None:
        ci_config.gate_policy.allow_pre_existing_failures = allow_preexisting
    if upload_url:
        ci_config.upload_url = upload_url
    if upload_token:
        ci_config.upload_token = upload_token

    if not json_out:
        print_banner()
        console.print(Panel(
            f"[bold cyan]Tracecase Continuous Quality Gate[/bold cyan]\n"
            f"[dim]Policy:[/dim] [yellow]{ci_config.gate_policy.name.upper()}[/yellow] | "
            f"[dim]Base:[/dim] [cyan]{ci_config.base_ref or 'HEAD (uncommitted)'}[/cyan] | "
            f"[dim]Budget:[/dim] [green]{ci_config.time_budget}[/green] | "
            f"[dim]Concurrency:[/dim] {ci_config.concurrency}",
            border_style="cyan",
        ))

    runner = CIRunner(config=ci_config)
    result = asyncio.run(runner.run())

    if json_out:
        console.print_json(result.model_dump_json())
        raise typer.Exit(code=result.exit_code)

    # Console visualization
    m = result.gate_result.metrics
    table = Table(title="Quality Gate Results Summary", border_style="dim")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_column("Status")

    table.add_row("Execution Duration", f"{result.duration_seconds:.2f}s", "ℹ")
    table.add_row("Considered Tests", str(result.total_considered), "ℹ")
    table.add_row("Selected / Executed", f"{result.selected_count} / {result.executed_count}", "ℹ")
    table.add_row(
        "Passed Tests",
        str(m.get("passed_count", 0)),
        "[green]✓[/green]" if m.get("passed_count", 0) > 0 else "—",
    )
    table.add_row(
        "Failed Tests",
        f"{m.get('failed_count', 0)} ({m.get('failure_rate_pct', 0.0)}%)",
        "[red]❌[/red]" if m.get("failed_count", 0) > 0 else "[green]✓[/green]",
    )
    table.add_row(
        "Critical Breakages",
        str(m.get("critical_failures_count", 0)),
        "[red]❌[/red]" if m.get("critical_failures_count", 0) > 0 else "[green]✓[/green]",
    )
    table.add_row(
        "Flaky Tests",
        f"{m.get('flaky_count', 0)} ({m.get('flakiness_rate_pct', 0.0)}%)",
        "[yellow]⚡[/yellow]" if m.get("flaky_count", 0) > 0 else "[green]✓[/green]",
    )
    table.add_row(
        "Surface File Coverage",
        f"{m.get('surface_coverage_pct', 0.0)}% (file mapping)",
        "[green]✓[/green]" if m.get("surface_coverage_pct", 0.0) >= 70.0 else "[yellow]⚠[/yellow]",
    )
    table.add_row(
        "Budget Exceptions",
        str(m.get("budget_exceptions_count", 0)),
        "[yellow]⚠[/yellow]" if m.get("budget_exceptions_count", 0) > 0 else "[green]✓[/green]",
    )

    console.print(table)
    console.print("[dim]ℹ Note: Surface file coverage measures changed files mapped to tests, not dynamic runtime branch coverage.[/dim]")

    if result.drift_summary and result.drift_summary.get("baseline_found"):
        d = result.drift_summary
        drift_table = Table(title="Regression Drift & Attribution (Phase 8.3)", border_style="cyan")
        drift_table.add_column("Classification", style="bold")
        drift_table.add_column("Count")
        drift_table.add_column("Attribution & Impact")

        new_regs = d.get("new_regressions_count", 0)
        drift_table.add_row(
            "New Regressions",
            str(new_regs),
            "[red]❌ Introduced by this PR (blocking)[/red]" if new_regs > 0 else "[green]✓ None[/green]",
        )
        drift_table.add_row(
            "Fixed Regressions",
            str(d.get("fixed_regressions_count", 0)),
            "[green]🎉 Fixed by this PR[/green]" if d.get("fixed_regressions_count", 0) > 0 else "—",
        )
        drift_table.add_row(
            "Pre-Existing Failures",
            str(d.get("pre_existing_failures_count", 0)),
            "[yellow]⏳ Technical debt on base commit[/yellow]" if d.get("pre_existing_failures_count", 0) > 0 else "✓ None",
        )
        drift_table.add_row(
            "Newly Flaky Tests",
            str(d.get("newly_flaky_count", 0)),
            "[yellow]⚡ Required retry on PR[/yellow]" if d.get("newly_flaky_count", 0) > 0 else "✓ None",
        )
        dur_delta = (d.get("duration_delta_ms") or 0.0) / 1000.0
        drift_table.add_row(
            "Duration Drift (Δ)",
            f"{dur_delta:+.2f}s ({d.get('duration_drift_pct', 0.0):+.1f}%)",
            "Execution duration vs baseline",
        )
        console.print(drift_table)

    if result.gate_result.violations:
        console.print("\n[bold red]Quality Gate Policy Violations:[/bold red]")
        for v in result.gate_result.violations:
            console.print(f"  [red]• [{v.severity.upper()}] {v.rule_name}:[/red] {v.message}")

    if result.exit_code == 0:
        console.print(f"\n[bold green]✓ QUALITY GATE PASSED[/bold green] (Exit Code: 0)")
    elif result.exit_code == 1:
        console.print(f"\n[bold red]✗ QUALITY GATE FAILED[/bold red] (Exit Code: 1)")
    elif result.exit_code == 2:
        console.print(f"\n[bold yellow]! CONFIGURATION / ENVIRONMENT ERROR[/bold yellow] (Exit Code: 2)")
        if result.error_detail:
            console.print(f"  [yellow]{result.error_detail}[/yellow]")
    elif result.exit_code == 3:
        console.print(f"\n[bold red]💥 INFRASTRUCTURE / EXECUTION ERROR[/bold red] (Exit Code: 3)")
        if result.error_detail:
            console.print(f"  [red]{result.error_detail}[/red]")

    # Generated reports info
    if ci_config.junit_path:
        console.print(f"  [dim]JUnit XML:[/dim] {ci_config.junit_path}")
    if ci_config.sarif_path:
        console.print(f"  [dim]SARIF 2.1.0:[/dim] {ci_config.sarif_path}")
    if ci_config.markdown_path:
        console.print(f"  [dim]Markdown Summary:[/dim] {ci_config.markdown_path}")
    if ci_config.json_path:
        console.print(f"  [dim]JSON Manifest:[/dim] {ci_config.json_path}")

    raise typer.Exit(code=result.exit_code)


@app.command(name="ci-upload")
def ci_upload_command(
    manifest_path: Annotated[Path, typer.Argument(help="Path to tracecase JSON manifest file")],
    url: Annotated[str, typer.Option("--url", "-u", help="Tracecase Studio server URL")],
    token: Annotated[str | None, typer.Option("--token", "-t", help="Ingestion token")] = None,
) -> None:
    """Upload an exported CI run manifest to Tracecase Studio."""
    import urllib.request
    import urllib.error

    if not manifest_path.is_file():
        console.print(f"[bold red]Error:[/bold red] Manifest file not found: {manifest_path}")
        raise typer.Exit(code=2)

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] Invalid JSON in {manifest_path}: {exc}")
        raise typer.Exit(code=2)

    base_url = url.rstrip("/")
    if not base_url.endswith("/api"):
        endpoint = f"{base_url}/api/ci/ingest"
    else:
        endpoint = f"{base_url}/ci/ingest"

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload_bytes = json.dumps({"manifest": manifest_data}).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload_bytes, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_body = json.loads(resp.read().decode("utf-8"))
            console.print(
                f"[bold green]✓[/bold green] Ingested run [cyan]{resp_body.get('run_id')}[/cyan] into Studio ({resp_body.get('gate_status')})"
            )
    except Exception as exc:
        console.print(f"[bold red]Error uploading manifest to {endpoint}:[/bold red] {exc}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
