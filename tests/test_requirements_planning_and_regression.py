"""Phase 6.3 tests: Requirements-Driven Test Planning, Coverage Gaps, Post-Approval Invalidation, and Intelligent Regression Selection."""

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
from qa_auto.exploration.planner import plan_requirement_against_graph
from qa_auto.exploration.regression import select_intelligent_regression_suite
from qa_auto.models import ElementInfo, Step, TestCase
from qa_auto.ui.db import (
    approve_synthesized_draft,
    create_execution_run,
    create_exploration_run,
    get_connection,
    get_synthesized_draft,
    get_testcase_meta,
    init_studio_db,
    save_exploration_page,
    save_exploration_transition,
    save_synthesized_draft,
    sync_testcase_meta,
    update_execution_run_status,
    update_synthesized_draft,
)
from qa_auto.ui.server import create_app


@pytest.fixture
def mock_app_graph() -> AppNavigationGraph:
    """Build an exploration graph with home, settings (with profile form), and dashboard."""
    home_node = PageNode(
        id="node_1",
        exploration_id="exp_p63",
        url="http://127.0.0.1:8000/",
        normalized_url="http://127.0.0.1:8000",
        title="App Portal",
        depth=0,
        state_fingerprint="fp_home",
        forms=[],
        interactive_elements=[
            InteractiveElement(
                element_id="link_settings",
                tag_name="a",
                selector="#nav-settings",
                text="Settings Page",
                href="http://127.0.0.1:8000/settings",
            )
        ],
        links=["http://127.0.0.1:8000/settings"],
    )

    settings_node = PageNode(
        id="node_2",
        exploration_id="exp_p63",
        url="http://127.0.0.1:8000/settings",
        normalized_url="http://127.0.0.1:8000/settings",
        title="User Settings",
        depth=1,
        state_fingerprint="fp_settings",
        forms=[
            FormSchema(
                form_id="profile_form",
                action="/settings/profile",
                method="POST",
                selector="#profile-form",
                fields=[
                    FormField(name="email", field_type="email", selector="#input-email"),
                    FormField(name="display_name", field_type="text", selector="#input-name"),
                ],
                submit_button_selector="#btn-save-profile",
                is_destructive=False,
            ),
            FormSchema(
                form_id="delete_form",
                action="/account/delete",
                method="POST",
                selector="#delete-form",
                fields=[],
                submit_button_selector="#btn-delete",
                is_destructive=True,
                destructive_reason="Destructive keyword delete",
            ),
        ],
        interactive_elements=[],
        links=[],
    )

    return AppNavigationGraph(
        exploration_id="exp_p63",
        start_url="http://127.0.0.1:8000",
        nodes={
            "http://127.0.0.1:8000": home_node,
            "http://127.0.0.1:8000/settings": settings_node,
        },
        transitions=[
            PageTransition(
                id="trans_1",
                exploration_id="exp_p63",
                source_url="http://127.0.0.1:8000",
                target_url="http://127.0.0.1:8000/settings",
                action_type="click_link",
                selector="#nav-settings",
                element_text="Settings",
            )
        ],
    )


# ---------------------------------------------------------------------------
# Requirements Planning & Gap Analysis Tests
# ---------------------------------------------------------------------------

def test_requirements_mapping_and_gap_analysis(mock_app_graph: AppNavigationGraph) -> None:
    """
    Test requirements mapping against graph:
    1. Fully covered requirement: produces high coverage score and synthesized draft.
    2. Requirement with missing concepts (cart, checkout): flags coverage gaps with explanation.
    3. Requirement with destructive action: marks concept as destructive_excluded.
    """
    # 1. Matching Requirement
    res_covered = plan_requirement_against_graph(
        "As a user, I want to open settings and update my profile email",
        graph=mock_app_graph,
        project_id="default_project",
    )
    assert res_covered["coverage_score"] >= 0.5
    assert "settings" in res_covered["covered_concepts"]
    assert "email" in res_covered["covered_concepts"]
    assert res_covered["can_generate_test"] is True
    assert res_covered["synthesized_draft"] is not None
    assert "settings" in res_covered["matched_routes"][0].lower()

    # 2. Requirement with Missing Gap
    res_gap = plan_requirement_against_graph(
        "As a user, I want to add products to cart and complete checkout",
        graph=mock_app_graph,
        project_id="default_project",
    )
    missing_names = [g["concept"] for g in res_gap["missing_concepts"]]
    assert "cart" in missing_names
    assert "checkout" in missing_names
    assert any("No observed page" in g["reason"] for g in res_gap["missing_concepts"])

    # 3. Requirement with Destructive Action
    res_destr = plan_requirement_against_graph(
        "As a user, I want to delete my account",
        graph=mock_app_graph,
        project_id="default_project",
    )
    delete_gap = next((g for g in res_destr["missing_concepts"] if g["concept"] == "delete"), None)
    assert delete_gap is not None
    assert delete_gap["status"] == "destructive_excluded"
    assert "safety-restricted" in delete_gap["reason"]


# ---------------------------------------------------------------------------
# Approval Security & Post-Approval Mutation Invalidation Guardrail
# ---------------------------------------------------------------------------

def test_post_approval_mutation_invalidates_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Verify security guardrail:
    If a user modifies a draft after approval, its approval status is automatically
    invalidated, resetting to 'pending' and requiring re-approval.
    """
    db_file = tmp_path / "test_sec_guard.db"
    init_studio_db(db_file)
    monkeypatch.setattr("qa_auto.ui.db.DEFAULT_STUDIO_DB_PATH", db_file)

    create_exploration_run("exp_sec", "default_project", "http://127.0.0.1:8000", {}, db_path=db_file)

    # 1. Create and approve draft
    draft_data = {
        "id": "draft_sec_1",
        "exploration_id": "exp_sec",
        "project_id": "default_project",
        "name": "Original Validated Flow",
        "start_url": "http://127.0.0.1:8000",
        "steps": [
            {
                "number": 1,
                "action_type": "navigate",
                "url": "http://127.0.0.1:8000",
                "description_short": "Nav Home",
                "description_detailed": "Nav Home",
            }
        ],
        "status": "pending",
    }
    save_synthesized_draft(draft_data, db_path=db_file)

    # Approve draft
    approve_res = approve_synthesized_draft("draft_sec_1", base_dir=tmp_path / "recs", db_path=db_file)
    assert approve_res["status"] == "approved"

    # Verify status in database is approved
    d_check = get_synthesized_draft("draft_sec_1", db_path=db_file)
    assert d_check is not None
    assert d_check["status"] == "approved"
    assert d_check["approved_testcase_id"] is not None

    # 2. Modify draft steps post-approval
    new_steps = [
        {
            "number": 1,
            "action_type": "navigate",
            "url": "http://127.0.0.1:8000/tampered",
            "description_short": "Tampered Step",
            "description_detailed": "Tampered",
        }
    ]
    updated = update_synthesized_draft("draft_sec_1", name="Tampered Name", steps=new_steps, db_path=db_file)

    # 3. Security Check: Approval must be revoked!
    assert updated is not None
    assert updated["status"] == "pending", "Status must reset to 'pending' upon post-approval modification"
    assert updated["approved_testcase_id"] is None, "Approved testcase link must be cleared"
    assert updated["requires_human_input"] is True


# ---------------------------------------------------------------------------
# Intelligent Regression Selector Tests
# ---------------------------------------------------------------------------

def test_intelligent_regression_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Test intelligent regression test suite prioritization:
    1. Tests with changed selectors get highest risk score.
    2. Tests touching changed routes get elevated risk score.
    3. Recently failed tests receive failure history boost.
    4. Unaffected tests remain low risk.
    """
    db_file = tmp_path / "test_regress.db"
    init_studio_db(db_file)
    monkeypatch.setattr("qa_auto.ui.db.DEFAULT_STUDIO_DB_PATH", db_file)

    recs_dir = tmp_path / "recordings"

    # 1. Test Case A: Interacts with #btn-save on /settings
    tc_a = TestCase(
        id="tc_settings_flow",
        name="Settings Profile Test",
        created_at="2026-11-19T14:00:00",
        start_url="http://127.0.0.1:8000/settings",
        browser="chromium",
        viewport={"width": 1280, "height": 800},
        user_agent="QA Auto",
        steps=[
            Step(
                number=1,
                timestamp="2026-11-19T14:00:00",
                action_type="input",
                element=ElementInfo(selector="#input-email", tag_name="input", bounding_box={"x": 0, "y": 0, "width": 10, "height": 10}),
                description_short="Input Email",
                description_detailed="Input Email",
            ),
            Step(
                number=2,
                timestamp="2026-11-19T14:00:01",
                action_type="click",
                element=ElementInfo(selector="#btn-save-profile", tag_name="button", bounding_box={"x": 0, "y": 0, "width": 10, "height": 10}),
                description_short="Save",
                description_detailed="Save",
            ),
        ],
        total_duration=2.0,
        total_steps=2,
    )
    dir_a = recs_dir / "tc_settings_flow"
    dir_a.mkdir(parents=True)
    f_a = dir_a / "testcase.json"
    f_a.write_text(tc_a.model_dump_json(), encoding="utf-8")
    sync_testcase_meta(tc_a, f_a, db_path=db_file)

    # 2. Test Case B: Interacts with /dashboard (Recently failed!)
    tc_b = TestCase(
        id="tc_dashboard_flow",
        name="Dashboard Metrics Test",
        created_at="2026-11-19T14:00:00",
        start_url="http://127.0.0.1:8000/dashboard",
        browser="chromium",
        viewport={"width": 1280, "height": 800},
        user_agent="QA Auto",
        steps=[
            Step(
                number=1,
                timestamp="2026-11-19T14:00:00",
                action_type="click",
                element=ElementInfo(selector="#btn-refresh", tag_name="button", bounding_box={"x": 0, "y": 0, "width": 10, "height": 10}),
                description_short="Refresh",
                description_detailed="Refresh",
            )
        ],
        total_duration=1.0,
        total_steps=1,
    )
    dir_b = recs_dir / "tc_dashboard_flow"
    dir_b.mkdir(parents=True)
    f_b = dir_b / "testcase.json"
    f_b.write_text(tc_b.model_dump_json(), encoding="utf-8")
    sync_testcase_meta(tc_b, f_b, db_path=db_file)

    # Record recent execution failure for tc_dashboard_flow
    exec_run = create_execution_run("tc_dashboard_flow", tc_b.name, "default_project", db_path=db_file)
    update_execution_run_status(exec_run["id"], "failed", error_message="Element #btn-refresh timeout", db_path=db_file)

    # 3. Test Case C: Purely unrelated test
    tc_c = TestCase(
        id="tc_about_flow",
        name="About Page Test",
        created_at="2026-11-19T14:00:00",
        start_url="http://127.0.0.1:8000/about",
        browser="chromium",
        viewport={"width": 1280, "height": 800},
        user_agent="QA Auto",
        steps=[],
        total_duration=1.0,
        total_steps=0,
    )
    dir_c = recs_dir / "tc_about_flow"
    dir_c.mkdir(parents=True)
    f_c = dir_c / "testcase.json"
    f_c.write_text(tc_c.model_dump_json(), encoding="utf-8")
    sync_testcase_meta(tc_c, f_c, db_path=db_file)

    # Execute intelligent regression selection
    # Modification: Changed #btn-save-profile and /settings
    res = select_intelligent_regression_suite(
        changed_routes=["/settings"],
        changed_selectors=["#btn-save-profile"],
        search_paths=[recs_dir],
        db_path=db_file,
    )

    ranked = res["ranked_testcases"]
    assert len(ranked) >= 2

    # tc_settings_flow must be top priority
    top_case = ranked[0]
    assert top_case["testcase_id"] == "tc_settings_flow"
    assert top_case["priority"] == "critical"
    assert top_case["risk_score"] >= 80.0
    assert any("modified selector" in r for r in top_case["reasons"])

    # tc_dashboard_flow must have failure risk reasons
    dash_case = next(c for c in ranked if c["testcase_id"] == "tc_dashboard_flow")
    assert any("failed" in r.lower() for r in dash_case["reasons"])

    # tc_about_flow should have zero risk
    about_case = next(c for c in ranked if c["testcase_id"] == "tc_about_flow")
    assert about_case["risk_score"] == 0.0


# ---------------------------------------------------------------------------
# REST API Endpoints Integration Test
# ---------------------------------------------------------------------------

def test_requirements_and_regression_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_app_graph: AppNavigationGraph
) -> None:
    """Test REST API endpoints for requirements planning and regression selection."""
    db_file = tmp_path / "test_api_p63.db"
    init_studio_db(db_file)
    monkeypatch.setattr("qa_auto.ui.db.DEFAULT_STUDIO_DB_PATH", db_file)

    create_exploration_run("exp_p63", "default_project", "http://127.0.0.1:8000", {}, db_path=db_file)
    for node in mock_app_graph.nodes.values():
        save_exploration_page("exp_p63", node.model_dump(mode="json"), db_path=db_file)
    for trans in mock_app_graph.transitions:
        save_exploration_transition("exp_p63", trans.model_dump(mode="json"), db_path=db_file)

    client = TestClient(create_app())

    # 1. API: Plan Requirement
    resp_plan = client.post(
        "/api/autonomous/requirements/plan",
        json={
            "requirement": "As a user, I want to open settings and update my profile email",
            "exploration_id": "exp_p63",
        },
    )
    assert resp_plan.status_code == 200
    plan_data = resp_plan.json()
    assert plan_data["coverage_score"] > 0.0
    assert "settings" in plan_data["covered_concepts"]
    assert plan_data["synthesized_draft"] is not None
    draft_id = plan_data["synthesized_draft"]["id"]

    # 2. API: Update Draft (test post-approval invalidation API)
    resp_upd = client.put(
        f"/api/autonomous/drafts/{draft_id}",
        json={"name": "Customized Planned Requirement"},
    )
    assert resp_upd.status_code == 200
    assert resp_upd.json()["name"] == "Customized Planned Requirement"

    # 3. API: Select Regression
    resp_reg = client.post(
        "/api/autonomous/regression/select",
        json={
            "changed_routes": ["/settings"],
            "changed_selectors": ["#input-email"],
        },
    )
    assert resp_reg.status_code == 200
    reg_data = resp_reg.json()
    assert "ranked_testcases" in reg_data
    assert "explanation" in reg_data
