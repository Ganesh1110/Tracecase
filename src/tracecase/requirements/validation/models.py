"""Data models and schemas for isolated Playwright sandbox validation (Phase 9.1.3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ValidationStatus = Literal["VERIFIED", "PARTIALLY_VERIFIED", "FAILED", "BLOCKED", "NOT_RUN"]
StepValidationStatus = Literal["PASSED", "FAILED", "BLOCKED", "SKIPPED"]


class SandboxSafetyPolicy(BaseModel):
    """Safety boundaries and execution permissions for sandbox dry-runs."""

    allow_destructive: bool = False
    allowed_origins: list[str] = Field(default_factory=list)
    action_timeout_ms: int = 10000
    navigation_timeout_ms: int = 20000
    max_steps: int = 50
    mask_credentials: bool = True


class AssertionValidationResult(BaseModel):
    """Outcome of validating a deterministic assertion in the sandbox."""

    assertion_type: str
    target_selector: str | None = None
    expected_value: Any = None
    actual_value: Any = None
    passed: bool = True
    source: Literal["evidence", "template", "manual"] = "evidence"
    requires_human_input: bool = False
    confidence: float = 1.0
    failure_reason: str | None = None
    evaluated_at: datetime = Field(default_factory=datetime.now)


class StepValidationResult(BaseModel):
    """Result of pre-checking and executing an individual journey step."""

    step_number: int
    action_type: str
    selector: str | None = None
    url: str | None = None
    status: StepValidationStatus = "PASSED"
    duration_ms: float = 0.0
    error_message: str | None = None
    screenshot_before: str | None = None
    screenshot_after: str | None = None
    target_uniqueness_count: int = 1
    is_visible: bool = True
    is_enabled: bool = True
    assertion_results: list[AssertionValidationResult] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)


class DraftValidationReport(BaseModel):
    """Complete validation record persisted for a specific draft version."""

    validation_id: str = Field(default_factory=lambda: f"val_{uuid.uuid4().hex[:8]}")
    draft_id: str
    draft_version: int = 1
    draft_content_hash: str | None = None
    browser: str = "chromium"
    headless: bool = True
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None
    overall_status: ValidationStatus = "NOT_RUN"
    step_results: list[StepValidationResult] = Field(default_factory=list)
    assertion_results: list[AssertionValidationResult] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    failure_summary: str | None = None
    environment: dict[str, Any] = Field(default_factory=dict)
    safety_policy: SandboxSafetyPolicy = Field(default_factory=SandboxSafetyPolicy)
    is_current_version: bool = True

    @property
    def passed_steps_count(self) -> int:
        return sum(1 for s in self.step_results if s.status == "PASSED")

    @property
    def failed_steps_count(self) -> int:
        return sum(1 for s in self.step_results if s.status == "FAILED")

    @property
    def blocked_steps_count(self) -> int:
        return sum(1 for s in self.step_results if s.status == "BLOCKED")
