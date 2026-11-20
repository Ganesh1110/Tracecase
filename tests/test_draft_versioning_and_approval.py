"""Phase 9.1.4 Tests: Authoritative Draft Versioning, Content-Hashed Validation Binding & Transactional Approval Gate."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tracecase.models import TestCase
from tracecase.ui.db import (
    approve_synthesized_draft,
    compute_draft_content_hash,
    create_exploration_run,
    create_project,
    create_suite,
    diff_draft_snapshots,
    get_draft_snapshot,
    get_draft_validation,
    get_latest_draft_validation,
    get_suite,
    get_synthesized_draft,
    get_testcase_meta,
    init_studio_db,
    list_draft_snapshots,
    save_draft_validation,
    save_synthesized_draft,
    update_synthesized_draft,
)
from tracecase.ui.server import create_app


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_phase_914.db"
    init_studio_db(db_file)
    create_exploration_run(
        exploration_id="exp_sample",
        project_id="default_project",
        start_url="http://127.0.0.1:8000/shop",
        config={},
        db_path=db_file,
    )
    return db_file


@pytest.fixture
def sample_draft_data() -> dict[str, Any]:
    return {
        "id": "draft_914_test",
        "exploration_id": "exp_sample",
        "project_id": "default_project",
        "name": "Checkout Flow Journey",
        "description": "User adds item and completes checkout",
        "journey_type": "form_interaction",
        "priority": "high",
        "start_url": "http://127.0.0.1:8000/shop",
        "steps": [
            {
                "number": 1,
                "action_type": "navigate",
                "url": "http://127.0.0.1:8000/shop",
                "selector": None,
                "input_value": None,
                "assertions": [
                    {
                        "assertion_type": "url_matches",
                        "target_selector": "",
                        "expected_value": "http://127.0.0.1:8000/shop",
                    }
                ],
            },
            {
                "number": 2,
                "action_type": "click",
                "url": "http://127.0.0.1:8000/shop",
                "selector": "#btn-add-cart",
                "input_value": None,
                "assertions": [],
            },
        ],
        "status": "pending",
        "requires_human_input": False,
    }


def test_deterministic_content_hashing(sample_draft_data: dict[str, Any]) -> None:
    """Verify content hash is strictly deterministic and ignores ephemeral fields."""
    steps1 = sample_draft_data["steps"]
    hash1 = compute_draft_content_hash(
        steps=steps1,
        start_url=sample_draft_data["start_url"],
        name=sample_draft_data["name"],
        journey_type=sample_draft_data["journey_type"],
    )

    # Identical content must yield identical hash
    hash2 = compute_draft_content_hash(
        steps=list(steps1),
        start_url=sample_draft_data["start_url"],
        name=sample_draft_data["name"],
        journey_type=sample_draft_data["journey_type"],
    )
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex string

    # Changing execution-relevant field (selector) must alter hash
    modified_steps = [dict(steps1[0]), dict(steps1[1], selector="#btn-add-cart-alt")]
    hash_modified = compute_draft_content_hash(
        steps=modified_steps,
        start_url=sample_draft_data["start_url"],
        name=sample_draft_data["name"],
        journey_type=sample_draft_data["journey_type"],
    )
    assert hash1 != hash_modified


def test_migration_and_snapshot_backfill(tmp_path: Path) -> None:
    """Verify existing legacy draft rows without snapshots get backfilled cleanly."""
    legacy_db = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(legacy_db))
    with conn:
        # Create minimal legacy table without content_hash or snapshots table
        conn.execute(
            """
            CREATE TABLE synthesized_drafts (
                id TEXT PRIMARY KEY,
                exploration_id TEXT,
                project_id TEXT,
                name TEXT,
                description TEXT,
                journey_type TEXT,
                priority TEXT,
                start_url TEXT,
                steps_json TEXT,
                status TEXT,
                approved_testcase_id TEXT,
                rejection_reason TEXT,
                requires_human_input INTEGER,
                created_at TEXT,
                reviewed_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO synthesized_drafts (
                id, exploration_id, project_id, name, description, journey_type,
                priority, start_url, steps_json, status, requires_human_input, created_at
            ) VALUES ('legacy_1', 'exp_old', 'default', 'Legacy Draft', 'Old draft',
                      'navigation', 'low', 'http://127.0.0.1:8000', '[]', 'pending', 0, '2026-11-01T00:00:00')
            """
        )
    conn.close()

    # Run init_studio_db to trigger migration and snapshot backfill
    init_studio_db(legacy_db)

    # Verify legacy draft has content_hash and a version 1 snapshot
    draft = get_synthesized_draft("legacy_1", db_path=legacy_db)
    assert draft is not None
    assert draft["version"] == 1
    assert draft["content_hash"] is not None

    snapshots = list_draft_snapshots("legacy_1", db_path=legacy_db)
    assert len(snapshots) == 1
    assert snapshots[0]["version"] == 1
    assert snapshots[0]["content_hash"] == draft["content_hash"]


def test_draft_edit_increments_version_and_creates_snapshots(
    test_db: Path, sample_draft_data: dict[str, Any]
) -> None:
    """Verify editing a draft creates immutable version snapshots, diffs correctly, and invalidates approval."""
    # 1. Save Initial Draft (v1)
    d1 = save_synthesized_draft(sample_draft_data, db_path=test_db)
    assert d1["version"] == 1
    assert d1["content_hash"] is not None
    v1_hash = d1["content_hash"]

    # Approve v1
    approved_res = approve_synthesized_draft(d1["id"], db_path=test_db)
    assert approved_res["status"] == "approved"
    assert get_synthesized_draft(d1["id"], db_path=test_db)["status"] == "approved"

    # 2. Edit Draft: update selector in step 2 (triggers v2)
    new_steps = [
        dict(d1["steps"][0]),
        dict(d1["steps"][1], selector="#btn-add-cart-updated", input_value="SKU-999"),
        {
            "number": 3,
            "action_type": "click",
            "url": "http://127.0.0.1:8000/shop",
            "selector": "#btn-checkout",
            "input_value": None,
            "assertions": [],
        },
    ]

    d2 = update_synthesized_draft(
        draft_id=d1["id"],
        name="Checkout Flow Journey V2",
        steps=new_steps,
        changelog="Added checkout button and updated SKU",
        author="alice",
        db_path=test_db,
    )
    assert d2 is not None
    assert d2["version"] == 2
    assert d2["content_hash"] != v1_hash
    # Guardrail: Approval status must be invalidated
    assert d2["status"] == "pending"
    assert d2["approved_testcase_id"] is None
    assert d2["validation_status"] == "not_run"

    # 3. Verify Snapshots Listing & Diff
    snapshots = list_draft_snapshots(d1["id"], db_path=test_db)
    assert len(snapshots) == 2
    assert snapshots[0]["version"] == 1
    assert snapshots[1]["version"] == 2
    assert snapshots[1]["author"] == "alice"

    # Diff v1 and v2
    diff = diff_draft_snapshots(d1["id"], v1=1, v2=2, db_path=test_db)
    assert diff["has_changes"] is True
    assert diff["base_version"] == 1
    assert diff["target_version"] == 2
    assert len(diff["step_diffs"]) == 3

    # Step 1 unchanged
    assert diff["step_diffs"][0]["diff_type"] == "unchanged"
    # Step 2 modified
    assert diff["step_diffs"][1]["diff_type"] == "modified"
    assert "selector" in diff["step_diffs"][1]["change_summary"]
    # Step 3 added
    assert diff["step_diffs"][2]["diff_type"] == "added"


def test_old_validation_cannot_validate_newer_draft_version(
    test_db: Path, sample_draft_data: dict[str, Any]
) -> None:
    """
    Verify Guardrail B:
    Validation runs are bound to exact draft_version and content_hash.
    A validation report for an older version cannot mark a newer version as validated.
    """
    # 1. Create Draft v1
    draft = save_synthesized_draft(sample_draft_data, db_path=test_db)
    v1_hash = draft["content_hash"]

    # 2. Simulate validation for v1
    val_report_v1 = {
        "validation_id": "val_v1_run",
        "draft_id": draft["id"],
        "draft_version": 1,
        "draft_content_hash": v1_hash,
        "overall_status": "VERIFIED",
        "started_at": "2026-11-20T10:00:00",
        "completed_at": "2026-11-20T10:00:05",
        "step_results": [{"status": "PASSED"}],
    }
    save_draft_validation(val_report_v1, db_path=test_db)

    # Parent draft should show verified
    d_after_v1 = get_synthesized_draft(draft["id"], db_path=test_db)
    assert d_after_v1["validation_status"] == "verified"

    # 3. Edit draft to v2
    d_v2 = update_synthesized_draft(
        draft_id=draft["id"],
        name="Updated Name v2",
        steps=draft["steps"],
        db_path=test_db,
    )
    assert d_v2["version"] == 2
    assert d_v2["validation_status"] == "not_run"

    # 4. A late validation arriving for v1 must NOT update v2 status
    late_v1_report = {
        "validation_id": "val_late_v1",
        "draft_id": draft["id"],
        "draft_version": 1,
        "draft_content_hash": v1_hash,
        "overall_status": "VERIFIED",
        "started_at": "2026-11-20T10:01:00",
        "step_results": [{"status": "PASSED"}],
    }
    save_draft_validation(late_v1_report, db_path=test_db)

    # v2 draft must STILL remain "not_run"
    d_v2_check = get_synthesized_draft(draft["id"], db_path=test_db)
    assert d_v2_check["validation_status"] == "not_run"

    # Latest validation check for v2 must reflect that it is not current
    latest = get_latest_draft_validation(draft["id"], db_path=test_db)
    assert latest is not None
    assert latest["is_current_version"] is False


def test_transactional_approval_with_validation_and_optimistic_locking(
    test_db: Path, sample_draft_data: dict[str, Any], tmp_path: Path
) -> None:
    """Verify transactional approval: validation enforcement, version checking, and optimistic locking."""
    recordings_dir = tmp_path / "recordings"
    draft = save_synthesized_draft(sample_draft_data, db_path=test_db)
    v1_hash = draft["content_hash"]

    # 1. Approval with require_validation=True MUST FAIL if not verified
    with pytest.raises(ValueError, match="has not passed sandbox validation"):
        approve_synthesized_draft(
            draft_id=draft["id"],
            require_validation=True,
            base_dir=recordings_dir,
            db_path=test_db,
        )

    # 2. Save passing validation for v1
    save_draft_validation(
        {
            "validation_id": "val_success_1",
            "draft_id": draft["id"],
            "draft_version": 1,
            "draft_content_hash": v1_hash,
            "overall_status": "VERIFIED",
            "started_at": "2026-11-20T10:05:00",
            "step_results": [{"status": "PASSED"}],
        },
        db_path=test_db,
    )

    # 3. Version conflict guard: approving with wrong expected_version must fail
    with pytest.raises(ValueError, match="version conflict"):
        approve_synthesized_draft(
            draft_id=draft["id"],
            expected_version=99,
            db_path=test_db,
        )

    # 4. Hash conflict guard: approving with wrong expected_content_hash must fail
    with pytest.raises(ValueError, match="content hash mismatch"):
        approve_synthesized_draft(
            draft_id=draft["id"],
            expected_content_hash="bad_hash_value",
            db_path=test_db,
        )

    # 5. Successful Transactional Approval
    suite = create_suite("Regression Suite", project_id="default_project", db_path=test_db)
    approved = approve_synthesized_draft(
        draft_id=draft["id"],
        expected_version=1,
        expected_content_hash=v1_hash,
        suite_id=suite["id"],
        require_validation=True,
        base_dir=recordings_dir,
        db_path=test_db,
    )
    assert approved["status"] == "approved"
    assert approved["idempotent"] is False
    tc_id = approved["testcase_id"]

    # Verify suite association
    suite_data = get_suite(suite["id"], db_path=test_db)
    assert suite_data is not None
    assert tc_id in suite_data["testcase_ids"]

    # Verify testcase file exists
    assert Path(approved["file_path"]).exists()

    # 6. Idempotency Check: Calling approval again on already-approved draft returns existing tc
    idempotent_res = approve_synthesized_draft(
        draft_id=draft["id"],
        expected_version=1,
        base_dir=recordings_dir,
        db_path=test_db,
    )
    assert idempotent_res["status"] == "approved"
    assert idempotent_res["idempotent"] is True
    assert idempotent_res["testcase_id"] == tc_id


def test_rollback_protection_on_failure(test_db: Path, sample_draft_data: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify that if database write fails, disk artifacts are cleaned up and no partial promotion state remains."""
    recordings_dir = tmp_path / "recordings"
    draft = save_synthesized_draft(sample_draft_data, db_path=test_db)

    # Force a database failure during sync_testcase_meta
    def fail_sync(*args: Any, **kwargs: Any) -> None:
        raise sqlite3.OperationalError("Simulated database failure during testcase promotion")

    monkeypatch.setattr("tracecase.ui.db.sync_testcase_meta", fail_sync)

    with pytest.raises(sqlite3.OperationalError, match="Simulated database failure"):
        approve_synthesized_draft(
            draft_id=draft["id"],
            base_dir=recordings_dir,
            db_path=test_db,
        )

    # Verify draft is NOT marked approved
    check_draft = get_synthesized_draft(draft["id"], db_path=test_db)
    assert check_draft["status"] == "pending"
    assert check_draft["approved_testcase_id"] is None

    # Verify no orphaned testcase directory left on disk
    tc_dirs = list(recordings_dir.glob("tc_*"))
    assert len(tc_dirs) == 0


def test_api_snapshots_and_diff(test_db: Path, sample_draft_data: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify REST API endpoints for draft snapshots, diff, and approval."""
    monkeypatch.setattr("tracecase.ui.db.DEFAULT_STUDIO_DB_PATH", test_db)
    draft = save_synthesized_draft(sample_draft_data, db_path=test_db)
    client = TestClient(create_app())

    # 1. Get Snapshots
    resp = client.get(f"/api/autonomous/drafts/{draft['id']}/snapshots")
    assert resp.status_code == 200
    snaps = resp.json()
    assert len(snaps) == 1
    assert snaps[0]["version"] == 1

    # 2. Update Draft (v2)
    new_steps = list(draft["steps"]) + [{"number": 3, "action_type": "navigate", "url": "http://127.0.0.1:8000/done"}]
    update_synthesized_draft(draft["id"], steps=new_steps, db_path=test_db)

    # 3. Get Diff
    resp_diff = client.get(f"/api/autonomous/drafts/{draft['id']}/diff?v1=1&v2=2")
    assert resp_diff.status_code == 200
    diff_data = resp_diff.json()
    assert diff_data["has_changes"] is True
    assert diff_data["base_version"] == 1
    assert diff_data["target_version"] == 2

    # 4. Approve via API with expected version
    resp_app = client.post(
        f"/api/autonomous/drafts/{draft['id']}/approve",
        json={"expected_version": 2, "custom_name": "API Promoted Case"},
    )
    assert resp_app.status_code == 200
    app_data = resp_app.json()
    assert app_data["status"] == "approved"
    assert app_data["version"] == 2
