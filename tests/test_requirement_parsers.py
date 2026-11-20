"""Tests for Phase 9.1.1: Requirement Data Models and Multi-Format Parsers."""

from __future__ import annotations

import json
import pytest

from tracecase.exploration.models import SynthesizedAssertion, SynthesizedStep, TestJourneyDraft
from tracecase.requirements import (
    AcceptanceCriterion,
    RequirementFormat,
    RequirementSpec,
    TestIntent,
    detect_requirement_format,
    parse_acceptance_criteria,
    parse_gherkin,
    parse_natural_language,
    parse_openapi,
    parse_requirement,
    parse_user_story,
)


def test_user_story_parser_standard():
    raw = (
        "As a registered shopper, I want to add items to my shopping cart, "
        "so that I can purchase them later from /checkout."
    )
    spec = parse_user_story(raw)

    assert spec.format == "user_story"
    assert spec.user_role == "registered shopper"
    assert "add items to my shopping cart" in spec.capability
    assert "purchase them later" in spec.benefit
    assert "/checkout" in spec.target_routes
    assert len(spec.acceptance_criteria) >= 1
    assert len(spec.test_intents) >= 2

    # Check intent derivation
    route_intent = next((i for i in spec.test_intents if i.target_action == "navigate"), None)
    assert route_intent is not None
    assert route_intent.target_element_hint == "/checkout"

    action_intent = next((i for i in spec.test_intents if i.target_action in ("click", "input", "submit")), None)
    assert action_intent is not None


def test_user_story_with_embedded_acceptance_criteria():
    raw = """
    As an administrator, I want to manage user permissions on /admin/roles
    so that I can enforce security policies.

    Acceptance Criteria:
    - User can toggle admin privileges for any role
    - Changes must be saved when clicking 'Save Roles'
    - Delete role action should require explicit confirmation
    """
    spec = parse_user_story(raw)

    assert spec.user_role == "administrator"
    assert "/admin/roles" in spec.target_routes
    assert len(spec.acceptance_criteria) == 3
    # Verify destructive detection
    delete_intent = next((i for i in spec.test_intents if "Delete" in i.summary or "delete" in i.summary.lower()), None)
    assert delete_intent is not None
    assert delete_intent.is_destructive is True


def test_gherkin_parser_scenarios_and_steps():
    raw = """
    Feature: Customer Checkout
      Scenario: Successful checkout with credit card
        Given the customer is on "/checkout/payment"
        When the customer enters "Jane Doe" into the name field
        And the customer enters "4111222233334444" into the card number field
        And the customer clicks the "Place Order" button
        Then the customer should be redirected to "/checkout/success"
        And the page should display "Order Confirmation #12345"
    """
    spec = parse_gherkin(raw)

    assert spec.format == "gherkin"
    assert "Customer Checkout" in spec.title
    assert "/checkout/payment" in spec.target_routes
    assert "/checkout/success" in spec.target_routes
    assert len(spec.acceptance_criteria) == 1
    ac = spec.acceptance_criteria[0]
    assert ac.criterion_type == "given_when_then"
    assert ac.given is not None
    assert ac.when is not None
    assert ac.then is not None

    # Verify extracted test intents
    intents = spec.test_intents
    assert len(intents) == 6

    # 1. Given intent
    assert intents[0].target_action == "navigate"
    assert intents[0].target_element_hint == "/checkout/payment"

    # 2. Input intents with extracted values
    input_intents = [i for i in intents if i.target_action == "input"]
    assert len(input_intents) == 2
    assert input_intents[0].input_value_hint == "Jane Doe"
    assert input_intents[1].input_value_hint == "4111222233334444"

    # 3. Click intent
    click_intent = next(i for i in intents if i.target_action == "click")
    assert "Place Order" in click_intent.summary

    # 4. Assert intents
    assert_intents = [i for i in intents if i.target_action == "assert"]
    assert len(assert_intents) == 2
    assert any("/checkout/success" in (i.expected_outcome or "") for i in assert_intents)


def test_acceptance_criteria_parser_bullets_and_gwt():
    raw = """
    1. Given the user visits /login When they input valid email Then they are redirected to /home
    2. Must display an error message when password is less than 8 characters
    3. Clicking logout must clear the session and return to /welcome
    """
    spec = parse_acceptance_criteria(raw)

    assert spec.format == "acceptance_criteria"
    assert len(spec.acceptance_criteria) == 3
    assert "/login" in spec.target_routes
    assert "/welcome" in spec.target_routes

    # First criterion is GWT
    assert spec.acceptance_criteria[0].criterion_type == "given_when_then"
    assert spec.acceptance_criteria[0].given is not None


def test_openapi_parser():
    spec_dict = {
        "openapi": "3.0.0",
        "info": {
            "title": "User Management Service",
            "version": "1.0.0",
            "description": "API for managing users and teams.",
        },
        "paths": {
            "/api/v1/users": {
                "get": {
                    "summary": "List all users",
                    "responses": {"200": {"description": "List of users"}},
                },
                "post": {
                    "summary": "Create new user",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "email": {"type": "string"},
                                        "full_name": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {"description": "User created"},
                        "400": {"description": "Invalid input"},
                    },
                },
            },
            "/api/v1/users/{id}": {
                "delete": {
                    "summary": "Delete user",
                    "responses": {"204": {"description": "User deleted"}},
                }
            },
        },
    }

    spec = parse_openapi(spec_dict)
    assert spec.format == "openapi"
    assert spec.title == "User Management Service"
    assert "/api/v1/users" in spec.target_routes
    assert "/api/v1/users/{id}" in spec.target_routes
    assert len(spec.acceptance_criteria) == 3

    # Check request body parameter intents
    email_intent = next((i for i in spec.test_intents if i.target_element_hint == "email"), None)
    assert email_intent is not None
    assert email_intent.target_action == "input"

    # Check destructive DELETE operation
    delete_intent = next((i for i in spec.test_intents if "DELETE" in i.summary and i.target_action == "submit"), None)
    assert delete_intent is not None
    assert delete_intent.is_destructive is True


def test_natural_language_parser():
    raw = "Ensure customers can update their profile picture on /settings/avatar and see the updated image preview."
    spec = parse_natural_language(raw)

    assert spec.format == "natural_language"
    assert "/settings/avatar" in spec.target_routes
    assert len(spec.test_intents) >= 2
    assert spec.test_intents[0].target_action == "navigate"
    assert spec.test_intents[0].target_element_hint == "/settings/avatar"


def test_detect_requirement_format_and_unified_parser():
    # User story detection
    us_text = "As a member, I want to bookmark articles, so that I can read them offline."
    assert detect_requirement_format(us_text) == "user_story"
    res_us = parse_requirement(us_text)
    assert res_us.format == "user_story"
    assert res_us.user_role == "member"

    # Gherkin detection
    gh_text = "Feature: Search\nScenario: Simple query\nGiven on /search\nWhen query 'books'\nThen see results"
    assert detect_requirement_format(gh_text) == "gherkin"
    res_gh = parse_requirement(gh_text)
    assert res_gh.format == "gherkin"

    # OpenAPI detection
    oai_json = json.dumps({"openapi": "3.0.0", "paths": {"/status": {"get": {}}}})
    assert detect_requirement_format(oai_json) == "openapi"
    res_oai = parse_requirement(oai_json)
    assert res_oai.format == "openapi"


def test_backwards_compatibility_and_model_enhancements():
    """Verify that TestJourneyDraft, SynthesizedStep, and SynthesizedAssertion enhancements satisfy 9.1 design constraints."""
    assertion = SynthesizedAssertion(
        assertion_type="element_visible",
        target_selector="#submit-btn",
        assertion_confidence=0.95,
        validation_outcome="passed",
    )
    assert assertion.assertion_confidence == 0.95
    assert assertion.validation_outcome == "passed"

    # Never invent selector: unresolved status & separate selector confidence
    step = SynthesizedStep(
        number=1,
        action_type="click",
        selector=None,
        target_status="unresolved",
        selector_confidence=0.0,
        description_short="Click missing submit button",
        description_detailed="Target was not observed in navigation graph",
        assertions=[assertion],
    )
    assert step.target_status == "unresolved"
    assert step.selector_confidence == 0.0
    assert step.assertions[0].assertion_confidence == 0.95

    # Draft with validation status states: verified, partially_verified, failed, blocked, not_run
    draft = TestJourneyDraft(
        id="draft_test_1",
        exploration_id="exp_1",
        name="Cart Flow",
        start_url="https://example.com",
        steps=[step],
        validation_status="partially_verified",
        validation_details={"passed_steps": 0, "unresolved_steps": 1},
        requirement_id="req_cart_1",
    )
    assert draft.validation_status == "partially_verified"
    assert draft.requirement_id == "req_cart_1"
    assert draft.version == 1
