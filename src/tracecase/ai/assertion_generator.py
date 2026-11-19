"""Automatic Assertion Generator for Tracecase.

Inspects test case steps, DOM elements, URLs, and network traffic to derive
resilient assertions (URL, text, visibility, HTTP status, and console health).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from tracecase.ai.models import Message
from tracecase.ai.provider import Provider
from tracecase.models import TestCase


class AssertionSuggestion(BaseModel):
    """An intelligent assertion recommendation."""

    step_number: int
    kind: str  # status, text, visible, url, no_page_error
    assertion_type: str = ""
    target: str | None = None
    expected: Any = None
    confidence: float = 0.8
    reasoning: str = ""
    rationale: str = ""
    source: str = "heuristic"  # heuristic or ai


class AssertionGenerationResult(BaseModel):
    """Container for generated assertion recommendations."""

    testcase_id: str
    total_suggested: int = 0
    total_suggestions: int = 0
    provider_used: str = "heuristic"
    is_llm_generated: bool = False
    suggestions: list[AssertionSuggestion] = Field(default_factory=list)


def generate_heuristic_assertions(testcase: TestCase) -> list[AssertionSuggestion]:
    """Derive deterministic heuristic assertions from recorded steps and traffic."""
    suggestions: list[AssertionSuggestion] = []
    seen_keys: set[tuple[int, str, str | None]] = set()

    def _add_suggestion(s: AssertionSuggestion) -> None:
        if not s.rationale:
            s.rationale = s.reasoning
        if not s.reasoning:
            s.reasoning = s.rationale
        if not s.assertion_type:
            s.assertion_type = f"{s.kind.capitalize()} Assertion"
        key = (s.step_number, s.kind, s.target)
        if key not in seen_keys:
            seen_keys.add(key)
            suggestions.append(s)

    # 1. Navigation Steps -> URL path and status assertions
    for step in testcase.steps:
        if step.action_type == "navigate" and step.url:
            parsed = urlparse(step.url)
            path = parsed.path or "/"
            _add_suggestion(
                AssertionSuggestion(
                    step_number=step.number,
                    kind="url",
                    expected=path,
                    confidence=0.95,
                    reasoning=f"Verify browser successfully navigated to route '{path}'.",
                    source="heuristic",
                )
            )
            _add_suggestion(
                AssertionSuggestion(
                    step_number=step.number,
                    kind="status",
                    target=step.url,
                    expected=200,
                    confidence=0.9,
                    reasoning=f"Verify HTTP response code for {step.url} is 200 OK.",
                    source="heuristic",
                )
            )

        # 2. Click on elements with text / buttons -> Visibility and text assertions (if element remains)
        if step.action_type in ("click", "dblclick") and step.element:
            selector = step.element.selector
            text = (step.element.text or "").strip()
            is_submit_or_nav = (
                step.element.attributes.get("type") == "submit"
                or step.element.tag_name == "a"
                or bool(step.network_requests)
            )
            if not is_submit_or_nav:
                if selector:
                    _add_suggestion(
                        AssertionSuggestion(
                            step_number=step.number,
                            kind="visible",
                            target=selector,
                            expected=True,
                            confidence=0.85,
                            reasoning=f"Verify target element '{selector}' is rendered and visible.",
                            source="heuristic",
                        )
                    )
                if text and len(text) < 40 and not text.isdigit():
                    _add_suggestion(
                        AssertionSuggestion(
                            step_number=step.number,
                            kind="text",
                            target=selector,
                            expected=text,
                            confidence=0.8,
                            reasoning=f"Confirm element contains expected label text '{text}'.",
                            source="heuristic",
                        )
                    )
            else:
                _add_suggestion(
                    AssertionSuggestion(
                        step_number=step.number,
                        kind="no_page_error",
                        expected=True,
                        confidence=0.9,
                        reasoning=f"Confirm action '{step.description_short or 'Click'}' triggers no uncaught client exceptions.",
                        source="heuristic",
                    )
                )

        # 3. Form input steps -> Verify input value reflection
        if step.action_type == "input" and step.input_value and step.element:
            selector = step.element.selector
            _add_suggestion(
                AssertionSuggestion(
                    step_number=step.number,
                    kind="visible",
                    target=selector,
                    expected=True,
                    confidence=0.9,
                    reasoning=f"Confirm input field '{selector}' remains visible and active.",
                    source="heuristic",
                )
            )

    # 4. Critical API network requests -> HTTP status assertions
    for step in testcase.steps:
        for req in step.network_requests:
            if req.status in (200, 201, 204) and any(
                frag in req.url for frag in ("/api/", "/v1/", "/v2/", "/graphql", "/rest/")
            ):
                _add_suggestion(
                    AssertionSuggestion(
                        step_number=step.number,
                        kind="status",
                        target=req.url,
                        expected=req.status,
                        confidence=0.9,
                        reasoning=f"Verify HTTP response status for {req.url} is {req.status} OK.",
                        source="heuristic",
                    )
                )

    # 5. Page health: no page errors on final step
    if testcase.steps:
        final_step = testcase.steps[-1]
        _add_suggestion(
            AssertionSuggestion(
                step_number=final_step.number,
                kind="no_page_error",
                confidence=0.9,
                reasoning="Ensure no unhandled JavaScript runtime exceptions occurred during test flow.",
                source="heuristic",
            )
        )

    return suggestions


async def suggest_assertions(
    testcase: TestCase, provider: Provider | None = None
) -> AssertionGenerationResult:
    """Generate comprehensive assertion suggestions using heuristics and optional LLM."""
    suggestions = generate_heuristic_assertions(testcase)

    # Enrich with LLM provider if available
    llm_generated_count = 0
    provider_name = "heuristic"
    if provider and provider.name != "null":
        try:
            steps_desc = [
                f"Step {s.number} [{s.action_type}]: {s.description_short or ''} (selector: {s.element.selector if s.element else 'None'})"
                for s in testcase.steps
            ]
            prompt = (
                f"You are a senior QA test architect. Analyze this UI flow and recommend high-confidence assertions.\n"
                f"Testcase: '{testcase.name}' at {testcase.start_url}\n"
                f"Steps:\n" + "\n".join(steps_desc) + "\n\n"
                "Return a JSON object with key 'suggestions', a list of objects with: "
                "step_number (int), kind ('text'|'visible'|'url'|'status'|'no_page_error'), target (str or null), "
                "expected (any), confidence (float between 0.0 and 1.0), reasoning (str)."
            )
            response = await provider.chat([Message(role="user", content=prompt)], schema={})
            ai_list = response.get("suggestions", [])
            if isinstance(ai_list, list) and ai_list:
                for item in ai_list:
                    if isinstance(item, dict) and "kind" in item:
                        suggestions.append(
                            AssertionSuggestion(
                                step_number=int(item.get("step_number", 1)),
                                kind=str(item["kind"]),
                                target=item.get("target"),
                                expected=item.get("expected"),
                                confidence=float(item.get("confidence", 0.8)),
                                reasoning=str(item.get("reasoning", "Recommended by QA Intelligence LLM")),
                                source=f"llm:{provider.name}",
                            )
                        )
                        llm_generated_count += 1
                if llm_generated_count > 0:
                    provider_name = provider.name
        except Exception:
            pass

    for s in suggestions:
        if not s.rationale:
            s.rationale = s.reasoning
        if not s.reasoning:
            s.reasoning = s.rationale
        if not s.assertion_type:
            s.assertion_type = f"{s.kind.capitalize()} Assertion"

    return AssertionGenerationResult(
        testcase_id=testcase.id,
        total_suggested=len(suggestions),
        total_suggestions=len(suggestions),
        provider_used=provider_name,
        is_llm_generated=llm_generated_count > 0,
        suggestions=suggestions,
    )
