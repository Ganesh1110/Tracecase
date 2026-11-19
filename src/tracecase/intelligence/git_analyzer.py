"""Git Change Intelligence Analyzer for Tracecase (Phase 7.5.1).

Parses unified git diffs and inspects repository state to extract:
1. Changed files and lines (added, modified, deleted, renamed).
2. Changed DOM selectors (IDs, classes, data-testids, CSS rules, locator strings).
3. Changed application routes and API endpoints (FastAPI, Flask, Express, React Router, Next.js).
4. Changed functions, classes, and component symbols.
5. Changed dependencies and import declarations.
"""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from tracecase.intelligence.models import (
    ChangedFile,
    ChangeType,
    DiffHunk,
    GitChangeSet,
    GitChangeSummary,
)

logger = logging.getLogger(__name__)

# Regular expressions for semantic entity extraction
RE_SELECTOR_ATTRIBUTES = [
    re.compile(r"""data-test(?:id)?=["']([^"']+)["']""", re.IGNORECASE),
    re.compile(r"""id=["']([^"']+)["']""", re.IGNORECASE),
    re.compile(r"""class(?:Name)?=["']([^"']+)["']""", re.IGNORECASE),
    re.compile(r"""name=["']([^"']+)["']""", re.IGNORECASE),
    re.compile(r"""(?:locator|querySelector|findByTestId|\$)\s*\(\s*["']([^"']+)["']""", re.IGNORECASE),
]

RE_ROUTE_PATTERNS = [
    # Python FastAPI / Flask
    re.compile(r"""@(?:app|router|api|blueprint)\.(?:get|post|put|delete|patch|route)\s*\(\s*["']([^"']+)["']""", re.IGNORECASE),
    # Express / Node
    re.compile(r"""(?:app|router)\.(?:get|post|put|delete|patch|use)\s*\(\s*["']([^"']+)["']""", re.IGNORECASE),
    # React Router / Next.js
    re.compile(r"""path:\s*["']([^"']+)["']""", re.IGNORECASE),
    re.compile(r"""<Route\s+[^>]*path=["']([^"']+)["']""", re.IGNORECASE),
    # HTML link / API fetch
    re.compile(r"""<a\s+[^>]*href=["'](/[^"']*)["']""", re.IGNORECASE),
    re.compile(r"""(?:fetch|axios\.(?:get|post|put|delete)|api\.(?:get|post|put|delete))\s*\(\s*["'](/[^"']*)["']""", re.IGNORECASE),
]

RE_JS_SYMBOLS = [
    re.compile(r"""(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z0-9_$]+)"""),
    re.compile(r"""(?:export\s+)?(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"""),
    re.compile(r"""(?:export\s+default\s+)?class\s+([a-zA-Z0-9_$]+)"""),
]

RE_IMPORT_PATTERNS = [
    re.compile(r"""import\s+.*?from\s+["']([^"']+)["']"""),
    re.compile(r"""require\s*\(\s*["']([^"']+)["']\s*\)"""),
    re.compile(r"""from\s+([a-zA-Z0-9_.]+)\s+import"""),
    re.compile(r"""import\s+([a-zA-Z0-9_.]+)"""),
]


class GitChangeAnalyzer:
    """Extracts code diffs, semantic changes, and impacted symbols from a Git repository."""

    def __init__(self, repo_path: Path | str = ".") -> None:
        self.repo_path = Path(repo_path).resolve()

    # -----------------------------------------------------------------------
    # Git Command Runner
    # -----------------------------------------------------------------------

    def _run_git(self, args: list[str]) -> str:
        """Run a git subcommand and return stripped stdout."""
        try:
            res = subprocess.run(
                ["git", *args],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode != 0:
                logger.debug("Git command failed (code %d): %s", res.returncode, res.stderr)
                return ""
            return res.stdout
        except Exception as exc:
            logger.debug("Failed to invoke git: %s", exc)
            return ""

    def get_repo_info(self) -> tuple[str | None, str | None, bool]:
        """Return (current_commit, current_branch, is_dirty)."""
        commit = self._run_git(["rev-parse", "--short", "HEAD"]).strip() or None
        branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip() or None
        status = self._run_git(["status", "--porcelain"]).strip()
        is_dirty = bool(status)
        return commit, branch, is_dirty

    # -----------------------------------------------------------------------
    # Unified Diff Parser
    # -----------------------------------------------------------------------

    def parse_unified_diff(self, diff_text: str) -> list[ChangedFile]:
        """Parse unified git diff output into structured ChangedFile objects."""
        if not diff_text.strip():
            return []

        files: list[ChangedFile] = []
        current_file: ChangedFile | None = None
        current_hunk: DiffHunk | None = None

        lines = diff_text.splitlines()
        i = 0
        n = len(lines)

        while i < n:
            line = lines[i]

            # Detect file boundary: diff --git a/path b/path
            if line.startswith("diff --git "):
                if current_file:
                    if current_hunk:
                        current_file.hunks.append(current_hunk)
                        current_hunk = None
                    files.append(current_file)

                parts = line.split(" ")
                old_p = parts[2][2:] if len(parts) > 2 and parts[2].startswith("a/") else ""
                new_p = parts[3][2:] if len(parts) > 3 and parts[3].startswith("b/") else ""

                current_file = ChangedFile(
                    path=new_p or old_p,
                    old_path=old_p if old_p != new_p else None,
                    change_type="modified",
                )
                i += 1
                continue

            if not current_file:
                i += 1
                continue

            # Check change type headers
            if line.startswith("new file mode"):
                current_file.change_type = "added"
            elif line.startswith("deleted file mode"):
                current_file.change_type = "deleted"
            elif line.startswith("similarity index"):
                current_file.change_type = "renamed"

            # Check hunk header: @@ -old_start,old_lines +new_start,new_lines @@ heading
            if line.startswith("@@ "):
                if current_hunk:
                    current_file.hunks.append(current_hunk)

                match = re.search(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)", line)
                if match:
                    old_s = int(match.group(1))
                    old_l = int(match.group(2) or 1)
                    new_s = int(match.group(3))
                    new_l = int(match.group(4) or 1)
                    heading = match.group(5).strip()

                    current_hunk = DiffHunk(
                        old_start=old_s,
                        old_lines=old_l,
                        new_start=new_s,
                        new_lines=new_l,
                        heading=heading,
                    )
                i += 1
                continue

            # Process diff hunk lines (+, -, context)
            if current_hunk is not None:
                if line.startswith("+") and not line.startswith("+++"):
                    current_file.additions += 1
                    current_hunk.lines.append(line)
                elif line.startswith("-") and not line.startswith("---"):
                    current_file.deletions += 1
                    current_hunk.lines.append(line)
                elif line.startswith(" "):
                    current_hunk.lines.append(line)

            i += 1

        if current_file:
            if current_hunk:
                current_file.hunks.append(current_hunk)
            files.append(current_file)

        return files

    # -----------------------------------------------------------------------
    # Semantic Extractors
    # -----------------------------------------------------------------------

    def extract_selectors_from_lines(self, lines: list[str], file_path: str) -> list[str]:
        """Extract changed DOM and CSS selectors from modified lines."""
        found: set[str] = set()
        for raw_line in lines:
            # Only analyze added or removed content
            if not (raw_line.startswith("+") or raw_line.startswith("-")):
                continue
            line = raw_line[1:].strip()

            for pattern in RE_SELECTOR_ATTRIBUTES:
                for match in pattern.finditer(line):
                    val = match.group(1).strip()
                    if val and len(val) < 80:
                        # If space-delimited classes, extract both individual tokens and full class
                        if " " in val and not any(ch in val for ch in [">", ":", "["]):
                            tokens = val.split()
                            for tok in tokens:
                                if re.match(r"^[a-zA-Z0-9_\-]+$", tok):
                                    found.add(f".{tok}")
                        else:
                            if not val.startswith((".", "#", "[", ">")):
                                found.add(f"#{val}" if "id" in pattern.pattern else val)
                            else:
                                found.add(val)

            # CSS / SCSS file rules: e.g. .btn-submit, #checkout-form
            if file_path.endswith((".css", ".scss", ".sass", ".less")):
                css_match = re.findall(r"""([.#][a-zA-Z0-9_\-]+)""", line)
                for cm in css_match:
                    found.add(cm)

        return sorted(found)

    def extract_routes_from_lines(self, lines: list[str], file_path: str) -> list[str]:
        """Extract modified routes and endpoints from added/removed lines or file path."""
        found: set[str] = set()

        # 1. File-system routing conventions (Next.js / Nuxt / SvelteKit)
        fp = file_path.replace("\\", "/")
        if "pages/" in fp or "app/" in fp:
            # e.g., pages/checkout.jsx -> /checkout
            # e.g., app/settings/page.tsx -> /settings
            route_candidate = ""
            if "pages/" in fp:
                sub = fp.split("pages/", 1)[1]
                sub = re.sub(r"\.(jsx?|tsx?|vue|svelte)$", "", sub)
                if sub == "index":
                    route_candidate = "/"
                elif sub.endswith("/index"):
                    route_candidate = "/" + sub[:-6]
                else:
                    route_candidate = "/" + sub
            elif "app/" in fp and (fp.endswith("/page.tsx") or fp.endswith("/page.jsx")):
                sub = fp.split("app/", 1)[1]
                sub = re.sub(r"/page\.(jsx?|tsx?)$", "", sub)
                route_candidate = "/" + sub if sub else "/"

            if route_candidate:
                found.add(route_candidate.lower())

        # 2. Extract explicit route definitions in code lines
        for raw_line in lines:
            if not (raw_line.startswith("+") or raw_line.startswith("-")):
                continue
            line = raw_line[1:].strip()

            for pattern in RE_ROUTE_PATTERNS:
                for match in pattern.finditer(line):
                    r = match.group(1).strip()
                    if r and r.startswith("/") and not r.startswith("//"):
                        # Clean query params or regex placeholders
                        clean_r = r.split("?")[0].rstrip("/") or "/"
                        found.add(clean_r.lower())

        return sorted(found)

    def extract_symbols(self, file_obj: ChangedFile, full_content: str | None = None) -> None:
        """Extract modified function, class, and component names."""
        fp = file_obj.path
        symbols_fn: set[str] = set()
        symbols_cls: set[str] = set()

        # Python files: try AST line-range overlap with hunks
        if fp.endswith(".py"):
            target_content = full_content
            if target_content is None:
                real_file = self.repo_path / fp
                if real_file.exists() and real_file.is_file():
                    try:
                        target_content = real_file.read_text(errors="replace")
                    except OSError:
                        pass

            if target_content:
                try:
                    tree = ast.parse(target_content)
                    # Collect line numbers touched in hunks
                    touched_new_lines: set[int] = set()
                    for h in file_obj.hunks:
                        cur = h.new_start
                        for l in h.lines:
                            if l.startswith("+") or l.startswith(" "):
                                touched_new_lines.add(cur)
                                cur += 1

                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            end_lineno = getattr(node, "end_lineno", node.lineno)
                            if any(node.lineno <= ln <= end_lineno for ln in touched_new_lines):
                                symbols_fn.add(node.name)
                        elif isinstance(node, ast.ClassDef):
                            end_lineno = getattr(node, "end_lineno", node.lineno)
                            if any(node.lineno <= ln <= end_lineno for ln in touched_new_lines):
                                symbols_cls.add(node.name)
                except Exception:
                    pass

        # Diff hunk regex scanning for Python, JS, TS, etc.
        for h in file_obj.hunks:
            if h.heading:
                # Often git hunk headers include `def func_name` or `class ClassName`
                m_py = re.search(r"""(?:def|class)\s+([a-zA-Z0-9_]+)""", h.heading)
                if m_py:
                    symbols_fn.add(m_py.group(1))

            for raw_line in h.lines:
                if not (raw_line.startswith("+") or raw_line.startswith("-")):
                    continue
                line = raw_line[1:].strip()

                # Python def / class
                m_def = re.match(r"""(?:async\s+)?def\s+([a-zA-Z0-9_]+)""", line)
                if m_def:
                    symbols_fn.add(m_def.group(1))
                m_cls = re.match(r"""class\s+([a-zA-Z0-9_]+)""", line)
                if m_cls:
                    symbols_cls.add(m_cls.group(1))

                # JS / TS function / component / class
                for pat in RE_JS_SYMBOLS:
                    m_js = pat.search(line)
                    if m_js:
                        name = m_js.group(1)
                        if "class" in pat.pattern:
                            symbols_cls.add(name)
                        else:
                            symbols_fn.add(name)

        file_obj.changed_functions = sorted(symbols_fn)
        file_obj.changed_classes = sorted(symbols_cls)

    def extract_dependencies_from_lines(self, lines: list[str]) -> list[str]:
        """Extract imported module names and paths from modified lines."""
        found: set[str] = set()
        for raw_line in lines:
            if not (raw_line.startswith("+") or raw_line.startswith("-")):
                continue
            line = raw_line[1:].strip()
            for pattern in RE_IMPORT_PATTERNS:
                for match in pattern.finditer(line):
                    dep = match.group(1).strip()
                    if dep:
                        found.add(dep)
        return sorted(found)

    # -----------------------------------------------------------------------
    # Comprehensive Analysis
    # -----------------------------------------------------------------------

    def analyze_diff_text(
        self,
        diff_text: str,
        base_ref: str | None = None,
        target_ref: str | None = None,
    ) -> GitChangeSet:
        """Analyze a raw unified diff string and produce an enriched GitChangeSet."""
        files = self.parse_unified_diff(diff_text)
        commit, branch, is_dirty = self.get_repo_info()

        total_routes: set[str] = set()
        total_selectors: set[str] = set()
        total_symbols: set[str] = set()
        files_by_type: dict[str, int] = {}
        total_adds = 0
        total_dels = 0

        for f in files:
            all_hunk_lines = [line for h in f.hunks for line in h.lines]

            # 1. Selectors
            f.changed_selectors = self.extract_selectors_from_lines(all_hunk_lines, f.path)
            total_selectors.update(f.changed_selectors)

            # 2. Routes
            f.changed_routes = self.extract_routes_from_lines(all_hunk_lines, f.path)
            total_routes.update(f.changed_routes)

            # 3. Symbols
            self.extract_symbols(f)
            total_symbols.update(f.changed_functions)
            total_symbols.update(f.changed_classes)

            # 4. Dependencies
            f.dependencies = self.extract_dependencies_from_lines(all_hunk_lines)

            # Totals
            total_adds += f.additions
            total_dels += f.deletions

            ext = Path(f.path).suffix.lstrip(".").lower() or "other"
            files_by_type[ext] = files_by_type.get(ext, 0) + 1

        summary = GitChangeSummary(
            total_files_changed=len(files),
            total_additions=total_adds,
            total_deletions=total_dels,
            files_by_type=files_by_type,
            total_changed_routes=sorted(total_routes),
            total_changed_selectors=sorted(total_selectors),
            total_changed_symbols=sorted(total_symbols),
        )

        return GitChangeSet(
            repo_path=str(self.repo_path),
            base_ref=base_ref,
            target_ref=target_ref,
            current_commit=commit,
            current_branch=branch,
            is_dirty=is_dirty,
            files=files,
            summary=summary,
        )

    def analyze_repo(
        self,
        base_ref: str | None = None,
        target_ref: str | None = None,
        staged_only: bool = False,
        include_untracked: bool = True,
    ) -> GitChangeSet:
        """
        Inspect live git repository diffs and return an enriched GitChangeSet.
        
        If base_ref is supplied, compares base_ref..target_ref (or base_ref..HEAD).
        Otherwise, inspects dirty working directory changes (unstaged + staged + untracked).
        """
        diff_chunks: list[str] = []

        if base_ref:
            target = target_ref or "HEAD"
            diff_out = self._run_git(["diff", "-U3", f"{base_ref}...{target}"])
            if not diff_out:
                diff_out = self._run_git(["diff", "-U3", f"{base_ref}..{target}"])
            diff_chunks.append(diff_out)
        else:
            if staged_only:
                diff_chunks.append(self._run_git(["diff", "-U3", "--cached"]))
            else:
                # Unstaged modifications
                diff_chunks.append(self._run_git(["diff", "-U3"]))
                # Staged modifications
                diff_chunks.append(self._run_git(["diff", "-U3", "--cached"]))

            # Handle untracked files as synthetic additions
            if include_untracked:
                untracked = self._get_untracked_files()
                for uf in untracked:
                    synthetic_diff = self._generate_untracked_diff(uf)
                    if synthetic_diff:
                        diff_chunks.append(synthetic_diff)

        full_diff = "\n".join(chunk for chunk in diff_chunks if chunk.strip())
        return self.analyze_diff_text(full_diff, base_ref=base_ref, target_ref=target_ref)

    def _get_untracked_files(self) -> list[str]:
        """List untracked files in the repository."""
        out = self._run_git(["status", "--porcelain"])
        untracked: list[str] = []
        for line in out.splitlines():
            if line.startswith("?? "):
                untracked.append(line[3:].strip())
        return untracked

    def _generate_untracked_diff(self, rel_path: str) -> str:
        """Construct a unified diff representation for a newly added untracked file."""
        abs_p = self.repo_path / rel_path
        if not abs_p.is_file():
            return ""

        try:
            content = abs_p.read_text(errors="replace")
        except OSError:
            return ""

        lines = content.splitlines()
        added_lines = "\n".join(f"+{l}" for l in lines)
        header = (
            f"diff --git a/{rel_path} b/{rel_path}\n"
            f"new file mode 100644\n"
            f"--- /dev/null\n"
            f"+++ b/{rel_path}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n"
        )
        return header + added_lines
