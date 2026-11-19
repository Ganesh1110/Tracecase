"""Test Coverage Intelligence.

Analyzes the corpus of test cases across projects to detect untested workflows,
unasserted paths, input coverage, and provide actionable test gaps recommendations.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse
from pydantic import BaseModel, Field

from qa_auto.ai.selectors import audit_testcase_selectors
from qa_auto.models import TestCase


class RouteCoverage(BaseModel):
    """Coverage details for a unique URL route/path."""

    path: str
    host: str
    visit_count: int
    testcase_ids: list[str]


class CoverageIntelligenceResult(BaseModel):
    """Corpus coverage intelligence report."""

    total_testcases: int
    total_steps: int
    unique_routes_count: int
    routes: list[RouteCoverage]
    testcases_without_assertions: list[dict[str, str]]
    assertion_density: float = Field(
        description="Average number of assertions per test case"
    )
    untested_interaction_types: list[str] = Field(
        default_factory=list,
        description="Action types not exercised in the suite (e.g. dblclick, select, hover)",
    )
    fragile_selector_count: int
    total_selectors_analyzed: int
    coverage_score: int = Field(
        description="Overall test suite health and coverage score from 0 to 100"
    )
    risk_level: str = Field(description="Low, Moderate, High, or Critical")
    recommendations: list[dict[str, str]] = Field(default_factory=list)


def analyze_corpus_coverage(testcases: list[TestCase]) -> CoverageIntelligenceResult:
    """Analyze a collection of testcases to produce comprehensive coverage intelligence."""
    total_tc = len(testcases)
    if total_tc == 0:
        return CoverageIntelligenceResult(
            total_testcases=0,
            total_steps=0,
            unique_routes_count=0,
            routes=[],
            testcases_without_assertions=[],
            assertion_density=0.0,
            untested_interaction_types=["click", "input", "select", "check", "navigate"],
            fragile_selector_count=0,
            total_selectors_analyzed=0,
            coverage_score=0,
            risk_level="Critical",
            recommendations=[
                {
                    "type": "create_tests",
                    "severity": "high",
                    "title": "No Test Cases Recorded",
                    "message": "Record at least one critical user workflow using the Browser Recorder.",
                }
            ],
        )

    total_steps = 0
    route_map: dict[str, dict[str, Any]] = {}
    testcases_without_assertions: list[dict[str, str]] = []
    total_assertions = 0

    all_action_types = {"click", "input", "select", "check", "navigate", "scroll", "hover", "keypress"}
    exercised_action_types = set()

    total_selectors = 0
    fragile_selectors = 0

    for tc in testcases:
        steps_count = len(tc.steps)
        total_steps += steps_count
        assertions_count = len(tc.custom_assertions)
        total_assertions += assertions_count

        if assertions_count == 0:
            testcases_without_assertions.append(
                {"id": tc.id, "name": tc.name, "start_url": tc.start_url}
            )

        # Track route coverage from start_url
        if tc.start_url:
            parsed = urlparse(tc.start_url)
            host = parsed.netloc or "localhost"
            path = parsed.path or "/"
            route_key = f"{host}{path}"
            if route_key not in route_map:
                route_map[route_key] = {"path": path, "host": host, "count": 0, "tc_ids": set()}
            route_map[route_key]["count"] += 1
            route_map[route_key]["tc_ids"].add(tc.id)

        for step in tc.steps:
            exercised_action_types.add(step.action_type)
            if step.url:
                parsed = urlparse(step.url)
                host = parsed.netloc or "localhost"
                path = parsed.path or "/"
                route_key = f"{host}{path}"
                if route_key not in route_map:
                    route_map[route_key] = {"path": path, "host": host, "count": 0, "tc_ids": set()}
                route_map[route_key]["count"] += 1
                route_map[route_key]["tc_ids"].add(tc.id)

        # Audit selectors in testcase
        audit = audit_testcase_selectors(tc)
        total_selectors += audit.total_evaluated
        fragile_selectors += audit.fragile_count

    routes: list[RouteCoverage] = [
        RouteCoverage(
            path=info["path"],
            host=info["host"],
            visit_count=info["count"],
            testcase_ids=sorted(list(info["tc_ids"])),
        )
        for info in route_map.values()
    ]

    assertion_density = round(total_assertions / total_tc, 2) if total_tc > 0 else 0.0
    untested_actions = sorted(list(all_action_types - exercised_action_types))

    # Calculate overall coverage score (0 - 100)
    score = 100

    # Penalize for tests missing assertions
    unasserted_ratio = len(testcases_without_assertions) / total_tc if total_tc > 0 else 0
    score -= int(unasserted_ratio * 40)

    # Penalize for fragile selectors
    fragile_ratio = fragile_selectors / total_selectors if total_selectors > 0 else 0
    score -= int(fragile_ratio * 25)

    # Bonus / penalty for step volume & action diversity
    if len(exercised_action_types) < 3:
        score -= 15

    score = max(5, min(100, score))

    if score >= 80:
        risk_level = "Low"
    elif score >= 60:
        risk_level = "Moderate"
    elif score >= 40:
        risk_level = "High"
    else:
        risk_level = "Critical"

    # Actionable recommendations
    recommendations: list[dict[str, str]] = []
    if testcases_without_assertions:
        first_few = ", ".join(t["name"] for t in testcases_without_assertions[:3])
        recommendations.append(
            {
                "type": "missing_assertions",
                "severity": "high",
                "title": f"{len(testcases_without_assertions)} Test Cases Lack Assertions",
                "message": (
                    f"Test cases without assertions only verify that steps do not crash. "
                    f"Use AI Automatic Assertion Generation on: {first_few}"
                ),
            }
        )

    if fragile_selectors > 0:
        recommendations.append(
            {
                "type": "fragile_selectors",
                "severity": "medium",
                "title": f"{fragile_selectors} Fragile Selectors Detected",
                "message": (
                    "Hierarchical XPaths and dynamic IDs may fail during UI updates. "
                    "Review Selector Intelligence recommendations to apply resilient locators."
                ),
            }
        )

    if "input" not in exercised_action_types:
        recommendations.append(
            {
                "type": "input_coverage",
                "severity": "medium",
                "title": "No Form Inputs Tested",
                "message": "Add test cases that exercise form inputs, form submissions, and input validation.",
            }
        )

    return CoverageIntelligenceResult(
        total_testcases=total_tc,
        total_steps=total_steps,
        unique_routes_count=len(routes),
        routes=routes,
        testcases_without_assertions=testcases_without_assertions,
        assertion_density=assertion_density,
        untested_interaction_types=untested_actions,
        fragile_selector_count=fragile_selectors,
        total_selectors_analyzed=total_selectors,
        coverage_score=score,
        risk_level=risk_level,
        recommendations=recommendations,
    )
