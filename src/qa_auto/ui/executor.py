"""Background execution orchestrator and live status tracker for QA Auto Studio."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from qa_auto.replay.engine import ReplayEngine
from qa_auto.replay.models import ReplayResult, StepResult
from qa_auto.ui.broadcaster import broadcast_execution_event
from qa_auto.ui.db import (
    create_execution_run,
    log_execution_step,
    update_execution_run_status,
)
from qa_auto.ui.service import resolve_testcase_file

logger = logging.getLogger("qa_auto.ui.executor")


class ExecutionOrchestrator:
    """Manages active and queued background execution tasks."""

    def __init__(self) -> None:
        self.active_tasks: dict[str, asyncio.Task[Any]] = {}

    async def start_execution(
        self,
        testcase_id: str,
        project_id: str = "default_project",
        suite_id: str | None = None,
        browser: str = "chromium",
        headed: bool = False,
        heal: bool = True,
        assertions: bool = True,
        visual_diff: bool = False,
        diff_threshold: float = 0.1,
    ) -> dict[str, Any]:
        """Create execution record and start asynchronous execution worker."""
        # Resolve test case
        tc_file, testcase = resolve_testcase_file(testcase_id)

        # Create record in database
        run_record = create_execution_run(
            testcase_id=testcase.id,
            testcase_name=testcase.name,
            project_id=project_id,
            suite_id=suite_id,
            browser=browser,
            headed=headed,
            heal=heal,
            assertions=assertions,
            visual_diff=visual_diff,
        )
        execution_id = run_record["id"]

        # Spawn background task
        task = asyncio.create_task(
            self._run_execution_worker(
                execution_id=execution_id,
                testcase_id=testcase_id,
                tc_file=tc_file,
                browser=browser,
                headed=headed,
                heal=heal,
                assertions=assertions,
                visual_diff=visual_diff,
                diff_threshold=diff_threshold,
            )
        )
        self.active_tasks[execution_id] = task

        # Broadcast initial queued/started event
        await broadcast_execution_event(
            execution_id=execution_id,
            event_type="execution_queued",
            data=run_record,
        )

        return run_record

    async def _run_execution_worker(
        self,
        execution_id: str,
        testcase_id: str,
        tc_file: Path,
        browser: str,
        headed: bool,
        heal: bool,
        assertions: bool,
        visual_diff: bool,
        diff_threshold: float,
    ) -> None:
        """Internal execution loop."""
        _, testcase = resolve_testcase_file(testcase_id)
        testcase_dir = tc_file.parent
        output_dir = testcase_dir / "replay_runs" / datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Update status to running
        update_execution_run_status(
            execution_id=execution_id,
            status="running",
        )
        await broadcast_execution_event(
            execution_id=execution_id,
            event_type="execution_started",
            data={"status": "running", "total_steps": len(testcase.steps)},
        )

        logs: list[str] = []

        async def _step_callback(step_res: StepResult, step_num: int, total_steps: int) -> None:
            # Step metadata
            curr_step = next((s for s in testcase.steps if s.number == step_num), None)
            action_type = curr_step.action_type if curr_step else None
            screenshot = (
                str(step_res.screenshot)
                if getattr(step_res, "screenshot", None)
                else (str(step_res.screenshot_path) if getattr(step_res, "screenshot_path", None) else None)
            )

            assertions_data = []
            for a in getattr(step_res, "assertions", []):
                assertions_data.append(
                    {
                        "kind": getattr(getattr(a, "assertion", None), "kind", ""),
                        "target": getattr(getattr(a, "assertion", None), "target", None),
                        "expected": str(a.assertion.expected)
                        if getattr(getattr(a, "assertion", None), "expected", None) is not None
                        else None,
                        "passed": bool(getattr(a, "passed", False)),
                        "actual": str(a.actual) if getattr(a, "actual", None) is not None else None,
                        "message": getattr(a, "message", ""),
                    }
                )

            # Log to SQLite
            log_execution_step(
                execution_id=execution_id,
                step_number=step_num,
                action_type=action_type,
                status=step_res.status,
                duration_ms=step_res.duration_ms,
                selector_used=step_res.selector_used,
                healed_from=step_res.healed_from,
                error=step_res.error,
                screenshot_path=screenshot,
                visual_diff=step_res.visual_diff.model_dump(mode="json")
                if step_res.visual_diff
                else None,
                assertions=assertions_data,
            )

            log_entry = f"Step {step_num}/{total_steps} [{action_type}]: {step_res.status.upper()} ({step_res.duration_ms:.1f}ms)"
            if step_res.healed_from:
                log_entry += f" [HEALED from '{step_res.healed_from}']"
            if step_res.error:
                log_entry += f" - Error: {step_res.error}"
            for ad in assertions_data:
                ast_status = "PASS" if ad["passed"] else "FAIL"
                log_entry += f" | Assert [{ad['kind']}]: {ast_status}"
            logs.append(log_entry)

            # Broadcast real-time step progress
            await broadcast_execution_event(
                execution_id=execution_id,
                event_type="step_progress",
                data={
                    "step_number": step_num,
                    "total_steps": total_steps,
                    "action_type": action_type,
                    "status": step_res.status,
                    "duration_ms": step_res.duration_ms,
                    "selector_used": step_res.selector_used,
                    "healed_from": step_res.healed_from,
                    "error": step_res.error,
                    "screenshot_path": screenshot,
                    "assertions": assertions_data,
                    "log": log_entry,
                },
            )

        start_time = datetime.now()
        try:
            engine = ReplayEngine(
                testcase=testcase,
                browser_type=browser,
                headless=not headed,
                heal=heal,
                assertions_enabled=assertions,
                visual_diff=visual_diff,
                diff_threshold=diff_threshold,
                output_dir=output_dir,
                testcase_dir=testcase_dir,
                step_callback=_step_callback,
            )
            replay_res: ReplayResult = await engine.run()
            finish_time = datetime.now()
            duration_ms = (finish_time - start_time).total_seconds() * 1000.0

            passed_count = sum(1 for s in replay_res.steps if s.status == "passed")
            failed_count = sum(1 for s in replay_res.steps if s.status in ("failed", "error"))

            # Determine final status
            final_status = replay_res.status

            update_execution_run_status(
                execution_id=execution_id,
                status=final_status,
                finished_at=finish_time.isoformat(),
                duration_ms=duration_ms,
                passed_steps=passed_count,
                failed_steps=failed_count,
                total_steps=len(replay_res.steps),
                exit_code=replay_res.exit_code,
                report_path=str(output_dir),
                logs=logs,
            )

            await broadcast_execution_event(
                execution_id=execution_id,
                event_type="execution_completed",
                data={
                    "status": final_status,
                    "duration_ms": duration_ms,
                    "passed_steps": passed_count,
                    "failed_steps": failed_count,
                    "total_steps": len(replay_res.steps),
                    "exit_code": replay_res.exit_code,
                    "logs": logs,
                },
            )
        except Exception as exc:
            logger.exception("Execution failed for %s: %s", execution_id, exc)
            finish_time = datetime.now()
            duration_ms = (finish_time - start_time).total_seconds() * 1000.0
            error_str = str(exc)
            logs.append(f"Execution Error: {error_str}")

            update_execution_run_status(
                execution_id=execution_id,
                status="error",
                finished_at=finish_time.isoformat(),
                duration_ms=duration_ms,
                error_message=error_str,
                logs=logs,
            )
            await broadcast_execution_event(
                execution_id=execution_id,
                event_type="execution_failed",
                data={"status": "error", "error": error_str, "logs": logs},
            )
        finally:
            self.active_tasks.pop(execution_id, None)

    async def cancel_execution(self, execution_id: str) -> bool:
        """Cancel a running execution task."""
        task = self.active_tasks.get(execution_id)
        if task and not task.done():
            task.cancel()
            update_execution_run_status(
                execution_id=execution_id,
                status="cancelled",
                finished_at=datetime.now().isoformat(),
                error_message="Execution cancelled by user.",
            )
            await broadcast_execution_event(
                execution_id=execution_id,
                event_type="execution_cancelled",
                data={"status": "cancelled"},
            )
            return True
        return False


# Singleton orchestrator
orchestrator = ExecutionOrchestrator()
