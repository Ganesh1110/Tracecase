"""Requirement parsers for Phase 9.1: User Stories, Gherkin, Acceptance Criteria, OpenAPI, and Natural Language."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any
from urllib.parse import urlparse

import yaml

from tracecase.requirements.models import (
    AcceptanceCriterion,
    IntentActionType,
    RequirementFormat,
    RequirementSpec,
    TestIntent,
)

DESTRUCTIVE_KEYWORDS = {"delete", "remove", "drop", "purge", "pay", "checkout", "destroy", "cancel_subscription"}

USER_STORY_PATTERNS = [
    # "As a <role>, I want <capability>, so that <benefit>" (comma optional)
    re.compile(
        r"^\s*As\s+(?:an?|the)\s+(?P<role>.+?)(?:,\s*|\s+)(?:I\s+(?:want|need|would\s+like)\s+(?:to\s+)?)(?P<capability>.+?)(?:,\s*so\s+that\s+|\s+so\s+that\s+|\s+in\s+order\s+to\s+)(?P<benefit>.+?)\.?\s*$",
        re.IGNORECASE | re.DOTALL,
    ),
    # "In order to <benefit>, as a <role>, I want <capability>" (comma optional)
    re.compile(
        r"^\s*In\s+order\s+to\s+(?P<benefit>.+?)(?:,\s*|\s+)as\s+(?:an?|the)\s+(?P<role>.+?)(?:,\s*|\s+)(?:I\s+(?:want|need|would\s+like)\s+(?:to\s+)?)(?P<capability>.+?)\.?\s*$",
        re.IGNORECASE | re.DOTALL,
    ),
]


def _extract_routes(text: str) -> list[str]:
    """Find potential URL routes mentioned in text (e.g. /login, /dashboard/settings)."""
    # Look for paths starting with / followed by word characters or path separators
    matches = re.findall(r"(?:^|[\s\"'‘`])(\/[a-zA-Z0-9_\-\/\.\?\=\&\%]+)", text)
    routes: list[str] = []
    for m in matches:
        cleaned = m.strip().rstrip(".,;:!\"')`")
        if cleaned.startswith("/") and len(cleaned) > 1 and not cleaned.startswith("//"):
            if cleaned not in routes:
                routes.append(cleaned)
    return routes


def _is_destructive(text: str) -> bool:
    """Check if action or summary involves safety-critical destructive actions."""
    words = set(re.findall(r"\w+", text.lower()))
    return bool(words.intersection(DESTRUCTIVE_KEYWORDS))


def parse_user_story(
    raw_text: str,
    title: str | None = None,
    req_id: str | None = None,
) -> RequirementSpec:
    """Parse a User Story with optional embedded acceptance criteria."""
    lines = [line.strip() for line in raw_text.strip().splitlines() if line.strip()]
    header_part = ""
    ac_part_lines: list[str] = []

    # Check if there is an explicit Acceptance Criteria section
    split_index = -1
    for idx, line in enumerate(lines):
        if re.match(r"^(?:acceptance\s+criteria|ac|scenarios)[\s:]*$", line, re.IGNORECASE):
            split_index = idx
            break

    if split_index != -1:
        header_part = "\n".join(lines[:split_index])
        ac_part_lines = lines[split_index + 1 :]
    else:
        # Search for first line or paragraph that matches user story pattern
        header_part = raw_text

    role: str | None = None
    capability: str | None = None
    benefit: str | None = None

    for pattern in USER_STORY_PATTERNS:
        match = pattern.search(header_part)
        if match:
            role = match.group("role").strip()
            capability = match.group("capability").strip()
            benefit = match.group("benefit").strip()
            break

    # If pattern didn't strictly match, attempt looser extraction
    if not capability:
        role_match = re.search(r"As\s+(?:an?|the)\s+([a-zA-Z0-9_\-\s]+?)(?:,|\s+I\s+want|\s+I\s+need)", header_part, re.IGNORECASE)
        cap_match = re.search(r"I\s+(?:want|need|would\s+like)\s+(?:to\s+)?([^\n,\.]*)", header_part, re.IGNORECASE)
        ben_match = re.search(r"so\s+that\s+([^\n\.]*)", header_part, re.IGNORECASE)
        if role_match:
            role = role_match.group(1).strip()
        if cap_match:
            capability = cap_match.group(1).strip()
        if ben_match:
            benefit = ben_match.group(1).strip()

    spec_title = title or (f"User Story: {capability}" if capability else "User Story Requirement")
    routes = _extract_routes(raw_text)

    acceptance_criteria: list[AcceptanceCriterion] = []
    test_intents: list[TestIntent] = []

    # Parse embedded criteria if present
    if ac_part_lines:
        parsed_ac_spec = parse_acceptance_criteria("\n".join(ac_part_lines), title=spec_title)
        acceptance_criteria.extend(parsed_ac_spec.acceptance_criteria)
        test_intents.extend(parsed_ac_spec.test_intents)
    else:
        # Derive default acceptance criterion and intents from user story capability and benefit
        main_desc = capability or raw_text.strip()
        ac_id = f"ac_{uuid.uuid4().hex[:6]}"
        acceptance_criteria.append(
            AcceptanceCriterion(
                id=ac_id,
                description=f"Verify {main_desc}" + (f" so that {benefit}" if benefit else ""),
                criterion_type="rule",
                confidence=1.0,
            )
        )

        # 1. Navigation intent
        if routes:
            test_intents.append(
                TestIntent(
                    summary=f"Navigate to {routes[0]}",
                    target_action="navigate",
                    target_element_hint=routes[0],
                    criterion_id=ac_id,
                    source="user_story",
                )
            )

        # 2. Capability action intent
        if capability:
            action_type: IntentActionType = "click"
            cap_lower = capability.lower()
            if any(w in cap_lower for w in ("enter", "fill", "input", "type", "provide", "update", "change", "set", "edit")):
                action_type = "input"
            elif any(w in cap_lower for w in ("submit", "send")):
                action_type = "submit"
            elif any(w in cap_lower for w in ("select", "choose")):
                action_type = "select"

            test_intents.append(
                TestIntent(
                    summary=f"Perform action: {capability}",
                    target_action=action_type,
                    target_element_hint=capability,
                    criterion_id=ac_id,
                    source="user_story",
                    is_destructive=_is_destructive(capability),
                )
            )

        # 3. Expected outcome / benefit assertion intent
        if benefit:
            test_intents.append(
                TestIntent(
                    summary=f"Verify benefit: {benefit}",
                    target_action="assert",
                    expected_outcome=benefit,
                    criterion_id=ac_id,
                    source="user_story",
                )
            )

    return RequirementSpec(
        id=req_id or f"req_{uuid.uuid4().hex[:8]}",
        title=spec_title,
        raw_text=raw_text,
        format="user_story",
        user_role=role,
        capability=capability,
        benefit=benefit,
        acceptance_criteria=acceptance_criteria,
        test_intents=test_intents,
        target_routes=routes,
    )


def parse_gherkin(
    raw_text: str,
    title: str | None = None,
    req_id: str | None = None,
) -> RequirementSpec:
    """Parse Gherkin feature and scenario specifications (Feature, Scenario, Given, When, Then, And, But)."""
    lines = raw_text.strip().splitlines()
    feature_title: str | None = None
    feature_desc: list[str] = []

    current_scenario_title: str | None = None
    current_given: list[str] = []
    current_when: list[str] = []
    current_then: list[str] = []
    last_keyword: str = ""

    scenarios: list[dict[str, Any]] = []

    def flush_scenario() -> None:
        if current_scenario_title or current_given or current_when or current_then:
            scenarios.append(
                {
                    "title": current_scenario_title or "Default Scenario",
                    "given": list(current_given),
                    "when": list(current_when),
                    "then": list(current_then),
                }
            )

    for line in lines:
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue

        feat_match = re.match(r"^Feature:\s*(.+)$", cleaned, re.IGNORECASE)
        if feat_match:
            feature_title = feat_match.group(1).strip()
            continue

        scen_match = re.match(r"^(?:Scenario|Scenario\s+Outline):\s*(.+)$", cleaned, re.IGNORECASE)
        if scen_match:
            flush_scenario()
            current_scenario_title = scen_match.group(1).strip()
            current_given = []
            current_when = []
            current_then = []
            last_keyword = ""
            continue

        step_match = re.match(r"^(Given|When|Then|And|But)\s+(.+)$", cleaned, re.IGNORECASE)
        if step_match:
            kw = step_match.group(1).capitalize()
            step_text = step_match.group(2).strip()

            if kw in ("And", "But"):
                kw = last_keyword or "When"

            if kw == "Given":
                current_given.append(step_text)
                last_keyword = "Given"
            elif kw == "When":
                current_when.append(step_text)
                last_keyword = "When"
            elif kw == "Then":
                current_then.append(step_text)
                last_keyword = "Then"
        else:
            if not current_scenario_title:
                feature_desc.append(cleaned)

    flush_scenario()

    routes = _extract_routes(raw_text)
    acceptance_criteria: list[AcceptanceCriterion] = []
    test_intents: list[TestIntent] = []

    for scen in scenarios:
        ac_id = f"ac_{uuid.uuid4().hex[:6]}"
        given_str = " AND ".join(scen["given"]) if scen["given"] else None
        when_str = " AND ".join(scen["when"]) if scen["when"] else None
        then_str = " AND ".join(scen["then"]) if scen["then"] else None

        criterion = AcceptanceCriterion(
            id=ac_id,
            description=f"Scenario: {scen['title']}",
            criterion_type="given_when_then",
            given=given_str,
            when=when_str,
            then=then_str,
            confidence=1.0,
        )
        acceptance_criteria.append(criterion)

        # 1. Given intents (Navigation, Setup, Preconditions)
        for g in scen["given"]:
            g_routes = _extract_routes(g)
            action: IntentActionType = "navigate" if g_routes else "wait"
            hint = g_routes[0] if g_routes else g
            test_intents.append(
                TestIntent(
                    summary=f"Given {g}",
                    target_action=action,
                    target_element_hint=hint,
                    criterion_id=ac_id,
                    source="gherkin",
                    preconditions=[g],
                )
            )

        # 2. When intents (User interactions)
        for w in scen["when"]:
            w_lower = w.lower()
            action = "click"
            input_val = None
            if any(k in w_lower for k in ("enter", "fill", "type", "input")):
                action = "input"
                # Extract quoted value if present
                val_match = re.search(r"[\"']([^\"']+)[\"']", w)
                if val_match:
                    input_val = val_match.group(1)
            elif any(k in w_lower for k in ("submit", "send")):
                action = "submit"
            elif any(k in w_lower for k in ("select", "choose")):
                action = "select"
            elif any(k in w_lower for k in ("check", "tick")):
                action = "check"

            target_hint = w
            target_match = re.search(r"(?:into|on|in|the)\s+[\"']?([^\"'\.\,]+)[\"']?", w)
            if target_match:
                target_hint = target_match.group(1).strip()

            test_intents.append(
                TestIntent(
                    summary=f"When {w}",
                    target_action=action,
                    target_element_hint=target_hint,
                    input_value_hint=input_val,
                    criterion_id=ac_id,
                    source="gherkin",
                    is_destructive=_is_destructive(w),
                )
            )

        # 3. Then intents (Assertions)
        for t in scen["then"]:
            test_intents.append(
                TestIntent(
                    summary=f"Then {t}",
                    target_action="assert",
                    target_element_hint=t,
                    expected_outcome=t,
                    criterion_id=ac_id,
                    source="gherkin",
                )
            )

    spec_title = title or (f"Feature: {feature_title}" if feature_title else "Gherkin Specification")

    return RequirementSpec(
        id=req_id or f"req_{uuid.uuid4().hex[:8]}",
        title=spec_title,
        raw_text=raw_text,
        format="gherkin",
        capability=feature_title,
        acceptance_criteria=acceptance_criteria,
        test_intents=test_intents,
        target_routes=routes,
        metadata={"scenario_count": len(scenarios)},
    )


def parse_acceptance_criteria(
    raw_text: str,
    title: str | None = None,
    req_id: str | None = None,
) -> RequirementSpec:
    """Parse bulleted or numbered acceptance criteria list (e.g. Jira AC format or checklist)."""
    lines = raw_text.strip().splitlines()
    criteria_items: list[str] = []
    current_item: list[str] = []

    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue
        # Check for bullet or number prefix: -, *, 1., AC1:, [ ], etc.
        is_bullet = bool(re.match(r"^(?:[\*\-\+]|\d+[\.\)]|AC\d+[:\-]?|\[[ xX]?\])\s+", cleaned))
        if is_bullet:
            if current_item:
                criteria_items.append(" ".join(current_item))
                current_item = []
            stripped = re.sub(r"^(?:[\*\-\+]|\d+[\.\)]|AC\d+[:\-]?|\[[ xX]?\])\s+", "", cleaned)
            current_item.append(stripped)
        else:
            if current_item:
                current_item.append(cleaned)
            else:
                current_item.append(cleaned)

    if current_item:
        criteria_items.append(" ".join(current_item))

    routes = _extract_routes(raw_text)
    acceptance_criteria: list[AcceptanceCriterion] = []
    test_intents: list[TestIntent] = []

    for item in criteria_items:
        ac_id = f"ac_{uuid.uuid4().hex[:6]}"
        is_dest = _is_destructive(item)

        # Check for embedded Given/When/Then inside bullet
        gwt_match = re.search(r"Given\s+(.+?)\s+When\s+(.+?)\s+Then\s+(.+)", item, re.IGNORECASE)
        if gwt_match:
            c_type = "given_when_then"
            g_part = gwt_match.group(1).strip()
            w_part = gwt_match.group(2).strip()
            t_part = gwt_match.group(3).strip()
            ac = AcceptanceCriterion(
                id=ac_id,
                description=item,
                criterion_type=c_type,
                given=g_part,
                when=w_part,
                then=t_part,
            )
            # Create intents for Given, When, Then
            test_intents.append(
                TestIntent(
                    summary=f"Given {g_part}",
                    target_action="navigate" if "/" in g_part else "wait",
                    target_element_hint=g_part,
                    criterion_id=ac_id,
                    source="acceptance_criteria",
                )
            )
            test_intents.append(
                TestIntent(
                    summary=f"When {w_part}",
                    target_action="click" if "click" in w_part.lower() else "input",
                    target_element_hint=w_part,
                    criterion_id=ac_id,
                    source="acceptance_criteria",
                    is_destructive=is_dest,
                )
            )
            test_intents.append(
                TestIntent(
                    summary=f"Then {t_part}",
                    target_action="assert",
                    expected_outcome=t_part,
                    criterion_id=ac_id,
                    source="acceptance_criteria",
                )
            )
        else:
            c_type = "rule"
            ac = AcceptanceCriterion(
                id=ac_id,
                description=item,
                criterion_type=c_type,
            )
            # Derive action intent and assertion intent
            action_type: IntentActionType = "click"
            item_lower = item.lower()
            if any(w in item_lower for w in ("enter", "fill", "type", "input")):
                action_type = "input"
            elif any(w in item_lower for w in ("assert", "verify", "should", "display", "see")):
                action_type = "assert"

            test_intents.append(
                TestIntent(
                    summary=f"Verify criterion: {item}",
                    target_action=action_type,
                    target_element_hint=item,
                    expected_outcome=item if action_type == "assert" else None,
                    criterion_id=ac_id,
                    source="acceptance_criteria",
                    is_destructive=is_dest,
                )
            )

        acceptance_criteria.append(ac)

    spec_title = title or "Acceptance Criteria Specification"

    return RequirementSpec(
        id=req_id or f"req_{uuid.uuid4().hex[:8]}",
        title=spec_title,
        raw_text=raw_text,
        format="acceptance_criteria",
        acceptance_criteria=acceptance_criteria,
        test_intents=test_intents,
        target_routes=routes,
        metadata={"criteria_count": len(acceptance_criteria)},
    )


def parse_openapi(
    raw_input: str | dict[str, Any],
    title: str | None = None,
    req_id: str | None = None,
) -> RequirementSpec:
    """Parse OpenAPI 3.x or Swagger 2.0 specifications to derive API and UI journey intents."""
    if isinstance(raw_input, dict):
        spec_dict = raw_input
        raw_text = json.dumps(raw_input, indent=2)
    else:
        raw_text = raw_input.strip()
        try:
            spec_dict = json.loads(raw_text)
        except Exception:
            spec_dict = yaml.safe_load(raw_text) or {}

    info = spec_dict.get("info", {})
    api_title = title or info.get("title", "OpenAPI Specification")
    paths = spec_dict.get("paths", {})

    acceptance_criteria: list[AcceptanceCriterion] = []
    test_intents: list[TestIntent] = []
    routes: list[str] = []

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        if path not in routes:
            routes.append(path)

        for method in ("get", "post", "put", "patch", "delete"):
            op = path_item.get(method)
            if not op or not isinstance(op, dict):
                continue

            summary = op.get("summary") or op.get("operationId") or f"{method.upper()} {path}"
            op_desc = op.get("description", "")
            ac_id = f"ac_{uuid.uuid4().hex[:6]}"
            is_dest = method in ("delete", "purge") or _is_destructive(summary)

            criterion = AcceptanceCriterion(
                id=ac_id,
                description=f"{method.upper()} {path}: {summary}",
                criterion_type="rule",
                tags=[method.upper(), path],
                confidence=1.0,
            )
            acceptance_criteria.append(criterion)

            # Route navigation / endpoint intent
            test_intents.append(
                TestIntent(
                    summary=f"Navigate / Target endpoint {path} ({method.upper()})",
                    target_action="navigate",
                    target_element_hint=path,
                    criterion_id=ac_id,
                    source="openapi",
                )
            )

            # Request body parameters
            req_body = op.get("requestBody", {})
            content = req_body.get("content", {})
            json_schema = content.get("application/json", {}).get("schema", {})
            properties = json_schema.get("properties", {})

            for prop_name, prop_meta in properties.items():
                p_type = prop_meta.get("type", "string")
                test_intents.append(
                    TestIntent(
                        summary=f"Input parameter '{prop_name}' ({p_type}) for {path}",
                        target_action="input",
                        target_element_hint=prop_name,
                        input_value_hint=f"test_{prop_name}",
                        criterion_id=ac_id,
                        source="openapi",
                    )
                )

            # Submission or execution intent
            if method in ("post", "put", "patch", "delete"):
                test_intents.append(
                    TestIntent(
                        summary=f"Submit {method.upper()} request to {path}",
                        target_action="submit",
                        target_element_hint=f"submit-{method}",
                        criterion_id=ac_id,
                        source="openapi",
                        is_destructive=is_dest,
                    )
                )

            # Response assertion intents
            responses = op.get("responses", {})
            for status_code, resp_obj in responses.items():
                r_desc = resp_obj.get("description", "") if isinstance(resp_obj, dict) else ""
                test_intents.append(
                    TestIntent(
                        summary=f"Assert response status {status_code} for {method.upper()} {path}: {r_desc}",
                        target_action="assert",
                        expected_outcome=f"status_code_{status_code}",
                        criterion_id=ac_id,
                        source="openapi",
                    )
                )

    return RequirementSpec(
        id=req_id or f"req_{uuid.uuid4().hex[:8]}",
        title=api_title,
        raw_text=raw_text,
        format="openapi",
        capability=info.get("description", api_title),
        acceptance_criteria=acceptance_criteria,
        test_intents=test_intents,
        target_routes=routes,
        metadata={"openapi_version": spec_dict.get("openapi") or spec_dict.get("swagger", "unknown")},
    )


def parse_natural_language(
    raw_text: str,
    title: str | None = None,
    req_id: str | None = None,
) -> RequirementSpec:
    """Parse unstructured natural language requirements, PR descriptions, or feature summaries."""
    text_clean = raw_text.strip()
    routes = _extract_routes(text_clean)
    spec_title = title or (text_clean.splitlines()[0][:80] if text_clean else "Requirement")

    acceptance_criteria: list[AcceptanceCriterion] = []
    test_intents: list[TestIntent] = []

    # Break into sentences or clauses
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text_clean) if s.strip()]
    if not sentences:
        sentences = [text_clean]

    for sent in sentences:
        ac_id = f"ac_{uuid.uuid4().hex[:6]}"
        is_dest = _is_destructive(sent)

        ac = AcceptanceCriterion(
            id=ac_id,
            description=sent,
            criterion_type="rule",
            confidence=0.9,
        )
        acceptance_criteria.append(ac)

        # Look for actions inside the sentence
        sent_lower = sent.lower()
        action_found: IntentActionType = "assert"
        if any(w in sent_lower for w in ("click", "press", "tap")):
            action_found = "click"
        elif any(w in sent_lower for w in ("enter", "fill", "type", "provide", "write")):
            action_found = "input"
        elif any(w in sent_lower for w in ("select", "pick", "choose")):
            action_found = "select"
        elif any(w in sent_lower for w in ("navigate", "open", "visit", "go to")):
            action_found = "navigate"
        elif any(w in sent_lower for w in ("submit", "send")):
            action_found = "submit"

        test_intents.append(
            TestIntent(
                summary=f"Intent: {sent}",
                target_action=action_found,
                target_element_hint=sent,
                expected_outcome=sent if action_found == "assert" else None,
                criterion_id=ac_id,
                source="natural_language",
                is_destructive=is_dest,
                confidence=0.85,
            )
        )

    # If routes discovered, add explicit navigation intent at the top
    for route in routes:
        test_intents.insert(
            0,
            TestIntent(
                summary=f"Navigate to {route}",
                target_action="navigate",
                target_element_hint=route,
                source="natural_language",
                confidence=1.0,
            ),
        )

    return RequirementSpec(
        id=req_id or f"req_{uuid.uuid4().hex[:8]}",
        title=spec_title,
        raw_text=raw_text,
        format="natural_language",
        acceptance_criteria=acceptance_criteria,
        test_intents=test_intents,
        target_routes=routes,
    )


def detect_requirement_format(raw_input: str | dict[str, Any]) -> RequirementFormat:
    """Auto-detect the format of input requirement text or payload."""
    if isinstance(raw_input, dict):
        if "openapi" in raw_input or "swagger" in raw_input or "paths" in raw_input:
            return "openapi"
        return "natural_language"

    text = raw_input.strip()

    # Check for OpenAPI JSON or YAML
    if text.startswith("{") or text.startswith("openapi:") or text.startswith("swagger:"):
        try:
            parsed = json.loads(text) if text.startswith("{") else yaml.safe_load(text)
            if isinstance(parsed, dict) and ("openapi" in parsed or "swagger" in parsed or "paths" in parsed):
                return "openapi"
        except Exception:
            pass

    # Check for Gherkin keywords
    if re.search(r"^\s*(?:Feature|Scenario|Scenario\s+Outline):", text, re.IGNORECASE | re.MULTILINE):
        return "gherkin"

    # Check for Given/When/Then block
    if (
        re.search(r"\bGiven\b", text, re.IGNORECASE)
        and re.search(r"\bWhen\b", text, re.IGNORECASE)
        and re.search(r"\bThen\b", text, re.IGNORECASE)
    ):
        return "gherkin"

    # Check for User Story template
    for pattern in USER_STORY_PATTERNS:
        if pattern.search(text):
            return "user_story"
    if re.search(r"^\s*As\s+(?:an?|the)\s+[a-zA-Z0-9_\-\s]+?(?:,\s*|\s+)I\s+(?:want|need)", text, re.IGNORECASE | re.MULTILINE):
        return "user_story"

    # Check for structured Acceptance Criteria headers or numbered bullet points
    if re.search(r"^(?:acceptance\s+criteria|ac|scenarios)[\s:]*", text, re.IGNORECASE | re.MULTILINE):
        return "acceptance_criteria"
    if re.search(r"^\s*(?:AC\d+|[0-9]+\.|\-|\*)\s+(?:User\s+can|Must|Should|Ensure|Verify)", text, re.IGNORECASE | re.MULTILINE):
        return "acceptance_criteria"

    return "natural_language"


def parse_requirement(
    raw_input: str | dict[str, Any],
    format: RequirementFormat | None = None,
    title: str | None = None,
    req_id: str | None = None,
) -> RequirementSpec:
    """
    Unified entrypoint to parse requirements from any format into a structured RequirementSpec.
    
    Auto-detects format if not explicitly provided.
    """
    detected_format = format or detect_requirement_format(raw_input)

    if detected_format == "user_story" and isinstance(raw_input, str):
        return parse_user_story(raw_input, title=title, req_id=req_id)
    elif detected_format == "gherkin" and isinstance(raw_input, str):
        return parse_gherkin(raw_input, title=title, req_id=req_id)
    elif detected_format == "acceptance_criteria" and isinstance(raw_input, str):
        return parse_acceptance_criteria(raw_input, title=title, req_id=req_id)
    elif detected_format == "openapi":
        return parse_openapi(raw_input, title=title, req_id=req_id)
    else:
        text = str(raw_input) if not isinstance(raw_input, str) else raw_input
        return parse_natural_language(text, title=title, req_id=req_id)
