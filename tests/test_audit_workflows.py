"""End-to-End Audit & Workflow Verification for Phase 2.1."""

from __future__ import annotations

import time
from fastapi.testclient import TestClient

from qa_auto.ui.server import create_app

app = create_app()
client = TestClient(app)


def test_e2e_core_product_workflow():
    # 1. Project Management
    res = client.post("/api/projects", json={
        "name": "E2E Audit Project",
        "slug": "e2e-audit-project",
        "description": "Project created during Phase 2.1 verification"
    })
    assert res.status_code == 200, res.text
    project = res.json()
    assert project["name"] == "E2E Audit Project"
    project_id = project["id"]

    # 2. Test Case Creation
    tc_res = client.post("/api/testcases", json={
        "name": "Audit Checkout Flow",
        "start_url": "https://example.com/shop",
        "browser": "chromium",
        "description": "Verify customer checkout and confirmation"
    })
    assert tc_res.status_code == 200, tc_res.text
    tc_data = tc_res.json()
    tc_id = tc_data["id"]
    assert tc_data["name"] == "Audit Checkout Flow"
    assert len(tc_data["steps"]) == 1

    # 3. Add Steps
    step_res = client.post(f"/api/testcases/{tc_id}/steps", json={
        "action_type": "click",
        "selector": "#add-to-cart-button",
        "tag_name": "button",
        "text": "Add to Cart",
        "description_short": "Click Add to Cart",
        "description_detailed": "Click Add to Cart button on product detail"
    })
    assert step_res.status_code == 200, step_res.text
    updated_tc = step_res.json()
    assert len(updated_tc["steps"]) == 2

    # 4. Add Custom Assertion
    assert_res = client.post(f"/api/testcases/{tc_id}/assertions", json={
        "step_number": 2,
        "kind": "text",
        "target": "#cart-count",
        "expected": "1"
    })
    assert assert_res.status_code == 200, assert_res.text
    assert len(assert_res.json()["custom_assertions"]) == 1

    # 5. Fetch Single Test Case
    get_res = client.get(f"/api/testcases/{tc_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == tc_id

    # 6. Codegen (Generate Pytest Code)
    cg_res = client.post(f"/api/testcases/{tc_id}/codegen", json={"target": "pytest"})
    assert cg_res.status_code == 200, cg_res.text
    cg_data = cg_res.json()
    assert "code" in cg_data
    assert "def test_audit_checkout_flow" in cg_data["code"] or "test_" in cg_data["code"]

    # 7. AI Analysis
    ai_res = client.post("/api/ai/analyze", json={
        "testcase_id": tc_id,
        "mode": "summary"
    })
    assert ai_res.status_code == 200, ai_res.text
    ai_data = ai_res.json()
    assert ai_data["testcase_id"] == tc_id
    assert "summary" in ai_data

    # 8. Negative Mutation Scenarios
    mut_res = client.post("/api/mutations/generate", json={
        "testcase_id": tc_id,
        "strategies": ["empty_input", "boundary_strings"]
    })
    assert mut_res.status_code == 200, mut_res.text
    mut_data = mut_res.json()
    assert isinstance(mut_data, list)

    # 9. Storage Stats
    storage_res = client.get("/api/storage/stats")
    assert storage_res.status_code == 200
    stats = storage_res.json()
    assert "total_size_mb" in stats

    # 10. Clean Up Test Case
    del_res = client.delete(f"/api/testcases/{tc_id}")
    assert del_res.status_code == 200, del_res.text

    # 11. Clean Up Project
    del_proj = client.delete(f"/api/projects/{project_id}")
    assert del_proj.status_code == 200, del_proj.text


def test_e2e_suites_and_settings_workflows():
    # 1. Settings Get & Update
    s_res = client.get("/api/settings")
    assert s_res.status_code == 200
    settings = s_res.json()
    assert "ai_provider" in settings

    put_res = client.put("/api/settings", json={"ai_provider": "ollama", "ai_model": "mistral"})
    assert put_res.status_code == 200
    assert put_res.json()["ai_model"] == "mistral"

    # 2. Test Suite Lifecycle
    suite_res = client.post("/api/suites", json={
        "name": "Regression Smoke Suite",
        "description": "Critical path smoke tests",
        "testcase_ids": []
    })
    assert suite_res.status_code == 200
    suite = suite_res.json()
    suite_id = suite["id"]
    assert suite["name"] == "Regression Smoke Suite"

    list_s = client.get("/api/suites")
    assert list_s.status_code == 200
    assert any(s["id"] == suite_id for s in list_s.json())

    del_s = client.delete(f"/api/suites/{suite_id}")
    assert del_s.status_code == 200


def test_e2e_search_and_repository():
    res = client.get("/api/repository/search?q=checkout")
    assert res.status_code == 200
    data = res.json()
    assert "results" in data or isinstance(data, list)

