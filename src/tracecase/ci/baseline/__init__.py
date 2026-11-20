"""Tracecase CI Baseline Management package."""

from tracecase.ci.baseline.executor import BaselineExecutor
from tracecase.ci.baseline.manager import BaselineManager, init_baseline_db
from tracecase.ci.baseline.models import (
    BaselineSnapshot,
    BaselineTestOutcome,
    compute_test_revision_hash,
)
from tracecase.ci.baseline.resolver import (
    BaselineMatchStatus,
    BaselineResolutionResult,
    BaselineResolver,
)

__all__ = [
    "BaselineExecutor",
    "BaselineManager",
    "init_baseline_db",
    "BaselineSnapshot",
    "BaselineTestOutcome",
    "compute_test_revision_hash",
    "BaselineMatchStatus",
    "BaselineResolutionResult",
    "BaselineResolver",
]
