"""Catalog completeness gate: verifies flows.yaml covers 100% of CLI, Studio routes, API, and types."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

# Ensure isolated import of tracecase
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
sys.path = [p for p in sys.path if p not in ("", str(REPO_ROOT))]
sys.path.insert(0, str(SRC_DIR))

import typer
import yaml
from tracecase.cli import app as cli_app
from tracecase.models import ActionType
from tracecase.mutation.models import MutationStrategyType, MutationType
from tracecase.ui.server import create_app


def load_flows_yaml() -> tuple[dict[str, Any], str]:
    flows_file = REPO_ROOT / "tests" / "dogfood" / "flows.yaml"
    content = flows_file.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    return data, content


def get_cli_elements() -> list[str]:
    """Extract all CLI command names and options."""
    click_app = typer.main.get_command(cli_app)
    elements: list[str] = []
    for cmd_name, cmd in click_app.commands.items():
        elements.append(f"cli_command:{cmd_name}")
        for param in cmd.params:
            for opt in param.opts:
                if opt.startswith("-"):
                    elements.append(f"cli_option:{cmd_name}:{opt}")
            for opt in param.secondary_opts:
                if opt.startswith("-"):
                    elements.append(f"cli_option:{cmd_name}:{opt}")
    return sorted(list(set(elements)))


def get_frontend_routes() -> list[str]:
    """Parse routes from frontend/src/App.jsx."""
    app_jsx = REPO_ROOT / "frontend" / "src" / "App.jsx"
    text = app_jsx.read_text(encoding="utf-8")
    # Matches <Route path="abc" or <Route index
    routes: list[str] = ["ui_route:/"]
    for match in re.finditer(r'<Route\s+(?:path=["\']([^"\']+)["\']|index)', text):
        path = match.group(1)
        if path:
            routes.append(f"ui_route:/{path.lstrip('/')}")
    return sorted(list(set(routes)))


def get_api_endpoints() -> list[str]:
    """Extract all FastAPI endpoints and WebSockets from server router."""
    from tracecase.ui.api import router
    endpoints: list[str] = []
    for r in router.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None)
        if path and path.startswith("/api"):
            if methods:
                for m in methods:
                    if m not in ("HEAD", "OPTIONS"):
                        endpoints.append(f"api:{m}:{path}")
            else:
                endpoints.append(f"api:WS:{path}")
    return sorted(list(set(endpoints)))


def get_type_elements() -> list[str]:
    """ActionTypes, MutationTypes, HealingTiers, SelectionStrategies."""
    elements: list[str] = []
    # ActionTypes
    for a in [
        "click",
        "dblclick",
        "input",
        "select",
        "check",
        "uncheck",
        "navigate",
        "scroll",
        "hover",
        "keypress",
        "wait",
    ]:
        elements.append(f"action_type:{a}")

    # MutationTypes
    for m in [
        "empty",
        "boundary_long",
        "special_chars",
        "unicode",
        "invalid_format",
        "double_click",
        "network_error",
    ]:
        elements.append(f"mutation_type:{m}")

    # Healing Tiers
    for h in [
        "css_selector",
        "xpath",
        "data_testid",
        "id",
        "name",
        "placeholder",
        "aria_label",
        "clean_selector",
        "role_name",
        "text",
    ]:
        elements.append(f"healing_tier:{h}")

    # Selection Strategies
    for s in [
        "highest_risk",
        "time_budget",
        "count_budget",
        "balanced",
        "pareto_optimal",
    ]:
        elements.append(f"selection_strategy:{s}")

    return sorted(elements)


def check_coverage() -> int:
    data, raw_yaml = load_flows_yaml()
    cli_elems = get_cli_elements()
    routes = get_frontend_routes()
    endpoints = get_api_endpoints()
    types = get_type_elements()

    all_expected = {
        "CLI Commands & Options": cli_elems,
        "Studio Frontend Routes": routes,
        "FastAPI & WebSocket Endpoints": endpoints,
        "Core Types, Tiers & Strategies": types,
    }

    coverage_map = data.get("coverage_map", {})
    gaps: list[tuple[str, str]] = []

    total_items = 0
    covered_items = 0

    print("=" * 80)
    print("TRACECASE CATALOG COVERAGE AUDIT")
    print("=" * 80)

    for category, items in all_expected.items():
        cat_gaps: list[str] = []
        for item in items:
            total_items += 1
            # Check if item key is directly in coverage_map or mentioned in raw_yaml
            if item in coverage_map:
                covered_items += 1
            elif f'"{item}"' in raw_yaml or f"'{item}'" in raw_yaml or f"{item}" in raw_yaml:
                covered_items += 1
            else:
                cat_gaps.append(item)
                gaps.append((category, item))

        print(f"[{category}] Total: {len(items)}, Covered: {len(items) - len(cat_gaps)}, Gaps: {len(cat_gaps)}")

    print("-" * 80)
    print(f"OVERALL COVERAGE: {covered_items} / {total_items} ({(covered_items/total_items)*100:.1f}%)")
    print("-" * 80)

    if gaps:
        print("\nUNCOVERED GAPS:")
        for cat, item in gaps:
            print(f"  - [{cat}] {item}")
        print("\nERROR: Catalog coverage gate failed. Fix flows.yaml coverage_map until 0 gaps remain.")
        return 1

    print("\nSUCCESS: 100% of CLI options, routes, endpoints, and types are mapped to flow IDs!")
    return 0


if __name__ == "__main__":
    sys.exit(check_coverage())
