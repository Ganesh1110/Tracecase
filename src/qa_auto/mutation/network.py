"""Network fault mutation strategy: inject simulated HTTP 500 error responses."""

from __future__ import annotations

import copy

from qa_auto.models import TestCase
from qa_auto.mutation.models import MutatedTestCase, MutationMetadata


def mutate_network_faults(testcase: TestCase) -> list[MutatedTestCase]:
    """Inspect recorded network requests and synthesize error responses (HTTP 500)."""
    mutations: list[MutatedTestCase] = []

    for step in testcase.steps:
        for req_idx, req in enumerate(step.network_requests):
            # Only mutate successful requests (HTTP 2xx or 3xx)
            if req.status is not None and req.status >= 400:
                continue

            mutated_tc = copy.deepcopy(testcase)
            mutated_tc.id = f"{testcase.id}_mut_net_{step.number}_{req_idx}_500"
            mutated_tc.name = f"{testcase.name} [Negative: 500 error on step {step.number}]"

            # In step requests
            for target_step in mutated_tc.steps:
                if target_step.number == step.number and req_idx < len(
                    target_step.network_requests
                ):
                    target_req = target_step.network_requests[req_idx]
                    target_req.status = 500
                    target_req.response_body = '{"error": "Simulated Internal Server Error"}'
                    break

            meta = MutationMetadata(
                mutation_type="network_error",
                strategy="network",
                target_step=step.number,
                description=f"Inject HTTP 500 on {req.url} at step {step.number}",
                original_value=str(req.status or 200),
                mutated_value="500",
            )
            mutations.append(MutatedTestCase(testcase=mutated_tc, metadata=meta))

    return mutations
