"""Mutation engine orchestrator: generates and exports negative test variations."""

from __future__ import annotations

from pathlib import Path

from tracecase.models import TestCase
from tracecase.mutation.actions import mutate_actions
from tracecase.mutation.inputs import mutate_inputs
from tracecase.mutation.models import MutatedTestCase
from tracecase.mutation.network import mutate_network_faults


class MutationEngine:
    """Orchestrates mutation strategies and exports synthesized negative test cases."""

    def __init__(self) -> None:
        pass

    def generate(
        self,
        testcase: TestCase,
        strategies: list[str] | None = None,
        limit: int = 20,
    ) -> list[MutatedTestCase]:
        """Generate negative test case variations using selected strategies."""
        selected = strategies or ["inputs", "actions", "network"]
        results: list[MutatedTestCase] = []

        if "inputs" in selected or "all" in selected:
            results.extend(mutate_inputs(testcase))

        if "actions" in selected or "all" in selected:
            results.extend(mutate_actions(testcase))

        if "network" in selected or "all" in selected:
            results.extend(mutate_network_faults(testcase))

        return results[:limit]

    def export_mutations(
        self,
        mutations: list[MutatedTestCase],
        output_dir: Path | str,
    ) -> list[Path]:
        """Write mutated test cases and metadata to disk."""
        base_dir = Path(output_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []

        for m in mutations:
            item_dir = base_dir / m.testcase.id
            item_dir.mkdir(parents=True, exist_ok=True)

            tc_path = item_dir / "testcase.json"
            tc_path.write_text(m.testcase.model_dump_json(indent=2), encoding="utf-8")

            meta_path = item_dir / "mutation_meta.json"
            meta_path.write_text(m.metadata.model_dump_json(indent=2), encoding="utf-8")

            paths.append(tc_path)

        return paths
