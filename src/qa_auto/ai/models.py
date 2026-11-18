"""Data models for AI-assisted QA analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from qa_auto.replay.models import Assertion


class Message(BaseModel):
    """Chat message for LLM interactions."""

    role: Literal["system", "user", "assistant"]
    content: str


class Annotation(BaseModel):
    """An analytical insight, warning, or risk note."""

    type: Literal["assertion_suggestion", "risk", "test_idea", "bug_report", "summary"]
    message: str
    severity: Literal["info", "warning", "error"] = "info"
    step_number: int | None = None
    provider: str | None = None
    model: str | None = None


class AnalysisResult(BaseModel):
    """Complete analysis artifact stored in analysis.json."""

    testcase_id: str
    testcase_name: str
    generated_at: datetime = Field(default_factory=datetime.now)
    provider: str
    model: str | None = None
    summary: str
    annotations: list[Annotation] = Field(default_factory=list)
    suggested_assertions: list[Assertion] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    negative_scenarios: list[str] = Field(default_factory=list)
