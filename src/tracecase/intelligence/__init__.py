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
    GitChangeSet,
    GitChangeSummary,
    ImpactedTestResult,
    RelationType,
    TestCodeMapping,
    TestCoverageProfile,
)

__all__ = [
    "ChangedFile",
    "ChangeType",
    "CodeImpactReport",
    "CodebaseFileIndex",
    "DiffHunk",
    "GitChangeAnalyzer",
    "GitChangeSet",
    "GitChangeSummary",
    "ImpactedTestResult",
    "RelationType",
    "TestCodeMapping",
    "TestCoverageProfile",
    "TestReferenceExtractor",
    "TestToCodeGraph",
    "TestToCodeMapper",
]
