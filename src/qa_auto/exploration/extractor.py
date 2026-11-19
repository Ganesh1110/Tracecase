"""DOM inspection and interactive element extraction for autonomous exploration."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

from playwright.async_api import Page

from qa_auto.exploration.models import (
    FormField,
    FormSchema,
    InteractiveElement,
    compute_state_fingerprint,
    normalize_url,
)

DESTRUCTIVE_KEYWORDS = {
    "delete",
    "remove",
    "destroy",
    "drop",
    "purge",
    "erase",
    "pay",
    "payment",
    "purchase",
    "checkout",
    "credit-card",
    "billing",
    "buy",
    "publish",
    "terminate",
    "revoke",
    "cancel-subscription",
}


def is_destructive_element(
    text: str | None = None,
    tag_name: str | None = None,
    element_type: str | None = None,
    attributes: dict[str, str] | None = None,
) -> tuple[bool, str | None]:
    """
    Heuristically determine if an interactive element or form could perform a destructive action.
    
    Returns (is_destructive, reason).
    """
    text_corpus = (text or "").lower()
    attrs = attributes or {}
    
    for k, v in attrs.items():
        if isinstance(v, str):
            text_corpus += f" {v.lower()}"
            
    if element_type:
        text_corpus += f" {element_type.lower()}"

    # Tokenize words
    tokens = set(re.findall(r"[a-z0-9\-]+", text_corpus))
    matched = tokens.intersection(DESTRUCTIVE_KEYWORDS)
    if matched:
        keyword = next(iter(matched))
        return True, f"Potentially destructive action detected (keyword: '{keyword}')"
        
    return False, None


# JS script to safely extract DOM interactive elements without executing external scripts
EXTRACT_DOM_SCRIPT = """
() => {
    function getCssSelector(el) {
        if (el.id) return '#' + el.id;
        const testId = el.getAttribute('data-testid') || el.getAttribute('data-test');
        if (testId) return `[data-testid="${testId}"]`;
        if (el.name) return `${el.tagName.toLowerCase()}[name="${el.name}"]`;
        
        let path = el.tagName.toLowerCase();
        if (el.className && typeof el.className === 'string') {
            const classes = el.className.trim().split(/\\s+/).filter(c => c && !c.includes(':') && !c.includes('/'));
            if (classes.length > 0) {
                path += '.' + classes.slice(0, 2).join('.');
            }
        }
        return path;
    }

    function isVisible(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    // 1. Extract Links
    const links = [];
    const linkElements = document.querySelectorAll('a[href]');
    for (const a of linkElements) {
        if (isVisible(a)) {
            const href = a.getAttribute('href');
            if (href && !href.startsWith('javascript:') && !href.startsWith('#') && !href.startsWith('mailto:')) {
                links.push({
                    href: a.href,
                    text: (a.innerText || a.textContent || '').trim().slice(0, 100),
                    selector: getCssSelector(a),
                    aria_label: a.getAttribute('aria-label')
                });
            }
        }
    }

    // 2. Extract Buttons
    const buttons = [];
    const buttonElements = document.querySelectorAll('button, input[type="button"], input[type="submit"], [role="button"]');
    for (const b of buttonElements) {
        if (isVisible(b)) {
            const text = (b.innerText || b.value || b.getAttribute('aria-label') || '').trim().slice(0, 100);
            buttons.push({
                tag: b.tagName.toLowerCase(),
                type: b.getAttribute('type') || 'button',
                text: text,
                selector: getCssSelector(b),
                id: b.id || '',
                name: b.getAttribute('name') || '',
                aria_label: b.getAttribute('aria-label') || ''
            });
        }
    }

    // 3. Extract Forms
    const forms = [];
    const formElements = document.querySelectorAll('form');
    let formIdx = 0;
    for (const form of formElements) {
        formIdx++;
        const formId = form.id || `form_${formIdx}`;
        const action = form.getAttribute('action') || '';
        const method = (form.getAttribute('method') || 'POST').toUpperCase();
        const formSelector = form.id ? `#${form.id}` : `form:nth-of-type(${formIdx})`;

        const fields = [];
        const inputs = form.querySelectorAll('input:not([type="hidden"]), select, textarea');
        for (const input of inputs) {
            if (isVisible(input)) {
                fields.push({
                    name: input.getAttribute('name') || '',
                    field_type: input.getAttribute('type') || input.tagName.toLowerCase(),
                    selector: getCssSelector(input),
                    placeholder: input.getAttribute('placeholder') || '',
                    required: input.hasAttribute('required'),
                    label: ''
                });
            }
        }

        const submitBtn = form.querySelector('button[type="submit"], input[type="submit"], button:not([type])');
        let submitSelector = null;
        let submitText = null;
        if (submitBtn) {
            submitSelector = getCssSelector(submitBtn);
            submitText = (submitBtn.innerText || submitBtn.value || '').trim();
        }

        forms.push({
            form_id: formId,
            action: action,
            method: method,
            selector: formSelector,
            fields: fields,
            submit_button_selector: submitSelector,
            submit_button_text: submitText
        });
    }

    return {
        title: document.title || '',
        links: links,
        buttons: buttons,
        forms: forms
    };
}
"""


async def extract_page_surface(page: Page, current_url: str) -> dict[str, Any]:
    """
    Safely extract DOM interactive elements, links, forms, and state fingerprint from a loaded page.
    """
    try:
        raw_data = await page.evaluate(EXTRACT_DOM_SCRIPT)
    except Exception as exc:
        raw_data = {"title": "", "links": [], "buttons": [], "forms": []}

    title = raw_data.get("title", "")
    discovered_links: list[str] = []
    interactive_elements: list[InteractiveElement] = []
    forms: list[FormSchema] = []
    element_selectors: list[str] = []

    # 1. Process Links
    parsed_base = urlparse(current_url)
    for l_data in raw_data.get("links", []):
        href = l_data.get("href")
        if not href:
            continue
        full_url = urljoin(current_url, href)
        normalized = normalize_url(full_url)
        discovered_links.append(normalized)

        selector = l_data.get("selector", "a")
        element_selectors.append(selector)
        text = l_data.get("text", "")
        aria_label = l_data.get("aria_label")
        is_destr, reason = is_destructive_element(text=text, attributes={"href": href, "aria-label": aria_label or ""})

        interactive_elements.append(
            InteractiveElement(
                element_id=f"link_{len(interactive_elements) + 1}",
                tag_name="a",
                selector=selector,
                element_type="link",
                text=text,
                aria_label=aria_label,
                href=normalized,
                is_visible=True,
                is_interactive=True,
                is_destructive=is_destr,
                destructive_reason=reason,
            )
        )

    # 2. Process Buttons
    for b_data in raw_data.get("buttons", []):
        selector = b_data.get("selector", "button")
        element_selectors.append(selector)
        text = b_data.get("text", "")
        tag = b_data.get("tag", "button")
        b_type = b_data.get("type", "button")
        aria_label = b_data.get("aria_label")
        name = b_data.get("name")
        id_val = b_data.get("id")

        is_destr, reason = is_destructive_element(
            text=text,
            tag_name=tag,
            element_type=b_type,
            attributes={"id": id_val, "name": name, "aria-label": aria_label or ""},
        )

        interactive_elements.append(
            InteractiveElement(
                element_id=f"btn_{len(interactive_elements) + 1}",
                tag_name=tag,
                selector=selector,
                element_type=b_type,
                text=text,
                aria_label=aria_label,
                name=name,
                is_visible=True,
                is_interactive=True,
                is_destructive=is_destr,
                destructive_reason=reason,
            )
        )

    # 3. Process Forms
    for f_data in raw_data.get("forms", []):
        fields = [FormField(**field_dict) for field_dict in f_data.get("fields", [])]
        submit_text = f_data.get("submit_button_text")
        action = f_data.get("action")
        form_sel = f_data.get("selector", "form")
        element_selectors.append(form_sel)

        # Check if form is destructive
        is_destr, reason = is_destructive_element(
            text=submit_text,
            attributes={"action": action or "", "id": f_data.get("form_id", "")},
        )

        forms.append(
            FormSchema(
                form_id=f_data.get("form_id", "form"),
                action=action,
                method=f_data.get("method", "POST"),
                selector=form_sel,
                fields=fields,
                submit_button_selector=f_data.get("submit_button_selector"),
                submit_button_text=submit_text,
                is_destructive=is_destr,
                destructive_reason=reason,
            )
        )

    fingerprint = compute_state_fingerprint(current_url, title, element_selectors)

    return {
        "title": title,
        "links": list(dict.fromkeys(discovered_links)),
        "interactive_elements": interactive_elements,
        "forms": forms,
        "fingerprint": fingerprint,
    }
