"""Tests for Phase 9.1.2: Evidence-Grounded AI Journey Generation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from tracecase.ai.models import Message
from tracecase.ai.provider import NullProvider, OllamaProvider, OpenAICompatProvider
from tracecase.exploration.models import (
    AppNavigationGraph,
    FormField,
    FormSchema,
    InteractiveElement,
    PageNode,
    PageTransition,
)
from tracecase.requirements import (
    AcceptanceCriterion,
    EvidenceCatalog,
    IntentMatchResult,
    RequirementSpec,
    TestIntent,
    extract_evidence_catalog,
    generate_journey_from_requirements,
    generate_journey_from_requirements_sync,
    match_intent_to_evidence,
    parse_requirement,
)


@pytest.fixture
def mock_evidence_graph() -> AppNavigationGraph:
    """Graph with home, login, profile settings, and payment/delete forms."""
    home_node = PageNode(
        id="node_home",
        exploration_id="exp_912",
        url="http://127.0.0.1:8000/",
        normalized_url="http://127.0.0.1:8000",
        title="App Home Portal",
        depth=0,
        state_fingerprint="fp_home",
        forms=[],
        interactive_elements=[
            InteractiveElement(
                element_id="btn_login",
                tag_name="button",
                selector="#btn-login",
                text="Log In",
                aria_label="Log In to Account",
            ),
            InteractiveElement(
                element_id="link_pricing",
                tag_name="a",
                selector="#nav-pricing",
                text="Pricing",
                href="http://127.0.0.1:8000/pricing",
            ),
        ],
        links=["http://127.0.0.1:8000/login", "http://127.0.0.1:8000/pricing"],
    )

    profile_node = PageNode(
        id="node_profile",
        exploration_id="exp_912",
        url="http://127.0.0.1:8000/settings/profile",
        normalized_url="http://127.0.0.1:8000/settings/profile",
        title="User Profile Settings",
        depth=1,
        state_fingerprint="fp_profile",
        forms=[
            FormSchema(
                form_id="profile_form",
                action="/settings/profile",
                method="POST",
                selector="#form-profile",
                fields=[
                    FormField(
                        name="email",
                        field_type="email",
                        selector="#input-email",
                        label="Email Address",
                        placeholder="you@example.com",
                    ),
                    FormField(
                        name="full_name",
                        field_type="text",
                        selector="#input-fullname",
                        label="Full Name",
                        placeholder="Jane Doe",
                    ),
                ],
                submit_button_selector="#btn-save-profile",
                submit_button_text="Save Profile",
                is_destructive=False,
            ),
            FormSchema(
                form_id="delete_account_form",
                action="/settings/delete",
                method="POST",
                selector="#form-delete-account",
                fields=[
                    FormField(
                        name="confirm_text",
                        field_type="text",
                        selector="#input-delete-confirm",
                        label="Type DELETE to confirm",
                    ),
                ],
                submit_button_selector="#btn-confirm-delete",
                submit_button_text="Permanently Delete Account",
                is_destructive=True,
                destructive_reason="Irreversible account deletion",
            ),
        ],
        interactive_elements=[
            # Two generic Save buttons to test ambiguity handling
            InteractiveElement(
                element_id="btn_save_draft_1",
                tag_name="button",
                selector="#btn-save-draft-top",
                text="Save",
                aria_label="Save",
            ),
            InteractiveElement(
                element_id="btn_save_draft_2",
                tag_name="button",
                selector="#btn-save-draft-bottom",
                text="Save",
                aria_label="Save",
            ),
        ],
    )

    transitions = [
        PageTransition(
            id="trans_home_profile",
            exploration_id="exp_912",
            source_url="http://127.0.0.1:8000/",
            target_url="http://127.0.0.1:8000/settings/profile",
            action_type="click_link",
            selector="#nav-settings",
            element_text="Settings",
            is_safe=True,
        )
    ]

    return AppNavigationGraph(
        exploration_id="exp_912",
        start_url="http://127.0.0.1:8000/",
        nodes={home_node.id: home_node, profile_node.id: profile_node},
        transitions=transitions,
    )


@pytest.mark.asyncio
async def test_requirement_intent_matches_observed_element(mock_evidence_graph):
    """Test 1: Intent with observed target resolves to observed element with high confidence."""
    catalog = extract_evidence_catalog(mock_evidence_graph)
    intent = TestIntent(
        id="intent_email",
        summary="Enter email address into the profile form",
        target_action="input",
        target_element_hint="Email Address",
        input_value_hint="tester@example.com",
    )

    match = match_intent_to_evidence(intent, catalog)
    assert match.resolution_status == "resolved"
    assert match.primary_evidence_id is not None
    assert match.selector_confidence >= 0.8
    assert "input-email" in match.explanation


@pytest.mark.asyncio
async def test_missing_element_produces_unresolved_confidence_zero(mock_evidence_graph):
    """Test 2: Missing element produces unresolved target with confidence 0.0."""
    catalog = extract_evidence_catalog(mock_evidence_graph)
    intent = TestIntent(
        id="intent_missing",
        summary="Click the non-existent Crypto Checkout button",
        target_action="click",
        target_element_hint="Pay with Bitcoin",
    )

    match = match_intent_to_evidence(intent, catalog)
    assert match.resolution_status == "unresolved"
    assert match.primary_evidence_id is None
    assert match.selector_confidence == 0.0
    assert len(match.matched_evidence_ids) == 0


@pytest.mark.asyncio
async def test_multiple_matching_elements_produce_ambiguous_target(mock_evidence_graph):
    """Test 3: Multiple elements with identical text produce an ambiguous target."""
    catalog = extract_evidence_catalog(mock_evidence_graph)
    intent = TestIntent(
        id="intent_save_ambiguous",
        summary="Click Save",
        target_action="click",
        target_element_hint="Save",
    )

    match = match_intent_to_evidence(intent, catalog)
    assert match.resolution_status == "ambiguous"
    assert match.ambiguity_status == "ambiguous"
    assert len(match.matched_evidence_ids) >= 2
    assert match.primary_evidence_id is None
    assert match.selector_confidence == 0.5


@pytest.mark.asyncio
async def test_llm_invented_evidence_id_rejected(mock_evidence_graph):
    """Test 4: LLM returning an invented evidence ID is rejected and marked unresolved."""
    spec = parse_requirement("As a user I want to save my profile on /settings/profile so that changes persist.")
    fake_provider = NullProvider()

    # Mock provider returning invented evidence ID
    mock_llm_response = {
        "journey_name": "Invented Flow",
        "description": "Hallucinated draft",
        "steps": [
            {
                "intent_id": spec.test_intents[0].id if spec.test_intents else "intent_1",
                "evidence_id": "ev_invented_non_existent_12345",
                "action_type": "click",
                "description_short": "Invented Click",
                "selector": "#synthetic-button",
            }
        ],
    }

    with patch.object(fake_provider, "name", "mock_ai"), patch.object(
        fake_provider, "chat", AsyncMock(return_value=mock_llm_response)
    ):
        draft = await generate_journey_from_requirements(spec, mock_evidence_graph, provider=fake_provider)

        assert len(draft.steps) == 1
        step = draft.steps[0]
        assert step.target_status == "unresolved"
        assert step.selector is None
        assert step.selector_confidence == 0.0
        assert "ev_invented_non_existent_12345" in draft.validation_details["rejected_invented_ids"]


@pytest.mark.asyncio
async def test_llm_unsupported_selector_rejected(mock_evidence_graph):
    """Test 5: LLM returning a valid evidence ID with an invented selector is overridden with observed selector."""
    spec = parse_requirement("As a user I want to save my profile on /settings/profile so that changes persist.")
    fake_provider = NullProvider()

    # Use a real evidence ID from the catalog, but provide a synthetic selector
    catalog = extract_evidence_catalog(mock_evidence_graph)
    real_evidence = catalog.get_evidence("ev_submit_profile_form")
    assert real_evidence is not None

    mock_llm_response = {
        "journey_name": "Profile Flow",
        "description": "Valid evidence, synthetic selector",
        "steps": [
            {
                "intent_id": "intent_test",
                "evidence_id": real_evidence.evidence_id,
                "action_type": "click",
                "selector": "#invented-synthetic-xpath",
                "description_short": "Save Profile",
            }
        ],
    }

    with patch.object(fake_provider, "name", "mock_ai"), patch.object(
        fake_provider, "chat", AsyncMock(return_value=mock_llm_response)
    ):
        draft = await generate_journey_from_requirements(spec, mock_evidence_graph, provider=fake_provider)

        assert len(draft.steps) == 1
        step = draft.steps[0]
        assert step.target_status == "resolved"
        # Overridden with real observed selector
        assert step.selector == real_evidence.selector
        assert "#invented-synthetic-xpath" in draft.validation_details["rejected_unsupported_selectors"]


@pytest.mark.asyncio
async def test_null_provider_generates_valid_evidence_grounded_draft(mock_evidence_graph):
    """Test 6: NullProvider generates a valid, evidence-grounded draft using deterministic matching."""
    spec = parse_requirement(
        "As a user I want to update my Full Name on /settings/profile so that my team recognizes me."
    )
    draft = await generate_journey_from_requirements(spec, mock_evidence_graph, provider=NullProvider())

    assert draft.status == "pending"
    assert draft.approved_testcase_id is None
    assert draft.validation_status == "not_run"
    assert len(draft.steps) >= 2

    # Step 1 is initial navigation
    nav_step = draft.steps[0]
    assert nav_step.action_type == "navigate"
    assert nav_step.target_status == "resolved"

    # Input step matches input-fullname
    input_step = next((s for s in draft.steps if s.action_type == "input"), None)
    assert input_step is not None
    assert input_step.selector == "#input-fullname"
    assert input_step.target_status == "resolved"
    assert input_step.selector_confidence >= 0.8


@pytest.mark.asyncio
async def test_ollama_and_openai_providers_follow_same_output_contract(mock_evidence_graph):
    """Test 7: Ollama and OpenAI providers conform to identical output contract."""
    spec = parse_requirement("As a user I want to log in on / so that I access my account.")
    catalog = extract_evidence_catalog(mock_evidence_graph)
    login_ev = catalog.get_evidence("ev_el_btn_login")
    assert login_ev is not None

    contract_response = {
        "journey_name": "Log In Journey",
        "description": "Standard login flow",
        "steps": [
            {
                "intent_id": "intent_login",
                "evidence_id": login_ev.evidence_id,
                "action_type": "click",
                "selector": login_ev.selector,
                "description_short": "Click Log In button",
                "assertions": [
                    {
                        "assertion_type": "element_visible",
                        "expected_value": "Log In",
                    }
                ],
            }
        ],
    }

    ollama_p = OllamaProvider()
    openai_p = OpenAICompatProvider()

    with patch.object(ollama_p, "chat", AsyncMock(return_value=contract_response)):
        draft_ollama = await generate_journey_from_requirements(spec, mock_evidence_graph, provider=ollama_p)
        assert draft_ollama.validation_details["provider_used"] == "ollama"
        assert draft_ollama.validation_details["is_llm_assisted"] is True
        assert draft_ollama.steps[0].selector == "#btn-login"

    with patch.object(openai_p, "chat", AsyncMock(return_value=contract_response)):
        draft_openai = await generate_journey_from_requirements(spec, mock_evidence_graph, provider=openai_p)
        assert draft_openai.validation_details["provider_used"] == "openai"
        assert draft_openai.validation_details["is_llm_assisted"] is True
        assert draft_openai.steps[0].selector == "#btn-login"


@pytest.mark.asyncio
async def test_assertion_confidence_independent_of_selector_confidence(mock_evidence_graph):
    """Test 8: Selector confidence does not inflate assertion confidence."""
    catalog = extract_evidence_catalog(mock_evidence_graph)
    spec = RequirementSpec(
        title="Profile Update",
        raw_text="Update email",
        format="natural_language",
        test_intents=[
            TestIntent(
                id="intent_1",
                summary="Enter email",
                target_action="input",
                target_element_hint="Email Address",
                input_value_hint="user@test.com",
                expected_outcome="account created successfully and balance updated",
            )
        ],
    )

    draft = await generate_journey_from_requirements(spec, mock_evidence_graph, provider=NullProvider())
    input_step = next(s for s in draft.steps if s.action_type == "input")

    assert input_step.selector_confidence >= 0.8
    # Assertions for this step
    biz_assertion = next(a for a in input_step.assertions if a.assertion_type == "text_matches")
    assert biz_assertion.requires_human_input is True
    assert biz_assertion.assertion_confidence <= 0.5
    assert biz_assertion.assertion_confidence < input_step.selector_confidence


@pytest.mark.asyncio
async def test_unobserved_business_outcomes_require_human_confirmation(mock_evidence_graph):
    """Test 9: Business outcome assertions require explicit human confirmation."""
    spec = parse_requirement("As a user I want to save my profile so that payment verified and ordered.")
    draft = await generate_journey_from_requirements(spec, mock_evidence_graph, provider=NullProvider())

    assert draft.requires_human_input is True
    assert any(a.requires_human_input for s in draft.steps for a in s.assertions)


@pytest.mark.asyncio
async def test_destructive_operations_blocked_from_automatic_execution(mock_evidence_graph):
    """Test 10: Destructive actions are flagged and require human confirmation."""
    spec = parse_requirement("As an admin I want to delete user account on /settings/profile.")
    draft = await generate_journey_from_requirements(spec, mock_evidence_graph, provider=NullProvider())

    assert draft.requires_human_input is True
    assert draft.validation_details["destructive_steps"] >= 1
    # Check that draft status is pending and not auto-executed or approved
    assert draft.status == "pending"
    assert draft.approved_testcase_id is None


def test_sync_journey_generation_wrapper(mock_evidence_graph):
    """Test sync wrapper generate_journey_from_requirements_sync."""
    spec = parse_requirement("As a user I want to log in on /")
    draft = generate_journey_from_requirements_sync(spec, mock_evidence_graph)
    assert draft.id.startswith("draft_")
    assert len(draft.steps) >= 1
