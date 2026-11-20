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
