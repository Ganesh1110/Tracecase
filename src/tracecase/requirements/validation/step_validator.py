"""Pre-execution validation and deterministic assertion evaluation for sandbox runs."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Page

from tracecase.exploration.models import SynthesizedAssertion, SynthesizedStep
from tracecase.requirements.validation.models import (
    AssertionValidationResult,
    SandboxSafetyPolicy,
)

logger = logging.getLogger("tracecase.requirements.validation.step_validator")

DESTRUCTIVE_KEYWORDS = {"delete", "remove", "drop", "purge", "pay", "checkout", "destroy", "cancel_subscription"}


async def validate_step_pre_execution(
    step: SynthesizedStep,
    page: Page,
    policy: SandboxSafetyPolicy,
) -> tuple[bool, str | None, dict[str, Any]]:
    """
    Perform pre-execution validation before interacting with the live browser page.
    
    Checks:
    1. Rejects unresolved targets (missing evidence).
    2. Rejects ambiguous targets (multiple matching elements requiring manual resolution).
    3. Blocks destructive actions unless explicitly permitted by safety policy.
    4. Validates selector uniqueness on the live DOM (fails if count == 0 or count > 1).
    5. Validates element visibility and enabled state.
    """
    metadata: dict[str, Any] = {
        "uniqueness": 1,
        "visible": True,
        "enabled": True,
        "is_destructive": False,
    }

    # 1. Grounding check: unresolved evidence
    if step.target_status == "unresolved":
        metadata.update({"uniqueness": 0, "visible": False, "enabled": False})
        return False, "Target is unresolved: missing exploration evidence in catalog.", metadata

    # 2. Grounding check: ambiguous evidence
    if step.target_status == "ambiguous":
        metadata.update({"uniqueness": 0, "visible": False, "enabled": False})
        return False, "Target is ambiguous: multiple candidate elements exist and require explicit resolution.", metadata

    # 3. Missing selector check for interactive actions
    if not step.selector and step.action_type not in ("navigate", "wait"):
        metadata.update({"uniqueness": 0, "visible": False, "enabled": False})
        return False, f"Missing selector for action '{step.action_type}'.", metadata

    # 4. Safety boundary check
    import re
    action_words = set(re.findall(r"\b[a-zA-Z]+\b", f"{step.action_type} {step.description_short} {step.selector or ''}".lower()))
    is_dest = getattr(step, "is_destructive", False) or bool(action_words.intersection(DESTRUCTIVE_KEYWORDS))
    if is_dest:
        metadata["is_destructive"] = True
        if not policy.allow_destructive:
            metadata.update({"uniqueness": 0, "visible": False, "enabled": False})
            return False, "Destructive operation blocked by sandbox safety policy.", metadata

    # 5. Non-DOM actions (navigate, wait) can proceed safely
    if step.action_type in ("navigate", "wait"):
        return True, None, metadata

    # 6. Live DOM verification
    assert step.selector is not None
    try:
        loc = page.locator(step.selector)
        count = await loc.count()
        metadata["uniqueness"] = count

        if count == 0:
            metadata.update({"visible": False, "enabled": False})
            return False, f"Stale selector: element '{step.selector}' was not found in live DOM.", metadata

        if count > 1:
            metadata.update({"visible": False, "enabled": False})
            return False, f"Non-unique selector: '{step.selector}' matched {count} elements in live DOM.", metadata

        # Check visibility
        is_vis = await loc.first.is_visible()
        metadata["visible"] = is_vis
        if not is_vis:
            return False, f"Target element '{step.selector}' is hidden or not visible.", metadata

        # Check enabled state for interactive actions
        is_en = await loc.first.is_enabled()
        metadata["enabled"] = is_en
        if not is_en and step.action_type in ("click", "input", "check", "select"):
            return False, f"Target element '{step.selector}' is disabled.", metadata

        return True, None, metadata
    except Exception as ex:
        logger.warning("DOM verification exception for selector '%s': %s", step.selector, ex)
        metadata.update({"visible": False, "enabled": False})
        return False, f"DOM check failed with exception: {ex}", metadata


async def evaluate_step_assertion(
    assertion: SynthesizedAssertion,
    page: Page,
    page_errors: list[str],
) -> AssertionValidationResult:
    """
    Deterministically evaluate a single step assertion against live page state.
    
    Guarantees:
    1. Evaluates DOM text, visibility, URLs, and page errors deterministically.
    2. Keeps selector validity strictly separate from business outcome validation.
    3. Retains failed assertions with diagnostic evidence.
    """
    a_type = assertion.assertion_type
    expected = assertion.expected_value
    actual: Any = None
    passed = False
    failure_reason: str | None = None

    try:
        if a_type == "url_matches":
            actual = page.url
            if expected:
                passed = str(expected).lower() in actual.lower()
            else:
                passed = True
            if not passed:
                failure_reason = f"Expected URL containing '{expected}', got '{actual}'"

        elif a_type == "title_matches":
            actual = await page.title()
            if expected:
                passed = str(expected).lower() in (actual or "").lower()
            else:
                passed = True
            if not passed:
                failure_reason = f"Expected title containing '{expected}', got '{actual}'"

        elif a_type == "element_visible":
            sel = assertion.target_selector or ""
            if sel:
                loc = page.locator(sel)
                count = await loc.count()
                actual = (await loc.first.is_visible()) if count > 0 else False
                passed = bool(actual)
                if not passed:
                    failure_reason = f"Target element '{sel}' is not visible in DOM."
            else:
                passed = False
                failure_reason = "No target selector provided for element_visible assertion."

        elif a_type == "text_matches":
            sel = assertion.target_selector
            if sel:
                loc = page.locator(sel)
                count = await loc.count()
                actual = (await loc.first.inner_text()) if count > 0 else ""
            else:
                actual = await page.inner_text("body")

            exp_str = str(expected or "").strip().lower()
            act_str = str(actual or "").strip().lower()
            passed = exp_str in act_str if exp_str else False
            if not passed:
                failure_reason = f"Expected text '{expected}' not found in target text."

        elif a_type == "no_page_error":
            actual = len(page_errors)
            passed = len(page_errors) == 0
            if not passed:
                failure_reason = f"Uncaught page errors detected: {page_errors}"

        else:
            # Unsupported or generic assertion
            passed = False
            failure_reason = f"Unsupported assertion type '{a_type}'."

    except Exception as ex:
        passed = False
        failure_reason = f"Assertion evaluation error: {ex}"

    return AssertionValidationResult(
        assertion_type=a_type,
        target_selector=assertion.target_selector,
        expected_value=expected,
        actual_value=actual,
        passed=passed,
        source=assertion.source,
        requires_human_input=assertion.requires_human_input,
        confidence=assertion.assertion_confidence,
        failure_reason=failure_reason,
    )
