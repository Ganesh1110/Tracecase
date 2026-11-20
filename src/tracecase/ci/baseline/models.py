"""Data models for baseline execution results, snapshots, and revision hashes."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any
from pydantic import BaseModel, Field

from tracecase.models import TestCase


def compute_test_revision_hash(testcase: TestCase) -> str:
    """Compute a deterministic hash representing the structural definition of a test case.
    
    If locators, steps, URLs, or assertions change between base and PR, this hash changes,
    signaling test definition drift.
    """
    elements = []
    for s in testcase.steps:
        step_dict = {
            "order": s.number,
            "action": s.action_type,
            "url": s.url,
            "selector": s.element.selector if s.element else None,
            "xpath": s.element.xpath if s.element else None,
            "input_value": s.input_value,
        }
        elements.append(step_dict)

    assertions_data = getattr(testcase, "custom_assertions", [])
    raw = json.dumps(
        {
            "id": testcase.id,
            "start_url": testcase.start_url,
            "steps": elements,
            "assertions": assertions_data,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class BaselineTestOutcome(BaseModel):
    """Execution outcome of a single test case within a baseline snapshot."""
    testcase_id: str
    testcase_name: str
    status: str  # "passed", "failed", "flaky", "error", "skipped"
    duration_ms: float = 0.0
    error_message: str | None = None
    retry_count: int = 0
    test_revision_hash: str = ""
    run_id: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class BaselineSnapshot(BaseModel):
    """Persisted baseline execution record for a specific commit and environment."""
    id: str
    project_id: str = "default_project"
    commit_hash: str
    branch: str | None = None
    browser: str = "chromium"
    environment: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    total_tests: int = 0
    passed_count: int = 0
    failed_count: int = 0
    flaky_count: int = 0
    error_count: int = 0
    outcomes: dict[str, BaselineTestOutcome] = Field(default_factory=dict)

    def get_outcome(self, testcase_id: str) -> BaselineTestOutcome | None:
        """Retrieve recorded outcome for a test case."""
        return self.outcomes.get(testcase_id)
