"""Data models for regression drift detection, classification, and metrics."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field


class DriftClassification(StrEnum):
    """Categorization of a test case outcome between baseline and PR."""
    NEW_REGRESSION = "new_regression"                    # Base: passed -> PR: failed
    PRE_EXISTING_FAILURE = "pre_existing_failure"        # Base: failed -> PR: failed
    FIXED_REGRESSION = "fixed_regression"                # Base: failed -> PR: passed
    PARTIAL_RECOVERY = "partial_recovery"                # Base: failed -> PR: flaky
    STABLE_PASS = "stable_pass"                          # Base: passed -> PR: passed
    NEWLY_FLAKY = "newly_flaky"                          # Base: passed -> PR: flaky
    PERSISTENT_FLAKY = "persistent_flaky"                # Base: flaky  -> PR: flaky
    UNKNOWN_BASELINE_FAILURE = "unknown_baseline_failure"# Base: missing -> PR: failed
    NEW_TEST_PASS = "new_test_pass"                      # Base: missing -> PR: passed
    INFRASTRUCTURE_ERROR = "infrastructure_error"        # PR: error (browser/system fault)
    SKIPPED = "skipped"                                  # PR: skipped or cancelled


class TestDriftItem(BaseModel):
    """Drift analysis details for a single test case comparison."""
    __test__ = False
    testcase_id: str
    testcase_name: str
    classification: DriftClassification
    pr_status: str
    base_status: str | None = None
    test_definition_drift: bool = False
    base_duration_ms: float | None = None
    pr_duration_ms: float = 0.0
    duration_delta_ms: float | None = None
    pr_error_message: str | None = None
    base_error_message: str | None = None
    explanation: str = ""


class DriftAnalysisResult(BaseModel):
    """Comprehensive regression drift analysis between baseline and current PR run."""
    run_id: str
    project_id: str = "default_project"
    base_commit: str | None = None
    pr_commit: str | None = None
    browser: str = "chromium"
    baseline_found: bool = True
    baseline_match_type: str = "exact"  # "exact", "branch", "none"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Classification Counts
    total_compared: int = 0
    new_regressions_count: int = 0
    pre_existing_failures_count: int = 0
    fixed_regressions_count: int = 0
    partial_recoveries_count: int = 0
    newly_flaky_count: int = 0
    persistent_flaky_count: int = 0
    stable_passes_count: int = 0
    unknown_baseline_failures_count: int = 0
    infrastructure_errors_count: int = 0
    tests_with_definition_drift_count: int = 0

    # Timing Metrics
    total_base_duration_ms: float = 0.0
    total_pr_duration_ms: float = 0.0
    duration_delta_ms: float = 0.0
    duration_drift_pct: float = 0.0

    # Detailed items
    items: list[TestDriftItem] = Field(default_factory=list)

    @property
    def has_new_regressions(self) -> bool:
        return self.new_regressions_count > 0

    @property
    def newly_flaky_pct(self) -> float:
        if self.total_compared == 0:
            return 0.0
        return round((self.newly_flaky_count / self.total_compared) * 100.0, 2)
