"""Action sequence mutation strategy: simulate rapid double clicks and race conditions."""

from __future__ import annotations

import copy

from tracecase.models import Step, TestCase
from tracecase.mutation.models import MutatedTestCase, MutationMetadata


def mutate_actions(testcase: TestCase) -> list[MutatedTestCase]:
    """Inspect click steps and synthesize duplicate rapid click variations."""
    mutations: list[MutatedTestCase] = []

    for idx, step in enumerate(testcase.steps):
        if step.action_type != "click":
            continue

        mutated_tc = copy.deepcopy(testcase)
        mutated_tc.id = f"{testcase.id}_mut_action_{step.number}_double_click"
        mutated_tc.name = f"{testcase.name} [Negative: double_click on step {step.number}]"

        # Duplicate the click step right after the original
        dup_step = copy.deepcopy(step)
        dup_step.description_short = f"{step.description_short} (rapid double click)"
        dup_step.description_detailed = (
            f"{step.description_detailed} (Duplicate rapid click to test idempotency/race)"
        )

        new_steps: list[Step] = []
        for i, s in enumerate(mutated_tc.steps):
            new_steps.append(s)
            if i == idx:
                new_steps.append(dup_step)

        # Renumber all steps sequentially
        for new_num, s in enumerate(new_steps, 1):
            s.number = new_num

        mutated_tc.steps = new_steps
        mutated_tc.total_steps = len(new_steps)

        meta = MutationMetadata(
            mutation_type="double_click",
            strategy="actions",
            target_step=step.number,
            description=f"Duplicate rapid click on step {step.number}",
            original_value=step.action_type,
            mutated_value="double_click",
        )
        mutations.append(MutatedTestCase(testcase=mutated_tc, metadata=meta))

    return mutations
