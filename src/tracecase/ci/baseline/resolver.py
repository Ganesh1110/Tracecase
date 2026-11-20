"""Baseline Resolver responsible for discovering and validating baseline snapshots."""

from __future__ import annotations

from enum import StrEnum
import logging
from pathlib import Path
from typing import Any

from tracecase.ci.baseline.manager import BaselineManager
from tracecase.ci.baseline.models import BaselineSnapshot

logger = logging.getLogger("tracecase.ci.baseline.resolver")


class BaselineMatchStatus(StrEnum):
    """Status indicating how closely the resolved baseline matches the requested base."""
    FOUND_EXACT_COMMIT = "found_exact_commit"
    FOUND_BRANCH_SNAPSHOT = "found_branch_snapshot"
    NOT_FOUND = "not_found"
    INCOMPATIBLE_ENVIRONMENT = "incompatible_environment"


class BaselineResolutionResult:
    """Outcome of resolving a baseline snapshot for a CI run."""

    def __init__(
        self,
        status: BaselineMatchStatus,
        snapshot: BaselineSnapshot | None = None,
        reason: str = "",
    ) -> None:
        self.status = status
        self.snapshot = snapshot
        self.reason = reason

    @property
    def is_valid(self) -> bool:
        """Whether a usable baseline snapshot was resolved."""
        return self.status in (
            BaselineMatchStatus.FOUND_EXACT_COMMIT,
            BaselineMatchStatus.FOUND_BRANCH_SNAPSHOT,
        ) and self.snapshot is not None


class BaselineResolver:
    """Resolves and validates baseline execution snapshots for base refs."""

    def __init__(self, manager: BaselineManager) -> None:
        self.manager = manager

    def resolve(
        self,
        project_id: str,
        base_ref: str | None = None,
        base_commit: str | None = None,
        browser: str = "chromium",
        require_exact_commit: bool = False,
    ) -> BaselineResolutionResult:
        """Resolve the best matching baseline snapshot for the base reference."""
        # 1. Check exact base commit SHA if provided
        if base_commit:
            snap = self.manager.get_snapshot_by_commit(
                project_id=project_id,
                commit_hash=base_commit,
                browser=browser,
            )
            if snap:
                return BaselineResolutionResult(
                    status=BaselineMatchStatus.FOUND_EXACT_COMMIT,
                    snapshot=snap,
                    reason=f"Found verified baseline snapshot for exact base commit {base_commit[:8]}.",
                )

        if require_exact_commit:
            return BaselineResolutionResult(
                status=BaselineMatchStatus.NOT_FOUND,
                snapshot=None,
                reason=f"No baseline snapshot found for exact commit {base_commit or 'unknown'}.",
            )

        # 2. Check latest snapshot for base branch
        if base_ref:
            snap = self.manager.get_latest_branch_snapshot(
                project_id=project_id,
                branch=base_ref,
                browser=browser,
            )
            if snap:
                return BaselineResolutionResult(
                    status=BaselineMatchStatus.FOUND_BRANCH_SNAPSHOT,
                    snapshot=snap,
                    reason=(
                        f"Found baseline snapshot from branch '{base_ref}' recorded at "
                        f"commit {snap.commit_hash[:8]}."
                    ),
                )

        return BaselineResolutionResult(
            status=BaselineMatchStatus.NOT_FOUND,
            snapshot=None,
            reason=f"No baseline snapshot found for base ref '{base_ref or base_commit or 'unknown'}'.",
        )
