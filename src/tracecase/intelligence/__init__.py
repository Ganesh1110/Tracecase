"""Tracecase Intelligence Package.

Provides Git change intelligence, code impact mapping, predictive risk scoring,
and intelligent regression test prioritization.
"""

from tracecase.intelligence.code_mapper import (
    CodebaseFileIndex,
    TestReferenceExtractor,
    TestToCodeGraph,
    TestToCodeMapper,
)
from tracecase.intelligence.git_analyzer import GitChangeAnalyzer
from tracecase.intelligence.models import (
    ChangedFile,
    ChangeType,
    CodeImpactReport,
    DiffHunk,
    DurationSource,
    EvidenceCategory,
    EvidenceItem,
    EvidenceType,
    GitChangeSet,
    GitChangeSummary,
    ImpactedTestResult,
    PredictiveRiskReport,
    PrioritizationReport,
    RegressionSelectionResult,
    RelationType,
    RiskFactorBreakdown,
    RiskScoringWeights,
    RiskTier,
    SelectedTestItem,
    SelectionDecision,
    SelectionStrategy,
    TestCodeMapping,
    TestCoverageProfile,
    TestPrioritizationExplanation,
    TestRiskScore,
)
from tracecase.intelligence.explainer import PrioritizationExplainer
from tracecase.intelligence.risk_scorer import PredictiveRiskScorer
from tracecase.intelligence.selector import (
    IntelligentRegressionSelector,
    parse_duration_string,
)

__all__ = [
    "ChangedFile",
    "ChangeType",
    "CodeImpactReport",
    "CodebaseFileIndex",
    "DiffHunk",
    "DurationSource",
    "EvidenceCategory",
    "EvidenceItem",
    "EvidenceType",
    "GitChangeAnalyzer",
    "GitChangeSet",
    "GitChangeSummary",
    "ImpactedTestResult",
    "IntelligentRegressionSelector",
    "PredictiveRiskReport",
    "PredictiveRiskScorer",
    "PrioritizationExplainer",
    "PrioritizationReport",
    "RegressionSelectionResult",
    "RelationType",
    "RiskFactorBreakdown",
    "RiskScoringWeights",
    "RiskTier",
    "SelectedTestItem",
    "SelectionDecision",
    "SelectionStrategy",
    "TestCodeMapping",
    "TestCoverageProfile",
    "TestPrioritizationExplanation",
    "TestReferenceExtractor",
    "TestRiskScore",
    "TestToCodeGraph",
    "TestToCodeMapper",
    "parse_duration_string",
]
