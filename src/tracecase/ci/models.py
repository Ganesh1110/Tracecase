"""Data models for CI/CD integration, Quality Gates, and CI execution results."""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Any, Literal
from pydantic import BaseModel, Field


class CIExitCode(IntEnum):
    """Deterministic Unix exit codes for tracecase ci command."""
    PASSED = 0               # Quality gate passed
    GATE_FAILED = 1          # Quality gate failed (policy violations, test failures)
    CONFIG_ERROR = 2         # Configuration, argument, or git environment error
    INFRASTRUCTURE_ERROR = 3 # Internal Tracecase execution or browser crash error


QualityGateStatus = Literal["PASSED", "FAILED", "WARNING"]


class QualityGateRuleViolation(BaseModel):
    """Specific rule violation detected during Quality Gate evaluation."""
    rule_name: str
    severity: Literal["critical", "high", "medium", "low"]
    message: str
    actual_value: Any = None
    threshold_value: Any = None


class QualityGateResult(BaseModel):
    """Comprehensive verdict from the Quality Gate evaluation."""
    status: QualityGateStatus
    passed: bool
    policy_name: str
    summary: str
    violations: list[QualityGateRuleViolation] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    evaluated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class CIRunResult(BaseModel):
    """End-to-end outcome of a tracecase ci execution."""
    run_id: str
    project_id: str = "default_project"
    commit_hash: str | None = None
    base_ref: str | None = None
    target_ref: str | None = None
    branch: str | None = None
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    duration_seconds: float = 0.0
    exit_code: int = 0
    gate_result: QualityGateResult
    selection_id: str | None = None
    batch_id: str | None = None
    total_considered: int = 0
    selected_count: int = 0
    executed_count: int = 0
    selected_test_ids: list[str] = Field(default_factory=list)
    executed_test_ids: list[str] = Field(default_factory=list)
    test_results: list[dict[str, Any]] = Field(default_factory=list)
    reports: dict[str, str] = Field(default_factory=dict)
    drift_summary: dict[str, Any] | None = None
    error_category: Literal["quality_gate", "config", "infrastructure", "none"] = "none"
    error_detail: str | None = None
