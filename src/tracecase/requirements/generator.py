"""Evidence-Grounded AI Journey Generation Orchestrator for Phase 9.1.2."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Literal
from urllib.parse import urlparse

from tracecase.ai.models import Message
from tracecase.ai.provider import NullProvider, Provider
from tracecase.exploration.models import (
    AppNavigationGraph,
    SynthesizedAssertion,
    SynthesizedStep,
    TestJourneyDraft,
    normalize_url,
)
from tracecase.requirements.evidence import EvidenceCatalog, ObservedEvidenceRecord, extract_evidence_catalog
from tracecase.requirements.matcher import IntentMatchResult, match_intent_to_evidence
from tracecase.requirements.models import RequirementSpec, TestIntent

logger = logging.getLogger("tracecase.requirements.generator")


def _is_business_outcome_assertion(text: str) -> bool:
    """Check if assertion text describes a speculative business state rather than pure DOM element existence."""
    words = text.lower()
    return any(
        term in words
        for term in (
            "confirmed", "successful", "processed", "purchased", "ordered",
            "saved to database", "email sent", "account created", "payment verified",
            "balance updated", "permission granted"
        )
    )


async def generate_journey_from_requirements(
    spec: RequirementSpec,
    graph: AppNavigationGraph,
    provider: Provider | None = None,
    project_id: str = "default_project",
) -> TestJourneyDraft:
    """
    Generate an evidence-grounded TestJourneyDraft from a RequirementSpec and AppNavigationGraph.
    
    Guarantees:
    1. Selectors are strictly derived from observed evidence, never invented.
    2. Missing evidence stays missing (target_status="unresolved", selector_confidence=0.0).
    3. Invented evidence IDs or synthetic selectors from LLM output are rejected.
    4. Assertion confidence is kept strictly independent of selector confidence.
    5. Speculative business outcomes require explicit human verification.
    6. Destructive operations are identified and flagged for human confirmation.
    7. Generated drafts remain in 'pending' status and cannot be promoted without human review.
    """
    catalog = extract_evidence_catalog(graph, spec)
    active_provider = provider or NullProvider()

    # 1. Deterministic Pre-Matching of all intents against observed evidence
    intent_matches: dict[str, IntentMatchResult] = {}
    for intent in spec.test_intents:
        intent_matches[intent.id] = match_intent_to_evidence(intent, catalog)

    # 2. LLM Assistance or Heuristic Synthesis
    journey_name = f"Test Journey: {spec.title}"
    journey_desc = f"Synthesized from {spec.format} requirement '{spec.title}'"
    provider_used = active_provider.name
    is_llm_assisted = False
    llm_payload: dict[str, Any] | None = None

    if active_provider.name != "null":
        prompt = _build_llm_prompt(spec, catalog, intent_matches)
        try:
            ai_resp = await active_provider.chat(
                [
                    Message(
                        role="system",
                        content=(
                            "You are the Tracecase QA Journey Planner. Your job is to organize observed browser "
                            "evidence into a coherent test journey matching requirements. You must NEVER invent "
                            "selectors, routes, or evidence IDs. Use strictly the evidence IDs provided."
                        ),
                    ),
                    Message(role="user", content=prompt),
                ],
                schema={"type": "object"},
            )
            if ai_resp and isinstance(ai_resp, dict) and "steps" in ai_resp:
                llm_payload = ai_resp
                is_llm_assisted = True
                if "journey_name" in ai_resp:
                    journey_name = str(ai_resp["journey_name"])
                if "description" in ai_resp:
                    journey_desc = str(ai_resp["description"])
        except Exception as ex:
            logger.warning("AI provider failed during journey generation; falling back to deterministic: %s", ex)
            llm_payload = None

    # 3. Step Construction with Strict Evidence Validation
    steps: list[SynthesizedStep] = []
    unresolved_count = 0
    ambiguous_count = 0
    destructive_count = 0
    rejected_invented_ids: list[str] = []
    rejected_unsupported_selectors: list[str] = []

    if llm_payload and is_llm_assisted:
        # Construct and validate steps from LLM plan
        raw_steps = llm_payload.get("steps", [])
        for idx, r_step in enumerate(raw_steps, start=1):
            intent_id = str(r_step.get("intent_id", ""))
            ev_id = r_step.get("evidence_id")
            action_type = r_step.get("action_type", "click")
            if action_type not in ("navigate", "click", "input", "check", "select", "wait"):
                action_type = "click"

            # Strict Validation 1: Verify evidence_id exists in catalog
            if ev_id and not catalog.contains_id(str(ev_id)):
                # REJECT invented evidence ID!
                rejected_invented_ids.append(str(ev_id))
                unresolved_count += 1
                step = SynthesizedStep(
                    number=idx,
                    action_type=action_type,
                    selector=None,
                    url=None,
                    description_short=f"Unresolved step {idx} (invalid evidence ID)",
                    description_detailed=f"AI returned invalid/invented evidence ID '{ev_id}'. Target unresolved.",
                    target_status="unresolved",
                    selector_confidence=0.0,
                    intent_id=intent_id or None,
                )
                steps.append(step)
                continue

            evidence_rec = catalog.get_evidence(str(ev_id)) if ev_id else None

            # Strict Validation 2: Ensure selector matches observed record exactly
            supplied_selector = r_step.get("selector")
            final_selector = evidence_rec.selector if evidence_rec else None
            if supplied_selector and evidence_rec and supplied_selector != evidence_rec.selector:
                rejected_unsupported_selectors.append(str(supplied_selector))

            # Derive resolution and confidence
            if evidence_rec:
                target_status = "resolved"
                sel_conf = 0.95
                url_val = evidence_rec.route if evidence_rec.evidence_source == "page_route" else None
                if evidence_rec.is_destructive:
                    destructive_count += 1
            else:
                target_status = "unresolved"
                sel_conf = 0.0
                url_val = None
                unresolved_count += 1

            # Build assertions for this step
            step_assertions = _build_step_assertions(
                r_step.get("assertions", []),
                evidence_rec,
                spec,
            )

            step = SynthesizedStep(
                number=idx,
                action_type=action_type,
                selector=final_selector,
                url=url_val,
                input_value=r_step.get("input_value"),
                description_short=str(r_step.get("description_short") or f"Step {idx}: {action_type}"),
                description_detailed=str(
                    r_step.get("description_detailed")
                    or (f"Execute {action_type} on {evidence_rec.element_tag} ({evidence_rec.evidence_id})" if evidence_rec else "Unresolved target")
                ),
                source_node_id=evidence_rec.page_id if evidence_rec else None,
                target_status=target_status,
                selector_confidence=sel_conf,
                intent_id=intent_id or None,
                assertions=step_assertions,
            )
            steps.append(step)
    else:
        # Deterministic journey construction from pre-matched intents
        start_norm = normalize_url(graph.start_url)
        start_node = graph.get_node(start_norm) or (next(iter(graph.nodes.values())) if graph.nodes else None)
        step_number = 1

        # Initial navigation step
        if start_node:
            steps.append(
                SynthesizedStep(
                    number=step_number,
                    action_type="navigate",
                    url=start_node.url,
                    description_short=f"Open {urlparse(start_node.url).path or '/'}",
                    description_detailed=f"Navigate to {start_node.url}",
                    source_node_id=start_node.id,
                    target_status="resolved",
                    selector_confidence=1.0,
                    assertions=[
                        SynthesizedAssertion(
                            assertion_type="url_matches",
                            expected_value=start_node.url,
                            source="evidence",
                            requires_human_input=False,
                            assertion_confidence=1.0,
                            validation_outcome="passed",
                            evidence_provenance={"node_id": start_node.id},
                        ),
                        SynthesizedAssertion(
                            assertion_type="no_page_error",
                            source="evidence",
                            requires_human_input=False,
                            assertion_confidence=1.0,
                            validation_outcome="passed",
                        ),
                    ],
                )
            )
            step_number += 1

        # Convert each intent into a verified step
        for intent in spec.test_intents:
            match_res = intent_matches[intent.id]
            ev_rec = catalog.get_evidence(match_res.primary_evidence_id) if match_res.primary_evidence_id else None

            if match_res.resolution_status == "unresolved":
                unresolved_count += 1
                if intent.is_destructive or match_res.is_destructive:
                    destructive_count += 1

                unres_assertions: list[SynthesizedAssertion] = []
                if intent.expected_outcome or intent.target_action == "assert":
                    outcome_text = intent.expected_outcome or intent.summary
                    is_biz = _is_business_outcome_assertion(outcome_text)
                    unres_assertions.append(
                        SynthesizedAssertion(
                            assertion_type="text_matches",
                            expected_value=outcome_text,
                            source="template" if is_biz else "evidence",
                            requires_human_input=True,
                            assertion_confidence=0.5 if is_biz else 0.85,
                            review_prompt="Verify business outcome in backend." if is_biz else None,
                        )
                    )

                steps.append(
                    SynthesizedStep(
                        number=step_number,
                        action_type="wait",
                        selector=None,
                        url=None,
                        description_short=f"Unresolved: {intent.summary[:40]}",
                        description_detailed=f"Target element not observed in exploration graph. {match_res.explanation}",
                        target_status="unresolved",
                        selector_confidence=0.0,
                        intent_id=intent.id,
                        criterion_id=intent.criterion_id,
                        assertions=unres_assertions,
                    )
                )
                step_number += 1
            elif match_res.resolution_status == "ambiguous":
                ambiguous_count += 1
                if intent.is_destructive or match_res.is_destructive:
                    destructive_count += 1
                steps.append(
                    SynthesizedStep(
                        number=step_number,
                        action_type="wait",
                        selector=None,
                        url=None,
                        description_short=f"Ambiguous: {intent.summary[:40]}",
                        description_detailed=f"Multiple candidate elements observed in graph. {match_res.explanation}",
                        target_status="ambiguous",
                        selector_confidence=match_res.selector_confidence,
                        intent_id=intent.id,
                        criterion_id=intent.criterion_id,
                    )
                )
                step_number += 1
            else:
                # Resolved step backed by observed evidence
                if match_res.is_destructive or intent.is_destructive:
                    destructive_count += 1

                act_type: Literal["navigate", "click", "input", "check", "select", "wait"] = "click"
                if ev_rec and (ev_rec.evidence_source == "form_field" or ev_rec.element_tag in ("input", "textarea")):
                    act_type = "input"
                elif intent.target_action in ("navigate", "click", "input", "check", "select", "wait"):
                    act_type = intent.target_action
                elif intent.target_action == "submit":
                    act_type = "click"
                elif intent.target_action == "assert":
                    act_type = "wait"

                # Input value if input action
                val = intent.input_value_hint
                if act_type == "input" and not val and ev_rec:
                    val = ev_rec.observed_attributes.get("placeholder") or "test_input"

                # Assertions for this step
                step_assertions: list[SynthesizedAssertion] = []
                if ev_rec and ev_rec.selector:
                    step_assertions.append(
                        SynthesizedAssertion(
                            assertion_type="element_visible",
                            target_selector=ev_rec.selector,
                            expected_value=ev_rec.observed_text or ev_rec.accessible_name,
                            source="evidence",
                            requires_human_input=False,
                            assertion_confidence=0.9,
                            evidence_provenance={"evidence_id": ev_rec.evidence_id, "route": ev_rec.route},
                        )
                    )

                if intent.expected_outcome:
                    is_biz = _is_business_outcome_assertion(intent.expected_outcome)
                    step_assertions.append(
                        SynthesizedAssertion(
                            assertion_type="text_matches",
                            target_selector=ev_rec.selector if ev_rec else None,
                            expected_value=intent.expected_outcome,
                            source="template" if is_biz else "evidence",
                            requires_human_input=is_biz,
                            assertion_confidence=0.5 if is_biz else 0.85,
                            review_prompt="Verify business outcome actually succeeded in backend." if is_biz else None,
                        )
                    )

                steps.append(
                    SynthesizedStep(
                        number=step_number,
                        action_type=act_type,
                        selector=ev_rec.selector if ev_rec else None,
                        url=ev_rec.route if ev_rec and ev_rec.evidence_source == "page_route" else None,
                        input_value=val,
                        description_short=intent.summary[:60],
                        description_detailed=(
                            f"Action '{act_type}' mapped to observed {ev_rec.element_tag} ({ev_rec.evidence_id}). "
                            f"{match_res.explanation}"
                            if ev_rec
                            else match_res.explanation
                        ),
                        source_node_id=ev_rec.page_id if ev_rec else None,
                        target_status="resolved",
                        selector_confidence=match_res.selector_confidence,
                        intent_id=intent.id,
                        criterion_id=intent.criterion_id,
                        assertions=step_assertions,
                    )
                )
                step_number += 1

    # Check if human review is required
    has_unresolved = unresolved_count > 0 or ambiguous_count > 0
    has_destructive = destructive_count > 0
    has_human_assertions = any(
        a.requires_human_input for s in steps for a in s.assertions
    )
    requires_human_input = has_unresolved or has_destructive or has_human_assertions

    validation_details = {
        "total_intents": len(spec.test_intents),
        "unresolved_steps": unresolved_count,
        "ambiguous_steps": ambiguous_count,
        "destructive_steps": destructive_count,
        "rejected_invented_ids": rejected_invented_ids,
        "rejected_unsupported_selectors": rejected_unsupported_selectors,
        "provider_used": provider_used,
        "is_llm_assisted": is_llm_assisted,
        "evidence_catalog_size": catalog.total_evidence(),
    }

    draft = TestJourneyDraft(
        id=f"draft_{uuid.uuid4().hex[:8]}",
        exploration_id=graph.exploration_id,
        project_id=project_id,
        name=journey_name,
        description=journey_desc,
        journey_type="deep_journey" if len(steps) > 4 else "navigation",
        priority="high" if spec.user_role == "administrator" or destructive_count > 0 else "medium",
        start_url=graph.start_url,
        steps=steps,
        status="pending",
        approved_testcase_id=None,
        requires_human_input=requires_human_input,
        requirement_id=spec.id,
        validation_status="not_run",
        validation_details=validation_details,
        version=1,
    )

    return draft


def _build_step_assertions(
    raw_assertions: list[dict[str, Any]],
    rec: ObservedEvidenceRecord | None,
    spec: RequirementSpec,
) -> list[SynthesizedAssertion]:
    """Build and classify assertions strictly separating selector confidence from assertion confidence."""
    assertions: list[SynthesizedAssertion] = []

    if rec and rec.selector:
        assertions.append(
            SynthesizedAssertion(
                assertion_type="element_visible",
                target_selector=rec.selector,
                expected_value=rec.observed_text or rec.accessible_name,
                source="evidence",
                requires_human_input=False,
                assertion_confidence=0.9,
                evidence_provenance={"evidence_id": rec.evidence_id, "route": rec.route},
            )
        )

    for item in raw_assertions:
        if not isinstance(item, dict):
            continue
        a_type = item.get("assertion_type", "text_matches")
        if a_type not in ("url_matches", "title_matches", "element_visible", "no_page_error", "text_matches"):
            a_type = "text_matches"

        exp = item.get("expected_value")
        is_biz = _is_business_outcome_assertion(str(exp or ""))

        assertions.append(
            SynthesizedAssertion(
                assertion_type=a_type,
                target_selector=rec.selector if rec else None,
                expected_value=exp,
                source="template" if is_biz else "evidence",
                requires_human_input=is_biz,
                assertion_confidence=0.5 if is_biz else 0.85,
                review_prompt="Verify business outcome in backend." if is_biz else None,
            )
        )

    return assertions


def _build_llm_prompt(
    spec: RequirementSpec,
    catalog: EvidenceCatalog,
    intent_matches: dict[str, IntentMatchResult],
) -> str:
    """Build compact, evidence-indexed prompt for LLM journey planning."""
    intents_summary = [
        {
            "intent_id": i.id,
            "summary": i.summary,
            "action": i.target_action,
            "hint": i.target_element_hint,
            "deterministic_match": (
                intent_matches[i.id].primary_evidence_id
                if intent_matches[i.id].resolution_status == "resolved"
                else intent_matches[i.id].resolution_status
            ),
        }
        for i in spec.test_intents
    ]

    evidence_summary = [
        {
            "evidence_id": r.evidence_id,
            "route": r.route,
            "tag": r.element_tag,
            "text": r.observed_text,
            "accessible_name": r.accessible_name,
            "selector": r.selector,
            "is_destructive": r.is_destructive,
        }
        for r in catalog.all_records()[:50]
    ]

    return (
        f"Requirement Spec: {spec.title} (Format: {spec.format})\n"
        f"User Role: {spec.user_role or 'User'}\n"
        f"Capability: {spec.capability or spec.raw_text[:100]}\n"
        f"Benefit: {spec.benefit or 'None'}\n\n"
        f"Test Intents to Satisfy:\n{json.dumps(intents_summary, indent=2)}\n\n"
        f"OBSERVED EVIDENCE CATALOG (Use ONLY these evidence_ids):\n{json.dumps(evidence_summary, indent=2)}\n\n"
        "STRICT CONSTRAINTS:\n"
        "1. Every step MUST use an 'evidence_id' from the OBSERVED EVIDENCE CATALOG above. Do NOT invent IDs.\n"
        "2. Do NOT invent selectors. Use the exact selector associated with the evidence_id.\n"
        "3. Output JSON with format: {'journey_name': '...', 'description': '...', 'steps': ["
        "{'intent_id': '...', 'evidence_id': '...', 'action_type': 'navigate|click|input|check|select|wait', "
        "'description_short': '...', 'description_detailed': '...', 'input_value': null|str, 'assertions': []}]}"
    )


def generate_journey_from_requirements_sync(
    spec: RequirementSpec,
    graph: AppNavigationGraph,
    provider: Provider | None = None,
    project_id: str = "default_project",
) -> TestJourneyDraft:
    """Synchronous wrapper for generate_journey_from_requirements."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Running in an active event loop
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(
            generate_journey_from_requirements(spec, graph, provider, project_id)
        )
    else:
        return asyncio.run(
            generate_journey_from_requirements(spec, graph, provider, project_id)
        )
