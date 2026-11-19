"""Phase 6.2 tests: Journey Synthesis, Evidence Provenance, Draft Management & Human Approval Gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from qa_auto.exploration.models import (
    AppNavigationGraph,
    FormField,
    FormSchema,
    InteractiveElement,
    PageNode,
    PageTransition,
)
from qa_auto.exploration.synthesizer import synthesize_test_journeys
from qa_auto.models import TestCase
from qa_auto.ui.db import (
    add_testcase_to_suite,
    approve_synthesized_draft,
    create_exploration_run,
    create_project,
    create_suite,
    get_connection,
    get_synthesized_draft,
    get_testcase_meta,
    init_studio_db,
    list_synthesized_drafts,
    reject_synthesized_draft,
    save_exploration_page,
    save_exploration_transition,
    save_synthesized_draft,
    sync_testcase_meta,
)
from qa_auto.ui.executor import orchestrator
from qa_auto.ui.server import create_app


@pytest.fixture
def sample_exploration_graph() -> AppNavigationGraph:
    """Build a deterministic navigation graph with safe forms and a destructive form."""
    home_node = PageNode(
        id="node_1",
        exploration_id="exp_test",
        url="http://127.0.0.1:8000/",
        normalized_url="http://127.0.0.1:8000",
        title="Enterprise Home",
        depth=0,
        state_fingerprint="fp_home",
        forms=[],
        interactive_elements=[
            InteractiveElement(
                element_id="link_1",
                tag_name="a",
                selector="#nav-dash",
                text="Dashboard",
                href="http://127.0.0.1:8000/dashboard",
            )
        ],
        links=["http://127.0.0.1:8000/dashboard"],
    )

    dash_node = PageNode(
        id="node_2",
        exploration_id="exp_test",
        url="http://127.0.0.1:8000/dashboard",
        normalized_url="http://127.0.0.1:8000/dashboard",
        title="Main Dashboard",
        depth=1,
        state_fingerprint="fp_dash",
        forms=[],
        interactive_elements=[
            InteractiveElement(
                element_id="link_2",
                tag_name="a",
                selector="#nav-settings",
                text="Settings",
                href="http://127.0.0.1:8000/settings",
            )
        ],
        links=["http://127.0.0.1:8000/settings"],
    )

    settings_node = PageNode(
        id="node_3",
        exploration_id="exp_test",
        url="http://127.0.0.1:8000/settings",
        normalized_url="http://127.0.0.1:8000/settings",
        title="User Settings",
        depth=2,
        state_fingerprint="fp_settings",
        forms=[
            # Safe form
            FormSchema(
                form_id="profile_form",
                action="/settings/profile",
                method="POST",
                selector="#profile-form",
                fields=[
                    FormField(name="display_name", field_type="text", selector="#input-name"),
                    FormField(name="email", field_type="email", selector="#input-email"),
                ],
                submit_button_selector="#btn-save-profile",
                is_destructive=False,
            ),
            # Destructive form
            FormSchema(
                form_id="delete_account_form",
                action="/account/delete",
                method="POST",
                selector="#delete-form",
                fields=[FormField(name="confirm", field_type="text", selector="#input-confirm")],
                submit_button_selector="#btn-delete-acct",
                is_destructive=True,
                destructive_reason="Detected destructive keyword 'delete'",
            ),
        ],
        interactive_elements=[],
        links=[],
    )

    transitions = [
        PageTransition(
            id="trans_1",
            exploration_id="exp_test",
            source_url="http://127.0.0.1:8000",
            target_url="http://127.0.0.1:8000/dashboard",
            action_type="click_link",
            selector="#nav-dash",
            element_text="Dashboard",
        ),
        PageTransition(
            id="trans_2",
            exploration_id="exp_test",
            source_url="http://127.0.0.1:8000/dashboard",
            target_url="http://127.0.0.1:8000/settings",
            action_type="click_link",
            selector="#nav-settings",
            element_text="Settings",
        ),
    ]

    return AppNavigationGraph(
        exploration_id="exp_test",
        start_url="http://127.0.0.1:8000",
        nodes={
            "http://127.0.0.1:8000": home_node,
            "http://127.0.0.1:8000/dashboard": dash_node,
            "http://127.0.0.1:8000/settings": settings_node,
        },
        transitions=transitions,
    )


# ---------------------------------------------------------------------------
# Journey Synthesizer Tests (Critical Rules 1 & 3)
# ---------------------------------------------------------------------------

def test_journey_synthesis_rules(sample_exploration_graph: AppNavigationGraph) -> None:
    """
    Verify:
    1. Navigation journeys and safe form journeys are synthesized.
    2. Destructive forms (delete account) are strictly skipped.
    3. Assertions are evidence-grounded, not speculative.
    4. Unproven outcomes carry requires_human_input=True.
    """
    drafts = synthesize_test_journeys(sample_exploration_graph, project_id="default_project", max_journeys=5)

    assert len(drafts) >= 2, "Should synthesize at least navigation and form flow journeys"

    # 1. Inspect navigation journey
    nav_draft = next((d for d in drafts if d.journey_type in ("navigation", "deep_journey")), None)
    assert nav_draft is not None
    assert nav_draft.status == "pending"

    # Verify evidence-based assertions
    for step in nav_draft.steps:
        for assertion in step.assertions:
            assert assertion.source == "evidence"
            assert assertion.requires_human_input is False
            assert "node_id" in assertion.evidence_provenance

    # 2. Inspect safe form journey
    form_draft = next((d for d in drafts if d.journey_type == "form_interaction"), None)
    assert form_draft is not None
    assert "Profile Form" in form_draft.name

    # Destructive form must NOT be synthesized
    assert not any("Delete" in d.name for d in drafts), "Destructive form must never be synthesized"

    # Form submission requires human confirmation of outcome
    assert form_draft.requires_human_input is True
    submit_step = form_draft.steps[-1]
    assert any(a.requires_human_input for a in submit_step.assertions)


# ---------------------------------------------------------------------------
# Backend Gatekeeper & Approval Tests (Critical Rule 2)
# ---------------------------------------------------------------------------

def test_backend_gatekeeper_blocks_draft_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Verify Critical Rule 2:
    Unapproved draft testcases CANNOT be executed or added to suites.
    The gatekeeper must enforce this at backend API & database level.
    """
    db_file = tmp_path / "test_gatekeeper.db"
    init_studio_db(db_file)
    monkeypatch.setattr("qa_auto.ui.db.DEFAULT_STUDIO_DB_PATH", db_file)

    proj = create_project("Test Workspace", "Desc", db_path=db_file)
    suite = create_suite("Smoke Suite", project_id=proj["id"], db_path=db_file)

    # 1. Create a dummy testcase file and mark it as 'draft' in testcases_meta
    tc_dir = tmp_path / "recordings" / "tc_draft_1"
    tc_dir.mkdir(parents=True)
    tc_file = tc_dir / "testcase.json"
    dummy_tc = TestCase(
        id="tc_draft_1",
        name="Draft Test Case",
        created_at="2026-11-19T14:00:00",
        start_url="http://127.0.0.1:8000",
        browser="chromium",
        viewport={"width": 1280, "height": 800},
        user_agent="QA Auto",
        steps=[],
        total_duration=1.0,
        total_steps=0,
    )
    tc_file.write_text(dummy_tc.model_dump_json(), encoding="utf-8")

    sync_testcase_meta(
        testcase=dummy_tc,
        file_path=tc_file,
        project_id=proj["id"],
        approval_status="draft",
        db_path=db_file,
    )

    # Verify status is draft
    meta = get_testcase_meta("tc_draft_1", db_path=db_file)
    assert meta is not None
    assert meta["approval_status"] == "draft"

    # 2. Gatekeeper 1: Adding unapproved draft to suite MUST FAIL
    with pytest.raises(ValueError, match="draft"):
        add_testcase_to_suite(suite["id"], "tc_draft_1", db_path=db_file)

    # 3. Gatekeeper 2: Attempting to execute unapproved draft MUST FAIL
    monkeypatch.setattr("qa_auto.ui.service.find_testcase_files", lambda paths=None: [tc_file])
    with pytest.raises(ValueError, match="draft"):
        import asyncio
        asyncio.run(
            orchestrator.start_execution(
                testcase_id="tc_draft_1",
                project_id=proj["id"],
            )
        )


def test_draft_approval_and_rejection_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Test full lifecycle:
    Draft Creation -> Human Review -> Approval -> Test Case Promotion -> Ready for Execution.
    """
    db_file = tmp_path / "test_lifecycle.db"
    init_studio_db(db_file)
    monkeypatch.setattr("qa_auto.ui.db.DEFAULT_STUDIO_DB_PATH", db_file)

    create_exploration_run(
        exploration_id="exp_100",
        project_id="default_project",
        start_url="http://127.0.0.1:8000",
        config={},
        db_path=db_file,
    )

    # 1. Save synthesized draft
    draft_data = {
        "id": "draft_sample_1",
        "exploration_id": "exp_100",
        "project_id": "default_project",
        "name": "Verify User Journey",
        "description": "Navigation and verification flow",
        "journey_type": "navigation",
        "priority": "high",
        "start_url": "http://127.0.0.1:8000",
        "steps": [
            {
                "number": 1,
                "action_type": "navigate",
                "url": "http://127.0.0.1:8000",
                "description_short": "Navigate home",
                "description_detailed": "Open initial page",
                "assertions": [
                    {
                        "assertion_type": "url_matches",
                        "expected_value": "http://127.0.0.1:8000",
                        "source": "evidence",
                        "requires_human_input": False,
                    }
                ],
            }
        ],
        "status": "pending",
        "requires_human_input": False,
    }
    saved = save_synthesized_draft(draft_data, db_path=db_file)
    assert saved["status"] == "pending"

    # 2. Rejection Test
    reject_draft_data = dict(draft_data, id="draft_sample_reject")
    save_synthesized_draft(reject_draft_data, db_path=db_file)
    rejected = reject_synthesized_draft("draft_sample_reject", reason="Out of test scope", db_path=db_file)
    assert rejected is True
    check_rej = get_synthesized_draft("draft_sample_reject", db_path=db_file)
    assert check_rej is not None
    assert check_rej["status"] == "rejected"
    assert check_rej["rejection_reason"] == "Out of test scope"

    # 3. Approval Test
    recordings_dir = tmp_path / "recordings"
    approved_res = approve_synthesized_draft(
        draft_id="draft_sample_1",
        custom_name="Approved User Flow",
        base_dir=recordings_dir,
        db_path=db_file,
    )
    assert approved_res["status"] == "approved"
    promoted_tc_id = approved_res["testcase_id"]
    assert promoted_tc_id.startswith("tc_")

    # Verify promoted testcase file exists
    assert Path(approved_res["file_path"]).exists()

    # Verify promoted testcase metadata is marked 'approved'
    meta = get_testcase_meta(promoted_tc_id, db_path=db_file)
    assert meta is not None
    assert meta["approval_status"] == "approved"
    assert meta["name"] == "Approved User Flow"

    # Verify approved testcase CAN now be added to suite without error
    suite = create_suite("Release Suite", project_id="default_project", db_path=db_file)
    suite_updated = add_testcase_to_suite(suite["id"], promoted_tc_id, db_path=db_file)
    assert suite_updated is not None
    assert promoted_tc_id in suite_updated["testcase_ids"]


# ---------------------------------------------------------------------------
# REST API End-to-End Test
# ---------------------------------------------------------------------------

def test_autonomous_synthesis_and_approval_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sample_exploration_graph: AppNavigationGraph
) -> None:
    """Test full REST API journey: Synthesize -> List Drafts -> Approve -> Verify."""
    db_file = tmp_path / "test_api_drafts.db"
    init_studio_db(db_file)
    monkeypatch.setattr("qa_auto.ui.db.DEFAULT_STUDIO_DB_PATH", db_file)

    # Seed exploration run and pages in database
    create_exploration_run(
        exploration_id="exp_test",
        project_id="default_project",
        start_url="http://127.0.0.1:8000",
        config={},
        db_path=db_file,
    )
    for node in sample_exploration_graph.nodes.values():
        save_exploration_page("exp_test", node.model_dump(mode="json"), db_path=db_file)
    for trans in sample_exploration_graph.transitions:
        save_exploration_transition("exp_test", trans.model_dump(mode="json"), db_path=db_file)

    client = TestClient(create_app())

    # 1. Synthesize Journeys via API
    resp_synth = client.post("/api/autonomous/runs/exp_test/synthesize", json={"max_journeys": 4})
    assert resp_synth.status_code == 200
    drafts = resp_synth.json()
    assert len(drafts) >= 2
    draft_id = drafts[0]["id"]

    # 2. List Drafts via API
    resp_list = client.get("/api/autonomous/drafts?status=pending")
    assert resp_list.status_code == 200
    listed_drafts = resp_list.json()
    assert any(d["id"] == draft_id for d in listed_drafts)

    # 3. Get Draft Details
    resp_detail = client.get(f"/api/autonomous/drafts/{draft_id}")
    assert resp_detail.status_code == 200
    assert resp_detail.json()["id"] == draft_id
    assert len(resp_detail.json()["steps"]) > 0

    # 4. Approve Draft via API
    resp_appr = client.post(
        f"/api/autonomous/drafts/{draft_id}/approve",
        json={"custom_name": "API Approved Test Case"},
    )
    assert resp_appr.status_code == 200
    appr_data = resp_appr.json()
    assert appr_data["status"] == "approved"
    assert "testcase_id" in appr_data

    # 5. Verify draft status updated to approved
    resp_recheck = client.get(f"/api/autonomous/drafts/{draft_id}")
    assert resp_recheck.json()["status"] == "approved"

    # 6. Reject another draft via API
    other_draft_id = drafts[1]["id"]
    resp_rej = client.post(
        f"/api/autonomous/drafts/{other_draft_id}/reject",
        json={"reason": "Redundant scenario"},
    )
    assert resp_rej.status_code == 200
    assert resp_rej.json()["status"] == "rejected"
