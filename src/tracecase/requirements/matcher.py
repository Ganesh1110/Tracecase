"""Deterministic Intent-to-Evidence Matching layer for Phase 9.1.2."""

from __future__ import annotations

import logging
import re
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from tracecase.requirements.evidence import EvidenceCatalog, ObservedEvidenceRecord
from tracecase.requirements.models import TestIntent

logger = logging.getLogger("tracecase.requirements.matcher")

ResolutionStatus = Literal["resolved", "unresolved", "ambiguous"]
AmbiguityStatus = Literal["unambiguous", "ambiguous", "none"]


class IntentMatchResult(BaseModel):
    """Deterministic match result connecting a TestIntent to observed evidence."""

    intent_id: str
    matched_evidence_ids: list[str] = Field(default_factory=list)
    primary_evidence_id: str | None = None
    match_method: str = "none"
    selector_confidence: float = 0.0
    ambiguity_status: AmbiguityStatus = "none"
    resolution_status: ResolutionStatus = "unresolved"
    explanation: str = ""
    is_destructive: bool = False
    destructive_reason: str | None = None


def _clean_tokens(text: str) -> set[str]:
    """Extract lowercase alphanumeric tokens ignoring common stop words."""
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\s]", " ", text.lower())
    stop_words = {
        "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "with",
        "user", "customer", "clicks", "click", "enters", "enter", "into", "field",
        "button", "should", "must", "can", "is", "be", "page", "screen"
    }
    return {token for token in cleaned.split() if len(token) > 2 and token not in stop_words}


def match_intent_to_evidence(
    intent: TestIntent,
    catalog: EvidenceCatalog,
) -> IntentMatchResult:
    """
    Deterministically match a TestIntent against observed evidence in the catalog.
    
    Guarantees:
    1. If no observed evidence matches, marks unresolved with selector_confidence 0.0.
    2. If multiple equally plausible candidates exist, marks ambiguous.
    3. Never invents synthetic selectors or references nonexistent evidence IDs.
    4. Separates selector confidence from assertion confidence.
    """
    hint = (intent.target_element_hint or intent.summary).strip()
    hint_lower = hint.lower()
    intent_tokens = _clean_tokens(hint)

    # 1. Navigation intent matching
    if intent.target_action == "navigate":
        # Extract route path from hint
        routes_in_hint = re.findall(r"\/[a-zA-Z0-9_\-\/\.\?\=\&\%]+", hint)
        target_path = routes_in_hint[0] if routes_in_hint else hint

        norm_target = EvidenceCatalog._normalize_route(target_path)
        matching_routes: list[ObservedEvidenceRecord] = []

        for record in catalog.all_records():
            if record.evidence_source == "page_route":
                rec_norm = EvidenceCatalog._normalize_route(record.route)
                if rec_norm == norm_target or (len(norm_target) > 1 and norm_target in rec_norm):
                    matching_routes.append(record)

        if len(matching_routes) == 1:
            rec = matching_routes[0]
            return IntentMatchResult(
                intent_id=intent.id,
                matched_evidence_ids=[rec.evidence_id],
                primary_evidence_id=rec.evidence_id,
                match_method="route_match",
                selector_confidence=1.0,
                ambiguity_status="unambiguous",
                resolution_status="resolved",
                explanation=f"Exact route match to observed page {rec.route} ({rec.evidence_id}).",
                is_destructive=intent.is_destructive or rec.is_destructive,
            )
        elif len(matching_routes) > 1:
            return IntentMatchResult(
                intent_id=intent.id,
                matched_evidence_ids=[r.evidence_id for r in matching_routes],
                primary_evidence_id=None,
                match_method="route_match_ambiguous",
                selector_confidence=0.5,
                ambiguity_status="ambiguous",
                resolution_status="ambiguous",
                explanation=f"Multiple observed routes match '{target_path}': {[r.route for r in matching_routes]}.",
                is_destructive=intent.is_destructive,
            )
        else:
            return IntentMatchResult(
                intent_id=intent.id,
                matched_evidence_ids=[],
                primary_evidence_id=None,
                match_method="none",
                selector_confidence=0.0,
                ambiguity_status="none",
                resolution_status="unresolved",
                explanation=f"No observed route matching '{target_path}' found in exploration graph.",
                is_destructive=intent.is_destructive,
            )

    # 2. Interactive and DOM element matching (click, input, submit, select, check, wait, assert)
    scored_candidates: list[tuple[float, str, ObservedEvidenceRecord]] = []

    for record in catalog.all_records():
        if record.evidence_source == "page_route":
            continue

        score = 0.0
        primary_method = "token_overlap"

        acc_name = (record.accessible_name or "").strip().lower()
        obs_text = (record.observed_text or "").strip().lower()
        name_attr = str(record.observed_attributes.get("name", "")).strip().lower()
        ph_attr = str(record.observed_attributes.get("placeholder", "")).strip().lower()
        sel = (record.selector or "").lower()

        # Exact accessible name match
        if acc_name and (acc_name == hint_lower or acc_name == hint_lower.replace("button", "").strip()):
            score += 10.0
            primary_method = "exact_accessible_name"
        # Exact observed text match
        elif obs_text and (obs_text == hint_lower or obs_text == hint_lower.replace("button", "").strip()):
            score += 8.5
            primary_method = "exact_text"
        # Exact attribute match (name or placeholder)
        elif (name_attr and name_attr == hint_lower) or (ph_attr and ph_attr == hint_lower):
            score += 7.5
            primary_method = "attribute_match"
        else:
            # Substring checks (bidirectional)
            if hint_lower and ((acc_name and (hint_lower in acc_name or acc_name in hint_lower)) or (obs_text and (hint_lower in obs_text or obs_text in hint_lower))):
                score += 5.5
                primary_method = "substring_match"
            elif hint_lower and (hint_lower in name_attr or hint_lower in ph_attr or (name_attr and name_attr in hint_lower)):
                score += 4.5
                primary_method = "attribute_substring"

        # Action-type compatibility weighting
        if intent.target_action == "input":
            if record.evidence_source == "form_field" or record.element_tag in ("input", "textarea"):
                score += 2.5
        elif intent.target_action == "click":
            if record.element_tag in ("button", "a") or "button" in sel or record.evidence_source == "form_submit":
                score += 2.0
        elif intent.target_action == "submit":
            if record.evidence_source == "form_submit" or record.element_type == "submit" or "submit" in sel:
                score += 3.5
        elif intent.target_action == "select":
            if record.element_tag == "select" or record.element_type == "select":
                score += 3.5
        elif intent.target_action == "check":
            if record.element_type in ("checkbox", "radio"):
                score += 3.5

        # Search token overlap
        overlap = intent_tokens.intersection(record.searchable_tokens)
        if overlap:
            score += len(overlap) * 1.5

        if score >= 4.0:
            scored_candidates.append((score, primary_method, record))

    if not scored_candidates:
        return IntentMatchResult(
            intent_id=intent.id,
            matched_evidence_ids=[],
            primary_evidence_id=None,
            match_method="none",
            selector_confidence=0.0,
            ambiguity_status="none",
            resolution_status="unresolved",
            explanation=f"No observed DOM evidence matches target hint '{hint}'.",
            is_destructive=intent.is_destructive,
        )

    # Sort descending by score
    scored_candidates.sort(key=lambda item: item[0], reverse=True)
    top_score, top_method, top_record = scored_candidates[0]

    # Check for ambiguity: multiple top candidates within 0.5 of each other with identical high confidence
    top_ties = [c for c in scored_candidates if c[0] >= top_score - 0.5]
    if len(top_ties) > 1:
        return IntentMatchResult(
            intent_id=intent.id,
            matched_evidence_ids=[c[2].evidence_id for c in top_ties],
            primary_evidence_id=None,
            match_method=f"{top_method}_ambiguous",
            selector_confidence=0.5,
            ambiguity_status="ambiguous",
            resolution_status="ambiguous",
            explanation=f"Ambiguous: {len(top_ties)} candidates matched hint '{hint}' with similar scores ({top_score}).",
            is_destructive=intent.is_destructive or any(c[2].is_destructive for c in top_ties),
        )

    # Resolved single candidate
    confidence = min(round(top_score / 10.0, 2), 1.0)
    is_dest = intent.is_destructive or top_record.is_destructive
    dest_reason = top_record.destructive_reason if top_record.is_destructive else None

    return IntentMatchResult(
        intent_id=intent.id,
        matched_evidence_ids=[top_record.evidence_id],
        primary_evidence_id=top_record.evidence_id,
        match_method=top_method,
        selector_confidence=confidence,
        ambiguity_status="unambiguous",
        resolution_status="resolved",
        explanation=f"Resolved via {top_method} to observed {top_record.element_tag} ({top_record.evidence_id}) with selector '{top_record.selector}'.",
        is_destructive=is_dest,
        destructive_reason=dest_reason,
    )
