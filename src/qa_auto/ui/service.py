"""Backend service layer for QA Auto Web Studio."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from qa_auto.codegen.pytest_exporter import generate_pytest_code
from qa_auto.exporters.html_exporter import HTMLExporter
from qa_auto.exporters.markdown_exporter import MarkdownExporter
from qa_auto.models import ElementInfo, Step, TestCase
from qa_auto.recorder import Recorder
from qa_auto.replay.engine import ReplayEngine
from qa_auto.replay.models import ReplayResult
from qa_auto.replay.visual import VisualDiffResult, compare_images

logger = logging.getLogger("qa_auto.ui.service")


class RecordingSessionManager:
    """Tracks active and recent recording sessions."""

    def __init__(self) -> None:
        self.current_session: dict[str, Any] | None = None
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._recorder: Recorder | None = None

    async def start(
        self,
        url: str,
        name: str | None = None,
        output_dir: Path | str | None = None,
        browser_type: str = "chromium",
        headless: bool = False,
        timeout: int = 30000,
    ) -> dict[str, Any]:
        """Start a new recording session."""
        async with self._lock:
            if self.current_session and self.current_session.get("status") == "recording":
                raise RuntimeError("A recording session is already active.")

            session_id = f"rec_{uuid.uuid4().hex[:8]}"
            safe_name = (
                name.strip()
                if name and name.strip()
                else f"Recorded Test {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )

            # Target output folder
            if output_dir:
                target_dir = Path(output_dir)
            else:
                slug = "".join(
                    c if c.isalnum() or c in ("-", "_") else "_" for c in safe_name.lower()
                )
                target_dir = Path("recordings") / f"{slug}_{session_id}"

            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "screenshots").mkdir(exist_ok=True)

            self.current_session = {
                "session_id": session_id,
                "name": safe_name,
                "url": url,
                "status": "recording",
                "output_dir": str(target_dir),
                "started_at": datetime.now().isoformat(),
                "completed_at": None,
                "error": None,
                "testcase_id": None,
            }

            # Spawn recording task
            self._task = asyncio.create_task(
                self._run_recorder_task(
                    session_id=session_id,
                    target_dir=target_dir,
                    url=url,
                    name=safe_name,
                    browser_type=browser_type,
                    headless=headless,
                    timeout=timeout,
                )
            )

            return dict(self.current_session)

    async def _run_recorder_task(
        self,
        session_id: str,
        target_dir: Path,
        url: str,
        name: str,
        browser_type: str,
        headless: bool,
        timeout: int,
    ) -> None:
        try:
            recorder = Recorder(
                output_dir=target_dir,
                start_url=url,
                name=name,
                browser_type=browser_type,
                headless=headless,
                viewport=(1280, 720),
                timeout=timeout,
            )
            self._recorder = recorder
            await recorder.run()

            # Find generated testcase.json
            tc_file = target_dir / "testcase.json"
            testcase_id = None
            if tc_file.exists():
                try:
                    data = json.loads(tc_file.read_text(encoding="utf-8"))
                    testcase_id = data.get("id")
                    tc = TestCase.model_validate(data)
                    from qa_auto.index.store import index_testcase
                    from qa_auto.ui.db import sync_testcase_meta

                    sync_testcase_meta(tc, tc_file)
                    index_testcase(tc, tc_file)
                except Exception as exc:
                    logger.warning("Could not sync recorded test case to index: %s", exc)

            if self.current_session and self.current_session.get("session_id") == session_id:
                self.current_session["status"] = "completed"
                self.current_session["completed_at"] = datetime.now().isoformat()
                self.current_session["testcase_id"] = testcase_id

            from qa_auto.ui.broadcaster import broadcast_recording_event

            await broadcast_recording_event(
                session_id=session_id,
                event_type="recording_completed",
                data={"status": "completed", "testcase_id": testcase_id},
            )
        except Exception as exc:
            logger.exception("Recording failed: %s", exc)
            if self.current_session and self.current_session.get("session_id") == session_id:
                self.current_session["status"] = "error"
                self.current_session["error"] = str(exc)
                self.current_session["completed_at"] = datetime.now().isoformat()

            from qa_auto.ui.broadcaster import broadcast_recording_event

            await broadcast_recording_event(
                session_id=session_id,
                event_type="recording_error",
                data={"status": "error", "error": str(exc)},
            )
        finally:
            self._recorder = None

    async def stop(self) -> dict[str, Any]:
        """Stop an active recording session and finalize test case generation."""
        async with self._lock:
            if not self.current_session or self.current_session.get("status") != "recording":
                return self.get_status()

            if self._recorder:
                try:
                    await self._recorder.stop_recording()
                except Exception as exc:
                    logger.warning("Error stopping recorder: %s", exc)

            if self._task and not self._task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(self._task), timeout=5.0)
                except Exception:
                    pass

            return self.get_status()

    def get_status(self) -> dict[str, Any]:
        """Return the current recorder session status."""
        if not self.current_session:
            return {"status": "idle"}
        return dict(self.current_session)


# Singleton recording manager
recording_manager = RecordingSessionManager()


def find_testcase_files(search_paths: list[Path] | None = None) -> list[Path]:
    """Find all testcase.json files in designated directories."""
    if search_paths is None:
        search_paths = [Path("recordings"), Path(".")]

    found: list[Path] = []
    seen: set[str] = set()

    for base in search_paths:
        if not base.exists():
            continue
        # Scan for testcase.json
        for path in base.glob("**/testcase.json"):
            resolved = str(path.resolve())
            if resolved not in seen:
                seen.add(resolved)
                found.append(path)

    return found


def list_testcases(
    search_paths: list[Path] | None = None,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """Scan and list all recorded test cases with summary metadata."""
    from qa_auto.ui.db import get_connection
    meta_map = {}
    try:
        conn = get_connection()
        try:
            rows = conn.execute("SELECT id, project_id FROM testcases_meta").fetchall()
            meta_map = {r["id"]: r["project_id"] for r in rows}
        finally:
            conn.close()
    except Exception:
        pass

    files = find_testcase_files(search_paths)
    cases: list[dict[str, Any]] = []

    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
            data = json.loads(content)
            case_id = data.get("id", f.parent.name)
            tc_proj_id = meta_map.get(case_id, "default_project")
            if project_id and tc_proj_id != project_id:
                continue

            name = data.get("name", f.parent.name)
            created_at = data.get("created_at", "")
            start_url = data.get("start_url", "")
            browser = data.get("browser", "chromium")
            steps = data.get("steps", [])
            total_steps = data.get("total_steps", len(steps))
            total_duration = data.get("total_duration", 0.0)

            # Locate first screenshot for preview
            thumbnail: str | None = None
            if steps:
                first_step = steps[0]
                shot = first_step.get("screenshot_path") or first_step.get(
                    "screenshot_with_highlight"
                )
                if shot:
                    thumbnail = str(Path(shot).name)

            cases.append(
                {
                    "id": case_id,
                    "project_id": tc_proj_id,
                    "name": name,
                    "created_at": created_at,
                    "start_url": start_url,
                    "browser": browser,
                    "total_steps": total_steps,
                    "total_duration": total_duration,
                    "folder": str(f.parent),
                    "file_path": str(f),
                    "thumbnail": thumbnail,
                }
            )
        except Exception as exc:
            logger.warning("Failed to parse testcase file %s: %s", f, exc)

    # Sort descending by created_at or name
    cases.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    return cases


def resolve_testcase_file(
    identifier: str, search_paths: list[Path] | None = None
) -> tuple[Path, TestCase]:
    """Find and load a TestCase by ID, directory name, or direct path."""
    # Check if direct file path
    direct_path = Path(identifier)
    if direct_path.is_file() and direct_path.name == "testcase.json":
        data = json.loads(direct_path.read_text(encoding="utf-8"))
        return direct_path, TestCase.model_validate(data)
    if direct_path.is_dir() and (direct_path / "testcase.json").exists():
        target = direct_path / "testcase.json"
        data = json.loads(target.read_text(encoding="utf-8"))
        return target, TestCase.model_validate(data)

    # Search among all discovered test cases
    files = find_testcase_files(search_paths)
    for f in files:
        if f.parent.name == identifier:
            data = json.loads(f.read_text(encoding="utf-8"))
            return f, TestCase.model_validate(data)
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("id") == identifier:
                return f, TestCase.model_validate(data)
        except Exception:
            continue

    raise FileNotFoundError(f"Test case '{identifier}' not found.")


def get_screenshot_file(identifier: str, filename: str) -> Path:
    """Locate a screenshot inside a testcase's directory safely."""
    tc_file, _ = resolve_testcase_file(identifier)
    base_dir = tc_file.parent

    # Prevent path traversal
    safe_name = Path(filename).name
    candidate_1 = base_dir / "screenshots" / safe_name
    if candidate_1.exists():
        return candidate_1

    candidate_2 = base_dir / safe_name
    if candidate_2.exists():
        return candidate_2

    raise FileNotFoundError(f"Screenshot '{filename}' not found for test case '{identifier}'.")


async def execute_replay(
    identifier: str,
    browser_type: str | None = None,
    headed: bool = False,
    timeout: int = 30000,
    heal: bool = True,
    assertions_enabled: bool = True,
    visual_diff: bool = False,
    diff_threshold: float = 0.1,
    diff_fail: bool = False,
) -> ReplayResult:
    """Run ReplayEngine on a test case and return the result."""
    tc_file, testcase = resolve_testcase_file(identifier)
    testcase_dir = tc_file.parent
    output_dir = testcase_dir / "replay_runs" / datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = ReplayEngine(
        testcase=testcase,
        browser_type=browser_type or testcase.browser,
        headless=not headed,
        timeout=timeout,
        heal=heal,
        assertions_enabled=assertions_enabled,
        visual_diff=visual_diff,
        diff_threshold=diff_threshold,
        visual_fail=diff_fail,
        output_dir=output_dir,
        testcase_dir=testcase_dir,
    )

    result = await engine.run()
    return result


def export_pytest_code(identifier: str) -> str:
    """Generate Playwright pytest code for a test case."""
    _, testcase = resolve_testcase_file(identifier)
    return generate_pytest_code(testcase)


def save_testcase(tc_file: Path, testcase: TestCase) -> None:
    """Persist updated TestCase to disk and refresh HTML/Markdown reports."""
    tc_file.write_text(testcase.model_dump_json(indent=2), encoding="utf-8")

    # Refresh HTML and Markdown reports
    try:
        HTMLExporter().export(testcase, tc_file.parent)
        MarkdownExporter().export(testcase, tc_file.parent)
    except Exception as exc:
        logger.warning("Could not refresh HTML/MD reports for %s: %s", tc_file, exc)


def update_testcase_step(
    identifier: str, step_number: int, update_data: dict[str, Any]
) -> TestCase:
    """Update fields of an existing step in a testcase."""
    tc_file, testcase = resolve_testcase_file(identifier)
    target_step: Step | None = None
    for s in testcase.steps:
        if s.number == step_number:
            target_step = s
            break

    if target_step is None:
        raise ValueError(f"Step {step_number} not found in test case {identifier}")

    if "action_type" in update_data and update_data["action_type"]:
        target_step.action_type = update_data["action_type"]
    if "input_value" in update_data:
        target_step.input_value = update_data["input_value"]
    if "key" in update_data:
        target_step.key = update_data["key"]
    if "url" in update_data:
        target_step.url = update_data["url"]
    if "description_short" in update_data and update_data["description_short"]:
        target_step.description_short = update_data["description_short"]
    if "description_detailed" in update_data and update_data["description_detailed"]:
        target_step.description_detailed = update_data["description_detailed"]

    # Update element info if provided
    if "element" in update_data and isinstance(update_data["element"], dict):
        elem_data = update_data["element"]
        if target_step.element is None:
            target_step.element = ElementInfo(
                selector=elem_data.get("selector", ""),
                xpath=elem_data.get("xpath"),
                tag_name=elem_data.get("tag_name", "button"),
                text=elem_data.get("text"),
                attributes=elem_data.get("attributes", {}),
                bounding_box=elem_data.get(
                    "bounding_box", {"x": 0, "y": 0, "width": 0, "height": 0}
                ),
            )
        else:
            if "selector" in elem_data:
                target_step.element.selector = elem_data["selector"]
            if "xpath" in elem_data:
                target_step.element.xpath = elem_data["xpath"]
            if "text" in elem_data:
                target_step.element.text = elem_data["text"]
            if "tag_name" in elem_data:
                target_step.element.tag_name = elem_data["tag_name"]

    save_testcase(tc_file, testcase)
    return testcase


def reorder_testcase_step(identifier: str, step_number: int, direction: str) -> TestCase:
    """Move a step up or down in the sequence and re-index numbers."""
    tc_file, testcase = resolve_testcase_file(identifier)
    idx = -1
    for i, s in enumerate(testcase.steps):
        if s.number == step_number:
            idx = i
            break

    if idx == -1:
        raise ValueError(f"Step {step_number} not found in test case {identifier}")

    if direction == "up" and idx > 0:
        testcase.steps[idx], testcase.steps[idx - 1] = testcase.steps[idx - 1], testcase.steps[idx]
    elif direction == "down" and idx < len(testcase.steps) - 1:
        testcase.steps[idx], testcase.steps[idx + 1] = testcase.steps[idx + 1], testcase.steps[idx]
    else:
        return testcase

    # Re-index all step numbers
    for i, step in enumerate(testcase.steps):
        step.number = i + 1

    save_testcase(tc_file, testcase)
    return testcase


def delete_testcase_step(identifier: str, step_number: int) -> TestCase:
    """Delete a step from the test case and re-index remaining steps."""
    tc_file, testcase = resolve_testcase_file(identifier)
    testcase.steps = [s for s in testcase.steps if s.number != step_number]

    # Re-index step numbers
    for i, step in enumerate(testcase.steps):
        step.number = i + 1

    testcase.total_steps = len(testcase.steps)
    save_testcase(tc_file, testcase)
    return testcase


def add_testcase_step(
    identifier: str, step_data: dict[str, Any], position: int | None = None
) -> TestCase:
    """Add a new step to the test case at the given position (1-based) or append."""
    tc_file, testcase = resolve_testcase_file(identifier)
    action_type = step_data.get("action_type", "click")
    selector = step_data.get("selector") or (
        step_data.get("element", {}).get("selector")
        if isinstance(step_data.get("element"), dict)
        else ""
    )

    elem: ElementInfo | None = None
    if selector:
        elem = ElementInfo(
            selector=selector,
            xpath=step_data.get("xpath"),
            tag_name=step_data.get("tag_name", "button"),
            text=step_data.get("text"),
            attributes={},
            bounding_box={"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0},
        )

    short_desc = step_data.get("description_short")
    if not short_desc:
        if action_type == "navigate":
            short_desc = f"Navigate to {step_data.get('url', '')}"
        elif action_type == "input":
            short_desc = f"Enter '{step_data.get('input_value', '')}' into {selector or 'field'}"
        else:
            short_desc = f"{action_type.capitalize()} on {selector or 'element'}"

    new_step = Step(
        number=len(testcase.steps) + 1,
        timestamp=datetime.now(),
        action_type=action_type,
        element=elem,
        url=step_data.get("url"),
        input_value=step_data.get("input_value"),
        key=step_data.get("key"),
        description_short=short_desc,
        description_detailed=step_data.get("description_detailed", short_desc),
    )

    if position is not None and 1 <= position <= len(testcase.steps):
        testcase.steps.insert(position - 1, new_step)
    else:
        testcase.steps.append(new_step)

    # Re-index
    for i, step in enumerate(testcase.steps):
        step.number = i + 1

    testcase.total_steps = len(testcase.steps)
    save_testcase(tc_file, testcase)
    return testcase


def add_custom_assertion(identifier: str, assertion_data: dict[str, Any]) -> TestCase:
    """Attach a user-defined assertion to a step in the testcase."""
    tc_file, testcase = resolve_testcase_file(identifier)
    new_assertion = {
        "kind": assertion_data["kind"],
        "target": assertion_data.get("target"),
        "expected": assertion_data.get("expected"),
        "step_number": int(assertion_data.get("step_number", 1)),
        "source": "manual",
        "confidence": 1.0,
        "enforced": bool(assertion_data.get("enforced", True)),
    }
    testcase.custom_assertions.append(new_assertion)
    save_testcase(tc_file, testcase)
    return testcase


def delete_custom_assertion(identifier: str, index: int) -> TestCase:
    """Remove a custom assertion by index."""
    tc_file, testcase = resolve_testcase_file(identifier)
    if 0 <= index < len(testcase.custom_assertions):
        testcase.custom_assertions.pop(index)
        save_testcase(tc_file, testcase)
    return testcase


def run_visual_diff_for_step(
    identifier: str,
    step_number: int,
    candidate_filename: str | None = None,
    threshold: float = 0.1,
) -> VisualDiffResult:
    """Compare baseline screenshot of a step against a candidate/replay screenshot."""
    tc_file, testcase = resolve_testcase_file(identifier)
    base_dir = tc_file.parent

    target_step = next((s for s in testcase.steps if s.number == step_number), None)
    if not target_step:
        raise ValueError(f"Step {step_number} not found in {identifier}")

    baseline_rel = target_step.screenshot_with_highlight or target_step.screenshot_path
    if not baseline_rel:
        raise FileNotFoundError(f"No baseline screenshot recorded for step {step_number}")

    baseline_path = (
        base_dir / baseline_rel if not Path(baseline_rel).is_absolute() else Path(baseline_rel)
    )
    if not baseline_path.exists():
        raise FileNotFoundError(f"Baseline screenshot not found at {baseline_path}")

    # Determine candidate image
    if candidate_filename:
        candidate_path = Path(candidate_filename)
        if not candidate_path.is_absolute():
            candidate_path = base_dir / candidate_filename
    else:
        # Check latest replay run for this step
        replay_candidates = sorted(
            base_dir.glob(f"replay_runs/**/{step_number:03d}_*.png"), reverse=True
        )
        candidate_path = replay_candidates[0] if replay_candidates else baseline_path

    diff_dir = base_dir / "diffs"
    diff_dir.mkdir(parents=True, exist_ok=True)
    diff_output = diff_dir / f"diff_step_{step_number:03d}.png"

    return compare_images(
        baseline=baseline_path,
        candidate=candidate_path,
        diff_output=diff_output,
        threshold_percent=threshold,
    )


def create_manual_testcase(
    name: str,
    start_url: str,
    browser: str = "chromium",
    description: str = "",
    project_id: str = "default_project",
) -> TestCase:
    """Create a new test case directory and initialize it with start navigation."""
    import shutil

    case_id = f"tc_{uuid.uuid4().hex[:8]}"
    slug = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name.lower())
    target_dir = Path("recordings") / f"{slug}_{case_id}"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "screenshots").mkdir(exist_ok=True)

    initial_step = Step(
        number=1,
        timestamp=datetime.now(),
        action_type="navigate",
        url=start_url,
        description_short=f"Navigate to {start_url}",
        description_detailed=f"Open browser and navigate to {start_url}",
    )

    tc = TestCase(
        id=case_id,
        name=name,
        start_url=start_url,
        browser=browser,
        viewport={"width": 1280, "height": 720},
        user_agent="QA Auto Studio",
        steps=[initial_step],
        created_at=datetime.now(),
        total_steps=1,
        total_duration=0.0,
    )
    tc_file = target_dir / "testcase.json"
    save_testcase(tc_file, tc)

    from qa_auto.ui.db import sync_testcase_meta

    sync_testcase_meta(tc, tc_file, project_id=project_id)
    try:
        from qa_auto.index.store import index_testcase

        index_testcase(tc, tc_file)
    except Exception:
        pass
    return tc


def delete_testcase(identifier: str) -> bool:
    """Delete a test case folder and clear its records from SQLite."""
    import shutil
    from qa_auto.ui.db import get_connection

    tc_file, testcase = resolve_testcase_file(identifier)
    parent_dir = tc_file.parent
    if "recordings" in parent_dir.parts:
        shutil.rmtree(parent_dir, ignore_errors=True)
    elif tc_file.exists():
        tc_file.unlink(missing_ok=True)

    conn = get_connection()
    try:
        with conn:
            conn.execute("DELETE FROM testcases_meta WHERE id = ?", (testcase.id,))
            conn.execute("DELETE FROM execution_runs WHERE testcase_id = ?", (testcase.id,))
    finally:
        conn.close()

    try:
        from qa_auto.index.store import init_db
        c_conn = init_db()
        with c_conn:
            c_conn.execute("DELETE FROM testcases WHERE id = ?", (testcase.id,))
            c_conn.execute("DELETE FROM steps_fts WHERE testcase_id = ?", (testcase.id,))
        c_conn.close()
    except Exception:
        pass
    return True

