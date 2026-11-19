"""Background execution orchestrator and live status tracker for QA Auto Studio."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from qa_auto.replay.engine import ReplayEngine
from qa_auto.replay.models import ReplayResult, StepResult
from qa_auto.ui.broadcaster import (
    broadcast_batch_event,
    broadcast_execution_event,
    broadcast_matrix_event,
)
from qa_auto.ui.db import (
    create_execution_batch,
    create_execution_matrix,
    create_execution_run,
    get_execution_batch,
    get_execution_matrix,
    log_execution_step,
    update_execution_batch,
    update_execution_matrix,
    update_execution_run_status,
)
from qa_auto.ui.service import resolve_testcase_file

logger = logging.getLogger("qa_auto.ui.executor")


class ExecutionOrchestrator:
    """Manages active and queued background execution tasks."""

    def __init__(self) -> None:
        self.active_tasks: dict[str, asyncio.Task[Any]] = {}
        self.active_batches: dict[str, dict[str, Any]] = {}
        self.active_matrices: dict[str, dict[str, Any]] = {}

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

        # Enforce Rule 2: Unapproved drafts can NEVER be executed
        from qa_auto.ui.db import get_testcase_meta
        meta = get_testcase_meta(testcase.id)
        if meta and meta.get("approval_status") == "draft":
            raise ValueError(f"Cannot execute test case '{testcase.id}': draft requires human approval before execution.")

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

    async def start_batch_execution(
        self,
        testcase_ids: list[str],
        concurrency: int = 2,
        project_id: str = "default_project",
        suite_id: str | None = None,
        browser: str = "chromium",
        headed: bool = False,
        heal: bool = True,
        assertions: bool = True,
        visual_diff: bool = False,
        diff_threshold: float = 0.1,
    ) -> dict[str, Any]:
        """Launch parallel or sequential execution of multiple test cases via a bounded worker pool."""
        c = 2 if concurrency is None else int(concurrency)
        bounded_concurrency = max(1, min(8, c))

        # Deduplicate testcase_ids preserving original sequence order
        seen = set()
        deduped_ids = []
        for tid in testcase_ids:
            if tid and tid not in seen:
                seen.add(tid)
                deduped_ids.append(tid)

        if not deduped_ids:
            raise ValueError("No valid test cases provided for batch execution.")

        # Enforce Rule 2: Unapproved drafts can NEVER be executed
        from qa_auto.ui.db import get_testcase_meta

        items_to_run = []
        for tid in deduped_ids:
            tc_file, testcase = resolve_testcase_file(tid)
            meta = get_testcase_meta(testcase.id)
            if meta and meta.get("approval_status") == "draft":
                raise ValueError(
                    f"Cannot execute test case '{testcase.id}': draft requires human approval before execution."
                )
            items_to_run.append((tc_file, testcase))

        batch_id = f"batch_{uuid.uuid4().hex[:10]}"
        batch_record = create_execution_batch(
            batch_id=batch_id,
            project_id=project_id,
            suite_id=suite_id,
            concurrency=bounded_concurrency,
            total_tests=len(items_to_run),
        )

        queued_items = []
        run_records = []
        for tc_file, testcase in items_to_run:
            run_rec = create_execution_run(
                testcase_id=testcase.id,
                testcase_name=testcase.name,
                project_id=project_id,
                suite_id=suite_id,
                browser=browser,
                headed=headed,
                heal=heal,
                assertions=assertions,
                visual_diff=visual_diff,
                batch_id=batch_id,
                concurrency=bounded_concurrency,
            )
            queued_items.append((tc_file, testcase, run_rec))
            run_records.append(run_rec)

        queue: asyncio.Queue = asyncio.Queue()
        for item in queued_items:
            queue.put_nowait(item)

        batch_ctx: dict[str, Any] = {
            "batch_id": batch_id,
            "project_id": project_id,
            "suite_id": suite_id,
            "concurrency": bounded_concurrency,
            "total_tests": len(items_to_run),
            "queue": queue,
            "active_worker_tasks": {},
            "cancelled": False,
            "passed_tests": 0,
            "failed_tests": 0,
            "cancelled_tests": 0,
            "running_testcases": set(),
            "start_time": datetime.now(),
        }
        self.active_batches[batch_id] = batch_ctx

        coordinator_task = asyncio.create_task(
            self._run_batch_coordinator(
                batch_id=batch_id,
                batch_ctx=batch_ctx,
                browser=browser,
                headed=headed,
                heal=heal,
                assertions=assertions,
                visual_diff=visual_diff,
                diff_threshold=diff_threshold,
            )
        )
        self.active_tasks[batch_id] = coordinator_task

        # Broadcast initial batch event
        await broadcast_batch_event(
            batch_id=batch_id,
            event_type="batch_started",
            data={
                "batch_id": batch_id,
                "project_id": project_id,
                "suite_id": suite_id,
                "total_tests": len(items_to_run),
                "concurrency": bounded_concurrency,
                "status": "running",
                "runs": run_records,
            },
        )

        return {**batch_record, "runs": run_records}

    async def _run_batch_coordinator(
        self,
        batch_id: str,
        batch_ctx: dict[str, Any],
        browser: str,
        headed: bool,
        heal: bool,
        assertions: bool,
        visual_diff: bool,
        diff_threshold: float,
    ) -> None:
        """Coordinates concurrent workers, tracks overall batch progress, and finalizes status."""
        concurrency = batch_ctx["concurrency"]
        update_execution_batch(batch_id=batch_id, status="running")

        worker_tasks = []
        for i in range(concurrency):
            worker_id = f"worker-{i+1}"
            w_task = asyncio.create_task(
                self._run_batch_worker(
                    worker_id=worker_id,
                    batch_id=batch_id,
                    batch_ctx=batch_ctx,
                    browser=browser,
                    headed=headed,
                    heal=heal,
                    assertions=assertions,
                    visual_diff=visual_diff,
                    diff_threshold=diff_threshold,
                )
            )
            batch_ctx["active_worker_tasks"][worker_id] = w_task
            worker_tasks.append(w_task)

        try:
            await asyncio.gather(*worker_tasks, return_exceptions=True)
        finally:
            finish_time = datetime.now()
            duration_ms = (finish_time - batch_ctx["start_time"]).total_seconds() * 1000.0

            if batch_ctx.get("cancelled") or (batch_ctx["cancelled_tests"] > 0 and batch_ctx["passed_tests"] == 0 and batch_ctx["failed_tests"] == 0):
                status = "cancelled"
            elif batch_ctx["failed_tests"] > 0:
                status = "failed"
            else:
                status = "passed"

            update_execution_batch(
                batch_id=batch_id,
                status=status,
                passed_tests=batch_ctx["passed_tests"],
                failed_tests=batch_ctx["failed_tests"],
                cancelled_tests=batch_ctx["cancelled_tests"],
                finished_at=finish_time.isoformat(),
                duration_ms=duration_ms,
            )

            await broadcast_batch_event(
                batch_id=batch_id,
                event_type="batch_completed" if status != "cancelled" else "batch_cancelled",
                data={
                    "batch_id": batch_id,
                    "status": status,
                    "total_tests": batch_ctx["total_tests"],
                    "passed_tests": batch_ctx["passed_tests"],
                    "failed_tests": batch_ctx["failed_tests"],
                    "cancelled_tests": batch_ctx["cancelled_tests"],
                    "duration_ms": duration_ms,
                },
            )

            self.active_batches.pop(batch_id, None)
            self.active_tasks.pop(batch_id, None)

    async def _run_batch_worker(
        self,
        worker_id: str,
        batch_id: str,
        batch_ctx: dict[str, Any],
        browser: str,
        headed: bool,
        heal: bool,
        assertions: bool,
        visual_diff: bool,
        diff_threshold: float,
    ) -> None:
        """Worker loop consuming items from the queue with full browser context isolation."""
        queue: asyncio.Queue = batch_ctx["queue"]

        while not queue.empty() and not batch_ctx.get("cancelled", False):
            try:
                tc_file, testcase, run_record = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            if batch_ctx.get("cancelled", False):
                queue.task_done()
                break

            execution_id = run_record["id"]

            # Mutual exclusion: avoid simultaneous execution of identical test cases
            while testcase.id in batch_ctx["running_testcases"] and not batch_ctx.get("cancelled", False):
                await asyncio.sleep(0.1)

            if batch_ctx.get("cancelled", False):
                queue.task_done()
                break

            batch_ctx["running_testcases"].add(testcase.id)

            update_execution_run_status(
                execution_id=execution_id,
                status="running",
                worker_id=worker_id,
                batch_id=batch_id,
            )

            await broadcast_batch_event(
                batch_id=batch_id,
                event_type="worker_started",
                data={
                    "batch_id": batch_id,
                    "worker_id": worker_id,
                    "execution_id": execution_id,
                    "testcase_id": testcase.id,
                    "testcase_name": testcase.name,
                },
            )

            # Strict context & artifact isolation: dedicated directory per worker and run
            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            output_dir = tc_file.parent / "replay_runs" / f"{batch_id}_{worker_id}_{ts_str}"
            output_dir.mkdir(parents=True, exist_ok=True)

            logs: list[str] = []

            async def _step_callback(step_res: StepResult, step_num: int, total_steps: int) -> None:
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

                log_entry = f"[{worker_id}] Step {step_num}/{total_steps} [{action_type}]: {step_res.status.upper()} ({step_res.duration_ms:.1f}ms)"
                if step_res.healed_from:
                    log_entry += f" [HEALED from '{step_res.healed_from}']"
                if step_res.error:
                    log_entry += f" - Error: {step_res.error}"
                for ad in assertions_data:
                    ast_status = "PASS" if ad["passed"] else "FAIL"
                    log_entry += f" | Assert [{ad['kind']}]: {ast_status}"
                logs.append(log_entry)

                step_data = {
                    "batch_id": batch_id,
                    "worker_id": worker_id,
                    "execution_id": execution_id,
                    "testcase_id": testcase.id,
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
                }
                await broadcast_execution_event(
                    execution_id=execution_id,
                    event_type="step_progress",
                    data=step_data,
                )
                await broadcast_batch_event(
                    batch_id=batch_id,
                    event_type="worker_step_progress",
                    data=step_data,
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
                    testcase_dir=tc_file.parent,
                    step_callback=_step_callback,
                )
                replay_res: ReplayResult = await engine.run()
                finish_time = datetime.now()
                duration_ms = (finish_time - start_time).total_seconds() * 1000.0

                passed_count = sum(1 for s in replay_res.steps if s.status == "passed")
                failed_count = sum(1 for s in replay_res.steps if s.status in ("failed", "error"))
                final_status = replay_res.status

                if final_status == "passed":
                    batch_ctx["passed_tests"] += 1
                else:
                    batch_ctx["failed_tests"] += 1

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
                    worker_id=worker_id,
                    batch_id=batch_id,
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
                        "worker_id": worker_id,
                        "batch_id": batch_id,
                    },
                )
                await broadcast_batch_event(
                    batch_id=batch_id,
                    event_type="worker_completed",
                    data={
                        "batch_id": batch_id,
                        "worker_id": worker_id,
                        "execution_id": execution_id,
                        "testcase_id": testcase.id,
                        "status": final_status,
                        "duration_ms": duration_ms,
                        "passed_steps": passed_count,
                        "failed_steps": failed_count,
                    },
                )
            except asyncio.CancelledError:
                finish_time = datetime.now()
                duration_ms = (finish_time - start_time).total_seconds() * 1000.0
                batch_ctx["cancelled_tests"] += 1
                update_execution_run_status(
                    execution_id=execution_id,
                    status="cancelled",
                    finished_at=finish_time.isoformat(),
                    duration_ms=duration_ms,
                    error_message="Execution cancelled.",
                    worker_id=worker_id,
                    batch_id=batch_id,
                )
                raise
            except Exception as exc:
                # Exception isolation: failure in one test does not terminate sibling workers
                logger.exception("Worker %s failed on testcase %s: %s", worker_id, testcase.id, exc)
                finish_time = datetime.now()
                duration_ms = (finish_time - start_time).total_seconds() * 1000.0
                batch_ctx["failed_tests"] += 1
                err_msg = str(exc)
                logs.append(f"Worker Error: {err_msg}")
                update_execution_run_status(
                    execution_id=execution_id,
                    status="error",
                    finished_at=finish_time.isoformat(),
                    duration_ms=duration_ms,
                    error_message=err_msg,
                    logs=logs,
                    worker_id=worker_id,
                    batch_id=batch_id,
                )
                await broadcast_execution_event(
                    execution_id=execution_id,
                    event_type="execution_failed",
                    data={
                        "status": "error",
                        "error": err_msg,
                        "logs": logs,
                        "worker_id": worker_id,
                        "batch_id": batch_id,
                    },
                )
                await broadcast_batch_event(
                    batch_id=batch_id,
                    event_type="worker_completed",
                    data={
                        "batch_id": batch_id,
                        "worker_id": worker_id,
                        "execution_id": execution_id,
                        "testcase_id": testcase.id,
                        "status": "error",
                        "error": err_msg,
                    },
                )
            finally:
                batch_ctx["running_testcases"].discard(testcase.id)
                queue.task_done()
                completed_count = (
                    batch_ctx["passed_tests"]
                    + batch_ctx["failed_tests"]
                    + batch_ctx["cancelled_tests"]
                )
                await broadcast_batch_event(
                    batch_id=batch_id,
                    event_type="batch_progress",
                    data={
                        "batch_id": batch_id,
                        "total_tests": batch_ctx["total_tests"],
                        "completed_tests": completed_count,
                        "passed_tests": batch_ctx["passed_tests"],
                        "failed_tests": batch_ctx["failed_tests"],
                        "cancelled_tests": batch_ctx["cancelled_tests"],
                        "remaining_queue": queue.qsize(),
                    },
                )

    async def cancel_batch_execution(self, batch_id: str) -> bool:
        """Cancel a running batch execution and terminate active worker tasks."""
        batch_ctx = self.active_batches.get(batch_id)
        now_iso = datetime.now().isoformat()
        cancelled = False

        if batch_ctx:
            batch_ctx["cancelled"] = True
            queue: asyncio.Queue = batch_ctx["queue"]

            # Drain queued unstarted tests and mark them cancelled
            while not queue.empty():
                try:
                    tc_file, testcase, run_record = queue.get_nowait()
                    batch_ctx["cancelled_tests"] += 1
                    update_execution_run_status(
                        execution_id=run_record["id"],
                        status="cancelled",
                        finished_at=now_iso,
                        error_message="Batch execution cancelled before start.",
                        batch_id=batch_id,
                    )
                    queue.task_done()
                except asyncio.QueueEmpty:
                    break

            # Terminate active worker tasks
            for worker_id, w_task in list(batch_ctx["active_worker_tasks"].items()):
                if not w_task.done():
                    w_task.cancel()
            cancelled = True

        task = self.active_tasks.get(batch_id)
        if task and not task.done():
            task.cancel()
            cancelled = True

        batch = get_execution_batch(batch_id)
        if batch and batch.get("status") in ("queued", "running", "cancelled"):
            cancelled = True
            update_execution_batch(
                batch_id=batch_id,
                status="cancelled",
                finished_at=now_iso,
            )
            for r in batch.get("runs", []):
                if r.get("status") in ("queued", "running"):
                    update_execution_run_status(
                        execution_id=r["id"],
                        status="cancelled",
                        finished_at=now_iso,
                        error_message="Batch execution cancelled by user.",
                        batch_id=batch_id,
                    )

        if cancelled:
            update_execution_batch(
                batch_id=batch_id,
                status="cancelled",
                finished_at=now_iso,
            )
            await broadcast_batch_event(
                batch_id=batch_id,
                event_type="batch_cancelled",
                data={
                    "batch_id": batch_id,
                    "status": "cancelled",
                    "cancelled_tests": batch_ctx["cancelled_tests"] if batch_ctx else 0,
                },
            )
            return True
        return False

    async def start_matrix_execution(
        self,
        testcase_ids: list[str],
        browsers: list[str] | None = None,
        concurrency: int = 2,
        project_id: str = "default_project",
        suite_id: str | None = None,
        matrix_name: str | None = None,
        headed: bool = False,
        heal: bool = True,
        assertions: bool = True,
        visual_diff: bool = False,
        diff_threshold: float = 0.1,
    ) -> dict[str, Any]:
        """Launch cross-browser matrix execution of test cases across configured browser targets."""
        c = 2 if concurrency is None else int(concurrency)
        bounded_concurrency = max(1, min(8, c))

        # Validate and normalize browser targets
        valid_browsers = ["chromium", "firefox", "webkit"]
        target_browsers = [
            b.lower() for b in (browsers or ["chromium", "firefox", "webkit"]) if b.lower() in valid_browsers
        ]
        if not target_browsers:
            target_browsers = ["chromium"]

        # Deduplicate testcase_ids preserving sequence
        seen = set()
        deduped_ids = []
        for tid in testcase_ids:
            if tid and tid not in seen:
                seen.add(tid)
                deduped_ids.append(tid)

        if not deduped_ids:
            raise ValueError("No valid test cases provided for matrix execution.")

        from qa_auto.ui.db import get_testcase_meta

        items_to_run = []
        for tid in deduped_ids:
            tc_file, testcase = resolve_testcase_file(tid)
            meta = get_testcase_meta(testcase.id)
            if meta and meta.get("approval_status") == "draft":
                raise ValueError(
                    f"Cannot execute test case '{testcase.id}': draft requires human approval before execution."
                )
            items_to_run.append((tc_file, testcase))

        matrix_id = f"matrix_{uuid.uuid4().hex[:10]}"
        total_executions = len(items_to_run) * len(target_browsers)

        matrix_record = create_execution_matrix(
            matrix_id=matrix_id,
            project_id=project_id,
            suite_id=suite_id,
            name=matrix_name or f"Matrix: {len(items_to_run)} tests x {len(target_browsers)} browsers",
            concurrency=bounded_concurrency,
            browsers=target_browsers,
            total_executions=total_executions,
        )

        queued_items = []
        run_records = []
        for tc_file, testcase in items_to_run:
            for b in target_browsers:
                run_rec = create_execution_run(
                    testcase_id=testcase.id,
                    testcase_name=testcase.name,
                    project_id=project_id,
                    suite_id=suite_id,
                    browser=b,
                    headed=headed,
                    heal=heal,
                    assertions=assertions,
                    visual_diff=visual_diff,
                    matrix_id=matrix_id,
                    concurrency=bounded_concurrency,
                )
                queued_items.append((tc_file, testcase, b, run_rec))
                run_records.append(run_rec)

        queue: asyncio.Queue = asyncio.Queue()
        for item in queued_items:
            queue.put_nowait(item)

        matrix_ctx: dict[str, Any] = {
            "matrix_id": matrix_id,
            "project_id": project_id,
            "suite_id": suite_id,
            "concurrency": bounded_concurrency,
            "browsers": target_browsers,
            "total_executions": total_executions,
            "queue": queue,
            "active_worker_tasks": {},
            "cancelled": False,
            "passed_executions": 0,
            "failed_executions": 0,
            "cancelled_executions": 0,
            "running_keys": set(),
            "start_time": datetime.now(),
        }
        self.active_matrices[matrix_id] = matrix_ctx

        coordinator_task = asyncio.create_task(
            self._run_matrix_coordinator(
                matrix_id=matrix_id,
                matrix_ctx=matrix_ctx,
                headed=headed,
                heal=heal,
                assertions=assertions,
                visual_diff=visual_diff,
                diff_threshold=diff_threshold,
            )
        )
        self.active_tasks[matrix_id] = coordinator_task

        # Broadcast initial matrix event
        await broadcast_matrix_event(
            matrix_id=matrix_id,
            event_type="matrix_started",
            data={
                "matrix_id": matrix_id,
                "project_id": project_id,
                "suite_id": suite_id,
                "browsers": target_browsers,
                "total_executions": total_executions,
                "concurrency": bounded_concurrency,
                "status": "running",
                "runs": run_records,
            },
        )

        return get_execution_matrix(matrix_id) or matrix_record

    async def _run_matrix_coordinator(
        self,
        matrix_id: str,
        matrix_ctx: dict[str, Any],
        headed: bool,
        heal: bool,
        assertions: bool,
        visual_diff: bool,
        diff_threshold: float,
    ) -> None:
        """Coordinates concurrent workers for matrix execution and calculates cross-browser divergence."""
        concurrency = matrix_ctx["concurrency"]
        update_execution_matrix(matrix_id=matrix_id, status="running")

        worker_tasks = []
        for i in range(concurrency):
            worker_id = f"matrix-worker-{i+1}"
            w_task = asyncio.create_task(
                self._run_matrix_worker(
                    worker_id=worker_id,
                    matrix_id=matrix_id,
                    matrix_ctx=matrix_ctx,
                    headed=headed,
                    heal=heal,
                    assertions=assertions,
                    visual_diff=visual_diff,
                    diff_threshold=diff_threshold,
                )
            )
            matrix_ctx["active_worker_tasks"][worker_id] = w_task
            worker_tasks.append(w_task)

        try:
            await asyncio.gather(*worker_tasks, return_exceptions=True)
        finally:
            finish_time = datetime.now()
            duration_ms = (finish_time - matrix_ctx["start_time"]).total_seconds() * 1000.0

            if matrix_ctx.get("cancelled") or (
                matrix_ctx["cancelled_executions"] > 0
                and matrix_ctx["passed_executions"] == 0
                and matrix_ctx["failed_executions"] == 0
            ):
                status = "cancelled"
            elif matrix_ctx["failed_executions"] > 0:
                status = "failed"
            else:
                status = "passed"

            # Fetch consolidated grid & compute divergence count
            matrix_data = get_execution_matrix(matrix_id) or {}
            divergence_count = matrix_data.get("divergent_testcases_count", 0)

            update_execution_matrix(
                matrix_id=matrix_id,
                status=status,
                passed_executions=matrix_ctx["passed_executions"],
                failed_executions=matrix_ctx["failed_executions"],
                cancelled_executions=matrix_ctx["cancelled_executions"],
                divergence_count=divergence_count,
                finished_at=finish_time.isoformat(),
                duration_ms=duration_ms,
            )

            final_matrix = get_execution_matrix(matrix_id) or {}

            await broadcast_matrix_event(
                matrix_id=matrix_id,
                event_type="matrix_completed" if status != "cancelled" else "matrix_cancelled",
                data={
                    "matrix_id": matrix_id,
                    "status": status,
                    "total_executions": matrix_ctx["total_executions"],
                    "passed_executions": matrix_ctx["passed_executions"],
                    "failed_executions": matrix_ctx["failed_executions"],
                    "cancelled_executions": matrix_ctx["cancelled_executions"],
                    "divergence_count": divergence_count,
                    "cross_browser_parity_pct": final_matrix.get("cross_browser_parity_pct", 100.0),
                    "browser_pass_rates": final_matrix.get("browser_pass_rates", {}),
                    "duration_ms": duration_ms,
                },
            )

            self.active_matrices.pop(matrix_id, None)
            self.active_tasks.pop(matrix_id, None)

    async def _run_matrix_worker(
        self,
        worker_id: str,
        matrix_id: str,
        matrix_ctx: dict[str, Any],
        headed: bool,
        heal: bool,
        assertions: bool,
        visual_diff: bool,
        diff_threshold: float,
    ) -> None:
        """Worker loop executing (testcase, browser) tasks with browser-specific directory isolation."""
        queue: asyncio.Queue = matrix_ctx["queue"]

        while not queue.empty() and not matrix_ctx.get("cancelled", False):
            try:
                tc_file, testcase, browser, run_record = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            if matrix_ctx.get("cancelled", False):
                queue.task_done()
                break

            execution_id = run_record["id"]
            run_key = f"{testcase.id}::{browser}"

            # Avoid concurrent collision on the exact same (testcase, browser) tuple
            while run_key in matrix_ctx["running_keys"] and not matrix_ctx.get("cancelled", False):
                await asyncio.sleep(0.1)

            if matrix_ctx.get("cancelled", False):
                queue.task_done()
                break

            matrix_ctx["running_keys"].add(run_key)

            update_execution_run_status(
                execution_id=execution_id,
                status="running",
                worker_id=worker_id,
                matrix_id=matrix_id,
            )

            await broadcast_matrix_event(
                matrix_id=matrix_id,
                event_type="worker_started",
                data={
                    "matrix_id": matrix_id,
                    "worker_id": worker_id,
                    "execution_id": execution_id,
                    "testcase_id": testcase.id,
                    "testcase_name": testcase.name,
                    "browser": browser,
                },
            )

            # Strict context & artifact isolation: dedicated directory per matrix, browser, and worker run
            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            output_dir = tc_file.parent / "replay_runs" / f"{matrix_id}_{browser}_{worker_id}_{ts_str}"
            output_dir.mkdir(parents=True, exist_ok=True)

            logs: list[str] = []

            async def _step_callback(step_res: StepResult, step_num: int, total_steps: int) -> None:
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

                log_entry = f"[{worker_id}][{browser}] Step {step_num}/{total_steps} [{action_type}]: {step_res.status.upper()} ({step_res.duration_ms:.1f}ms)"
                if step_res.healed_from:
                    log_entry += f" [HEALED from '{step_res.healed_from}']"
                if step_res.error:
                    log_entry += f" - Error: {step_res.error}"
                for ad in assertions_data:
                    ast_status = "PASS" if ad["passed"] else "FAIL"
                    log_entry += f" | Assert [{ad['kind']}]: {ast_status}"
                logs.append(log_entry)

                step_data = {
                    "matrix_id": matrix_id,
                    "worker_id": worker_id,
                    "execution_id": execution_id,
                    "testcase_id": testcase.id,
                    "browser": browser,
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
                }
                await broadcast_execution_event(
                    execution_id=execution_id,
                    event_type="step_progress",
                    data=step_data,
                )
                await broadcast_matrix_event(
                    matrix_id=matrix_id,
                    event_type="worker_step_progress",
                    data=step_data,
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
                    testcase_dir=tc_file.parent,
                    step_callback=_step_callback,
                )
                replay_res: ReplayResult = await engine.run()
                finish_time = datetime.now()
                duration_ms = (finish_time - start_time).total_seconds() * 1000.0

                passed_count = sum(1 for s in replay_res.steps if s.status == "passed")
                failed_count = sum(1 for s in replay_res.steps if s.status in ("failed", "error"))
                final_status = replay_res.status

                first_err = next((s.error for s in replay_res.steps if s.error), None)
                if first_err:
                    is_env_error = any(
                        p in first_err.lower()
                        for p in [
                            "executable doesn't exist",
                            "playwright install",
                            "failed to launch",
                            "browser binary missing",
                            "executable path does not exist",
                        ]
                    )
                    if is_env_error:
                        first_err = f"Browser binary missing for '{browser}': Please run 'playwright install {browser}' ({first_err})"

                if final_status == "passed":
                    matrix_ctx["passed_executions"] += 1
                else:
                    matrix_ctx["failed_executions"] += 1

                update_execution_run_status(
                    execution_id=execution_id,
                    status=final_status,
                    finished_at=finish_time.isoformat(),
                    duration_ms=duration_ms,
                    passed_steps=passed_count,
                    failed_steps=failed_count,
                    total_steps=len(replay_res.steps),
                    exit_code=replay_res.exit_code,
                    error_message=first_err,
                    report_path=str(output_dir),
                    logs=logs,
                    worker_id=worker_id,
                    matrix_id=matrix_id,
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
                        "worker_id": worker_id,
                        "matrix_id": matrix_id,
                        "browser": browser,
                    },
                )
                await broadcast_matrix_event(
                    matrix_id=matrix_id,
                    event_type="worker_completed",
                    data={
                        "matrix_id": matrix_id,
                        "worker_id": worker_id,
                        "execution_id": execution_id,
                        "testcase_id": testcase.id,
                        "browser": browser,
                        "status": final_status,
                        "duration_ms": duration_ms,
                        "passed_steps": passed_count,
                        "failed_steps": failed_count,
                    },
                )
            except asyncio.CancelledError:
                finish_time = datetime.now()
                duration_ms = (finish_time - start_time).total_seconds() * 1000.0
                matrix_ctx["cancelled_executions"] += 1
                update_execution_run_status(
                    execution_id=execution_id,
                    status="cancelled",
                    finished_at=finish_time.isoformat(),
                    duration_ms=duration_ms,
                    error_message="Matrix execution cancelled.",
                    worker_id=worker_id,
                    matrix_id=matrix_id,
                )
                raise
            except Exception as exc:
                logger.exception("Matrix worker %s failed on %s [%s]: %s", worker_id, testcase.id, browser, exc)
                finish_time = datetime.now()
                duration_ms = (finish_time - start_time).total_seconds() * 1000.0
                matrix_ctx["failed_executions"] += 1
                raw_err = str(exc)

                # Distinguish browser binary missing / environment errors from test failures
                is_env_error = any(
                    p in raw_err.lower()
                    for p in [
                        "executable doesn't exist",
                        "playwright install",
                        "failed to launch",
                        "browser binary missing",
                        "executable path does not exist",
                    ]
                )
                if is_env_error:
                    err_msg = (
                        f"Browser binary missing for '{browser}': Please run 'playwright install {browser}' ({raw_err})"
                    )
                else:
                    err_msg = raw_err

                logs.append(f"Worker Error: {err_msg}")
                update_execution_run_status(
                    execution_id=execution_id,
                    status="error",
                    finished_at=finish_time.isoformat(),
                    duration_ms=duration_ms,
                    error_message=err_msg,
                    logs=logs,
                    worker_id=worker_id,
                    matrix_id=matrix_id,
                )
                await broadcast_execution_event(
                    execution_id=execution_id,
                    event_type="execution_failed",
                    data={
                        "status": "error",
                        "error": err_msg,
                        "logs": logs,
                        "worker_id": worker_id,
                        "matrix_id": matrix_id,
                        "browser": browser,
                    },
                )
                await broadcast_matrix_event(
                    matrix_id=matrix_id,
                    event_type="worker_completed",
                    data={
                        "matrix_id": matrix_id,
                        "worker_id": worker_id,
                        "execution_id": execution_id,
                        "testcase_id": testcase.id,
                        "browser": browser,
                        "status": "error",
                        "error": err_msg,
                    },
                )
            finally:
                matrix_ctx["running_keys"].discard(run_key)
                queue.task_done()
                completed_count = (
                    matrix_ctx["passed_executions"]
                    + matrix_ctx["failed_executions"]
                    + matrix_ctx["cancelled_executions"]
                )
                await broadcast_matrix_event(
                    matrix_id=matrix_id,
                    event_type="matrix_progress",
                    data={
                        "matrix_id": matrix_id,
                        "total_executions": matrix_ctx["total_executions"],
                        "completed_executions": completed_count,
                        "passed_executions": matrix_ctx["passed_executions"],
                        "failed_executions": matrix_ctx["failed_executions"],
                        "cancelled_executions": matrix_ctx["cancelled_executions"],
                        "remaining_queue": queue.qsize(),
                    },
                )

    async def cancel_matrix_execution(self, matrix_id: str) -> bool:
        """Cancel a running cross-browser matrix execution and terminate active worker tasks."""
        matrix_ctx = self.active_matrices.get(matrix_id)
        now_iso = datetime.now().isoformat()
        cancelled = False

        if matrix_ctx:
            matrix_ctx["cancelled"] = True
            queue: asyncio.Queue = matrix_ctx["queue"]

            # Drain queued unstarted runs and mark them cancelled
            while not queue.empty():
                try:
                    tc_file, testcase, browser, run_record = queue.get_nowait()
                    matrix_ctx["cancelled_executions"] += 1
                    update_execution_run_status(
                        execution_id=run_record["id"],
                        status="cancelled",
                        finished_at=now_iso,
                        error_message="Matrix execution cancelled before start.",
                        matrix_id=matrix_id,
                    )
                    queue.task_done()
                except asyncio.QueueEmpty:
                    break

            # Terminate active worker tasks
            for worker_id, w_task in list(matrix_ctx["active_worker_tasks"].items()):
                if not w_task.done():
                    w_task.cancel()
            cancelled = True

        task = self.active_tasks.get(matrix_id)
        if task and not task.done():
            task.cancel()
            cancelled = True

        matrix = get_execution_matrix(matrix_id)
        if matrix and matrix.get("status") in ("queued", "running", "cancelled"):
            cancelled = True
            update_execution_matrix(
                matrix_id=matrix_id,
                status="cancelled",
                finished_at=now_iso,
            )
            for r in matrix.get("runs", []):
                if r.get("status") in ("queued", "running"):
                    update_execution_run_status(
                        execution_id=r["id"],
                        status="cancelled",
                        finished_at=now_iso,
                        error_message="Matrix execution cancelled by user.",
                        matrix_id=matrix_id,
                    )

        if cancelled:
            update_execution_matrix(
                matrix_id=matrix_id,
                status="cancelled",
                finished_at=now_iso,
            )
            await broadcast_matrix_event(
                matrix_id=matrix_id,
                event_type="matrix_cancelled",
                data={
                    "matrix_id": matrix_id,
                    "status": "cancelled",
                    "cancelled_executions": matrix_ctx["cancelled_executions"] if matrix_ctx else 0,
                },
            )
            return True
        return False


# Singleton orchestrator
orchestrator = ExecutionOrchestrator()
