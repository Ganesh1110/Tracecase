"""Replay recorded test cases and evaluate assertions."""

from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from playwright.async_api import Error as PlaywrightError

from qa_auto.browser import BrowserManager, BrowserType
from qa_auto.models import Step, TestCase
from qa_auto.replay.assertions import derive_assertions, evaluate_assertions
from qa_auto.replay.har import install_har_routes
from qa_auto.replay.healing import resolve_element
from qa_auto.replay.models import ReplayResult, ReplayStatus, StepResult, StepStatus

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page


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
    ) -> None:
        self.testcase = testcase
        self.browser_type = browser_type or testcase.browser
        self.headless = headless
        self.timeout = timeout
        self.heal = heal
        self.har = har
        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.assertions_enabled = assertions_enabled

    async def run(self) -> ReplayResult:
        started_at = datetime.now()
        assertions = derive_assertions(self.testcase) if self.assertions_enabled else []
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
            if self.har is not None:
                await install_har_routes(page.context, self.har)
            page.on("response", lambda response: responses.append((response.url, response.status)))
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.goto(self.testcase.start_url, wait_until="domcontentloaded")

            for step in self.testcase.steps:
                result = await self._run_step(page, step, assertions, responses, errors)
                step_results.append(result)
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

        return ReplayResult(
            testcase_id=self.testcase.id,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            exit_code=exit_code,
            steps=step_results,
        )

    async def _run_step(
        self,
        page: Page,
        step: Step,
        assertions: list[Any],
        responses: list[tuple[str, int]],
        errors: list[str],
    ) -> StepResult:
        started = time.monotonic()
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
                locator, heal_result = await resolve_element(page, step, heal=self.heal)
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
                await self._perform(page, locator, step)

            targets = [
                item.target for item in step_assertions if item.kind == "status" and item.target
            ]
            if targets:
                await self._wait_for_responses(responses, response_count_start, targets)
        except Exception as exc:
            error = str(exc)

        step_statuses: dict[str, list[int]] = {}
        for url, status_code in responses[response_count_start:]:
            step_statuses.setdefault(url, []).append(status_code)

        assertion_results = evaluate_assertions(
            step,
            step_assertions,
            response_statuses=step_statuses,
            final_url=page.url,
            new_page_errors=errors[error_count_start:],
        )
        failed = any(not result.passed for result in assertion_results)

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
            screenshot=await self._screenshot(page, step),
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
        deadline = time.monotonic() + self.timeout / 1000
        while time.monotonic() < deadline:
            seen = {url for url, _ in responses[start:]}
            if all(target in seen for target in targets):
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
