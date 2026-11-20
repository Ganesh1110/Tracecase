"""Data models and schemas for Autonomous Exploration and Application Navigation Graphs."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import BaseModel, Field


def normalize_url(url: str, strip_query: bool = False) -> str:
    """
    Normalize URL for graph node representation and duplicate detection.
    
    Strips trailing slashes, fragments, and tracking parameters.
    """
    try:
        parsed = urlparse(url.strip())
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        
        # Remove standard default ports
        if (scheme == "http" and netloc.endswith(":80")) or (scheme == "https" and netloc.endswith(":443")):
            netloc = netloc.rsplit(":", 1)[0]
            
        path = parsed.path.rstrip("/") or "/"
        
        # Strip tracking query params
        if strip_query:
            query = ""
        else:
            filtered_query = []
            tracking_prefixes = ("utm_", "fbclid", "gclid", "ref", "source")
            for k, v in parse_qsl(parsed.query, keep_blank_values=True):
                if not any(k.lower().startswith(p) for p in tracking_prefixes):
                    filtered_query.append((k, v))
            filtered_query.sort(key=lambda item: item[0])
            query = urlencode(filtered_query)
            
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return url.strip()


def compute_state_fingerprint(url: str, title: str, element_selectors: list[str]) -> str:
    """Compute state fingerprint to detect dynamic DOM state changes and loops."""
    normalized_path = urlparse(url).path.rstrip("/") or "/"
    clean_title = (title or "").strip().lower()
    sample_selectors = ",".join(sorted(element_selectors[:30]))
    raw = f"{normalized_path}|{clean_title}|{sample_selectors}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class FormField(BaseModel):
    """Schema of an input field within an HTML form."""

    name: str = ""
    field_type: str = "text"
    selector: str
    label: str | None = None
    required: bool = False
    placeholder: str | None = None
    default_value: str | None = None


class FormSchema(BaseModel):
    """Discovered form structure and safety classification."""

    form_id: str
    action: str | None = None
    method: str = "POST"
    selector: str
    fields: list[FormField] = Field(default_factory=list)
    submit_button_selector: str | None = None
    submit_button_text: str | None = None
    is_destructive: bool = False
    destructive_reason: str | None = None


class InteractiveElement(BaseModel):
    """Interactive DOM element discovered during exploration."""

    element_id: str
    tag_name: str
    selector: str
    element_type: str | None = None
    text: str | None = None
    aria_label: str | None = None
    name: str | None = None
    placeholder: str | None = None
    href: str | None = None
    is_visible: bool = True
    is_interactive: bool = True
    is_destructive: bool = False
    destructive_reason: str | None = None


class PageTransition(BaseModel):
    """Directed edge representing navigation or interaction between application states."""

    id: str
    exploration_id: str
    source_url: str
    target_url: str
    action_type: Literal["navigate", "click_link", "click_button", "submit_form", "input_change"]
    selector: str | None = None
    element_text: str | None = None
    is_safe: bool = True
    duration_ms: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)


class PageNode(BaseModel):
    """Graph node representing a discovered unique page or DOM state."""

    id: str
    exploration_id: str
    url: str
    normalized_url: str
    title: str = ""
    depth: int = 0
    state_fingerprint: str
    status_code: int = 200
    forms: list[FormSchema] = Field(default_factory=list)
    interactive_elements: list[InteractiveElement] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    screenshot_path: str | None = None
    discovered_at: datetime = Field(default_factory=datetime.now)


class AppNavigationGraph(BaseModel):
    """Application Navigation Graph containing discovered nodes and state transitions."""

    exploration_id: str
    start_url: str
    nodes: dict[str, PageNode] = Field(default_factory=dict)
    transitions: list[PageTransition] = Field(default_factory=list)

    @property
    def total_pages(self) -> int:
        return len(self.nodes)

    @property
    def total_transitions(self) -> int:
        return len(self.transitions)

    @property
    def total_forms(self) -> int:
        return sum(len(node.forms) for node in self.nodes.values())

    def get_node(self, normalized_url: str) -> PageNode | None:
        return self.nodes.get(normalized_url)


class ExplorationConfig(BaseModel):
    """Execution parameters and safety limits for autonomous exploration."""

    start_url: str
    project_id: str = "default_project"
    allowed_origins: list[str] = Field(default_factory=list)
    max_depth: int = Field(default=3, ge=1, le=10)
    max_pages: int = Field(default=20, ge=1, le=100)
    max_interactions: int = Field(default=50, ge=1, le=200)
    execution_timeout: float = Field(default=120.0, ge=10.0, le=600.0)
    headless: bool = True
    browser: Literal["chromium", "firefox", "webkit"] = "chromium"
    allow_destructive: bool = False
    auth_cookies: list[dict[str, Any]] | None = None
    auth_headers: dict[str, str] | None = None


class SynthesizedAssertion(BaseModel):
    """Assertion generated from exploration evidence or marked for human review."""

    assertion_type: Literal[
        "url_matches", "title_matches", "element_visible", "no_page_error", "text_matches"
    ]
    target_selector: str | None = None
    expected_value: Any = None
    source: Literal["evidence", "template", "manual"] = "evidence"
    requires_human_input: bool = False
    evidence_provenance: dict[str, Any] = Field(default_factory=dict)
    review_prompt: str | None = None
    assertion_confidence: float = 1.0
    validation_outcome: Literal["passed", "failed", "untested"] = "untested"


class SynthesizedStep(BaseModel):
    """Synthesized test step with evidence linkage and verified assertions."""

    number: int
    action_type: Literal["navigate", "click", "input", "check", "select", "wait"]
    selector: str | None = None
    url: str | None = None
    input_value: str | None = None
    description_short: str = ""
    description_detailed: str = ""
    source_node_id: str | None = None
    screenshot_path: str | None = None
    assertions: list[SynthesizedAssertion] = Field(default_factory=list)
    target_status: Literal["resolved", "unresolved", "ambiguous"] = "resolved"
    selector_confidence: float = 1.0
    intent_id: str | None = None
    criterion_id: str | None = None


class TestJourneyDraft(BaseModel):
    """Test journey synthesized from navigation graph, pending human review and approval."""

    __test__ = False

    id: str
    exploration_id: str
    project_id: str = "default_project"
    name: str
    description: str = ""
    journey_type: Literal["navigation", "form_interaction", "deep_journey"] = "navigation"
    priority: Literal["high", "medium", "low"] = "medium"
    start_url: str
    steps: list[SynthesizedStep] = Field(default_factory=list)
    status: Literal["pending", "approved", "rejected"] = "pending"
    approved_testcase_id: str | None = None
    rejection_reason: str | None = None
    requires_human_input: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    reviewed_at: datetime | None = None
    requirement_id: str | None = None
    validation_status: Literal["verified", "partially_verified", "failed", "blocked", "not_run"] = "not_run"
    validation_details: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    content_hash: str | None = None


class TestJourneyDraftSnapshot(BaseModel):
    """Immutable version snapshot of a synthesized draft journey."""

    __test__ = False

    id: str
    draft_id: str
    version: int
    content_hash: str
    name: str
    description: str = ""
    journey_type: str = "navigation"
    start_url: str = ""
    steps: list[dict[str, Any]] = Field(default_factory=list)
    requires_human_input: bool = False
    changelog: str = ""
    author: str = "system"
    created_at: datetime = Field(default_factory=datetime.now)


class DraftDiffStep(BaseModel):
    """Detailed diff for a single step between two draft versions."""

    step_number: int
    diff_type: Literal["added", "removed", "modified", "unchanged"]
    change_summary: str
    old_step: dict[str, Any] | None = None
    new_step: dict[str, Any] | None = None


class DraftDiffSummary(BaseModel):
    """Structured step-by-step diff summary between two draft versions."""

    draft_id: str
    base_version: int
    target_version: int
    base_content_hash: str
    target_content_hash: str
    step_diffs: list[DraftDiffStep] = Field(default_factory=list)
    has_changes: bool = False

