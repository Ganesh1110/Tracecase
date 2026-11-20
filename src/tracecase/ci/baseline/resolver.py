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

    def _check_environment_parity(
        self,
        snapshot: BaselineSnapshot,
        expected_env: dict[str, Any] | None,
    ) -> tuple[bool, str]:
        """Verify environment compatibility between requested CI run and snapshot."""
        if not expected_env or not snapshot.environment:
            return True, ""

        # Check browser major version parity if specified
        if "browser_version" in expected_env and "browser_version" in snapshot.environment:
            exp_ver = str(expected_env["browser_version"]).split(".")[0]
            snap_ver = str(snapshot.environment["browser_version"]).split(".")[0]
            if exp_ver != snap_ver:
                return (
                    False,
                    f"Browser major version mismatch: baseline used {snap_ver}, current run uses {exp_ver}.",
                )

        # Check OS platform parity if strict platform checking enabled
        if expected_env.get("require_same_os"):
            exp_os = expected_env.get("os")
            snap_os = snapshot.environment.get("os")
            if exp_os and snap_os and exp_os != snap_os:
                return (
                    False,
                    f"OS platform mismatch: baseline ran on {snap_os}, current run is on {exp_os}.",
                )

        return True, ""

    def _is_git_ancestor(
        self,
        repo_path: Path | str,
        ancestor_sha: str,
        descendant_ref: str,
    ) -> bool:
        """Check whether ancestor_sha is a git ancestor of descendant_ref."""
        import subprocess

        try:
            res = subprocess.run(
                ["git", "merge-base", "--is-ancestor", ancestor_sha, descendant_ref],
                cwd=str(repo_path),
                capture_output=True,
                check=False,
            )
            return res.returncode == 0
        except Exception as exc:
            logger.warning("Failed to evaluate git merge-base ancestry: %s", exc)
            return True

    def resolve(
        self,
        project_id: str,
        base_ref: str | None = None,
        base_commit: str | None = None,
        browser: str = "chromium",
        require_exact_commit: bool = False,
        repo_path: Path | str | None = None,
        environment: dict[str, Any] | None = None,
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
                # Incomplete baseline execution check
                if snap.status in ("cancelled", "crashed", "aborted") or snap.total_tests == 0:
                    return BaselineResolutionResult(
                        status=BaselineMatchStatus.NOT_FOUND,
                        snapshot=None,
                        reason=f"Baseline snapshot for commit {base_commit[:8]} was incomplete (status: {snap.status}).",
                    )

                # Environment parity check
                env_ok, env_msg = self._check_environment_parity(snap, environment)
                if not env_ok:
                    return BaselineResolutionResult(
                        status=BaselineMatchStatus.INCOMPATIBLE_ENVIRONMENT,
                        snapshot=snap,
                        reason=env_msg,
                    )

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
                # Incomplete execution check
                if snap.status in ("cancelled", "crashed", "aborted") or snap.total_tests == 0:
                    return BaselineResolutionResult(
                        status=BaselineMatchStatus.NOT_FOUND,
                        snapshot=None,
                        reason=f"Branch snapshot from '{base_ref}' was incomplete (status: {snap.status}).",
                    )

                # Ancestry validation: verify candidate snapshot is ancestor of target/base
                target_ancestor_ref = base_commit or base_ref
                if repo_path and target_ancestor_ref:
                    is_ancestor = self._is_git_ancestor(
                        repo_path=repo_path,
                        ancestor_sha=snap.commit_hash,
                        descendant_ref=target_ancestor_ref,
                    )
                    if not is_ancestor:
                        return BaselineResolutionResult(
                            status=BaselineMatchStatus.NOT_FOUND,
                            snapshot=None,
                            reason=(
                                f"Branch snapshot commit {snap.commit_hash[:8]} from '{base_ref}' "
                                f"is not an ancestor of '{target_ancestor_ref}'."
                            ),
                        )

                # Environment parity check
                env_ok, env_msg = self._check_environment_parity(snap, environment)
                if not env_ok:
                    return BaselineResolutionResult(
                        status=BaselineMatchStatus.INCOMPATIBLE_ENVIRONMENT,
                        snapshot=snap,
                        reason=env_msg,
                    )

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
