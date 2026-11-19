"""Replay recorded test cases and evaluate assertions."""

from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from playwright.async_api import Error as PlaywrightError

from tracecase.browser import BrowserManager, BrowserType
from tracecase.models import Step, TestCase
from tracecase.replay.assertions import derive_assertions, evaluate_assertions
from tracecase.replay.har import install_har_routes
from tracecase.replay.healing import resolve_element
from tracecase.replay.models import ReplayResult, ReplayStatus, StepResult, StepStatus
from tracecase.replay.visual import compare_images

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Locator, Page


class ReplayEngine:
    """Replay a recorded test case in a fresh browser."""

    def __init__(
        self,
        testcase: TestCase,
        *,
        browser_type: str | None = None,
        headless: bool = True,
        timeout: int = 30000,
        heal: bool = False,
        har: dict[str, Any] | None = None,
        output_dir: Path | None = None,
        assertions_enabled: bool = True,
        visual_diff: bool = False,
        diff_threshold: float = 0.1,
        visual_fail: bool = False,
        testcase_dir: Path | None = None,
        step_callback: Any = None,
    ) -> None:
        self.testcase = testcase
        self.browser_type = browser_type or testcase.browser
        self.headless = headless
        self.timeout = timeout
        self.heal = heal
        self.har = har
        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.assertions_enabled = assertions_enabled
        self.visual_diff = visual_diff
        self.diff_threshold = diff_threshold
        self.visual_fail = visual_fail
        self.testcase_dir = Path(testcase_dir) if testcase_dir is not None else None
        self.step_callback = step_callback

    async def run(self) -> ReplayResult:
        started_at = datetime.now()
        assertions = derive_assertions(self.testcase) if self.assertions_enabled else []
        custom_assertions = getattr(self.testcase, "custom_assertions", []) or []
        if self.assertions_enabled and custom_assertions:
            from tracecase.replay.models import Assertion

            for ca in custom_assertions:
                if isinstance(ca, dict):
                    assertions.append(Assertion.model_validate(ca))
                elif isinstance(ca, Assertion):
                    assertions.append(ca)
        manager = BrowserManager(
            browser_type=cast(BrowserType, self.browser_type),
            headless=self.headless,
            viewport=(
                self.testcase.viewport.get("width", 1280),
                self.testcase.viewport.get("height", 720),
            ),
            timeout=self.timeout,
        )
        responses: list[tuple[str, int]] = []
        errors: list[str] = []
        step_results: list[StepResult] = []

        try:
            page = await manager.start()
            context = manager.context

            def _attach_page_listeners(p: Page) -> None:
                p.on(
                    "response",
                    lambda response: responses.append((response.url, response.status)),
                )
                p.on("pageerror", lambda error: errors.append(str(error)))

            _attach_page_listeners(page)
            context.on("page", _attach_page_listeners)

            if self.har is not None:
                await install_har_routes(context, self.har)

            await page.goto(self.testcase.start_url, wait_until="domcontentloaded")

            for step in self.testcase.steps:
                result = await self._run_step(context, step, assertions, responses, errors)
                step_results.append(result)
                if self.step_callback:
                    try:
                        cb_res = self.step_callback(result, step.number, len(self.testcase.steps))
                        if asyncio.iscoroutine(cb_res):
                            await cb_res
                    except Exception:
                        pass
        except Exception as exc:
            step_results.append(StepResult(number=0, status="error", error=str(exc)))
        finally:
            with contextlib.suppress(Exception):
                await manager.close()

        finished_at = datetime.now()
        errored = any(result.status == "error" for result in step_results)
        failed = any(result.status == "failed" for result in step_results)

        status: ReplayStatus
        exit_code: int
        if errored:
            status, exit_code = "error", 2
        elif failed:
            status, exit_code = "failed", 1
        else:
            status, exit_code = "passed", 0

        visual_diffs = [
            result.visual_diff for result in step_results if result.visual_diff is not None
        ]

        return ReplayResult(
            testcase_id=self.testcase.id,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            exit_code=exit_code,
            steps=step_results,
            visual_diffs=visual_diffs,
        )

    async def _get_target_page(self, context: BrowserContext, page_id: int | None) -> Page:
        """Resolve the target page/tab for a step, waiting for popups if needed."""
        target_idx = page_id or 0
        deadline = time.monotonic() + min(self.timeout / 1000, 5.0)

        while len(context.pages) <= target_idx and time.monotonic() < deadline:
            await asyncio.sleep(0.05)

        if target_idx < len(context.pages):
            return context.pages[target_idx]
        return context.pages[0]

    async def _run_step(
        self,
        context: BrowserContext,
        step: Step,
        assertions: list[Any],
        responses: list[tuple[str, int]],
        errors: list[str],
    ) -> StepResult:
        started = time.monotonic()
        page = await self._get_target_page(context, step.page_id)
        error_count_start = len(errors)
        response_count_start = len(responses)
        step_assertions = [item for item in assertions if item.step_number == step.number]
        selector_used: str | None = None
        healed_from: str | None = None
        error: str | None = None

        try:
            if step.action_type == "navigate" and step.url:
                await page.goto(step.url, wait_until="domcontentloaded")
            else:
                locator, heal_result = await resolve_element(
                    page, step, heal=self.heal, timeout_ms=min(self.timeout, 5000)
                )
                selector_used = heal_result.selector
                healed_from = heal_result.healed_from
                if locator is None:
                    attempts = ", ".join(heal_result.attempts)
                    return StepResult(
                        number=step.number,
                        status="error",
                        error=f"Element not found. Tried: {attempts}",
                        duration_ms=(time.monotonic() - started) * 1000,
                    )

                step_idx = step.number - 1
                expects_popup = step_idx + 1 < len(self.testcase.steps) and (
                    self.testcase.steps[step_idx + 1].page_id or 0
                ) > (step.page_id or 0)

                if expects_popup:
                    try:
                        async with page.expect_popup(timeout=min(self.timeout, 5000)):
                            await self._perform(page, locator, step)
                    except Exception:
                        pass
                else:
                    await self._perform(page, locator, step)

            targets = [
                item.target for item in step_assertions if item.kind == "status" and item.target
            ]
            if targets:
                await self._wait_for_responses(responses, response_count_start, targets)

            url_targets = [
                item.expected for item in step_assertions if item.kind == "url" and item.expected
            ]
            for exp in url_targets:
                with contextlib.suppress(Exception):
                    await page.wait_for_url(f"**{exp}*", timeout=min(self.timeout, 5000))
        except Exception as exc:
            error = str(exc)

        step_statuses: dict[str, list[int]] = {}
        for url, status_code in responses[response_count_start:]:
            step_statuses.setdefault(url, []).append(status_code)

        page_text: str | None = None
        visible_targets: set[str] = set()
        with contextlib.suppress(Exception):
            page_text = await page.inner_text("body")
        for item in step_assertions:
            if item.kind == "visible":
                target = item.target or (step.element.selector if step.element else None)
                if target:
                    with contextlib.suppress(Exception):
                        if await page.locator(target).first.is_visible():
                            visible_targets.add(target)

        assertion_results = evaluate_assertions(
            step,
            step_assertions,
            response_statuses=step_statuses,
            final_url=page.url,
            new_page_errors=errors[error_count_start:],
            visible_targets=visible_targets,
            page_text=page_text,
        )
        failed = any(not result.passed for result in assertion_results)

        candidate_screenshot = await self._screenshot(page, step)
        visual_diff_result = None
        baseline_screenshot = step.screenshot_path or step.screenshot_with_highlight

        if self.visual_diff and baseline_screenshot and candidate_screenshot and self.output_dir:
            base_file = Path(baseline_screenshot)
            if self.testcase_dir and not base_file.is_absolute():
                base_file = self.testcase_dir / baseline_screenshot
            if base_file.exists():
                cand_full_path = self.output_dir / candidate_screenshot
                diff_out = self.output_dir / "diffs" / f"{step.number:03d}_diff.png"
                visual_diff_result = compare_images(
                    base_file,
                    cand_full_path,
                    diff_output=diff_out,
                    threshold_percent=self.diff_threshold,
                )
                if self.visual_fail and not visual_diff_result.passed:
                    failed = True

        step_status: StepStatus
        if error is not None:
            step_status = "error"
        elif failed:
            step_status = "failed"
        elif healed_from is not None:
            step_status = "healed"
        else:
            step_status = "passed"

        return StepResult(
            number=step.number,
            status=step_status,
            selector_used=selector_used,
            healed_from=healed_from,
            assertions=assertion_results,
            screenshot=candidate_screenshot,
            visual_diff=visual_diff_result,
            error=error,
            duration_ms=(time.monotonic() - started) * 1000,
        )

    async def _perform(self, page: Page, locator: Locator, step: Step) -> None:
        action = step.action_type
        if action == "click":
            await locator.click()
        elif action == "dblclick":
            await locator.dblclick()
        elif action == "input":
            await locator.fill(step.input_value or "")
        elif action == "select":
            try:
                await locator.select_option(value=step.input_value or "")
            except PlaywrightError:
                await locator.select_option(label=step.input_value or "")
        elif action == "check":
            await locator.check()
        elif action == "uncheck":
            await locator.uncheck()
        elif action == "hover":
            await locator.hover()
        elif action == "keypress":
            await page.keyboard.press(step.key or "Enter")
        elif action == "wait":
            await page.wait_for_timeout(int(step.input_value or "0"))
        else:
            raise ValueError(f"Unsupported action type: {action}")

    async def _wait_for_responses(
        self,
        responses: list[tuple[str, int]],
        start: int,
        targets: list[str],
    ) -> None:
        from urllib.parse import urlparse

        deadline = time.monotonic() + min(self.timeout / 1000, 3.0)
        while time.monotonic() < deadline:
            seen = {url for url, _ in responses[start:]}
            matched_all = True
            for target in targets:
                t_path = urlparse(target).path or target
                if not any(target in s or (t_path and t_path in s) for s in seen):
                    matched_all = False
                    break
            if matched_all:
                return
            await asyncio.sleep(0.05)

    async def _screenshot(self, page: Page, step: Step) -> str | None:
        output_dir = self.output_dir
        if output_dir is None:
            return None
        path = output_dir / "replay" / f"{step.number:03d}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await page.screenshot(path=path)
            return str(path.relative_to(output_dir))
        except Exception:
            return None


def write_replay_result(result: ReplayResult, output_dir: Path) -> Path:
    """Write a replay report to disk."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "replay.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path
