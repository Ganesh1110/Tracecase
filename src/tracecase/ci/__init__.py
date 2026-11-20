"""Tracecase Continuous Quality Gates & CI/CD Integration Package."""

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
from tracecase.ci.config import CIRunnerConfig
from tracecase.ci.drift.analytics import DriftAnalytics
from tracecase.ci.drift.classifier import RegressionDriftClassifier
from tracecase.ci.drift.comparator import RegressionDriftComparator
from tracecase.ci.drift.models import (
    DriftAnalysisResult,
    DriftClassification,
    TestDriftItem,
)
from tracecase.ci.gate import QualityGateEvaluator
from tracecase.ci.models import (
    CIExitCode,
    CIRunResult,
    QualityGateResult,
    QualityGateRuleViolation,
    QualityGateStatus,
)
from tracecase.ci.policy import (
    LENIENT_POLICY,
    PERMISSIVE_POLICY,
    STANDARD_POLICY,
    STRICT_POLICY,
    QualityGatePolicy,
    get_policy,
)
from tracecase.ci.runner import CIRunner

__all__ = [
    "CIRunner",
    "CIRunnerConfig",
    "CIExitCode",
    "CIRunResult",
    "QualityGateEvaluator",
    "QualityGatePolicy",
    "QualityGateResult",
    "QualityGateRuleViolation",
    "QualityGateStatus",
    "STRICT_POLICY",
    "STANDARD_POLICY",
    "LENIENT_POLICY",
    "PERMISSIVE_POLICY",
    "get_policy",
    "BaselineExecutor",
    "BaselineManager",
    "init_baseline_db",
    "BaselineSnapshot",
    "BaselineTestOutcome",
    "compute_test_revision_hash",
    "BaselineMatchStatus",
    "BaselineResolutionResult",
    "BaselineResolver",
    "DriftAnalytics",
    "RegressionDriftClassifier",
    "RegressionDriftComparator",
    "DriftAnalysisResult",
    "DriftClassification",
    "TestDriftItem",
]
