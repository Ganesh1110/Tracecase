"""Quality Gate policies and predefined policy profiles for CI/CD gates."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class QualityGatePolicy(BaseModel):
    """Configurable criteria determining whether a pull request or commit passes quality gates."""
    name: str = "standard"
    fail_on_critical_breakage: bool = True
    max_failure_rate_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    max_flakiness_pct: float = Field(default=15.0, ge=0.0, le=100.0)
    block_on_budget_exceptions: bool = True
    min_surface_coverage_pct: float = Field(default=70.0, ge=0.0, le=100.0)
    fail_on_execution_errors: bool = True
    fail_on_unmapped_changes: bool = False
    # Baseline comparison & regression drift policies (Phase 8.3)
    baseline_enabled: bool = False
    require_valid_baseline: bool = False
    max_new_failures: int = 0
    max_new_flakiness_pct: float = Field(default=5.0, ge=0.0, le=100.0)
    allow_pre_existing_failures: bool = True
    block_on_unknown_baseline: bool = False
    compare_same_browser: bool = True


# Predefined named policy profiles
STRICT_POLICY = QualityGatePolicy(
    name="strict",
    fail_on_critical_breakage=True,
    max_failure_rate_pct=0.0,
    max_flakiness_pct=0.0,
    block_on_budget_exceptions=True,
    min_surface_coverage_pct=85.0,
    fail_on_execution_errors=True,
    fail_on_unmapped_changes=True,
    baseline_enabled=True,
    require_valid_baseline=True,
    max_new_failures=0,
    max_new_flakiness_pct=0.0,
    allow_pre_existing_failures=False,
    block_on_unknown_baseline=True,
    compare_same_browser=True,
)

STANDARD_POLICY = QualityGatePolicy(
    name="standard",
    fail_on_critical_breakage=True,
    max_failure_rate_pct=0.0,
    max_flakiness_pct=15.0,
    block_on_budget_exceptions=True,
    min_surface_coverage_pct=70.0,
    fail_on_execution_errors=True,
    fail_on_unmapped_changes=False,
    baseline_enabled=True,
    require_valid_baseline=False,
    max_new_failures=0,
    max_new_flakiness_pct=5.0,
    allow_pre_existing_failures=True,
    block_on_unknown_baseline=False,
    compare_same_browser=True,
)

LENIENT_POLICY = QualityGatePolicy(
    name="lenient",
    fail_on_critical_breakage=True,
    max_failure_rate_pct=10.0,
    max_flakiness_pct=30.0,
    block_on_budget_exceptions=False,
    min_surface_coverage_pct=50.0,
    fail_on_execution_errors=True,
    fail_on_unmapped_changes=False,
    baseline_enabled=True,
    require_valid_baseline=False,
    max_new_failures=1,
    max_new_flakiness_pct=15.0,
    allow_pre_existing_failures=True,
    block_on_unknown_baseline=False,
    compare_same_browser=True,
)

PERMISSIVE_POLICY = QualityGatePolicy(
    name="permissive",
    fail_on_critical_breakage=False,
    max_failure_rate_pct=100.0,
    max_flakiness_pct=100.0,
    block_on_budget_exceptions=False,
    min_surface_coverage_pct=0.0,
    fail_on_execution_errors=False,
    fail_on_unmapped_changes=False,
    baseline_enabled=False,
    allow_pre_existing_failures=True,
)

NAMED_POLICIES: dict[str, QualityGatePolicy] = {
    "strict": STRICT_POLICY,
    "standard": STANDARD_POLICY,
    "lenient": LENIENT_POLICY,
    "permissive": PERMISSIVE_POLICY,
}


def get_policy(name_or_policy: str | QualityGatePolicy | dict[str, Any] | None) -> QualityGatePolicy:
    """Resolve a QualityGatePolicy from a named profile, dictionary, or existing instance."""
    if name_or_policy is None:
        return STANDARD_POLICY
    if isinstance(name_or_policy, QualityGatePolicy):
        return name_or_policy
    if isinstance(name_or_policy, dict):
        return QualityGatePolicy(**name_or_policy)
    key = str(name_or_policy).strip().lower()
    return NAMED_POLICIES.get(key, STANDARD_POLICY)
