"""Machine-readable JSON manifest generator for CI/CD runs."""

from __future__ import annotations

from typing import Any
from tracecase.ci.models import CIRunResult, QualityGateResult


def generate_ci_json_manifest(
    run_result: CIRunResult,
    gate_result: QualityGateResult,
) -> dict[str, Any]:
    """Generate structured JSON manifest for CI pipeline automation and artifact storage."""
    return {
        "schema_version": "1.0.0",
        "generator": "Tracecase CI Execution Engine & Quality Gate",
        "run_id": run_result.run_id,
        "project_id": run_result.project_id,
        "commit_hash": run_result.commit_hash,
        "base_ref": run_result.base_ref,
        "target_ref": run_result.target_ref,
        "branch": run_result.branch,
        "started_at": run_result.started_at,
        "finished_at": run_result.finished_at,
        "duration_seconds": round(run_result.duration_seconds, 2),
        "exit_code": run_result.exit_code,
        "gate": {
            "status": gate_result.status,
            "passed": gate_result.passed,
            "policy": gate_result.policy_name,
            "summary": gate_result.summary,
            "violations": [v.model_dump() for v in gate_result.violations],
            "metrics": gate_result.metrics,
        },
        "selection": {
            "selection_id": run_result.selection_id,
            "total_considered": run_result.total_considered,
            "selected_count": run_result.selected_count,
            "executed_count": run_result.executed_count,
            "selected_test_ids": run_result.selected_test_ids,
            "executed_test_ids": run_result.executed_test_ids,
        },
        "test_results": run_result.test_results,
        "reports": run_result.reports,
    }
