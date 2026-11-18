"""Data models for replay and assertions."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from qa_auto.replay.visual import VisualDiffResult

AssertionKind = Literal["status", "no_page_error", "url", "text", "visible", "custom"]
AssertionSource = Literal["derived", "ai", "manual"]
StepStatus = Literal["passed", "failed", "healed", "skipped", "error"]
ReplayStatus = Literal["passed", "failed", "error"]


class Assertion(BaseModel):
    """An expected outcome attached to a step."""

    kind: AssertionKind
    target: str | None = None
    expected: str | int | None = None
    step_number: int
    source: AssertionSource = "derived"
    confidence: float = 1.0
    enforced: bool = True


class AssertionResult(BaseModel):
    """The outcome of evaluating one assertion."""

    assertion: Assertion
    passed: bool
    actual: str | None = None
    message: str = ""


class StepResult(BaseModel):
    """The outcome of replaying one step."""

    number: int
    status: StepStatus
    selector_used: str | None = None
    healed_from: str | None = None
    assertions: list[AssertionResult] = Field(default_factory=list)
    screenshot: str | None = None
    visual_diff: VisualDiffResult | None = None
    error: str | None = None
    duration_ms: float = 0.0


class ReplayResult(BaseModel):
    """The full outcome of replaying a test case."""

    testcase_id: str
    started_at: datetime
    finished_at: datetime
    status: ReplayStatus
    exit_code: int
    steps: list[StepResult] = Field(default_factory=list)
    visual_diffs: list[VisualDiffResult] = Field(default_factory=list)
