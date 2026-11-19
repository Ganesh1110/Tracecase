"""Domain models for Git Change Intelligence and Test-to-Code Mapping (Phase 7.5)."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

ChangeType = Literal["added", "modified", "deleted", "renamed"]

RelationType = Literal[
    "exact_route",
    "exact_selector",
    "api_endpoint",
    "route_prefix",
    "dependency_import",
    "heuristic_symbol",
    "ai_suggested",
]


class DiffHunk(BaseModel):
    """A contiguous hunk of lines modified in a unified diff."""
    old_start: int = 0
    old_lines: int = 0
    new_start: int = 0
    new_lines: int = 0
    heading: str = ""
    lines: list[str] = Field(default_factory=list)


class ChangedFile(BaseModel):
    """Detailed change metrics and extracted semantic entities for a single file."""
    path: str
    old_path: str | None = None
    change_type: ChangeType = "modified"
    additions: int = 0
    deletions: int = 0
    hunks: list[DiffHunk] = Field(default_factory=list)
    changed_functions: list[str] = Field(default_factory=list)
    changed_classes: list[str] = Field(default_factory=list)
    # Complete lists (for backward compatibility)
    changed_selectors: list[str] = Field(default_factory=list)
    changed_routes: list[str] = Field(default_factory=list)
    # Explicit breakdown of added vs removed entities
    added_selectors: list[str] = Field(default_factory=list)
    removed_selectors: list[str] = Field(default_factory=list)
    added_routes: list[str] = Field(default_factory=list)
    removed_routes: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class GitChangeSummary(BaseModel):
    """High-level summary of code modifications across the entire changeset."""
    total_files_changed: int = 0
    total_additions: int = 0
    total_deletions: int = 0
    files_by_type: dict[str, int] = Field(default_factory=dict)
    total_changed_routes: list[str] = Field(default_factory=list)
    total_changed_selectors: list[str] = Field(default_factory=list)
    total_changed_symbols: list[str] = Field(default_factory=list)
    total_removed_routes: list[str] = Field(default_factory=list)
    total_removed_selectors: list[str] = Field(default_factory=list)


class GitChangeSet(BaseModel):
    """Complete collection of code changes, diff hunks, and extracted semantic impact."""
    repo_path: str
    base_ref: str | None = None
    target_ref: str | None = None
    current_commit: str | None = None
    current_branch: str | None = None
    is_dirty: bool = False
    files: list[ChangedFile] = Field(default_factory=list)
    summary: GitChangeSummary = Field(default_factory=GitChangeSummary)


# ---------------------------------------------------------------------------
# Test-to-Code Mapping Models (Phase 7.5.2)
# ---------------------------------------------------------------------------

class TestCoverageProfile(BaseModel):
    """Extracted behavioral footprint of a recorded test case."""
    __test__ = False
    testcase_id: str
    testcase_name: str
    start_url: str
    page_routes: list[str] = Field(default_factory=list)
    api_endpoints: list[str] = Field(default_factory=list)
    selectors_used: list[str] = Field(default_factory=list)
    step_selector_map: dict[int, list[str]] = Field(default_factory=dict)
    action_types: list[str] = Field(default_factory=list)


class TestCodeMapping(BaseModel):
    """A verified, evidence-backed link between a testcase and an application code file."""
    __test__ = False
    id: str
    testcase_id: str
    testcase_name: str
    project_id: str = "default_project"
    file_path: str
    relation_type: RelationType
    matched_entity: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ImpactedTestResult(BaseModel):
    """A test identified as affected by code changes with ranked evidence."""
    testcase_id: str
    testcase_name: str
    project_id: str = "default_project"
    max_confidence: float = Field(ge=0.0, le=1.0)
    primary_reason: str
    affected_reasons: list[str] = Field(default_factory=list)
    affected_files: list[str] = Field(default_factory=list)
    matched_selectors: list[str] = Field(default_factory=list)
    matched_routes: list[str] = Field(default_factory=list)
    mappings: list[TestCodeMapping] = Field(default_factory=list)


class CodeImpactReport(BaseModel):
    """Complete analysis mapping git changes to impacted regression tests."""
    repo_path: str
    changeset_summary: GitChangeSummary
    impacted_tests: list[ImpactedTestResult] = Field(default_factory=list)
    total_impacted_tests: int = 0
    total_coverage_mappings: int = 0
