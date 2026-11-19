"""Smart Test Variation Generator.

Synthesizes boundary, security, invalid format, and edge-case test case variations
from existing recorded test cases.
"""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse
from pydantic import BaseModel, Field

from qa_auto.ai.provider import Provider
from qa_auto.models import Step, TestCase

logger = logging.getLogger("qa_auto.ai.variations")

VariationStrategy = Literal["boundary", "security", "invalid_format", "edge_cases"]


def is_safe_test_environment(url: str) -> bool:
    """Verify that target URL is strictly isolated to a local or test environment."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return (
        hostname in {"localhost", "127.0.0.1", "::1", "0.0.0.0", "testserver"}
        or hostname.endswith(".local")
        or hostname.endswith(".test")
    )

# Standard deterministic payloads for fast and reliable test generation
BOUNDARY_PAYLOADS: list[dict[str, str]] = [
    {"value": "", "label": "Empty string", "rationale": "Verifies required field validation"},
    {"value": "   ", "label": "Whitespace only", "rationale": "Checks trim and non-empty enforcement"},
    {
        "value": "A" * 256,
        "label": "256-char long string",
        "rationale": "Tests buffer limits and standard max-length handling",
    },
    {
        "value": "🔥🚀⚡️💎",
        "label": "Unicode / Multi-byte characters",
        "rationale": "Tests utf-8 encoding and database storage",
    },
]

SECURITY_PAYLOADS: list[dict[str, str]] = [
    {
        "value": "' OR '1'='1' --",
        "label": "SQL Injection probe",
        "rationale": "Tests for SQL injection vulnerability in form input",
    },
    {
        "value": "<script>alert('xss')</script>",
        "label": "XSS script probe",
        "rationale": "Verifies HTML escaping and prevents script execution",
    },
    {
        "value": '"><img src=x onerror=alert(1)>',
        "label": "XSS attribute breakout",
        "rationale": "Tests attribute sanitization and DOM-based injection",
    },
]

FORMAT_PAYLOADS: list[dict[str, str]] = [
    {
        "value": "not-an-email",
        "label": "Invalid email syntax",
        "rationale": "Verifies email regex / validation",
    },
    {"value": "-9999", "label": "Negative number", "rationale": "Tests negative numeric validation"},
    {"value": "abc!@#", "label": "Special chars in numeric field", "rationale": "Checks type casting"},
]


class VariationMutation(BaseModel):
    """Details of a single step mutation."""

    step_number: int
    field_name: str = "input_value"
    original_value: str
    mutated_value: str
    strategy: VariationStrategy
    rationale: str


class GeneratedVariation(BaseModel):
    """A generated test case variation with metadata."""

    variation_id: str
    name: str
    strategy: VariationStrategy
    rationale: str
    mutations: list[VariationMutation] = Field(default_factory=list)
    test_case: TestCase


def generate_heuristic_variations(
    testcase: TestCase,
    strategies: list[VariationStrategy] | None = None,
    max_variations_per_strategy: int = 2,
    allow_security_probes: bool = False,
) -> list[GeneratedVariation]:
    """Deterministically generate test variations from input steps in a testcase."""
    target_strategies = strategies or ["boundary", "security", "invalid_format"]
    results: list[GeneratedVariation] = []

    # Find input steps
    input_steps: list[tuple[int, Step]] = [
        (idx, s)
        for idx, s in enumerate(testcase.steps)
        if s.action_type == "input" and s.input_value is not None
    ]

    if not input_steps:
        return results

    for strategy in target_strategies:
        if strategy == "boundary":
            payloads = BOUNDARY_PAYLOADS[:max_variations_per_strategy]
        elif strategy == "security":
            if not is_safe_test_environment(testcase.start_url) and not allow_security_probes:
                logger.warning(
                    "Security variations skipped: '%s' is not an isolated test environment.",
                    testcase.start_url,
                )
                continue
            payloads = SECURITY_PAYLOADS[:max_variations_per_strategy]
        elif strategy == "invalid_format":
            payloads = FORMAT_PAYLOADS[:max_variations_per_strategy]
        else:
            payloads = BOUNDARY_PAYLOADS[:max_variations_per_strategy]

        for p_idx, payload in enumerate(payloads):
            # Clone test case
            new_tc = copy.deepcopy(testcase)
            new_id = f"{testcase.id}-var-{strategy[:4]}-{p_idx + 1}-{uuid.uuid4().hex[:6]}"
            new_tc.id = new_id
            new_tc.name = f"{testcase.name} [{strategy.capitalize()}: {payload['label']}]"
            new_tc.description = (
                f"Synthesized {strategy} test variation based on {testcase.name}.\n"
                f"Objective: {payload['rationale']}"
            )
            new_tc.created_at = datetime.now()

            mutations: list[VariationMutation] = []
            for step_idx, orig_step in input_steps:
                # Mutate step input value
                orig_val = orig_step.input_value or ""
                mutated_val = payload["value"]

                # Apply to step
                target_step = new_tc.steps[step_idx]
                target_step.input_value = mutated_val
                target_step.description_short = (
                    f"Input '{mutated_val[:20]}' into {target_step.element.selector if target_step.element else 'element'}"
                )
                target_step.description_detailed = (
                    f"Mutated for {strategy} testing ({payload['label']}): set value to '{mutated_val}'"
                )

                mutations.append(
                    VariationMutation(
                        step_number=target_step.number,
                        original_value=orig_val,
                        mutated_value=mutated_val,
                        strategy=strategy,
                        rationale=payload["rationale"],
                    )
                )

            results.append(
                GeneratedVariation(
                    variation_id=new_id,
                    name=new_tc.name,
                    strategy=strategy,
                    rationale=payload["rationale"],
                    mutations=mutations,
                    test_case=new_tc,
                )
            )

    return results


async def generate_smart_variations(
    testcase: TestCase,
    strategies: list[VariationStrategy] | None = None,
    provider: Provider | None = None,
    allow_security_probes: bool = False,
) -> list[GeneratedVariation]:
    """Generate smart test case variations using heuristics or an AI provider."""
    # Heuristics provide reliable, deterministic variations adhering strictly to Pydantic schemas
    variations = generate_heuristic_variations(
        testcase, strategies=strategies, allow_security_probes=allow_security_probes
    )
    return variations
