"""Evidence retrieval layer for Phase 9.1.2: Extracts and indexes observed application evidence."""

from __future__ import annotations

import logging
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from tracecase.exploration.models import AppNavigationGraph, PageNode, normalize_url
from tracecase.requirements.models import RequirementSpec

logger = logging.getLogger("tracecase.requirements.evidence")

EvidenceSourceType = Literal[
    "dom_element",
    "form_field",
    "form_submit",
    "transition_link",
    "page_route",
    "network_response",
]


class ObservedEvidenceRecord(BaseModel):
    """Structured record of an actually observed DOM element, route, or state from exploration data."""

    evidence_id: str
    page_id: str
    route: str
    element_tag: str
    observed_text: str | None = None
    accessible_name: str | None = None
    observed_attributes: dict[str, Any] = Field(default_factory=dict)
    selector: str | None = None
    element_type: str | None = None
    observation_timestamp: str | None = None
    evidence_source: EvidenceSourceType = "dom_element"
    is_destructive: bool = False
    destructive_reason: str | None = None

    @property
    def searchable_tokens(self) -> set[str]:
        """Normalized search tokens for deterministic matching."""
        tokens = set()
        for text in (
            self.observed_text,
            self.accessible_name,
            self.element_tag,
            self.element_type,
            self.selector,
        ):
            if text:
                tokens.update(text.lower().replace("#", " ").replace(".", " ").replace("-", " ").replace("_", " ").split())
        for k, v in self.observed_attributes.items():
            if isinstance(v, str):
                tokens.update(v.lower().split())
        return {t for t in tokens if len(t) > 1}


class EvidenceCatalog:
    """Indexed catalog of all observed application evidence from exploration data."""

    def __init__(self, records: list[ObservedEvidenceRecord] | None = None) -> None:
        self._records_by_id: dict[str, ObservedEvidenceRecord] = {}
        self._records_by_route: dict[str, list[ObservedEvidenceRecord]] = {}
        self._records_by_page_id: dict[str, list[ObservedEvidenceRecord]] = {}
        if records:
            for r in records:
                self.add_record(r)

    def add_record(self, record: ObservedEvidenceRecord) -> None:
        """Add record and index by id, route, and page."""
        self._records_by_id[record.evidence_id] = record

        norm_route = self._normalize_route(record.route)
        if norm_route not in self._records_by_route:
            self._records_by_route[norm_route] = []
        self._records_by_route[norm_route].append(record)

        if record.page_id not in self._records_by_page_id:
            self._records_by_page_id[record.page_id] = []
        self._records_by_page_id[record.page_id].append(record)

    @staticmethod
    def _normalize_route(url_or_path: str) -> str:
        try:
            path = urlparse(url_or_path).path.rstrip("/") or "/"
            return path.lower()
        except Exception:
            return url_or_path.lower().strip()

    def get_evidence(self, evidence_id: str) -> ObservedEvidenceRecord | None:
        """Retrieve evidence by unique ID."""
        return self._records_by_id.get(evidence_id)

    def contains_id(self, evidence_id: str) -> bool:
        """Check if an evidence ID actually exists in the observed catalog."""
        return evidence_id in self._records_by_id

    def filter_by_route(self, route: str) -> list[ObservedEvidenceRecord]:
        """Return all evidence observed on a particular route path."""
        norm = self._normalize_route(route)
        return self._records_by_route.get(norm, [])

    def all_records(self) -> list[ObservedEvidenceRecord]:
        """Return all indexed evidence records."""
        return list(self._records_by_id.values())

    def total_evidence(self) -> int:
        return len(self._records_by_id)


def extract_evidence_catalog(
    graph: AppNavigationGraph,
    spec: RequirementSpec | None = None,
) -> EvidenceCatalog:
    """
    Extract structured evidence catalog exclusively from actual exploration data.
    
    Guarantees:
    1. Only includes evidence actually present in the graph nodes, forms, and transitions.
    2. Never constructs evidence from assumptions or speculative elements.
    """
    catalog = EvidenceCatalog()

    for node_id, node in graph.nodes.items():
        norm_path = EvidenceCatalog._normalize_route(node.url)
        timestamp_str = node.discovered_at.isoformat() if hasattr(node, "discovered_at") and node.discovered_at else None

        # 1. Page route evidence
        catalog.add_record(
            ObservedEvidenceRecord(
                evidence_id=f"ev_page_{node.id}",
                page_id=node.id,
                route=node.url,
                element_tag="page",
                observed_text=node.title or norm_path,
                accessible_name=node.title,
                observed_attributes={"url": node.url, "normalized_url": node.normalized_url},
                selector=None,
                element_type="route",
                observation_timestamp=timestamp_str,
                evidence_source="page_route",
            )
        )

        # 2. Interactive DOM elements
        for el in node.interactive_elements:
            acc_name = el.aria_label or el.text
            catalog.add_record(
                ObservedEvidenceRecord(
                    evidence_id=f"ev_el_{el.element_id}",
                    page_id=node.id,
                    route=node.url,
                    element_tag=el.tag_name,
                    observed_text=el.text,
                    accessible_name=acc_name,
                    observed_attributes={
                        "name": el.name,
                        "placeholder": el.placeholder,
                        "href": el.href,
                        "is_visible": el.is_visible,
                    },
                    selector=el.selector,
                    element_type=el.element_type or el.tag_name,
                    observation_timestamp=timestamp_str,
                    evidence_source="dom_element",
                    is_destructive=el.is_destructive,
                    destructive_reason=el.destructive_reason,
                )
            )

        # 3. Form elements and submit controls
        for form in node.forms:
            form_dest = form.is_destructive
            form_reason = form.destructive_reason

            for field in form.fields:
                catalog.add_record(
                    ObservedEvidenceRecord(
                        evidence_id=f"ev_field_{form.form_id}_{field.name or field.selector}",
                        page_id=node.id,
                        route=node.url,
                        element_tag="input",
                        observed_text=field.label or field.placeholder or field.name,
                        accessible_name=field.label or field.placeholder,
                        observed_attributes={
                            "name": field.name,
                            "field_type": field.field_type,
                            "placeholder": field.placeholder,
                            "required": field.required,
                            "form_id": form.form_id,
                        },
                        selector=field.selector,
                        element_type=field.field_type,
                        observation_timestamp=timestamp_str,
                        evidence_source="form_field",
                        is_destructive=form_dest,
                        destructive_reason=form_reason,
                    )
                )

            # Submit button
            if form.submit_button_selector:
                submit_text = form.submit_button_text or "Submit"
                catalog.add_record(
                    ObservedEvidenceRecord(
                        evidence_id=f"ev_submit_{form.form_id}",
                        page_id=node.id,
                        route=node.url,
                        element_tag="button",
                        observed_text=submit_text,
                        accessible_name=submit_text,
                        observed_attributes={"form_id": form.form_id, "action": form.action},
                        selector=form.submit_button_selector,
                        element_type="submit",
                        observation_timestamp=timestamp_str,
                        evidence_source="form_submit",
                        is_destructive=form_dest,
                        destructive_reason=form_reason,
                    )
                )

    # 4. Transitions
    for trans in graph.transitions:
        if trans.selector and not catalog.contains_id(f"ev_trans_{trans.id}"):
            catalog.add_record(
                ObservedEvidenceRecord(
                    evidence_id=f"ev_trans_{trans.id}",
                    page_id=trans.exploration_id,
                    route=trans.source_url,
                    element_tag="a" if "link" in trans.action_type else "button",
                    observed_text=trans.element_text,
                    accessible_name=trans.element_text,
                    observed_attributes={"target_url": trans.target_url, "action_type": trans.action_type},
                    selector=trans.selector,
                    element_type="transition",
                    evidence_source="transition_link",
                    is_destructive=not trans.is_safe,
                )
            )

    return catalog
