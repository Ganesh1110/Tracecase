"""Domain models for Git Change Intelligence and Test-to-Code Mapping (Phase 7.5)."""

from __future__ import annotations

from datetime import datetime
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


# ---------------------------------------------------------------------------
# Predictive Risk Scoring Models (Phase 7.5.3)
# ---------------------------------------------------------------------------

RiskTier = Literal["critical", "high", "medium", "low"]


class RiskScoringWeights(BaseModel):
    """Configurable weights for the risk calculation model."""
    weight_impact: float = Field(default=0.30, ge=0.0, le=1.0)
    weight_breakage: float = Field(default=0.25, ge=0.0, le=1.0)
    weight_failure_rate: float = Field(default=0.20, ge=0.0, le=1.0)
    weight_flakiness_recency: float = Field(default=0.15, ge=0.0, le=1.0)
    weight_change_magnitude: float = Field(default=0.10, ge=0.0, le=1.0)


class RiskFactorBreakdown(BaseModel):
    """Detailed breakdown of individual normalized signals contributing to risk."""
    change_impact_score: float = Field(ge=0.0, le=100.0)
    selector_breakage_score: float = Field(ge=0.0, le=100.0)
    historical_failure_score: float = Field(ge=0.0, le=100.0)
    flakiness_recency_score: float = Field(ge=0.0, le=100.0)
    change_magnitude_score: float = Field(ge=0.0, le=100.0)

    weighted_impact: float
    weighted_breakage: float
    weighted_failure: float
    weighted_flakiness: float
    weighted_magnitude: float

    has_history: bool = True
    history_run_count: int = 0
    recent_failure_detected: bool = False
    broken_selectors_count: int = 0
    modified_selectors_count: int = 0
    lines_changed: int = 0


class TestRiskScore(BaseModel):
    """Calculated risk assessment for a single test case given a code change."""
    __test__ = False
    testcase_id: str
    testcase_name: str
    project_id: str = "default_project"
    risk_score: float = Field(ge=0.0, le=100.0)
    risk_tier: RiskTier
    mapping_confidence: float = Field(ge=0.0, le=1.0)
    primary_risk_driver: str
    explanation: list[str] = Field(default_factory=list)
    breakdown: RiskFactorBreakdown
    affected_files: list[str] = Field(default_factory=list)
    matched_selectors: list[str] = Field(default_factory=list)
    matched_routes: list[str] = Field(default_factory=list)


class PredictiveRiskReport(BaseModel):
    """Report ranking all project test cases by predictive risk score."""
    changeset_commit: str | None = None
    changeset_branch: str | None = None
    weights: RiskScoringWeights
    total_tests_evaluated: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    scores: list[TestRiskScore] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Intelligent Regression Selection Models (Phase 7.5.4)
# ---------------------------------------------------------------------------

SelectionStrategy = Literal["time_budget", "risk_threshold", "top_k", "combined"]
DurationSource = Literal["measured_history", "recorded_testcase", "estimated_fallback"]
SelectionDecision = Literal["selected", "excluded", "budget_exception"]


class SelectedTestItem(BaseModel):
    """A test case considered during regression selection with decision and rationale."""
    __test__ = False
    testcase_id: str
    testcase_name: str
    risk_score: float = Field(ge=0.0, le=100.0)
    risk_tier: RiskTier
    mapping_confidence: float = Field(ge=0.0, le=1.0)
    estimated_duration_s: float = Field(ge=0.0)
    duration_source: DurationSource
    decision: SelectionDecision
    decision_reason: str
    value_score: float = 0.0
    primary_risk_driver: str = ""
    affected_files: list[str] = Field(default_factory=list)


class RegressionSelectionResult(BaseModel):
    """Complete output of an intelligent regression test selection operation."""
    __test__ = False
    id: str
    project_id: str = "default_project"
    commit_hash: str | None = None
    branch: str | None = None
    strategy: SelectionStrategy
    strategy_params: dict[str, Any] = Field(default_factory=dict)
    selected_test_ids: list[str] = Field(default_factory=list)
    excluded_test_ids: list[str] = Field(default_factory=list)
    budget_exception_test_ids: list[str] = Field(default_factory=list)
    tests: list[SelectedTestItem] = Field(default_factory=list)
    total_tests_considered: int = 0
    selected_count: int = 0
    excluded_count: int = 0
    budget_exception_count: int = 0
    time_budget_s: float | None = None
    estimated_total_duration_s: float = 0.0
    risk_coverage_pct: float = 0.0
    critical_coverage_pct: float = 0.0
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    disclaimer: str = (
        "Estimated execution times are projections based on historical execution statistics "
        "and recorded steps, not guaranteed durations."
    )


# ---------------------------------------------------------------------------
# Explainable Test Prioritization Models (Phase 7.5.5)
# ---------------------------------------------------------------------------

EvidenceType = Literal["observed", "heuristic", "missing"]
EvidenceCategory = Literal["git_diff", "selector", "route", "dependency", "history", "budget", "approval"]


class EvidenceItem(BaseModel):
    """An individual verifiable piece of evidence explaining test prioritization."""
    evidence_type: EvidenceType
    category: EvidenceCategory
    description: str
    detail: dict[str, Any] = Field(default_factory=dict)


class TestPrioritizationExplanation(BaseModel):
    """Deep, transparent explanation for why a test was selected, prioritized, or excluded."""
    __test__ = False
    testcase_id: str
    testcase_name: str
    decision: SelectionDecision
    original_decision: str | None = None
    decision_summary: str
    risk_score: float = Field(ge=0.0, le=100.0)
    risk_tier: RiskTier
    mapping_confidence: float = Field(ge=0.0, le=1.0)
    confidence_type: str = "exact"
    estimated_duration_s: float = Field(ge=0.0)
    duration_source: DurationSource
    primary_risk_driver: str
    observed_evidence: list[EvidenceItem] = Field(default_factory=list)
    heuristic_inferences: list[EvidenceItem] = Field(default_factory=list)
    missing_evidence: list[EvidenceItem] = Field(default_factory=list)
    risk_narrative: str
    selection_rationale: str
    affected_files: list[str] = Field(default_factory=list)
    matched_selectors: list[str] = Field(default_factory=list)
    matched_routes: list[str] = Field(default_factory=list)


class DecisionTraceRecord(BaseModel):
    """Auditable historical trace of an individual regression decision."""
    id: str
    selection_id: str
    project_id: str = "default_project"
    testcase_id: str
    testcase_name: str
    decision: str
    original_decision: str | None = None
    risk_score: float
    risk_tier: str
    mapping_confidence: float
    estimated_duration_s: float
    duration_source: str
    decision_summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    rationale: str
    user_override: bool = False
    override_reason: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class PrioritizationReport(BaseModel):
    """Complete human- and machine-readable prioritization and explanation report."""
    __test__ = False
    selection_id: str
    project_id: str = "default_project"
    commit_hash: str | None = None
    branch: str | None = None
    strategy: SelectionStrategy
    strategy_params: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    total_tests: int = 0
    selected_count: int = 0
    excluded_count: int = 0
    budget_exception_count: int = 0
    time_budget_s: float | None = None
    estimated_total_duration_s: float = 0.0
    risk_coverage_pct: float = 0.0
    critical_coverage_pct: float = 0.0
    functional_surface_coverage_pct: float = 0.0
    covered_files_count: int = 0
    total_impacted_files_count: int = 0
    explanations: list[TestPrioritizationExplanation] = Field(default_factory=list)
    markdown_report: str = ""
    disclaimer: str = (
        "Estimated execution times are projections based on historical execution statistics "
        "and recorded steps, not guaranteed durations. Mapping confidence reflects relationship "
        "certainty, not probability of failure."
    )


