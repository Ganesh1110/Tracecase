"""Baseline Executor providing isolated worktree execution against base commits."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any
import uuid

from tracecase.ci.baseline.manager import BaselineManager
from tracecase.ci.baseline.models import (
    BaselineSnapshot,
    BaselineTestOutcome,
    compute_test_revision_hash,
)
from tracecase.models import TestCase
from tracecase.ui.db import get_execution_batch
from tracecase.ui.executor import ExecutionOrchestrator
from tracecase.ui.service import find_testcase_files, resolve_testcase_file

logger = logging.getLogger("tracecase.ci.baseline.executor")


class BaselineExecutor:
    """Executes test suites against base commits inside isolated git worktrees."""

    def __init__(
        self,
        manager: BaselineManager,
        orchestrator: ExecutionOrchestrator | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        self.manager = manager
        self._orchestrator = orchestrator
        self.db_path = db_path

    async def execute_baseline_in_worktree(
        self,
        repo_path: Path | str,
        base_commit: str,
        project_id: str = "default_project",
        branch: str | None = None,
        browser: str = "chromium",
        concurrency: int = 2,
        retries: int = 1,
        testcase_ids: list[str] | None = None,
    ) -> BaselineSnapshot:
        """Checkout base_commit in an isolated git worktree, execute tests, and persist snapshot."""
        repo_p = Path(repo_path).resolve()
        worktree_dir = Path(tempfile.mkdtemp(prefix="tc_base_worktree_"))

        try:
            # 1. Create isolated git worktree
            logger.info("Creating isolated git worktree at %s for base %s", worktree_dir, base_commit)
            add_res = subprocess.run(
                ["git", "worktree", "add", "--detach", str(worktree_dir), base_commit],
                cwd=str(repo_p),
                capture_output=True,
                text=True,
                check=False,
            )
            if add_res.returncode != 0:
                raise RuntimeError(
                    f"Failed to create git worktree for baseline {base_commit}: {add_res.stderr.strip()}"
                )

            # 2. Discover test cases in the base worktree
            tc_files = find_testcase_files([worktree_dir])
            base_testcases: list[TestCase] = []
            for f in tc_files:
                try:
                    _, tc = resolve_testcase_file(str(f))
                    if testcase_ids is None or tc.id in testcase_ids:
                        base_testcases.append(tc)
                except Exception:
                    pass

            target_ids = [tc.id for tc in base_testcases]
            if not target_ids:
                logger.warning("No test cases found in base worktree %s", base_commit)
                return BaselineSnapshot(
                    id=f"base_{base_commit[:8]}_{browser}",
                    project_id=project_id,
                    commit_hash=base_commit,
                    branch=branch,
                    browser=browser,
                    total_tests=0,
                )

            # 3. Execute via Orchestrator
            orchestrator = self._orchestrator or ExecutionOrchestrator()
            shutdown_browser = self._orchestrator is None

            batch = await orchestrator.start_batch_execution(
                testcase_ids=target_ids,
                concurrency=concurrency,
                project_id=project_id,
                browser=browser,
                retries=retries,
            )
            batch_id = batch.get("id")
            task = orchestrator.active_tasks.get(batch_id)
            if task:
                await task

            if shutdown_browser:
                try:
                    await orchestrator.browser_pool.shutdown()
                except Exception:
                    pass

            batch_rec = get_execution_batch(batch_id, db_path=self.db_path)
            runs = list(batch_rec.get("runs") or []) if batch_rec else []

            # 4. Map outcomes & compute revision hashes
            tc_map = {tc.id: tc for tc in base_testcases}
            outcomes: dict[str, BaselineTestOutcome] = {}
            passed_cnt = 0
            failed_cnt = 0
            flaky_cnt = 0
            error_cnt = 0

            for r in runs:
                tid = r.get("testcase_id", "")
                st = r.get("status", "unknown")
                if st == "passed":
                    passed_cnt += 1
                elif st == "failed":
                    failed_cnt += 1
                elif st == "flaky":
                    flaky_cnt += 1
                elif st == "error":
                    error_cnt += 1

                tc_obj = tc_map.get(tid)
                rev_hash = compute_test_revision_hash(tc_obj) if tc_obj else ""

                outcomes[tid] = BaselineTestOutcome(
                    testcase_id=tid,
                    testcase_name=r.get("testcase_name") or tid,
                    status=st,
                    duration_ms=float(r.get("duration_ms") or 0.0),
                    error_message=r.get("error_message"),
                    retry_count=len(r.get("retry_history") or []),
                    test_revision_hash=rev_hash,
                    run_id=r.get("id"),
                )

            snapshot = BaselineSnapshot(
                id=f"base_{base_commit[:8]}_{browser}",
                project_id=project_id,
                commit_hash=base_commit,
                branch=branch,
                browser=browser,
                total_tests=len(outcomes),
                passed_count=passed_cnt,
                failed_count=failed_cnt,
                flaky_count=flaky_cnt,
                error_count=error_cnt,
                outcomes=outcomes,
            )

            # 5. Persist baseline snapshot
            self.manager.save_snapshot(snapshot)
            return snapshot

        finally:
            # Always clean up isolated worktree
            logger.info("Cleaning up worktree at %s", worktree_dir)
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_dir)],
                cwd=str(repo_p),
                capture_output=True,
                check=False,
            )
            subprocess.run(["git", "worktree", "prune"], cwd=str(repo_p), capture_output=True, check=False)
            if worktree_dir.exists():
                shutil.rmtree(worktree_dir, ignore_errors=True)
