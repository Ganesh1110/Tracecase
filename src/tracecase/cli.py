"""Command-line interface for Tracecase."""

import asyncio
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
    from tracecase.ai.provider import get_provider
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
        chosen_provider = "ollama"

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


if __name__ == "__main__":
    app()
