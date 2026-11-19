"""Requirements-driven test planner and navigation graph mapping engine."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any
from urllib.parse import urlparse

from qa_auto.ai.models import Message
from qa_auto.ai.provider import get_provider
from qa_auto.exploration.models import (
    AppNavigationGraph,
    FormSchema,
    PageNode,
    PageTransition,
    SynthesizedAssertion,
    SynthesizedStep,
    TestJourneyDraft,
    normalize_url,
)
from qa_auto.exploration.synthesizer import _get_safe_default_input_value

logger = logging.getLogger("qa_auto.exploration.planner")


def _extract_intent_tokens(requirement: str) -> set[str]:
    """Extract normalized lowercase keyword tokens from natural language requirement."""
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\s]", " ", requirement.lower())
    stop_words = {
        "as", "a", "an", "the", "user", "i", "want", "to", "so", "that",
        "and", "or", "in", "on", "at", "by", "for", "with", "from", "be",
        "can", "should", "must", "of", "it", "my", "our", "their", "into"
    }
    return {token for token in cleaned.split() if len(token) > 2 and token not in stop_words}


def plan_requirement_against_graph(
    requirement: str,
    graph: AppNavigationGraph,
    project_id: str = "default_project",
    llm_provider: Any = None,
) -> dict[str, Any]:
    """
    Map natural language requirement to navigation graph, compute coverage gaps, and synthesize a draft.
    
    Guarantees:
    1. Highlights missing concepts that cannot be proven from exploration evidence.
    2. Respects safety boundaries: refuses to synthesize destructive actions.
    3. Clearly tags assertions as verified evidence vs requiring human input.
    4. Reports provider honesty (whether LLM was used or heuristic fallback).
    """
    req_clean = requirement.strip()
    if not req_clean:
        return {
            "requirement_text": requirement,
            "coverage_score": 0.0,
            "covered_concepts": [],
            "missing_concepts": [{"concept": "none", "status": "missing", "reason": "Empty requirement."}],
            "matched_routes": [],
            "synthesized_draft": None,
            "can_generate_test": False,
            "provider_used": "heuristic",
            "is_llm_generated": False,
        }

    tokens = _extract_intent_tokens(req_clean)
    provider_used = "heuristic"
    is_llm = False

    # 1. Score matching nodes in the navigation graph
    scored_nodes: list[tuple[float, PageNode]] = []
    matched_forms: list[tuple[float, FormSchema, PageNode]] = []

    for norm_url, node in graph.nodes.items():
        node_score = 0.0
        path = urlparse(node.url).path.lower()
        title = (node.title or "").lower()

        # Check path and title matches
        for token in tokens:
            if token in path:
                node_score += 3.0
            if token in title:
                node_score += 2.0

        # Check interactive elements
        for el in node.interactive_elements:
            el_text = (el.text or el.aria_label or el.name or "").lower()
            for token in tokens:
                if token in el_text:
                    node_score += 1.5

        if node_score > 0:
            scored_nodes.append((node_score, node))

        # Check forms on this node
        for form in node.forms:
            form_score = 0.0
            form_text = f"{form.form_id} {form.action or ''}".lower()
            for token in tokens:
                if token in form_text:
                    form_score += 4.0
            for field in form.fields:
                f_name = f"{field.name} {field.label or ''} {field.placeholder or ''}".lower()
                for token in tokens:
                    if token in f_name:
                        form_score += 3.0

            if form_score > 0:
                matched_forms.append((form_score, form, node))

    scored_nodes.sort(key=lambda item: item[0], reverse=True)
    matched_forms.sort(key=lambda item: item[0], reverse=True)

    # 2. Identify Covered Concepts vs Missing Gaps
    covered_concepts: list[str] = []
    missing_concepts: list[dict[str, str]] = []

    for token in tokens:
        found = False
        # Check if matched in any node or form
        for _, n in scored_nodes:
            if token in urlparse(n.url).path.lower() or token in (n.title or "").lower():
                found = True
                covered_concepts.append(token)
                break
        if not found:
            for _, f, _ in matched_forms:
                if f.is_destructive and (token in f.form_id.lower() or token in (f.action or "").lower()):
                    found = True
                    missing_concepts.append({
                        "concept": token,
                        "status": "destructive_excluded",
                        "reason": f"Action '{token}' matches destructive form '{f.form_id}' and is safety-restricted from automated execution.",
                    })
                    break
                elif token in f.form_id.lower() or any(token in fld.name.lower() for fld in f.fields):
                    found = True
                    covered_concepts.append(token)
                    break
        if not found:
            # Check if this token matches known destructive concepts
            if token in {"delete", "remove", "drop", "purge", "pay", "checkout"}:
                missing_concepts.append({
                    "concept": token,
                    "status": "destructive_excluded",
                    "reason": f"Action '{token}' is safety-restricted and excluded from automated execution.",
                })
            else:
                missing_concepts.append({
                    "concept": token,
                    "status": "missing",
                    "reason": f"No observed page, route, or form field matching '{token}' in the exploration graph.",
                })

    total_key_concepts = len(covered_concepts) + len(missing_concepts)
    coverage_score = round(len(covered_concepts) / total_key_concepts, 2) if total_key_concepts > 0 else 0.0
    matched_routes = [n.url for _, n in scored_nodes[:5]]

    # 3. Determine if we have enough evidence to synthesize a grounded test draft
    start_norm = normalize_url(graph.start_url)
    start_node = graph.get_node(start_norm) or next(iter(graph.nodes.values()))
    target_node = scored_nodes[0][1] if scored_nodes else start_node

    can_generate = len(covered_concepts) > 0 or len(matched_forms) > 0
    synthesized_draft: TestJourneyDraft | None = None

    if can_generate:
        draft_id = f"draft_{uuid.uuid4().hex[:8]}"
        steps: list[SynthesizedStep] = []

        # Step 1: Initial navigation
        initial_assertions = [
            SynthesizedAssertion(
                assertion_type="url_matches",
                expected_value=start_node.url,
                source="evidence",
                requires_human_input=False,
                evidence_provenance={"node_id": start_node.id},
            ),
            SynthesizedAssertion(
                assertion_type="no_page_error",
                source="evidence",
                requires_human_input=False,
                evidence_provenance={"node_id": start_node.id},
            ),
        ]
        if start_node.title:
            initial_assertions.append(
                SynthesizedAssertion(
                    assertion_type="title_matches",
                    expected_value=start_node.title.strip(),
                    source="evidence",
                    requires_human_input=False,
                    evidence_provenance={"node_id": start_node.id},
                )
            )

        steps.append(
            SynthesizedStep(
                number=1,
                action_type="navigate",
                url=start_node.url,
                description_short=f"Open {urlparse(start_node.url).path or '/'}",
                description_detailed=f"Navigate to {start_node.url}",
                source_node_id=start_node.id,
                screenshot_path=start_node.screenshot_path,
                assertions=initial_assertions,
            )
        )

        step_num = 2
        # If target node is different from start node, add navigation to target node
        if normalize_url(target_node.url) != start_norm:
            steps.append(
                SynthesizedStep(
                    number=step_num,
                    action_type="navigate",
                    url=target_node.url,
                    description_short=f"Navigate to {urlparse(target_node.url).path}",
                    description_detailed=f"Open matched route {target_node.url} for requirement",
                    source_node_id=target_node.id,
                    screenshot_path=target_node.screenshot_path,
                    assertions=[
                        SynthesizedAssertion(
                            assertion_type="url_matches",
                            expected_value=target_node.url,
                            source="evidence",
                            requires_human_input=False,
                            evidence_provenance={"node_id": target_node.id},
                        ),
                        SynthesizedAssertion(
                            assertion_type="no_page_error",
                            source="evidence",
                            requires_human_input=False,
                            evidence_provenance={"node_id": target_node.id},
                        ),
                    ],
                )
            )
            step_num += 1

        # If a safe form was matched, add form input steps
        requires_human_review = len(missing_concepts) > 0
        if matched_forms:
            _, form, f_node = matched_forms[0]
            if not form.is_destructive:
                for field in form.fields:
                    val = _get_safe_default_input_value(field.field_type, field.name)
                    steps.append(
                        SynthesizedStep(
                            number=step_num,
                            action_type="input",
                            selector=field.selector,
                            input_value=val,
                            description_short=f"Fill {field.name or 'field'}",
                            description_detailed=f"Input '{val}' into {field.selector}",
                            source_node_id=f_node.id,
                            screenshot_path=f_node.screenshot_path,
                            assertions=[],
                        )
                    )
                    step_num += 1

                submit_sel = form.submit_button_selector or f"{form.selector} button"
                steps.append(
                    SynthesizedStep(
                        number=step_num,
                        action_type="click",
                        selector=submit_sel,
                        description_short=f"Submit {form.form_id}",
                        description_detailed=f"Click submit button {submit_sel}",
                        source_node_id=f_node.id,
                        screenshot_path=f_node.screenshot_path,
                        assertions=[
                            SynthesizedAssertion(
                                assertion_type="no_page_error",
                                source="evidence",
                                requires_human_input=False,
                            ),
                            SynthesizedAssertion(
                                assertion_type="text_matches",
                                target_selector="body",
                                expected_value=None,
                                source="template",
                                requires_human_input=True,
                                review_prompt=f"Confirm expected result for requirement: '{requirement}'",
                            ),
                        ],
                    )
                )
                requires_human_review = True

        name_slug = " ".join(list(tokens)[:3]).title() or "Requirements Journey"
        synthesized_draft = TestJourneyDraft(
            id=draft_id,
            exploration_id=graph.exploration_id,
            project_id=project_id,
            name=f"Verify {name_slug}",
            description=f"Generated from requirement: '{requirement}'",
            journey_type="form_interaction" if matched_forms else "navigation",
            priority="high",
            start_url=start_node.url,
            steps=steps,
            status="pending",
            requires_human_input=requires_human_review,
        )

    return {
        "requirement_text": requirement,
        "coverage_score": coverage_score,
        "covered_concepts": list(dict.fromkeys(covered_concepts)),
        "missing_concepts": missing_concepts,
        "matched_routes": matched_routes,
        "synthesized_draft": synthesized_draft.model_dump(mode="json") if synthesized_draft else None,
        "can_generate_test": can_generate,
        "provider_used": provider_used,
        "is_llm_generated": is_llm,
    }
