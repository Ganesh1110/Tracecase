"""Domain models for Git Change Intelligence (Phase 7.5.1)."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

ChangeType = Literal["added", "modified", "deleted", "renamed"]


class DiffHunk(BaseModel):
    """A contiguous hunk of lines modified in a unified diff."""
    old_start: int = 0
    old_lines: int = 0
    new_start: int = 0
    new_lines: int = 0
    heading: str = ""
    lines: list[str] = Field(default_factory=list)


class ChangedFile(BaseModel):
    """Detailed change metrics and extracted semantic entities for a single file."""
    path: str
    old_path: str | None = None
    change_type: ChangeType = "modified"
    additions: int = 0
    deletions: int = 0
    hunks: list[DiffHunk] = Field(default_factory=list)
    changed_functions: list[str] = Field(default_factory=list)
    changed_classes: list[str] = Field(default_factory=list)
    changed_selectors: list[str] = Field(default_factory=list)
    changed_routes: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class GitChangeSummary(BaseModel):
    """High-level summary of code modifications across the entire changeset."""
    total_files_changed: int = 0
    total_additions: int = 0
    total_deletions: int = 0
    files_by_type: dict[str, int] = Field(default_factory=dict)
    total_changed_routes: list[str] = Field(default_factory=list)
    total_changed_selectors: list[str] = Field(default_factory=list)
    total_changed_symbols: list[str] = Field(default_factory=list)


class GitChangeSet(BaseModel):
    """Complete collection of code changes, diff hunks, and extracted semantic impact."""
    repo_path: str
    base_ref: str | None = None
    target_ref: str | None = None
    current_commit: str | None = None
    current_branch: str | None = None
    is_dirty: bool = False
    files: list[ChangedFile] = Field(default_factory=list)
    summary: GitChangeSummary = Field(default_factory=GitChangeSummary)
