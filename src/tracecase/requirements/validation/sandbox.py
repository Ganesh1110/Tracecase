"""Isolated Playwright Sandbox Executor for Draft Journeys (Phase 9.1.3)."""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page

from tracecase.browser_pool import BrowserPool
from tracecase.exploration.models import TestJourneyDraft
from tracecase.requirements.validation.models import (
    AssertionValidationResult,
    DraftValidationReport,
    SandboxSafetyPolicy,
    StepValidationResult,
    ValidationStatus,
)
from tracecase.requirements.validation.step_validator import (
    evaluate_step_assertion,
    validate_step_pre_execution,
)

logger = logging.getLogger("tracecase.requirements.validation.sandbox")

SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key", "token"}


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Sanitize sensitive request/response headers for safe artifact storage."""
    sanitized = {}
    for k, v in headers.items():
        if k.lower() in SENSITIVE_HEADERS:
            sanitized[k] = "[REDACTED]"
        else:
            sanitized[k] = v
    return sanitized


class SandboxExecutor:
    """Executes a single TestJourneyDraft in an isolated, sandboxed Playwright session."""

    def __init__(
        self,
        browser_pool: BrowserPool | None = None,
        base_artifacts_dir: Path | str = Path(".tracecase") / "artifacts" / "validations",
    ) -> None:
        self.browser_pool = browser_pool or BrowserPool()
        self.base_artifacts_dir = Path(base_artifacts_dir)

    async def execute_validation(
        self,
        draft: TestJourneyDraft,
        policy: SandboxSafetyPolicy | None = None,
        browser: str = "chromium",
        headless: bool = True,
        on_step_progress: Any = None,
    ) -> DraftValidationReport:
        """
        Execute draft journey validation inside a fresh, isolated browser context.
        
        Guarantees:
        1. 100% context isolation: context and page are dedicated to this run and closed on completion.
        2. Live pre-execution DOM verification prevents executing stale or ambiguous locators.
        3. Destructive actions are blocked unless explicitly authorized by policy.
        4. Traces, screenshots, and logs are safely stored with credential masking.
        5. Detailed diagnostics are preserved on step or assertion failures.
        """
        safety_policy = policy or SandboxSafetyPolicy()
        validation_id = f"val_{uuid.uuid4().hex[:8]}"
        run_artifact_dir = self.base_artifacts_dir / validation_id
        run_artifact_dir.mkdir(parents=True, exist_ok=True)

        started_at = datetime.now()
        step_results: list[StepValidationResult] = []
        all_assertion_results: list[AssertionValidationResult] = []
        page_errors: list[str] = []
        console_logs: list[dict[str, str]] = []
        network_requests: list[dict[str, Any]] = []

        overall_status: ValidationStatus = "NOT_RUN"
        failure_summary: str | None = None

        context: BrowserContext | None = None
        page: Page | None = None

        try:
            # 1. Acquire isolated browser context and page
            context, page = await self.browser_pool.acquire_context(
                browser_type=browser,
                headless=headless,
                timeout=safety_policy.action_timeout_ms,
            )

            # 2. Attach tracing and event collectors
            trace_path = run_artifact_dir / "trace.zip"
            await context.tracing.start(screenshots=True, snapshots=True, sources=True)

            def handle_console(msg: Any) -> None:
                console_logs.append({"type": msg.type, "text": msg.text})

            def handle_pageerror(err: Any) -> None:
                page_errors.append(str(err))

            def handle_request(req: Any) -> None:
                try:
                    network_requests.append(
                        {
                            "url": req.url,
                            "method": req.method,
                            "resource_type": req.resource_type,
                            "headers": _sanitize_headers(dict(req.headers)),
                        }
                    )
                except Exception:
                    pass

            page.on("console", handle_console)
            page.on("pageerror", handle_pageerror)
            page.on("request", handle_request)

            # 3. Step-by-step execution
            stop_execution = False

            for step in draft.steps:
                if stop_execution:
                    step_results.append(
                        StepValidationResult(
                            step_number=step.number,
                            action_type=step.action_type,
                            selector=step.selector,
                            url=step.url,
                            status="SKIPPED",
                            duration_ms=0.0,
                            error_message="Skipped due to previous step failure.",
                        )
                    )
                    continue

                step_start_time = time.monotonic()
                before_path = run_artifact_dir / f"step_{step.number}_before.png"
                after_path = run_artifact_dir / f"step_{step.number}_after.png"

                # Capture before screenshot if page has a valid URL
                if page.url and page.url != "about:blank":
                    try:
                        await page.screenshot(path=str(before_path), timeout=3000)
                    except Exception:
                        pass

                # Pre-execution validation
                valid, pre_err, meta = await validate_step_pre_execution(step, page, safety_policy)

                if not valid:
                    is_dest = meta.get("is_destructive", False)
                    status_val = "BLOCKED" if (is_dest or "ambiguous" in (pre_err or "") or "unresolved" in (pre_err or "")) else "FAILED"
                    duration = round((time.monotonic() - step_start_time) * 1000, 2)

                    step_res = StepValidationResult(
                        step_number=step.number,
                        action_type=step.action_type,
                        selector=step.selector,
                        url=step.url,
                        status=status_val,
                        duration_ms=duration,
                        error_message=pre_err,
                        screenshot_before=str(before_path) if before_path.exists() else None,
                        target_uniqueness_count=meta.get("uniqueness", 0),
                        is_visible=meta.get("visible", False),
                        is_enabled=meta.get("enabled", False),
                    )
                    step_results.append(step_res)
                    stop_execution = True
                    failure_summary = pre_err
                    if on_step_progress:
                        await on_step_progress(step.number, step_res)
                    continue

                # Execute action
                action_err: str | None = None
                try:
                    if step.action_type == "navigate":
                        target_url = step.url or draft.start_url
                        await page.goto(target_url, timeout=safety_policy.navigation_timeout_ms)
                    elif step.action_type == "click":
                        assert step.selector is not None
                        await page.locator(step.selector).first.click(timeout=safety_policy.action_timeout_ms)
                    elif step.action_type == "input":
                        assert step.selector is not None
                        val = step.input_value or ""
                        await page.locator(step.selector).first.fill(val, timeout=safety_policy.action_timeout_ms)
                    elif step.action_type == "check":
                        assert step.selector is not None
                        await page.locator(step.selector).first.check(timeout=safety_policy.action_timeout_ms)
                    elif step.action_type == "select":
                        assert step.selector is not None
                        val = step.input_value or ""
                        await page.locator(step.selector).first.select_option(val, timeout=safety_policy.action_timeout_ms)
                    elif step.action_type == "wait":
                        await page.wait_for_timeout(300)
                except Exception as ex:
                    action_err = f"Action '{step.action_type}' failed: {ex}"
                    logger.warning("Action failure on step %s: %s", step.number, ex)

                # Capture after screenshot
                try:
                    await page.screenshot(path=str(after_path), timeout=3000)
                except Exception:
                    pass

                # Evaluate step assertions
                step_assertions: list[AssertionValidationResult] = []
                for assertion in step.assertions:
                    assert_res = await evaluate_step_assertion(assertion, page, page_errors)
                    step_assertions.append(assert_res)
                    all_assertion_results.append(assert_res)

                duration = round((time.monotonic() - step_start_time) * 1000, 2)
                has_failed_assertion = any(not a.passed for a in step_assertions)

                if action_err:
                    step_status = "FAILED"
                    step_err_msg = action_err
                    stop_execution = True
                    failure_summary = action_err
                elif has_failed_assertion:
                    step_status = "FAILED"
                    first_fail = next(a for a in step_assertions if not a.passed)
                    step_err_msg = f"Assertion failed: {first_fail.failure_reason}"
                    stop_execution = True
                    failure_summary = step_err_msg
                else:
                    step_status = "PASSED"
                    step_err_msg = None

                step_res = StepValidationResult(
                    step_number=step.number,
                    action_type=step.action_type,
                    selector=step.selector,
                    url=step.url,
                    status=step_status,
                    duration_ms=duration,
                    error_message=step_err_msg,
                    screenshot_before=str(before_path) if before_path.exists() else None,
                    screenshot_after=str(after_path) if after_path.exists() else None,
                    target_uniqueness_count=meta.get("uniqueness", 1),
                    is_visible=meta.get("visible", True),
                    is_enabled=meta.get("enabled", True),
                    assertion_results=step_assertions,
                )
                step_results.append(step_res)
                if on_step_progress:
                    await on_step_progress(step.number, step_res)

            # 4. Stop tracing and persist artifacts
            try:
                await context.tracing.stop(path=str(trace_path))
            except Exception:
                pass

        except Exception as ex:
            logger.error("Sandbox execution error for draft %s: %s", draft.id, ex)
            overall_status = "BLOCKED"
            failure_summary = f"Sandbox execution infrastructure error: {ex}"
        finally:
            # 5. Clean up context and page
            if context:
                await self.browser_pool.release_context(context)

        # 6. Compute overall validation status
        if overall_status != "BLOCKED":
            has_blocked_steps = any(s.status == "BLOCKED" for s in step_results)
            has_failed_steps = any(s.status == "FAILED" for s in step_results)
            has_unverified_assertions = any(a.requires_human_input for a in all_assertion_results)

            if has_blocked_steps:
                overall_status = "BLOCKED"
            elif has_failed_steps:
                overall_status = "FAILED"
            elif has_unverified_assertions or draft.requires_human_input:
                overall_status = "PARTIALLY_VERIFIED"
            else:
                overall_status = "VERIFIED"

        completed_at = datetime.now()

        # Save artifact JSON summaries
        try:
            (run_artifact_dir / "console_logs.json").write_text(json.dumps(console_logs, indent=2))
            (run_artifact_dir / "network_summary.json").write_text(json.dumps(network_requests[:100], indent=2))
        except Exception:
            pass

        artifacts_meta = {
            "artifact_dir": str(run_artifact_dir),
            "trace_path": str(run_artifact_dir / "trace.zip") if (run_artifact_dir / "trace.zip").exists() else None,
            "total_screenshots": len(list(run_artifact_dir.glob("*.png"))),
            "page_errors": page_errors,
        }

        environment_meta = {
            "os": platform.platform(),
            "python_version": platform.python_version(),
            "browser": browser,
        }

        return DraftValidationReport(
            validation_id=validation_id,
            draft_id=draft.id,
            draft_version=getattr(draft, "version", 1),
            browser=browser,
            headless=headless,
            started_at=started_at,
            completed_at=completed_at,
            overall_status=overall_status,
            step_results=step_results,
            assertion_results=all_assertion_results,
            artifacts=artifacts_meta,
            failure_summary=failure_summary,
            environment=environment_meta,
            safety_policy=safety_policy,
            is_current_version=True,
        )
