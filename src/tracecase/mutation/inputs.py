"""Input mutation strategy: generate negative form inputs and edge cases."""

from __future__ import annotations

import copy

from tracecase.models import TestCase
from tracecase.mutation.models import MutatedTestCase, MutationMetadata


def mutate_inputs(testcase: TestCase) -> list[MutatedTestCase]:
    """Inspect input steps and generate negative variations (empty, boundary, SQLi/XSS, unicode)."""
    mutations: list[MutatedTestCase] = []

    for step in testcase.steps:
        if step.action_type != "input" or step.input_value is None:
            continue

        original_val = step.input_value

        # 1. Empty string
        mutations.append(
            _create_input_mutation(
                testcase,
                step.number,
                mutation_type="empty",
                original_value=original_val,
                mutated_value="",
                description=f"Empty input at step {step.number}",
            )
        )

        # 2. Boundary overflow string (2048 chars)
        boundary_val = "A" * 2048
        mutations.append(
            _create_input_mutation(
                testcase,
                step.number,
                mutation_type="boundary_long",
                original_value=original_val,
                mutated_value=boundary_val,
                description=f"Boundary overflow (2048 chars) at step {step.number}",
            )
        )

        # 3. Special characters & injection probe
        probe_val = "<script>alert(1)</script>' OR '1'='1"
        mutations.append(
            _create_input_mutation(
                testcase,
                step.number,
                mutation_type="special_chars",
                original_value=original_val,
                mutated_value=probe_val,
                description=f"Special characters & injection probe at step {step.number}",
            )
        )

        # 4. Unicode & emoji edge cases
        unicode_val = "🔥 測試 ᚠᛇᚻ 🚀"
        mutations.append(
            _create_input_mutation(
                testcase,
                step.number,
                mutation_type="unicode",
                original_value=original_val,
                mutated_value=unicode_val,
                description=f"Unicode and emoji characters at step {step.number}",
            )
        )

        # 5. Invalid format (email / phone / number)
        if "@" in original_val:
            invalid_val = "not-an-email"
        elif original_val.isdigit():
            invalid_val = "not-a-number"
        else:
            invalid_val = "!@#$%^&*"

        mutations.append(
            _create_input_mutation(
                testcase,
                step.number,
                mutation_type="invalid_format",
                original_value=original_val,
                mutated_value=invalid_val,
                description=f"Malformed format at step {step.number}",
            )
        )

    return mutations


def _create_input_mutation(
    base_tc: TestCase,
    step_number: int,
    mutation_type: str,
    original_value: str,
    mutated_value: str,
    description: str,
) -> MutatedTestCase:
    mutated_tc = copy.deepcopy(base_tc)
    mutated_tc.id = f"{base_tc.id}_mut_{step_number}_{mutation_type}"
    mutated_tc.name = f"{base_tc.name} [Negative: {mutation_type} on step {step_number}]"

    for step in mutated_tc.steps:
        if step.number == step_number:
            step.input_value = mutated_value
            step.description_detailed = f"{step.description_detailed} (Mutated: {mutation_type})"
            break

    meta = MutationMetadata(
        mutation_type=mutation_type,  # type: ignore[arg-type]
        strategy="inputs",
        target_step=step_number,
        description=description,
        original_value=original_value,
        mutated_value=mutated_value,
    )
    return MutatedTestCase(testcase=mutated_tc, metadata=meta)
