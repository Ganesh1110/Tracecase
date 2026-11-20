"""Validation Orchestrator coordinating sandboxed execution, background tasks, and event broadcasting."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from tracecase.browser_pool import BrowserPool
from tracecase.exploration.models import TestJourneyDraft
from tracecase.requirements.validation.models import (
    DraftValidationReport,
    SandboxSafetyPolicy,
    StepValidationResult,
)
from tracecase.requirements.validation.sandbox import SandboxExecutor
from tracecase.ui.broadcaster import broadcast_draft_validation_event
from tracecase.ui.db import (
    get_draft_validation,
    get_latest_draft_validation,
    get_synthesized_draft,
    list_draft_validations,
    save_draft_validation,
)

logger = logging.getLogger("tracecase.requirements.validation.orchestrator")


class ValidationOrchestrator:
    """Manages isolated browser validation lifecycles, background tasks, and reporting."""

    def __init__(self, browser_pool: BrowserPool | None = None) -> None:
        self.browser_pool = browser_pool or BrowserPool()
        self.executor = SandboxExecutor(browser_pool=self.browser_pool)
        self._active_tasks: dict[str, asyncio.Task[DraftValidationReport]] = {}

    async def validate_draft(
        self,
        draft_or_id: str | TestJourneyDraft,
        policy: SandboxSafetyPolicy | None = None,
        browser: str = "chromium",
        headless: bool = True,
        db_path: Any = None,
    ) -> DraftValidationReport:
        """
        Validate a draft journey in an isolated browser sandbox and persist results.
        
        Guarantees:
        1. Context isolation: always runs in dedicated browser context.
        2. Progress events are broadcast in real-time.
        3. Results are persisted and linked to the exact draft ID and draft version.
        4. Does NOT automatically approve or promote the draft.
        """
        if isinstance(draft_or_id, str):
            draft_dict = get_synthesized_draft(draft_or_id, db_path=db_path)
            if not draft_dict:
                raise ValueError(f"Draft '{draft_or_id}' not found.")
            draft = TestJourneyDraft(**draft_dict)
        else:
            draft = draft_or_id

        val_id = f"val_run_{draft.id}"

        # Real-time step progress callback
        async def on_step_progress(step_num: int, step_res: StepValidationResult) -> None:
            try:
                await broadcast_draft_validation_event(
                    draft_id=draft.id,
                    validation_id=val_id,
                    event_type="draft_validation:step",
                    data={
                        "step_number": step_num,
                        "status": step_res.status,
                        "error_message": step_res.error_message,
                        "duration_ms": step_res.duration_ms,
                    },
                )
            except Exception:
                pass

        try:
            await broadcast_draft_validation_event(
                draft_id=draft.id,
                validation_id=val_id,
                event_type="draft_validation:started",
                data={
                    "draft_id": draft.id,
                    "draft_version": getattr(draft, "version", 1),
                    "total_steps": len(draft.steps),
                    "browser": browser,
                },
            )
        except Exception:
            pass

        # Execute sandboxed validation
        report = await self.executor.execute_validation(
            draft=draft,
            policy=policy,
            browser=browser,
            headless=headless,
            on_step_progress=on_step_progress,
        )

        # Persist to SQLite
        try:
            save_draft_validation(report.model_dump(mode="json"), db_path=db_path)
        except Exception as ex:
            logger.warning("Failed to persist draft validation to SQLite: %s", ex)

        try:
            await broadcast_draft_validation_event(
                draft_id=draft.id,
                validation_id=report.validation_id,
                event_type="draft_validation:completed",
                data={
                    "overall_status": report.overall_status,
                    "passed_steps": report.passed_steps_count,
                    "failed_steps": report.failed_steps_count,
                    "blocked_steps": report.blocked_steps_count,
                    "failure_summary": report.failure_summary,
                },
            )
        except Exception:
            pass

        return report

    def start_background_validation(
        self,
        draft_or_id: str | TestJourneyDraft,
        policy: SandboxSafetyPolicy | None = None,
        browser: str = "chromium",
        headless: bool = True,
        db_path: Any = None,
    ) -> str:
        """Launch validation as an asynchronous background task."""
        draft_id = draft_or_id if isinstance(draft_or_id, str) else draft_or_id.id
        task = asyncio.create_task(
            self.validate_draft(
                draft_or_id=draft_or_id,
                policy=policy,
                browser=browser,
                headless=headless,
                db_path=db_path,
            )
        )
        self._active_tasks[draft_id] = task

        def _cleanup(t: asyncio.Task[Any]) -> None:
            self._active_tasks.pop(draft_id, None)

        task.add_done_callback(_cleanup)
        return draft_id

    def cancel_validation(self, draft_id: str) -> bool:
        """Cancel an in-flight background validation task."""
        task = self._active_tasks.get(draft_id)
        if task and not task.done():
            task.cancel()
            self._active_tasks.pop(draft_id, None)
            return True
        return False

    def is_validating(self, draft_id: str) -> bool:
        """Check whether a validation task is actively executing for the draft."""
        task = self._active_tasks.get(draft_id)
        return bool(task and not task.done())


# Default global orchestrator
_default_orchestrator: ValidationOrchestrator | None = None


def get_validation_orchestrator() -> ValidationOrchestrator:
    """Return the singleton validation orchestrator."""
    global _default_orchestrator
    if _default_orchestrator is None:
        _default_orchestrator = ValidationOrchestrator()
    return _default_orchestrator
