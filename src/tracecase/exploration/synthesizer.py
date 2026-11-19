"""Journey Synthesizer: converts AppNavigationGraph into verified, deterministic test drafts."""

from __future__ import annotations

import logging
import uuid
from typing import Literal
from urllib.parse import urlparse

from tracecase.exploration.models import (
    AppNavigationGraph,
    PageNode,
    PageTransition,
    SynthesizedAssertion,
    SynthesizedStep,
    TestJourneyDraft,
    normalize_url,
)

logger = logging.getLogger("tracecase.exploration.synthesizer")


def _get_safe_default_input_value(field_type: str, field_name: str) -> str:
    """Provide safe exploratory default values for form fields."""
    f_type = field_type.lower()
    f_name = field_name.lower()

    if "email" in f_type or "email" in f_name:
        return "qa.tester@example.com"
    elif "password" in f_type or "pass" in f_name:
        return "P@ssw0rd123!"
    elif "num" in f_type or "qty" in f_name or "amount" in f_name or "age" in f_name:
        return "5"
    elif "tel" in f_type or "phone" in f_name:
        return "555-0199"
    elif "url" in f_type or "website" in f_name:
        return "https://example.com"
    elif "search" in f_type or "search" in f_name or "query" in f_name or f_name == "q":
        return "tracecase test"
    elif "name" in f_name:
        return "Jane Doe"
    return "Test Value"


def synthesize_test_journeys(
    graph: AppNavigationGraph,
    project_id: str = "default_project",
    max_journeys: int = 6,
) -> list[TestJourneyDraft]:
    """
    Synthesize prioritized, evidence-grounded user journeys from an exploration graph.
    
    Guarantees:
    1. Never invents speculative results: assertions are generated strictly from observed DOM/network evidence.
    2. Any state-dependent or unproven outcome is explicitly marked requires_human_input=True.
    3. Destructive actions (payment, delete, purchase) are skipped.
    4. Bounded paths with deduplication to prevent combinatorial path explosion.
    """
    if not graph.nodes:
        return []

    start_norm = normalize_url(graph.start_url)
    start_node = graph.get_node(start_norm) or next(iter(graph.nodes.values()))

    # Build adjacency map of transitions: source_url -> list[PageTransition]
    adjacency: dict[str, list[PageTransition]] = {}
    for trans in graph.transitions:
        src = normalize_url(trans.source_url)
        if src not in adjacency:
            adjacency[src] = []
        adjacency[src].append(trans)

    # 1. Path finding via DFS to find distinct, non-cyclic routes from start_node
    discovered_paths: list[list[tuple[PageTransition, PageNode]]] = []

    def _dfs(
        current_url: str,
        current_path: list[tuple[PageTransition, PageNode]],
        visited_in_path: set[str],
        depth: int,
    ) -> None:
        if depth > 4:
            return

        transitions = adjacency.get(current_url, [])

        for t in transitions:
            tgt_norm = normalize_url(t.target_url)
            if tgt_norm not in visited_in_path and tgt_norm in graph.nodes:
                tgt_node = graph.nodes[tgt_norm]
                new_path = list(current_path) + [(t, tgt_node)]
                discovered_paths.append(new_path)
                _dfs(tgt_norm, new_path, visited_in_path | {tgt_norm}, depth + 1)

    _dfs(start_norm, [], {start_norm}, 1)

    # Sort discovered paths by length and unique node coverage
    discovered_paths.sort(key=lambda p: (len(p), len({t.target_url for t, _ in p})), reverse=True)

    # Deduplicate prefix sub-paths
    kept_paths: list[list[tuple[PageTransition, PageNode]]] = []
    seen_destinations: set[str] = set()

    for path in discovered_paths:
        dest = normalize_url(path[-1][0].target_url)
        # Avoid duplicate journeys leading to the exact same destination
        if dest not in seen_destinations:
            seen_destinations.add(dest)
            kept_paths.append(path)
        if len(kept_paths) >= max_journeys:
            break

    drafts: list[TestJourneyDraft] = []

    # Helper: Create initial navigation step
    def _create_initial_step(node: PageNode) -> SynthesizedStep:
        assertions: list[SynthesizedAssertion] = [
            SynthesizedAssertion(
                assertion_type="url_matches",
                expected_value=node.url,
                source="evidence",
                requires_human_input=False,
                evidence_provenance={"node_id": node.id, "observed_url": node.url},
            ),
            SynthesizedAssertion(
                assertion_type="no_page_error",
                source="evidence",
                requires_human_input=False,
                evidence_provenance={"node_id": node.id},
            ),
        ]

        if node.title and node.title.strip():
            assertions.append(
                SynthesizedAssertion(
                    assertion_type="title_matches",
                    expected_value=node.title.strip(),
                    source="evidence",
                    requires_human_input=False,
                    evidence_provenance={"node_id": node.id, "observed_title": node.title},
                )
            )

        return SynthesizedStep(
            number=1,
            action_type="navigate",
            url=node.url,
            description_short=f"Navigate to {urlparse(node.url).path or '/'}",
            description_detailed=f"Open initial application page at {node.url}",
            source_node_id=node.id,
            screenshot_path=node.screenshot_path,
            assertions=assertions,
        )

    # 2. Synthesize Navigation Journeys from Paths
    for path in kept_paths:
        target_node = path[-1][1]
        dest_path_name = urlparse(target_node.url).path.strip("/") or "home"
        clean_name = f"Verify {dest_path_name.replace('-', ' ').title()} Flow"
        journey_id = f"draft_{uuid.uuid4().hex[:8]}"

        steps: list[SynthesizedStep] = [_create_initial_step(start_node)]
        has_review_req = False

        step_num = 2
        for trans, node in path:
            # Evidence-grounded assertions for target node
            step_assertions: list[SynthesizedAssertion] = [
                SynthesizedAssertion(
                    assertion_type="url_matches",
                    expected_value=node.url,
                    source="evidence",
                    requires_human_input=False,
                    evidence_provenance={"node_id": node.id, "observed_url": node.url},
                ),
                SynthesizedAssertion(
                    assertion_type="no_page_error",
                    source="evidence",
                    requires_human_input=False,
                    evidence_provenance={"node_id": node.id},
                ),
            ]

            if node.title and node.title.strip():
                step_assertions.append(
                    SynthesizedAssertion(
                        assertion_type="title_matches",
                        expected_value=node.title.strip(),
                        source="evidence",
                        requires_human_input=False,
                        evidence_provenance={"node_id": node.id, "observed_title": node.title},
                    )
                )

            # Check if there is an interactive element on destination page
            if node.interactive_elements:
                first_el = node.interactive_elements[0]
                step_assertions.append(
                    SynthesizedAssertion(
                        assertion_type="element_visible",
                        target_selector=first_el.selector,
                        source="evidence",
                        requires_human_input=False,
                        evidence_provenance={
                            "node_id": node.id,
                            "tag": first_el.tag_name,
                            "selector": first_el.selector,
                        },
                    )
                )

            steps.append(
                SynthesizedStep(
                    number=step_num,
                    action_type="click",
                    selector=trans.selector or f"a[href='{node.url}']",
                    description_short=f"Click {trans.element_text or trans.action_type}",
                    description_detailed=f"Navigate to {node.url} via {trans.action_type}",
                    source_node_id=node.id,
                    screenshot_path=node.screenshot_path,
                    assertions=step_assertions,
                )
            )
            step_num += 1

        journey_type: Literal["navigation", "form_interaction", "deep_journey"] = (
            "deep_journey" if len(path) > 1 else "navigation"
        )
        drafts.append(
            TestJourneyDraft(
                id=journey_id,
                exploration_id=graph.exploration_id,
                project_id=project_id,
                name=clean_name,
                description=f"Automated journey navigating from {start_node.url} to {target_node.url}.",
                journey_type=journey_type,
                priority="high" if journey_type == "deep_journey" else "medium",
                start_url=start_node.url,
                steps=steps,
                status="pending",
                requires_human_input=has_review_req,
            )
        )

    # 3. Synthesize Form Interaction Journeys (Safe forms only)
    for node_url, node in graph.nodes.items():
        if len(drafts) >= max_journeys + 2:
            break

        for form in node.forms:
            # RULE: Never synthesize destructive forms
            if form.is_destructive:
                logger.info(
                    "Skipping destructive form %s on %s: %s",
                    form.form_id,
                    node.url,
                    form.destructive_reason,
                )
                continue

            form_name = form.form_id.replace("_", " ").title()
            form_journey_id = f"draft_{uuid.uuid4().hex[:8]}"

            form_steps: list[SynthesizedStep] = [_create_initial_step(start_node)]
            step_num = 2

            # If form is not on start_node, add navigation step to form page
            if normalize_url(node.url) != start_norm:
                form_steps.append(
                    SynthesizedStep(
                        number=step_num,
                        action_type="navigate",
                        url=node.url,
                        description_short=f"Navigate to {form_name} Page",
                        description_detailed=f"Open page containing form {form.form_id}",
                        source_node_id=node.id,
                        screenshot_path=node.screenshot_path,
                        assertions=[
                            SynthesizedAssertion(
                                assertion_type="url_matches",
                                expected_value=node.url,
                                source="evidence",
                                requires_human_input=False,
                                evidence_provenance={"node_id": node.id},
                            )
                        ],
                    )
                )
                step_num += 1

            # Fill each field in the form with safe exploratory defaults
            for field in form.fields:
                val = _get_safe_default_input_value(field.field_type, field.name)
                form_steps.append(
                    SynthesizedStep(
                        number=step_num,
                        action_type="input",
                        selector=field.selector,
                        input_value=val,
                        description_short=f"Enter {field.name or 'input'}",
                        description_detailed=f"Input '{val}' into {field.selector}",
                        source_node_id=node.id,
                        screenshot_path=node.screenshot_path,
                        assertions=[],
                    )
                )
                step_num += 1

            # Submit button step
            submit_sel = form.submit_button_selector or f"{form.selector} button"
            submit_assertions: list[SynthesizedAssertion] = [
                SynthesizedAssertion(
                    assertion_type="no_page_error",
                    source="evidence",
                    requires_human_input=False,
                    evidence_provenance={"form_id": form.form_id},
                ),
                # Unproven business-logic expectation marked for human review
                SynthesizedAssertion(
                    assertion_type="text_matches",
                    target_selector="body",
                    expected_value=None,
                    source="template",
                    requires_human_input=True,
                    review_prompt="Specify expected submission success message or confirmation banner.",
                ),
            ]

            form_steps.append(
                SynthesizedStep(
                    number=step_num,
                    action_type="click",
                    selector=submit_sel,
                    description_short=f"Submit {form_name}",
                    description_detailed=f"Click submit button {submit_sel}",
                    source_node_id=node.id,
                    screenshot_path=node.screenshot_path,
                    assertions=submit_assertions,
                )
            )

            drafts.append(
                TestJourneyDraft(
                    id=form_journey_id,
                    exploration_id=graph.exploration_id,
                    project_id=project_id,
                    name=f"Submit {form_name} Form Flow",
                    description=f"Fill safe fields and submit {form.form_id} on {node.url}.",
                    journey_type="form_interaction",
                    priority="high",
                    start_url=start_node.url,
                    steps=form_steps,
                    status="pending",
                    requires_human_input=True,  # Form requires human confirmation of expected result
                )
            )

    return drafts[:max_journeys]
