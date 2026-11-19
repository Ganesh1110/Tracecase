"""Selector Intelligence & Fragility Detection Engine for QA Auto.

Evaluates CSS and XPath locators for fragility risks (dynamic IDs, hashed CSS classes,
deep absolute XPaths, generic tags) and generates Playwright resilient alternatives.
"""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from qa_auto.models import TestCase

StabilityTier = Literal["resilient", "moderate", "fragile"]


class SelectorAnalysis(BaseModel):
    """Detailed stability audit and recommendations for an element selector."""

    step_number: int
    action_type: str
    original_selector: str
    current_selector: str = ""
    fragility_score: int = Field(description="Fragility from 0 (resilient) to 100 (extremely fragile)")
    stability_tier: StabilityTier
    is_fragile: bool = False
    issues: list[str] = Field(default_factory=list)
    recommended_selector: str
    playwright_locator: str
    recommended_locator: str = ""
    rationale: str


class SelectorAuditReport(BaseModel):
    """Corpus or testcase selector audit report."""

    total_evaluated: int
    fragile_count: int
    safe_count: int
    selectors: list[SelectorAnalysis]


# Regex patterns for common fragile selector artifacts
HASHED_CLASS_PATTERN = re.compile(
    r"\b(css-[a-z0-9]+|sc-[a-z0-9]+|ng-tns-[a-z0-9\-]+|jsx-[0-9]+|style__[a-zA-Z0-9_\-]+__[a-z0-9]+)\b",
    re.IGNORECASE,
)
DYNAMIC_ID_PATTERN = re.compile(r"#.*[0-9]{4,}", re.IGNORECASE)
ABSOLUTE_XPATH_PATTERN = re.compile(r"^/html/|^/body/|/\w+\[\d+\]/\w+\[\d+\]", re.IGNORECASE)


def evaluate_selector(
    selector: str,
    tag_name: str | None = None,
    text: str | None = None,
    attributes: dict[str, str] | None = None,
    step_number: int = 1,
    action_type: str = "click",
) -> SelectorAnalysis:
    """Analyze a single selector and compute stability metrics and resilient replacements."""
    issues: list[str] = []
    base_score = 15  # Baseline

    sel_clean = (selector or "").strip()
    attrs = attributes or {}
    text_clean = (text or "").strip()
    tag = (tag_name or "").lower().strip()

    # 1. Absolute XPath Check
    if ABSOLUTE_XPATH_PATTERN.search(sel_clean) or sel_clean.count("/") > 3:
        issues.append("Deep or absolute XPath hierarchy prone to breaking on layout changes.")
        base_score += 45

    # 2. Hashed / Generated CSS Class Check
    if HASHED_CLASS_PATTERN.search(sel_clean):
        issues.append("Hashed / auto-generated CSS class names detected (e.g., CSS-in-JS or Tailwind hash).")
        base_score += 35

    # 3. Dynamic Numeric ID Check
    if DYNAMIC_ID_PATTERN.search(sel_clean):
        issues.append("Dynamic or auto-incrementing numeric ID detected.")
        base_score += 30

    # 4. Overly Broad Tag / Index Selectors
    if re.search(r":nth-child\(\d+\)|:nth-of-type\(\d+\)", sel_clean):
        issues.append("Positional index selector (:nth-child) prone to off-by-one breakages.")
        base_score += 20
    if sel_clean in ("div > button", "div > a", "span > input", "button", "input"):
        issues.append("Broad generic tag selector without specific qualifier.")
        base_score += 25

    # 5. Check for Resilient Attributes
    test_id = attrs.get("data-testid") or attrs.get("data-test") or attrs.get("data-qa")
    aria_label = attrs.get("aria-label") or attrs.get("placeholder") or attrs.get("name")
    has_semantic_id = bool(re.search(r"#[a-zA-Z][a-zA-Z0-9_\-]{3,}$", sel_clean) and not DYNAMIC_ID_PATTERN.search(sel_clean))

    if test_id:
        base_score = max(5, base_score - 40)
    elif aria_label:
        base_score = max(10, base_score - 25)
    elif has_semantic_id:
        base_score = max(10, base_score - 20)

    fragility_score = min(100, max(0, base_score))

    if fragility_score <= 25:
        tier: StabilityTier = "resilient"
    elif fragility_score <= 60:
        tier = "moderate"
    else:
        tier = "fragile"

    # Derive Resilient Replacement & Playwright Locator
    recommended_selector = sel_clean
    playwright_locator = f"page.locator('{sel_clean}')"
    rationale = "Selector is reasonably stable."

    if test_id:
        recommended_selector = f"[data-testid='{test_id}']"
        playwright_locator = f"page.getByTestId('{test_id}')"
        rationale = f"Use dedicated test attribute data-testid='{test_id}' for maximum stability across UI redesigns."
    elif aria_label and tag in ("input", "textarea"):
        if attrs.get("placeholder"):
            recommended_selector = f"input[placeholder='{attrs['placeholder']}']"
            playwright_locator = f"page.getByPlaceholder('{attrs['placeholder']}')"
            rationale = "Locate input via visible user-facing placeholder."
        else:
            recommended_selector = f"[aria-label='{aria_label}']"
            playwright_locator = f"page.getByLabel('{aria_label}')"
            rationale = "Locate form control via accessible ARIA label."
    elif tag in ("button", "a") and text_clean and len(text_clean) < 30:
        role_name = "button" if tag == "button" else "link"
        recommended_selector = f"{tag}:has-text('{text_clean}')"
        playwright_locator = f"page.getByRole('{role_name}', name='{text_clean}')"
        rationale = f"Use accessible user-facing role '{role_name}' with name '{text_clean}'."
    elif has_semantic_id:
        recommended_selector = sel_clean
        playwright_locator = f"page.locator('{sel_clean}')"
        rationale = "Semantic unique element ID provides good stability."
    elif issues:
        # Fallback cleanup: if xpath had text, use text-based locator
        text_match = re.search(r"text\(\)\s*=\s*['\"]([^'\"]+)['\"]", sel_clean)
        if text_match:
            val = text_match.group(1)
            recommended_selector = f"text={val}"
            playwright_locator = f"page.getByText('{val}')"
            rationale = "Replaced fragile positional XPath with user-facing visible text locator."
        else:
            rationale = "Recommend adding a data-testid attribute to this element in your frontend source."

    is_fragile = fragility_score >= 35 or bool(issues)
    rec_loc = playwright_locator or recommended_selector

    return SelectorAnalysis(
        step_number=step_number,
        action_type=action_type,
        original_selector=sel_clean,
        current_selector=sel_clean,
        fragility_score=fragility_score,
        stability_tier=tier,
        is_fragile=is_fragile,
        issues=issues if issues else ["No major fragility risks detected."],
        recommended_selector=recommended_selector,
        playwright_locator=playwright_locator,
        recommended_locator=rec_loc,
        rationale=rationale,
    )


def audit_testcase_selectors(testcase: TestCase) -> SelectorAuditReport:
    """Audit all element selectors across an entire test case."""
    analyses: list[SelectorAnalysis] = []
    for step in testcase.steps:
        if step.element and step.element.selector:
            analysis = evaluate_selector(
                selector=step.element.selector,
                tag_name=step.element.tag_name,
                text=step.element.text,
                attributes=step.element.attributes,
                step_number=step.number,
                action_type=step.action_type,
            )
            analyses.append(analysis)

    fragile_count = sum(1 for a in analyses if a.is_fragile)
    safe_count = len(analyses) - fragile_count

    return SelectorAuditReport(
        total_evaluated=len(analyses),
        fragile_count=fragile_count,
        safe_count=safe_count,
        selectors=analyses,
    )


def normalize_playwright_selector(selector: str) -> str:
    """Convert code-style Playwright locator expressions into standard engine selectors."""
    sel = selector.strip()
    if not sel.startswith("page."):
        return sel

    # 1. getByTestId('id') or getByTestId("id")
    m_testid = re.search(r"getByTestId\(['\"]([^'\"]+)['\"]\)", sel)
    if m_testid:
        return f"[data-testid='{m_testid.group(1)}']"

    # 2. getByRole('role', name='Name')
    m_role = re.search(r"getByRole\(['\"]([^'\"]+)['\"](?:,\s*name=['\"]([^'\"]+)['\"])?\)", sel)
    if m_role:
        role = m_role.group(1)
        name = m_role.group(2)
        if name:
            return f"role={role}[name='{name}']"
        return f"role={role}"

    # 3. getByText('text')
    m_text = re.search(r"getByText\(['\"]([^'\"]+)['\"]\)", sel)
    if m_text:
        return f"text={m_text.group(1)}"

    # 4. getByLabel('label')
    m_label = re.search(r"getByLabel\(['\"]([^'\"]+)['\"]\)", sel)
    if m_label:
        return f"[aria-label='{m_label.group(1)}']"

    # 5. locator('selector')
    m_loc = re.search(r"locator\(['\"]([^'\"]+)['\"]\)", sel)
    if m_loc:
        return m_loc.group(1)

    return sel


async def verify_locator_in_live_dom(
    target_url: str,
    candidate_selector: str,
    step_number: int | None = None,
    expected_tag: str | None = None,
    expected_text: str | None = None,
    allowed_hosts: list[str] | None = None,
    timeout_ms: int = 5000,
) -> dict[str, Any]:
    """Live DOM resolution probe: verifies candidate locator matches exactly 1 intended element.

    Enforces allowed-host restrictions to prevent unrestricted arbitrary external navigation.
    """
    parsed = urlparse(target_url)
    hostname = (parsed.hostname or "").lower()
    default_allowed = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "testserver"}
    if allowed_hosts:
        default_allowed.update(h.lower() for h in allowed_hosts)

    if hostname not in default_allowed:
        raise ValueError(
            f"Host restriction denied: Target host '{hostname}' is not in the allowed verification hosts list."
        )

    clean_selector = normalize_playwright_selector(candidate_selector)

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)

            loc = page.locator(clean_selector)
            count = await loc.count()

            if count == 0:
                return {
                    "verified": False,
                    "count": 0,
                    "candidate_selector": candidate_selector,
                    "normalized_selector": clean_selector,
                    "reason": "No elements matched candidate locator in live DOM.",
                }

            if count > 1:
                return {
                    "verified": False,
                    "count": count,
                    "candidate_selector": candidate_selector,
                    "normalized_selector": clean_selector,
                    "reason": f"Ambiguous locator: matched {count} elements (must uniquely match exactly 1).",
                }

            # Exactly one match: verify semantic identity and visibility
            is_visible = await loc.first.is_visible()
            if not is_visible:
                return {
                    "verified": False,
                    "count": 1,
                    "candidate_selector": candidate_selector,
                    "normalized_selector": clean_selector,
                    "reason": "Element matched in DOM but is currently hidden/invisible.",
                }

            eval_res = await loc.first.evaluate(
                """el => {
                    const attrs = {};
                    for (let i = 0; i < el.attributes.length; i++) {
                        attrs[el.attributes[i].name] = el.attributes[i].value;
                    }
                    return {
                        tag: (el.tagName || '').toLowerCase(),
                        text: (el.textContent || '').trim().substring(0, 100),
                        attributes: attrs
                    };
                }"""
            )

            matched_tag = eval_res.get("tag", "")
            matched_text = eval_res.get("text", "")
            attrs = eval_res.get("attributes", {})

            # Check tag identity
            if expected_tag and matched_tag != expected_tag.lower():
                return {
                    "verified": False,
                    "count": 1,
                    "matched_tag": matched_tag,
                    "reason": f"Element tag mismatch: expected '{expected_tag}', found '{matched_tag}'.",
                }

            # Check text / semantic label identity
            if expected_text and expected_text.strip():
                clean_exp = expected_text.strip().lower()
                text_match = clean_exp in matched_text.lower()
                attr_match = any(clean_exp in str(v).lower() for v in attrs.values())
                if not (text_match or attr_match):
                    return {
                        "verified": False,
                        "count": 1,
                        "matched_text": matched_text,
                        "reason": f"Element semantic mismatch: expected text/label '{expected_text}', found '{matched_text}'.",
                    }

            return {
                "verified": True,
                "count": 1,
                "matched_tag": matched_tag,
                "matched_text": matched_text,
                "attributes": attrs,
                "candidate_selector": candidate_selector,
                "normalized_selector": clean_selector,
                "reason": "Locator verified: uniquely and accurately identifies intended DOM element.",
            }
        finally:
            await browser.close()

