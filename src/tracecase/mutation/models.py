"""Data models for test case mutation and negative scenario synthesis."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from tracecase.models import TestCase

MutationStrategyType = Literal["inputs", "actions", "network"]
MutationType = Literal[
    "empty",
    "boundary_long",
    "special_chars",
    "unicode",
    "invalid_format",
    "double_click",
    "network_error",
]


class MutationMetadata(BaseModel):
    """Metadata describing a synthesized negative test variation."""

    mutation_type: MutationType
    strategy: MutationStrategyType
    target_step: int
    description: str
    original_value: str | None = None
    mutated_value: str | None = None


class MutatedTestCase(BaseModel):
    """A synthesized test case paired with its mutation metadata."""

    testcase: TestCase
    metadata: MutationMetadata = Field(description="Details on how this test was mutated")
