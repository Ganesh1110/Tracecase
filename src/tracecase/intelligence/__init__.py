"""Tracecase Intelligence Package.

Provides Git change intelligence, code impact mapping, predictive risk scoring,
and intelligent regression test prioritization.
"""

from tracecase.intelligence.git_analyzer import GitChangeAnalyzer
from tracecase.intelligence.models import (
    ChangedFile,
    ChangeType,
    DiffHunk,
    GitChangeSet,
    GitChangeSummary,
)

__all__ = [
    "ChangedFile",
    "ChangeType",
    "DiffHunk",
    "GitChangeAnalyzer",
    "GitChangeSet",
    "GitChangeSummary",
]
