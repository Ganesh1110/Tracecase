"""Autonomous exploration controller and background lifecycle orchestrator."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from qa_auto.exploration.models import (
    AppNavigationGraph,
    ExplorationConfig,
)
from qa_auto.exploration.worker import ExplorationWorker
from qa_auto.ui.db import (
    create_exploration_run,
    delete_exploration_run,
    get_exploration_graph,
    get_exploration_run,
    list_exploration_runs,
    save_exploration_page,
    save_exploration_transition,
    update_exploration_run_status,
)

logger = logging.getLogger("qa_auto.exploration.controller")


class ExplorationController:
    """Manages background exploration tasks, life cycle, and event broadcasting."""

    def __init__(self) -> None:
        self.active_tasks: dict[str, asyncio.Task[Any]] = {}
        self.active_workers: dict[str, ExplorationWorker] = {}
        self.cancel_events: dict[str, asyncio.Event] = {}

    async def start_exploration(
        self,
        config: ExplorationConfig,
        db_path: Path | str | None = None,
    ) -> dict[str, Any]:
        """Start a new background autonomous exploration run."""
        exploration_id = f"exp_{uuid.uuid4().hex[:8]}"

        # Initialize database run record
        run_record = create_exploration_run(
            exploration_id=exploration_id,
            project_id=config.project_id,
            start_url=config.start_url,
            config=config.model_dump(mode="json"),
            db_path=db_path,
        )

        cancel_ev = asyncio.Event()
        self.cancel_events[exploration_id] = cancel_ev

        # Spawn asynchronous background task
        task = asyncio.create_task(
            self._run_worker(
                exploration_id=exploration_id,
                config=config,
                cancel_event=cancel_ev,
                db_path=db_path,
            )
        )
        self.active_tasks[exploration_id] = task

        return run_record

    async def _run_worker(
        self,
        exploration_id: str,
        config: ExplorationConfig,
        cancel_event: asyncio.Event,
        db_path: Path | str | None = None,
    ) -> None:
        """Internal worker runner hook that handles persistence and broadcasting."""
        pages_count = 0
        trans_count = 0
        forms_count = 0
        from qa_auto.ui.broadcaster import broadcast_exploration_event

        async def _event_handler(event_type: str, data: dict[str, Any]) -> None:
            nonlocal pages_count, trans_count, forms_count
            try:
                if event_type == "page_discovered":
                    pages_count += 1
                    forms_count += data.get("forms_count", 0)
                    # We can fetch node or store directly if full dict is provided
                    update_exploration_run_status(
                        exploration_id=exploration_id,
                        status="running",
                        pages_discovered=pages_count,
                        forms_discovered=forms_count,
                        db_path=db_path,
                    )
                elif event_type == "transition_discovered":
                    trans_count += 1
                    save_exploration_transition(exploration_id, data, db_path=db_path)
                    update_exploration_run_status(
                        exploration_id=exploration_id,
                        status="running",
                        transitions_discovered=trans_count,
                        db_path=db_path,
                    )

                # Broadcast live event to WebSocket clients
                await broadcast_exploration_event(exploration_id, event_type, data)
            except Exception as handler_err:
                logger.debug("Error in exploration event handler: %s", handler_err)

        worker = ExplorationWorker(
            exploration_id=exploration_id,
            config=config,
            on_event=_event_handler,
            cancel_event=cancel_event,
        )
        self.active_workers[exploration_id] = worker

        try:
            graph = await worker.run()

            # Save all page nodes into database
            for node_url, node in graph.nodes.items():
                save_exploration_page(
                    exploration_id=exploration_id,
                    page_data=node.model_dump(mode="json"),
                    db_path=db_path,
                )

            final_status = "cancelled" if cancel_event.is_set() else "completed"
            update_exploration_run_status(
                exploration_id=exploration_id,
                status=final_status,
                pages_discovered=len(graph.nodes),
                transitions_discovered=len(graph.transitions),
                forms_discovered=graph.total_forms,
                finished_at=datetime.now().isoformat(),
                db_path=db_path,
            )

        except Exception as exc:
            logger.exception("Exploration %s failed with exception: %s", exploration_id, exc)
            update_exploration_run_status(
                exploration_id=exploration_id,
                status="failed",
                error_message=str(exc),
                finished_at=datetime.now().isoformat(),
                db_path=db_path,
            )
            await broadcast_exploration_event(
                exploration_id, "exploration_failed", {"error": str(exc)}
            )
        finally:
            self.active_tasks.pop(exploration_id, None)
            self.active_workers.pop(exploration_id, None)
            self.cancel_events.pop(exploration_id, None)

    async def cancel_exploration(
        self, exploration_id: str, db_path: Path | str | None = None
    ) -> bool:
        """Cancel an in-progress exploration job."""
        cancel_ev = self.cancel_events.get(exploration_id)
        task = self.active_tasks.get(exploration_id)

        cancelled = False
        if cancel_ev:
            cancel_ev.set()
            cancelled = True

        if task and not task.done():
            task.cancel()
            cancelled = True

        run = get_exploration_run(exploration_id, db_path=db_path)
        if run and run.get("status") == "running":
            cancelled = True

        if cancelled:
            update_exploration_run_status(
                exploration_id=exploration_id,
                status="cancelled",
                finished_at=datetime.now().isoformat(),
                error_message="Exploration cancelled by user.",
                db_path=db_path,
            )
            from qa_auto.ui.broadcaster import broadcast_exploration_event
            await broadcast_exploration_event(
                exploration_id, "exploration_cancelled", {"status": "cancelled"}
            )
            return True
        return False

    def list_runs(
        self, project_id: str | None = None, db_path: Path | str | None = None
    ) -> list[dict[str, Any]]:
        """List past and current exploration runs."""
        return list_exploration_runs(project_id=project_id, db_path=db_path)

    def get_run(
        self, exploration_id: str, db_path: Path | str | None = None
    ) -> dict[str, Any] | None:
        """Get details of an exploration run."""
        return get_exploration_run(exploration_id=exploration_id, db_path=db_path)

    def get_graph(
        self, exploration_id: str, db_path: Path | str | None = None
    ) -> dict[str, Any]:
        """Get the full navigation graph for an exploration run."""
        return get_exploration_graph(exploration_id=exploration_id, db_path=db_path)

    def delete_run(
        self, exploration_id: str, db_path: Path | str | None = None
    ) -> bool:
        """Delete an exploration run and its graph data."""
        return delete_exploration_run(exploration_id=exploration_id, db_path=db_path)


# Global controller instance
exploration_controller = ExplorationController()
