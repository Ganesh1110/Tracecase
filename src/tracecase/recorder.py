"""Main recorder class for Tracecase."""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Callable, Coroutine
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import ConsoleMessage, Dialog, Download, FileChooser, Page, Request, Response
from rich.console import Console

from tracecase.browser import BrowserManager
from tracecase.control_panel import CONTROL_PANEL_JS, inject_control_panel, update_panel_ui
from tracecase.events import EVENT_LISTENER_JS, parse_element_info, setup_event_listeners
from tracecase.exporters import HTMLExporter, JSONExporter, MarkdownExporter
from tracecase.models import (
    ActionType,
    ConsoleLog,
    ConsoleLogLevel,
    ElementInfo,
    NetworkRequest,
    PageError,
    Step,
    TestCase,
)
from tracecase.screenshot import generate_screenshot_filename, take_screenshot
from tracecase.streaming.input import dispatch_input_event
from tracecase.streaming.models import (
    InputEvent,
    InputEventType,
    ScreencastFrame,
    StreamSessionConfig,
    StreamSessionInfo,
    StreamSessionState,
)
from tracecase.streaming.screencast import CDPScreencastManager, FrameCallback

logger = logging.getLogger("tracecase.recorder")
console = Console()


class Recorder:
    """
    Main class for recording browser actions.

    Manages the recording session, captures user actions, takes screenshots,
    captures console logs and network requests, and exports the test case
    in multiple formats.

    Usage:
        recorder = Recorder(
            output_dir=Path("./output"),
            start_url="https://example.com",
            name="My Test Case"
        )
        await recorder.run()
    """

    def __init__(
        self,
        output_dir: Path,
        start_url: str,
        name: str = "Test Case",
        browser_type: str = "chromium",
        headless: bool = False,
        viewport: tuple[int, int] = (1280, 720),
        timeout: int = 30000,
        auto_start: bool = False,
        embedded: bool = False,
        session_id: str | None = None,
        stream_token: str | None = None,
        owner_id: str = "default_user",
        project_id: str = "default_project",
    ) -> None:
        """
        Initialize the recorder.

        Args:
            output_dir: Directory to save output files
            start_url: URL to open when starting
            name: Name for the test case
            browser_type: Browser to use (chromium, firefox, webkit, msedge)
            headless: Run browser without GUI
            viewport: Browser window size (width, height)
            timeout: Default timeout for operations in ms
            auto_start: Automatically begin recording actions once navigated
            embedded: Whether to run as an embedded Studio session (headless + screencast)
            session_id: Unique streaming/recording session identifier
            stream_token: Secure random token required to connect to WebSocket stream
            owner_id: Session owner identity
            project_id: Target project ID
        """
        self.output_dir = Path(output_dir).resolve()
        self.start_url = start_url
        self.name = name
        self.browser_type = browser_type
        self.headless = headless
        self.viewport = viewport
        self.timeout = timeout
        self.auto_start = auto_start
        self.embedded = embedded
        self.session_id = session_id or f"rec_{uuid.uuid4().hex[:8]}"
        self.stream_token = stream_token
        self.owner_id = owner_id
        self.project_id = project_id

        # Streaming session state
        self.state = StreamSessionState.INITIALIZING
        self.config = StreamSessionConfig(
            session_id=self.session_id,
            url=start_url,
            browser=browser_type,
            headless=True if embedded else headless,
            viewport_width=viewport[0],
            viewport_height=viewport[1],
            timeout_ms=timeout,
            owner_id=owner_id,
            project_id=project_id,
        )

        # Multi-tab and streaming components
        self.active_page_id: int = 0
        self._screencasts: dict[int, CDPScreencastManager] = {}
        self._frame_listeners: list[FrameCallback] = []
        self._broadcast_listeners: list[Callable[[dict[str, Any]], Coroutine[Any, Any, None]]] = []
        self._pending_dialogs: dict[str, Dialog] = {}
        self._pending_file_choosers: dict[str, FileChooser] = {}

        # Recording state
        self.is_recording = False
        self.is_paused = False
        self.step_callback: Any = None
        self.steps: list[Step] = []
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None

        # Logs and network requests
        self.console_logs: list[ConsoleLog] = []
        self.network_requests: list[NetworkRequest] = []
        self.page_errors: list[PageError] = []
        self._pending_requests: dict[str, tuple[NetworkRequest, Request]] = {}
        self._step_console_logs: list[ConsoleLog] = []  # Logs for current step
        self._step_network_requests: list[NetworkRequest] = []  # Requests for current step

        # Browser manager and pages
        self._browser_manager: BrowserManager | None = None
        self._pages: list[Page] = []

        # Control flags
        self._stop_event = asyncio.Event()
        self._recording_complete = asyncio.Event()
        self.ready_event = asyncio.Event()

    @property
    def screenshots_dir(self) -> Path:
        """Get the screenshots directory."""
        return self.output_dir / "screenshots"

    @property
    def active_page(self) -> Page:
        """Get the currently focused tab/page."""
        if 0 <= self.active_page_id < len(self._pages):
            return self._pages[self.active_page_id]
        if self._pages:
            return self._pages[0]
        if self._browser_manager and self._browser_manager._page:
            return self._browser_manager._page
        raise RuntimeError("No active browser page available.")

    @property
    def page(self) -> Page:
        """Alias for active_page to satisfy streaming protocol."""
        return self.active_page

    @property
    def screencast(self) -> CDPScreencastManager | None:
        """Get active CDP screencast manager for the focused tab."""
        return self._screencasts.get(self.active_page_id)

    @property
    def latest_frame(self) -> ScreencastFrame | None:
        """Get most recent frame from the active screencast."""
        sc = self.screencast
        return sc.latest_frame if sc else None

    def add_frame_listener(self, callback: FrameCallback) -> None:
        """Register a callback for screencast frames."""
        if callback not in self._frame_listeners:
            self._frame_listeners.append(callback)
        sc = self.screencast
        if sc:
            sc.add_listener(callback)

    def remove_frame_listener(self, callback: FrameCallback) -> None:
        """Remove a registered screencast frame callback."""
        if callback in self._frame_listeners:
            self._frame_listeners.remove(callback)
        sc = self.screencast
        if sc:
            sc.remove_listener(callback)

    def add_broadcast_listener(
        self, callback: Callable[[dict[str, Any]], Coroutine[Any, Any, None]]
    ) -> None:
        """Register a callback to receive high-level stream broadcast messages."""
        if callback not in self._broadcast_listeners:
            self._broadcast_listeners.append(callback)

    def remove_broadcast_listener(
        self, callback: Callable[[dict[str, Any]], Coroutine[Any, Any, None]]
    ) -> None:
        """Remove a registered broadcast listener."""
        if callback in self._broadcast_listeners:
            self._broadcast_listeners.remove(callback)

    async def broadcast_stream_message(self, message: dict[str, Any]) -> None:
        """Broadcast high-level browser events to all active WebSocket clients."""
        for listener in list(self._broadcast_listeners):
            try:
                await listener(message)
            except Exception as exc:
                logger.debug("Broadcast listener error: %s", exc)

    async def run(self) -> None:
        """
        Run the recording session.

        Opens the browser (headless with CDP screencast in embedded mode,
        or headed with injected control panel in CLI mode), and waits for
        start/stop controls.
        """
        # Prepare output directory
        self._prepare_output_dir()

        # Optimize browser flags for screencasting in embedded mode
        launch_args = None
        if self.embedded:
            launch_args = [
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
            ]

        # In embedded mode, browser always runs headless
        run_headless = True if self.embedded else self.headless

        self._browser_manager = BrowserManager(
            browser_type=self.browser_type,  # type: ignore[arg-type]
            headless=run_headless,
            viewport=self.viewport,
            timeout=self.timeout,
            launch_args=launch_args,
        )

        try:
            # Start browser
            page = await self._browser_manager.start()
            self._pages = [page]
            self.active_page_id = 0
            console.print("[green]✓[/green] Browser launched")

            # Set up listeners for the primary page
            self._setup_page_listeners(page)
            console.print("[green]✓[/green] Console & network listeners attached")

            if self.embedded:
                # Set up CDP Screencast on primary page (0)
                sc = CDPScreencastManager(
                    page=page,
                    format="jpeg",
                    quality=75,
                    max_width=self.viewport[0],
                    max_height=self.viewport[1],
                    every_nth_frame=1,
                )
                for listener in self._frame_listeners:
                    sc.add_listener(listener)
                await sc.start()
                self._screencasts[0] = sc

                # Setup dialogs, file uploads, and downloads
                self._setup_embedded_page_handlers(page, page_id=0)

                # Set up event listeners without injected control panel
                await setup_event_listeners(page, self, page_id=0)
                self.state = StreamSessionState.ACTIVE
                console.print("[green]✓[/green] Embedded screencast active (no in-page panel)")
            else:
                # Set up control panel and event listeners for headed mode
                await inject_control_panel(page, self)
                await setup_event_listeners(page, self, page_id=0)
                console.print("[green]✓[/green] Control panel injected")

            # Listen for newly opened tabs and popups
            self._browser_manager.context.on(
                "page", lambda new_page: asyncio.create_task(self._on_new_page(new_page))
            )

            # Navigate to start URL
            await self._browser_manager.navigate(self.start_url)
            console.print(f"[green]✓[/green] Navigated to {self.start_url}")

            page_title = await page.title()
            if page_title:
                console.print(f"[green]✓[/green] Page loaded: {page_title}")

            if self.auto_start:
                await self.start_recording()

            self.ready_event.set()

            console.print("\n[bold]Ready to record![/bold]")
            if not self.embedded:
                console.print("[dim]Click '▶ Start' in the browser to begin recording.[/dim]")
            console.print("[dim]Press Ctrl+C to cancel.[/dim]\n")

            # Wait for recording to complete
            await self._recording_complete.wait()

        finally:
            self.ready_event.set()
            self.state = StreamSessionState.STOPPED
            for sc in list(self._screencasts.values()):
                with contextlib.suppress(Exception):
                    await sc.stop()
            self._screencasts.clear()

            # Cleanup
            if self._browser_manager:
                await self._browser_manager.close()
                console.print("[green]✓[/green] Browser closed")

    def _setup_page_listeners(self, page: Page) -> None:
        """Set up page lifecycle, console, and network listeners."""
        page.on("load", self._on_page_load)
        page.on("domcontentloaded", self._on_dom_ready)
        page.on("console", self._on_console_message)
        page.on("pageerror", self._on_page_error)
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        page.on("requestfailed", self._on_request_failed)

    async def _on_new_page(self, new_page: Page) -> None:
        """Handle newly opened tab or popup window."""
        if new_page in self._pages:
            return
        self._pages.append(new_page)
        page_id = len(self._pages) - 1
        self._setup_page_listeners(new_page)
        with contextlib.suppress(Exception):
            await setup_event_listeners(new_page, self, page_id=page_id)
        console.print(f"[green]✓[/green] New tab/popup #{page_id} detected and instrumented")

        if self.embedded:
            self._setup_embedded_page_handlers(new_page, page_id=page_id)

            sc = CDPScreencastManager(
                page=new_page,
                format="jpeg",
                quality=75,
                max_width=self.viewport[0],
                max_height=self.viewport[1],
                every_nth_frame=1,
            )
            self._screencasts[page_id] = sc

            def on_tab_close() -> None:
                asyncio.create_task(self._on_tab_closed(page_id))

            new_page.on("close", on_tab_close)

            try:
                title = await new_page.title()
            except Exception:
                title = f"Tab {page_id + 1}"

            await self.broadcast_stream_message({
                "type": "tab_opened",
                "payload": {
                    "page_id": page_id,
                    "url": new_page.url,
                    "title": title or f"Tab {page_id + 1}",
                },
            })
            await self.switch_tab(page_id)

    async def _on_tab_closed(self, page_id: int) -> None:
        """Handle closed tab."""
        sc = self._screencasts.pop(page_id, None)
        if sc:
            with contextlib.suppress(Exception):
                await sc.stop()
        await self.broadcast_stream_message({
            "type": "tab_closed",
            "payload": {"page_id": page_id},
        })
        if self.active_page_id == page_id:
            for idx, p in enumerate(self._pages):
                if not p.is_closed() and idx != page_id:
                    await self.switch_tab(idx)
                    return
            await self.switch_tab(0)

    def _setup_embedded_page_handlers(self, page: Page, page_id: int) -> None:
        """Set up JS dialogs, file choosers, and downloads for an embedded page."""
        async def on_dialog(dialog: Dialog) -> None:
            dialog_id = f"dlg_{uuid.uuid4().hex[:8]}"
            self._pending_dialogs[dialog_id] = dialog
            await self.broadcast_stream_message({
                "type": "dialog",
                "payload": {
                    "dialog_id": dialog_id,
                    "dialog_type": dialog.type,
                    "message": dialog.message,
                    "default_value": dialog.default_value,
                    "page_id": page_id,
                },
            })

        async def on_filechooser(chooser: FileChooser) -> None:
            fc_id = f"fc_{uuid.uuid4().hex[:8]}"
            self._pending_file_choosers[fc_id] = chooser
            await self.broadcast_stream_message({
                "type": "file_chooser",
                "payload": {
                    "chooser_id": fc_id,
                    "multiple": chooser.is_multiple,
                    "page_id": page_id,
                },
            })

        async def on_download(download: Download) -> None:
            suggested = download.suggested_filename
            await self.broadcast_stream_message({
                "type": "download_started",
                "payload": {
                    "filename": suggested,
                    "page_id": page_id,
                },
            })
            save_path = self.output_dir / "downloads" / suggested
            save_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                await download.save_as(str(save_path))
                await self.broadcast_stream_message({
                    "type": "download_completed",
                    "payload": {
                        "filename": suggested,
                        "path": str(save_path),
                        "page_id": page_id,
                    },
                })
            except Exception as exc:
                logger.debug("Download error: %s", exc)

        page.on("dialog", lambda d: asyncio.create_task(on_dialog(d)))
        page.on("filechooser", lambda fc: asyncio.create_task(on_filechooser(fc)))
        page.on("download", lambda dl: asyncio.create_task(on_download(dl)))

    async def switch_tab(self, page_id: int) -> None:
        """Switch active screencast stream and input focus to tab by page_id."""
        if page_id < 0 or page_id >= len(self._pages):
            return

        old_id = self.active_page_id
        if old_id in self._screencasts and old_id != page_id:
            old_sc = self._screencasts[old_id]
            for listener in self._frame_listeners:
                old_sc.remove_listener(listener)

        self.active_page_id = page_id
        new_page = self._pages[page_id]

        if page_id in self._screencasts:
            new_sc = self._screencasts[page_id]
            for listener in self._frame_listeners:
                new_sc.add_listener(listener)
            if not new_sc.is_active:
                with contextlib.suppress(Exception):
                    await new_sc.start()
            if new_sc.latest_frame:
                for listener in self._frame_listeners:
                    with contextlib.suppress(Exception):
                        await listener(new_sc.latest_frame)

        page_title = ""
        with contextlib.suppress(Exception):
            if not new_page.is_closed():
                page_title = await new_page.title()

        await self.broadcast_stream_message({
            "type": "tab_switched",
            "payload": {
                "page_id": page_id,
                "url": new_page.url if not new_page.is_closed() else "",
                "title": page_title,
            },
        })

    async def handle_input(self, event: InputEvent) -> None:
        """Forward interactive input from Studio canvas to the active browser page."""
        if self.active_page.is_closed():
            return
        bw, bh = self.viewport
        await dispatch_input_event(page=self.active_page, event=event, browser_viewport=(bw, bh))

    async def resize_viewport(self, width: int, height: int) -> None:
        """Adjust viewport geometry across active page and screencast managers."""
        w = max(320, min(width, 3840))
        h = max(240, min(height, 2160))
        self.viewport = (w, h)
        if not self.active_page.is_closed():
            await self.active_page.set_viewport_size({"width": w, "height": h})
        for sc in self._screencasts.values():
            sc.max_width = w
            sc.max_height = h

    async def navigate_to(self, target_url: str) -> None:
        """Navigate active page to URL."""
        url = target_url.strip()
        if not url.startswith("http://") and not url.startswith("https://") and not url.startswith("data:") and not url.startswith("about:"):
            url = f"https://{url}"
        await self.active_page.goto(url, wait_until="domcontentloaded")

    async def go_back(self) -> None:
        """Navigate back in active page history."""
        with contextlib.suppress(Exception):
            await self.active_page.go_back(wait_until="domcontentloaded")

    async def go_forward(self) -> None:
        """Navigate forward in active page history."""
        with contextlib.suppress(Exception):
            await self.active_page.go_forward(wait_until="domcontentloaded")

    async def reload_page(self) -> None:
        """Reload active page."""
        with contextlib.suppress(Exception):
            await self.active_page.reload(wait_until="domcontentloaded")

    async def handle_dialog_response(
        self, dialog_id: str, accept: bool, prompt_text: str | None = None
    ) -> None:
        """Respond to a pending JavaScript dialog (alert, confirm, prompt)."""
        dialog = self._pending_dialogs.pop(dialog_id, None)
        if not dialog:
            return
        try:
            if accept:
                await dialog.accept(prompt_text=prompt_text)
            else:
                await dialog.dismiss()
        except Exception as exc:
            logger.debug("Error responding to dialog %s: %s", dialog_id, exc)

    async def handle_file_chooser_response(self, chooser_id: str, files: list[str]) -> None:
        """Supply selected files to a pending browser file chooser."""
        chooser = self._pending_file_choosers.pop(chooser_id, None)
        if not chooser:
            return
        try:
            await chooser.set_files(files)
        except Exception as exc:
            logger.debug("Error setting files for chooser %s: %s", chooser_id, exc)

    async def get_info(self) -> StreamSessionInfo:
        """Retrieve public streaming telemetry for WebSocket metadata."""
        current_url = ""
        with contextlib.suppress(Exception):
            if not self.active_page.is_closed():
                current_url = self.active_page.url

        frames = self.screencast.frames_captured if self.screencast else 0
        total_bytes = self.screencast.total_bytes if self.screencast else 0
        last_frame = self.screencast.last_frame_at if self.screencast else None

        return StreamSessionInfo(
            session_id=self.session_id,
            state=StreamSessionState.ACTIVE
            if self.is_recording
            else (StreamSessionState.PAUSED if self.is_paused else StreamSessionState.INITIALIZING),
            url=current_url or self.start_url,
            browser=self.browser_type,
            headless=self.headless,
            viewport_width=self.viewport[0],
            viewport_height=self.viewport[1],
            started_at=self.start_time or datetime.now(),
            last_frame_at=last_frame,
            frames_sent=frames,
            total_bytes_streamed=total_bytes,
            owner_id=self.owner_id,
        )

    async def close(self) -> None:
        """Gracefully stop screencast, export recording if steps exist, and close browser."""
        self.state = StreamSessionState.STOPPED
        await self.stop_recording()

    def _prepare_output_dir(self) -> None:
        """Create output directories."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Console and Network Event Handlers
    # -------------------------------------------------------------------------

    def _on_console_message(self, message: ConsoleMessage) -> None:
        """Handle console message event."""
        if not self.is_recording or self.is_paused:
            return

        # Map playwright message types to our levels
        level_map: dict[str, ConsoleLogLevel] = {
            "log": "log",
            "info": "info",
            "warning": "warn",
            "error": "error",
            "debug": "debug",
            "trace": "trace",
        }

        level: ConsoleLogLevel = level_map.get(message.type, "log")

        log_entry = ConsoleLog(
            level=level,
            message=message.text,
            timestamp=datetime.now(),
            source=message.location.get("url") if message.location else None,
            args=[str(arg) for arg in message.args[:5]],  # Limit args
        )

        self.console_logs.append(log_entry)
        self._step_console_logs.append(log_entry)

        # Log to terminal based on level
        if level == "error":
            console.print(f"    [red]Console Error:[/red] {message.text[:80]}")
        elif level == "warn":
            console.print(f"    [yellow]Console Warn:[/yellow] {message.text[:80]}")

    def _on_page_error(self, error: Exception) -> None:
        """Handle page JavaScript error."""
        if not self.is_recording or self.is_paused:
            return

        page_error = PageError(
            message=str(error),
            stack=getattr(error, "stack", None),
            timestamp=datetime.now(),
        )

        self.page_errors.append(page_error)
        console.print(f"    [red]JS Error:[/red] {str(error)[:80]}")

    def _on_request(self, request: Request) -> None:
        """Handle network request start."""
        if not self.is_recording or self.is_paused:
            return

        # Skip data URLs and internal requests
        url = request.url
        if url.startswith("data:") or "__tracecase" in url:
            return

        # Get request body for POST/PUT/PATCH
        request_body: str | None = None
        if request.method in ("POST", "PUT", "PATCH"):
            with contextlib.suppress(Exception):
                request_body = request.post_data

        # Create network request entry
        net_request = NetworkRequest(
            method=request.method,
            url=url,
            resource_type=request.resource_type,
            timestamp=datetime.now(),
            request_headers=dict(request.headers),
            request_body=request_body,
        )

        # Store pending request to match with response
        self._pending_requests[url] = (net_request, request)

    def _on_response(self, response: Response) -> None:
        """Handle network response."""
        if not self.is_recording or self.is_paused:
            return

        url = response.url

        # Find matching request
        if url in self._pending_requests:
            net_request, original_request = self._pending_requests.pop(url)

            # Update with response data
            net_request.status = response.status
            net_request.response_headers = dict(response.headers)

            # Calculate timing
            timing = response.request.timing
            if timing and timing.get("responseEnd"):
                net_request.timing = timing.get("responseEnd", 0)

            # For XHR/fetch requests, try to capture response body
            if net_request.resource_type in ("xhr", "fetch"):
                # Schedule async body capture
                asyncio.create_task(self._capture_response_body(response, net_request))
            else:
                # Add to lists immediately for non-XHR requests
                self.network_requests.append(net_request)
                self._step_network_requests.append(net_request)

            # Log significant requests
            if response.status >= 400:
                console.print(
                    f"    [red]HTTP {response.status}:[/red] {net_request.method} {url[:60]}"
                )
            elif net_request.resource_type in ("xhr", "fetch"):
                console.print(
                    f"    [dim]API {response.status}:[/dim] {net_request.method} {url[:60]}"
                )

    async def _capture_response_body(self, response: Response, net_request: NetworkRequest) -> None:
        """Capture response body for XHR/fetch requests asynchronously."""
        try:
            # Try to get response body (limit to 50KB to avoid huge responses)
            body_bytes = await response.body()
            if len(body_bytes) <= 50 * 1024:  # 50KB limit
                try:
                    # Try to decode as text
                    body_text = body_bytes.decode("utf-8")
                    # Truncate if too long
                    if len(body_text) > 10000:
                        body_text = body_text[:10000] + "\n... (truncated)"
                    net_request.response_body = body_text
                except UnicodeDecodeError:
                    net_request.response_body = f"[Binary data, {len(body_bytes)} bytes]"
            else:
                net_request.response_body = f"[Large response, {len(body_bytes)} bytes]"
        except Exception as e:
            net_request.response_body = f"[Error capturing body: {e}]"
        finally:
            # Add to lists after body capture
            self.network_requests.append(net_request)
            self._step_network_requests.append(net_request)

    def _on_request_failed(self, request: Request) -> None:
        """Handle failed network request."""
        if not self.is_recording or self.is_paused:
            return

        url = request.url

        if url in self._pending_requests:
            net_request, _ = self._pending_requests.pop(url)
            net_request.error = request.failure or "Request failed"

            self.network_requests.append(net_request)
            self._step_network_requests.append(net_request)

            console.print(f"    [red]Request Failed:[/red] {net_request.method} {url[:60]}")

    # -------------------------------------------------------------------------
    # Page Navigation Handlers
    # -------------------------------------------------------------------------

    async def _on_page_load(self, _: Any) -> None:
        """Handle page load event."""
        if self._browser_manager and self._browser_manager._page:
            # Re-inject control panel and event listeners
            try:
                await self._browser_manager._page.evaluate(CONTROL_PANEL_JS)
                await self._browser_manager._page.evaluate(EVENT_LISTENER_JS)
                await update_panel_ui(
                    self._browser_manager._page,
                    self.is_recording,
                    len(self.steps),
                )
            except Exception:
                pass

    async def _on_dom_ready(self, _: Any) -> None:
        """Handle DOM content loaded event."""
        pass

    # -------------------------------------------------------------------------
    # Recording Control
    # -------------------------------------------------------------------------

    async def start_recording(self) -> None:
        """
        Start recording user actions.

        Called when user clicks the Start button in the control panel.
        """
        if self.is_recording:
            return

        self.is_recording = True
        self.is_paused = False
        self.start_time = datetime.now()
        self.steps = []
        self.console_logs = []
        self.network_requests = []
        self.page_errors = []

        console.print("\n[bold red]● Recording started[/bold red]")
        console.print("[dim]Perform your actions in the browser...[/dim]")
        console.print("[dim]Console logs and network requests are being captured.[/dim]\n")

        # Update UI
        if self._browser_manager and self._browser_manager._page:
            await update_panel_ui(
                self._browser_manager._page,
                is_recording=True,
                steps_count=0,
            )

    async def pause_recording(self) -> None:
        """Pause recording user actions."""
        if not self.is_recording or self.is_paused:
            return
        self.is_paused = True
        console.print("[yellow]❚❚ Recording paused[/yellow]")
        if self._browser_manager and self._browser_manager._page:
            with contextlib.suppress(Exception):
                await update_panel_ui(
                    self._browser_manager._page,
                    is_recording=True,
                    steps_count=len(self.steps),
                    message="Paused",
                )

    async def resume_recording(self) -> None:
        """Resume recording user actions."""
        if not self.is_recording or not self.is_paused:
            return
        self.is_paused = False
        console.print("[green]▶ Recording resumed[/green]")
        if self._browser_manager and self._browser_manager._page:
            with contextlib.suppress(Exception):
                await update_panel_ui(
                    self._browser_manager._page,
                    is_recording=True,
                    steps_count=len(self.steps),
                    message="Recording...",
                )

    async def stop_recording(self) -> None:
        """
        Stop recording and save results.

        Called when user clicks the Stop button in the control panel.
        """
        if not self.is_recording:
            # If not recording, just close
            self._recording_complete.set()
            return

        self.is_recording = False
        self.end_time = datetime.now()

        console.print("\n[bold green]■ Recording stopped[/bold green]")
        console.print(f"[dim]Recorded {len(self.steps)} steps[/dim]")
        console.print(f"[dim]Captured {len(self.console_logs)} console logs[/dim]")
        console.print(f"[dim]Captured {len(self.network_requests)} network requests[/dim]")

        # Update UI (headed mode only)
        if not self.embedded and self._browser_manager and self._browser_manager._page:
            await update_panel_ui(
                self._browser_manager._page,
                is_recording=False,
                steps_count=len(self.steps),
                message="Saving...",
            )

        # Export test case
        await self._export_testcase()

        # Update UI with completion message (headed mode only)
        if not self.embedded and self._browser_manager and self._browser_manager._page:
            await update_panel_ui(
                self._browser_manager._page,
                is_recording=False,
                steps_count=len(self.steps),
                message="✓ Saved!",
            )

            # Wait a bit before closing
            await asyncio.sleep(2)

        # Signal completion
        self._recording_complete.set()

    # -------------------------------------------------------------------------
    # Action Handling
    # -------------------------------------------------------------------------

    async def on_action(self, data: dict[str, Any], page_id: int = 0) -> None:
        """
        Handle an action event from the browser.

        Called by the injected JavaScript when user performs an action.

        Args:
            data: Action data from JavaScript
            page_id: 0-based index of the tab/page
        """
        if not self.is_recording or self.is_paused:
            return

        event_type = data.get("eventType", "")

        # Map event types to action types
        action_map: dict[str, ActionType] = {
            "click": "click",
            "dblclick": "dblclick",
            "input": "input",
            "select": "select",
            "check": "check",
            "uncheck": "uncheck",
            "keypress": "keypress",
        }

        action_type = action_map.get(event_type)
        if not action_type:
            return

        # Parse element info
        element_data = parse_element_info(data)

        # Create ElementInfo
        try:
            element = ElementInfo(
                selector=element_data["selector"],
                xpath=element_data.get("xpath"),
                tag_name=element_data["tag_name"],
                text=element_data.get("text"),
                placeholder=element_data.get("placeholder"),
                attributes=element_data.get("attributes", {}),
                bounding_box=element_data.get(
                    "bounding_box", {"x": 0, "y": 0, "width": 0, "height": 0}
                ),
            )
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to parse element: {e}[/yellow]")
            return

        # Generate step number
        step_number = len(self.steps) + 1

        # Generate descriptions
        description_short = self._generate_short_description(action_type, element, data)
        description_detailed = self._generate_detailed_description(action_type, element, data)

        # Determine target page for screenshot
        target_page: Page | None = None
        if page_id < len(self._pages):
            target_page = self._pages[page_id]
        elif self._browser_manager and self._browser_manager._page:
            target_page = self._browser_manager._page

        # Take screenshot
        screenshot_path: Path | None = None
        if target_page is not None:
            try:
                filename = generate_screenshot_filename(
                    step_number,
                    action_type,
                    element.attributes.get("id") or element.tag_name,
                )
                full_path = self.screenshots_dir / filename
                await take_screenshot(
                    target_page,
                    full_path,
                    highlight_selector=element.selector,
                )
                screenshot_path = Path("screenshots") / filename
            except Exception as e:
                console.print(f"[yellow]Warning: Screenshot failed: {e}[/yellow]")

        # Collect console logs and network requests for this step
        step_logs = self._step_console_logs.copy()
        step_requests = self._step_network_requests.copy()
        self._step_console_logs.clear()
        self._step_network_requests.clear()

        # Mask password input values to prevent credential leakage
        step_input_value = data.get("value")
        if (element.attributes.get("type") or "").lower() == "password" and step_input_value:
            step_input_value = "*" * len(step_input_value)

        # Create step
        step = Step(
            number=step_number,
            timestamp=datetime.now(),
            action_type=action_type,
            element=element,
            input_value=step_input_value,
            key=data.get("key"),
            page_id=page_id,
            screenshot_path=screenshot_path,
            network_requests=step_requests,
            console_logs=step_logs,
            description_short=description_short,
            description_detailed=description_detailed,
        )

        self.steps.append(step)

        if self.step_callback:
            try:
                cb_res = self.step_callback(step)
                if asyncio.iscoroutine(cb_res):
                    asyncio.create_task(cb_res)
            except Exception:
                pass

        # Log the action
        console.print(f"  [dim]{step_number}.[/dim] {description_short}")

        # Update UI
        if self._browser_manager and self._browser_manager._page:
            await update_panel_ui(
                self._browser_manager._page,
                is_recording=True,
                steps_count=len(self.steps),
            )

    # -------------------------------------------------------------------------
    # Description Generation
    # -------------------------------------------------------------------------

    def _generate_short_description(
        self,
        action_type: ActionType,
        element: ElementInfo,
        data: dict[str, Any],
    ) -> str:
        """Generate a short description for the step."""
        tag = element.tag_name
        text = element.text[:30] if element.text else None
        el_id = element.attributes.get("id")
        placeholder = element.placeholder

        identifier = text or el_id or placeholder or tag

        if action_type == "click":
            return f"Click on '{identifier}'"
        elif action_type == "dblclick":
            return f"Double-click on '{identifier}'"
        elif action_type == "input":
            value = data.get("value", "")
            if (element.attributes.get("type") or "").lower() == "password" and value:
                value = "*" * len(value)
            if len(value) > 20:
                return f"Type '{value[:20]}...' in {identifier}"
            return f"Type '{value}' in {identifier}"
        elif action_type == "select":
            selected = data.get("selectedText", data.get("value", ""))
            return f"Select '{selected}' in {identifier}"
        elif action_type == "check":
            return f"Check {identifier}"
        elif action_type == "uncheck":
            return f"Uncheck {identifier}"
        elif action_type == "keypress":
            key = data.get("key", "")
            return f"Press {key}"
        else:
            return f"{action_type} on {identifier}"

    def _generate_detailed_description(
        self,
        action_type: ActionType,
        element: ElementInfo,
        data: dict[str, Any],
    ) -> str:
        """Generate a detailed description for the step."""
        short = self._generate_short_description(action_type, element, data)
        selector = element.selector

        return f"{short}\nElement: {selector}"

    # -------------------------------------------------------------------------
    # Export
    # -------------------------------------------------------------------------

    async def _export_testcase(self) -> None:
        """Export the recorded test case to all formats."""
        if not self.steps:
            console.print("[yellow]No steps recorded. Nothing to export.[/yellow]")
            return

        # Calculate duration
        duration = 0.0
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()

        # Get user agent
        user_agent = "Unknown"
        if self._browser_manager:
            user_agent = self._browser_manager.browser_type

        # Create TestCase
        testcase = TestCase(
            id=f"tc_{uuid.uuid4().hex[:8]}",
            name=self.name,
            created_at=self.start_time or datetime.now(),
            start_url=self.start_url,
            browser=self.browser_type,
            viewport={"width": self.viewport[0], "height": self.viewport[1]},
            user_agent=user_agent,
            steps=self.steps,
            console_logs=self.console_logs,
            network_requests=self.network_requests,
            page_errors=self.page_errors,
            total_duration=duration,
            total_steps=len(self.steps),
        )

        # Export to all formats
        console.print("\n[bold]Exporting test case...[/bold]")

        # JSON
        json_exporter = JSONExporter()
        json_path = json_exporter.export(testcase, self.output_dir)
        console.print(f"  [green]✓[/green] JSON: {json_path}")

        # Markdown
        md_exporter = MarkdownExporter()
        md_path = md_exporter.export(testcase, self.output_dir)
        console.print(f"  [green]✓[/green] Markdown: {md_path}")

        # HTML
        html_exporter = HTMLExporter()
        html_path = html_exporter.export(testcase, self.output_dir)
        console.print(f"  [green]✓[/green] HTML: {html_path}")

        console.print(f"\n[bold green]✓ Test case saved to {self.output_dir}[/bold green]")
