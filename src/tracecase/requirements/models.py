"""Data models for requirement-driven test generation (Phase 9.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# Re-export exploration synthesis models for clean traceability and single source of truth
from tracecase.exploration.models import (
    SynthesizedAssertion,
    SynthesizedStep,
    TestJourneyDraft,
)

CriterionType = Literal["given_when_then", "rule", "scenario", "constraint", "heuristic"]
RequirementFormat = Literal[
    "user_story", "gherkin", "acceptance_criteria", "openapi", "natural_language"
]
ValidationStatus = Literal["verified", "partially_verified", "failed", "blocked", "not_run"]
IntentActionType = Literal[
    "navigate", "click", "input", "check", "select", "wait", "assert", "submit"
]


class AcceptanceCriterion(BaseModel):
    """An individual acceptance criterion or verification rule extracted from requirements."""

    id: str = Field(default_factory=lambda: f"ac_{uuid.uuid4().hex[:6]}")
    description: str
    criterion_type: CriterionType = "rule"
    given: str | None = None
    when: str | None = None
    then: str | None = None
    tags: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class TestIntent(BaseModel):
    """A concrete, executable intention derived from a requirement or acceptance criterion."""

    __test__ = False

    id: str = Field(default_factory=lambda: f"intent_{uuid.uuid4().hex[:6]}")
    summary: str
    target_action: IntentActionType = "navigate"
    target_element_hint: str | None = None
    input_value_hint: str | None = None
    expected_outcome: str | None = None
    criterion_id: str | None = None
    source: RequirementFormat = "user_story"
    is_destructive: bool = False
    preconditions: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class RequirementSpec(BaseModel):
    """Structured requirement specification containing extracted semantics, criteria, and test intents."""

    id: str = Field(default_factory=lambda: f"req_{uuid.uuid4().hex[:8]}")
    title: str
    raw_text: str
    format: RequirementFormat
    user_role: str | None = None
    capability: str | None = None
    benefit: str | None = None
    preconditions: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    test_intents: list[TestIntent] = Field(default_factory=list)
    target_routes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def total_intents(self) -> int:
        return len(self.test_intents)

    @property
    def total_criteria(self) -> int:
        return len(self.acceptance_criteria)
