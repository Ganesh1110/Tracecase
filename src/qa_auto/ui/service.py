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
from qa_auto.models import TestCase
from qa_auto.recorder import Recorder
from qa_auto.replay.engine import ReplayEngine
from qa_auto.replay.models import ReplayResult

logger = logging.getLogger("qa_auto.ui.service")


class RecordingSessionManager:
    """Tracks active and recent recording sessions."""

    def __init__(self) -> None:
        self.current_session: dict[str, Any] | None = None
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

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
            await recorder.run()

            # Find generated testcase.json
            tc_file = target_dir / "testcase.json"
            testcase_id = None
            if tc_file.exists():
                try:
                    data = json.loads(tc_file.read_text(encoding="utf-8"))
                    testcase_id = data.get("id")
                except Exception:
                    pass

            if self.current_session and self.current_session.get("session_id") == session_id:
                self.current_session["status"] = "completed"
                self.current_session["completed_at"] = datetime.now().isoformat()
                self.current_session["testcase_id"] = testcase_id
        except Exception as exc:
            logger.exception("Recording failed: %s", exc)
            if self.current_session and self.current_session.get("session_id") == session_id:
                self.current_session["status"] = "error"
                self.current_session["error"] = str(exc)
                self.current_session["completed_at"] = datetime.now().isoformat()

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


def list_testcases(search_paths: list[Path] | None = None) -> list[dict[str, Any]]:
    """Scan and list all recorded test cases with summary metadata."""
    files = find_testcase_files(search_paths)
    cases: list[dict[str, Any]] = []

    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
            data = json.loads(content)
            case_id = data.get("id", f.parent.name)
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
