"""Autonomous exploration worker powered by Playwright and graph-based exploration."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from tracecase.exploration.extractor import extract_page_surface
from tracecase.exploration.models import (
    AppNavigationGraph,
    ExplorationConfig,
    PageNode,
    PageTransition,
    normalize_url,
)

logger = logging.getLogger("tracecase.exploration.worker")


class ExplorationWorker:
    """Executes safe, bounded, graph-based exploration of an application under test."""

    def __init__(
        self,
        exploration_id: str,
        config: ExplorationConfig,
        on_event: Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
        cancel_event: asyncio.Event | None = None,
        artifact_dir: Path | None = None,
    ) -> None:
        self.exploration_id = exploration_id
        self.config = config
        self.on_event = on_event
        self.cancel_event = cancel_event or asyncio.Event()

        # Storage directory for screenshots
        if artifact_dir:
            self.artifact_dir = artifact_dir / "explorations" / exploration_id
        else:
            self.artifact_dir = Path(".tracecase") / "explorations" / exploration_id
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

        # Graph and tracking
        self.graph = AppNavigationGraph(
            exploration_id=exploration_id,
            start_url=normalize_url(config.start_url),
        )
        self.visited_urls: set[str] = set()
        self.visited_fingerprints: set[str] = set()
        self.interaction_count = 0

        # Allowed origins
        self.allowed_origins: set[str] = set()
        start_netloc = urlparse(config.start_url).netloc.lower()
        if start_netloc:
            self.allowed_origins.add(start_netloc)
        for orig in config.allowed_origins:
            clean_orig = urlparse(orig).netloc.lower() or orig.lower().strip()
            if clean_orig:
                self.allowed_origins.add(clean_orig)

    def _is_origin_allowed(self, target_url: str) -> bool:
        """Check if target URL belongs to an allowed origin."""
        target_netloc = urlparse(target_url).netloc.lower()
        if not target_netloc:
            return True  # relative or local URL
        return target_netloc in self.allowed_origins

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit progress event to listener if registered."""
        if self.on_event:
            try:
                await self.on_event(event_type, data)
            except Exception as exc:
                logger.debug("Failed emitting exploration event %s: %s", event_type, exc)

    async def run(self) -> AppNavigationGraph:
        """Execute the exploration loop until limits or completion reached."""
        start_time = time.monotonic()
        start_url_norm = normalize_url(self.config.start_url)

        # Queue items: (target_url, depth, source_url, action_type, selector, element_text)
        queue: deque[tuple[str, int, str | None, str, str | None, str | None]] = deque()
        queue.append((start_url_norm, 0, None, "navigate", None, "Initial Page Navigation"))

        playwright_cm = async_playwright()
        playwright = await playwright_cm.start()
        browser: Browser | None = None
        context: BrowserContext | None = None
        page: Page | None = None

        try:
            launcher = getattr(playwright, self.config.browser)
            browser = await launcher.launch(headless=self.config.headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=True,
            )

            # Apply cookies if provided
            if self.config.auth_cookies:
                await context.add_cookies(cast(Any, self.config.auth_cookies))

            # Apply extra headers if provided
            if self.config.auth_headers:
                await context.set_extra_http_headers(self.config.auth_headers)

            page = await context.new_page()
            page.set_default_timeout(10000)

            # Auto-handle dialogs (alerts, confirms, prompts) so they never freeze exploration
            page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))

            await self._emit(
                "exploration_started",
                {
                    "exploration_id": self.exploration_id,
                    "start_url": start_url_norm,
                    "max_depth": self.config.max_depth,
                    "max_pages": self.config.max_pages,
                },
            )

            while queue:
                # 1. Safety and Limit Checks
                if self.cancel_event.is_set():
                    logger.info("Exploration %s cancelled by user request", self.exploration_id)
                    await self._emit("exploration_cancelled", {"reason": "Cancelled by user"})
                    break

                elapsed = time.monotonic() - start_time
                if elapsed > self.config.execution_timeout:
                    logger.warning("Exploration %s exceeded timeout of %.1fs", self.exploration_id, self.config.execution_timeout)
                    break

                if len(self.graph.nodes) >= self.config.max_pages:
                    logger.info("Exploration %s reached max_pages limit (%d)", self.exploration_id, self.config.max_pages)
                    break

                if self.interaction_count >= self.config.max_interactions:
                    logger.info("Exploration %s reached max_interactions limit (%d)", self.exploration_id, self.config.max_interactions)
                    break

                # 2. Dequeue Next Target
                target_url, depth, source_url, action_type, selector, element_text = queue.popleft()
                norm_target = normalize_url(target_url)

                # Skip if cross-origin
                if not self._is_origin_allowed(norm_target):
                    logger.debug("Skipping cross-origin URL: %s", norm_target)
                    continue

                # Skip if already visited
                if norm_target in self.visited_urls:
                    # Still record transition edge if source differs
                    if source_url and source_url != norm_target:
                        trans_id = f"trans_{uuid.uuid4().hex[:8]}"
                        trans = PageTransition(
                            id=trans_id,
                            exploration_id=self.exploration_id,
                            source_url=source_url,
                            target_url=norm_target,
                            action_type=action_type,  # type: ignore[arg-type]
                            selector=selector,
                            element_text=element_text,
                            is_safe=True,
                            duration_ms=0.0,
                        )
                        self.graph.transitions.append(trans)
                    continue

                # 3. Navigate to Page
                nav_start = time.monotonic()
                status_code = 200
                try:
                    response = await page.goto(norm_target, wait_until="domcontentloaded", timeout=12000)
                    if response:
                        status_code = response.status
                except Exception as exc:
                    logger.warning("Failed navigating to %s: %s", norm_target, exc)
                    continue

                self.interaction_count += 1
                nav_duration = (time.monotonic() - nav_start) * 1000.0
                current_actual_url = normalize_url(page.url)

                # 4. Extract Page Surface
                surface = await extract_page_surface(page, current_actual_url)
                title = surface["title"]
                fingerprint = surface["fingerprint"]
                forms = surface["forms"]
                interactive_elements = surface["interactive_elements"]
                links = surface["links"]

                # Loop prevention by state fingerprint
                if fingerprint in self.visited_fingerprints and current_actual_url in self.visited_urls:
                    continue

                self.visited_urls.add(norm_target)
                self.visited_urls.add(current_actual_url)
                self.visited_fingerprints.add(fingerprint)

                # 5. Capture Page Screenshot
                screenshot_rel_path: str | None = None
                try:
                    shot_filename = f"node_{len(self.graph.nodes) + 1}.png"
                    shot_path = self.artifact_dir / shot_filename
                    await page.screenshot(path=str(shot_path), full_page=False)
                    screenshot_rel_path = str(shot_path)
                except Exception as shot_err:
                    logger.debug("Could not take exploration screenshot: %s", shot_err)

                # 6. Create Page Node
                node_id = f"node_{len(self.graph.nodes) + 1}"
                node = PageNode(
                    id=node_id,
                    exploration_id=self.exploration_id,
                    url=current_actual_url,
                    normalized_url=current_actual_url,
                    title=title,
                    depth=depth,
                    state_fingerprint=fingerprint,
                    status_code=status_code,
                    forms=forms,
                    interactive_elements=interactive_elements,
                    links=links,
                    screenshot_path=screenshot_rel_path,
                )
                self.graph.nodes[current_actual_url] = node

                # 7. Record Inbound Transition Edge
                if source_url and source_url != current_actual_url:
                    trans_id = f"trans_{uuid.uuid4().hex[:8]}"
                    trans = PageTransition(
                        id=trans_id,
                        exploration_id=self.exploration_id,
                        source_url=source_url,
                        target_url=current_actual_url,
                        action_type=action_type,  # type: ignore[arg-type]
                        selector=selector,
                        element_text=element_text,
                        is_safe=True,
                        duration_ms=nav_duration,
                    )
                    self.graph.transitions.append(trans)
                    await self._emit("transition_discovered", trans.model_dump(mode="json"))

                await self._emit(
                    "page_discovered",
                    {
                        "node_id": node.id,
                        "url": node.url,
                        "title": node.title,
                        "depth": node.depth,
                        "forms_count": len(node.forms),
                        "interactive_count": len(node.interactive_elements),
                        "total_pages": len(self.graph.nodes),
                    },
                )

                # 8. Queue Child Links for Exploration
                if depth < self.config.max_depth:
                    for link in links:
                        link_norm = normalize_url(link)
                        if link_norm not in self.visited_urls and self._is_origin_allowed(link_norm):
                            queue.append(
                                (
                                    link_norm,
                                    depth + 1,
                                    current_actual_url,
                                    "click_link",
                                    f"a[href='{link}']",
                                    f"Navigate to {link_norm}",
                                )
                            )

            await self._emit(
                "exploration_completed",
                {
                    "exploration_id": self.exploration_id,
                    "total_pages": len(self.graph.nodes),
                    "total_transitions": len(self.graph.transitions),
                    "total_forms": self.graph.total_forms,
                    "duration_seconds": round(time.monotonic() - start_time, 2),
                },
            )

        except Exception as exc:
            logger.exception("Exploration worker encountered error: %s", exc)
            await self._emit("exploration_failed", {"error": str(exc)})
            raise
        finally:
            # Clean up browser and context
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            await playwright.stop()

        return self.graph
