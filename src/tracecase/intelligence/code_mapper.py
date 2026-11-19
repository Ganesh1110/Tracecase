"""Test-to-Code Mapping Engine for Tracecase (Phase 7.5.2).

Extracts behavioral footprints from test cases and establishes bidirectional,
evidence-ranked mappings between test cases and application code:
1. Exact route and URL matches (Confidence 1.0)
2. Exact DOM / CSS selector matches (Confidence 0.95)
3. API endpoint network call matches (Confidence 0.90)
4. Route prefix matches (Confidence 0.85)
5. Direct module and dependency import relationships (Confidence 0.70)
6. Heuristic component and symbol matching (Confidence 0.50)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from tracecase.intelligence.models import (
    ChangedFile,
    CodeImpactReport,
    GitChangeSummary,
    ImpactedTestResult,
    RelationType,
    TestCodeMapping,
    TestCoverageProfile,
)
from tracecase.models import TestCase

logger = logging.getLogger(__name__)

# File extensions inspected for application source code
CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".svelte",
    ".html",
    ".css",
    ".scss",
}

# Directories to exclude during codebase scanning
IGNORE_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".tracecase",
    "recordings",
}


# ---------------------------------------------------------------------------
# Test Reference Extractor
# ---------------------------------------------------------------------------

class TestReferenceExtractor:
    """Extracts URLs, routes, selectors, actions, and API calls from a TestCase."""
    __test__ = False

    @staticmethod
    def extract_profile(tc: TestCase) -> TestCoverageProfile:
        """Extract a structured coverage profile from a TestCase instance."""
        routes: set[str] = set()
        api_endpoints: set[str] = set()
        selectors: set[str] = set()
        actions: set[str] = set()
        step_selector_map: dict[int, list[str]] = {}

        # 1. Starting URL route
        if tc.start_url:
            path = urlparse(tc.start_url).path.rstrip("/") or "/"
            routes.add(path.lower())

        # 2. Inspect each step
        for step in tc.steps:
            step_sels: set[str] = set()

            act = getattr(step, "action_type", None) or getattr(step, "action", None)
            if act:
                actions.add(str(act))

            # Step URL
            if step.url:
                p = urlparse(step.url).path.rstrip("/") or "/"
                routes.add(p.lower())

            # Step Element selectors
            if step.element:
                el = step.element
                if el.selector:
                    selectors.add(el.selector.strip())
                    step_sels.add(el.selector.strip())

                # Attributes (id, data-testid, class)
                if el.attributes:
                    for attr_key, attr_val in el.attributes.items():
                        if not attr_val:
                            continue
                        k_lower = attr_key.lower()
                        if k_lower == "id":
                            id_sel = f"#{attr_val.strip()}"
                            selectors.add(id_sel)
                            step_sels.add(id_sel)
                        elif "testid" in k_lower or "test-id" in k_lower:
                            selectors.add(attr_val.strip())
                            step_sels.add(attr_val.strip())
                        elif k_lower in ("class", "classname"):
                            for c in attr_val.split():
                                class_sel = f".{c.strip()}"
                                selectors.add(class_sel)
                                step_sels.add(class_sel)

            # Step Assertions
            assertions = getattr(step, "assertions", None)
            if assertions:
                for a in assertions:
                    if hasattr(a, "selector") and getattr(a, "selector", None):
                        sel = getattr(a, "selector").strip()
                        selectors.add(sel)
                        step_sels.add(sel)

            # Step Network Requests (API endpoints touched)
            if step.network_requests:
                for req in step.network_requests:
                    req_url = getattr(req, "url", "")
                    if req_url:
                        req_path = urlparse(req_url).path.rstrip("/") or "/"
                        api_endpoints.add(req_path.lower())

            if step_sels:
                step_selector_map[step.number] = sorted(step_sels)

        return TestCoverageProfile(
            testcase_id=tc.id,
            testcase_name=tc.name,
            start_url=tc.start_url,
            page_routes=sorted(routes),
            api_endpoints=sorted(api_endpoints),
            selectors_used=sorted(selectors),
            step_selector_map=step_selector_map,
            action_types=sorted(actions),
        )


# ---------------------------------------------------------------------------
# Codebase Scanner
# ---------------------------------------------------------------------------

class CodebaseFileIndex:
    """Indexed metadata for a single application code file."""

    def __init__(self, rel_path: str, abs_path: Path) -> None:
        self.rel_path = rel_path
        self.abs_path = abs_path
        self.content: str = ""
        self.declared_routes: set[str] = set()
        self.declared_selectors: set[str] = set()
        self.declared_symbols: set[str] = set()
        self.imported_modules: set[str] = set()

    def scan(self) -> None:
        """Scan file content and extract declared routes, selectors, and imports."""
        try:
            self.content = self.abs_path.read_text(errors="replace")
        except OSError:
            return

        # 1. Routes (FastAPI, Express, React Router, Next.js conventions)
        self._extract_routes()

        # 2. Selectors (id, class, data-testid, CSS)
        self._extract_selectors()

        # 3. Symbols (functions, classes, components)
        self._extract_symbols()

        # 4. Imports & Dependencies
        self._extract_imports()

    def _extract_routes(self) -> None:
        # File-system routing: pages/checkout.jsx -> /checkout
        fp = self.rel_path.replace("\\", "/")
        if "pages/" in fp or "app/" in fp:
            if "pages/" in fp:
                sub = fp.split("pages/", 1)[1]
                sub = re.sub(r"\.(jsx?|tsx?|vue|svelte)$", "", sub)
                route = "/" if sub == "index" else "/" + (sub[:-6] if sub.endswith("/index") else sub)
                self.declared_routes.add(route.lower())
            elif "app/" in fp and (fp.endswith("/page.tsx") or fp.endswith("/page.jsx")):
                sub = fp.split("app/", 1)[1]
                sub = re.sub(r"/page\.(jsx?|tsx?)$", "", sub)
                self.declared_routes.add("/" + sub.lower() if sub else "/")

        # Code annotations / router patterns
        route_patterns = [
            re.compile(r"""@(?:app|router|api|blueprint)\.(?:get|post|put|delete|patch|route)\s*\(\s*["']([^"']+)["']""", re.I),
            re.compile(r"""(?:app|router)\.(?:get|post|put|delete|patch|use)\s*\(\s*["']([^"']+)["']""", re.I),
            re.compile(r"""path:\s*["']([^"']+)["']""", re.I),
            re.compile(r"""<Route\s+[^>]*path=["']([^"']+)["']""", re.I),
        ]
        for pat in route_patterns:
            for match in pat.finditer(self.content):
                r = match.group(1).strip()
                if r and r.startswith("/") and not r.startswith("//"):
                    clean_r = r.split("?")[0].rstrip("/") or "/"
                    self.declared_routes.add(clean_r.lower())

    def _extract_selectors(self) -> None:
        patterns = [
            re.compile(r"""data-test(?:id)?=["']([^"']+)["']""", re.I),
            re.compile(r"""id=["']([^"']+)["']""", re.I),
            re.compile(r"""class(?:Name)?=["']([^"']+)["']""", re.I),
        ]
        for pat in patterns:
            for match in pat.finditer(self.content):
                val = match.group(1).strip()
                if not val or len(val) > 80:
                    continue
                if " " in val and not any(ch in val for ch in [">", ":", "["]):
                    for tok in val.split():
                        if re.match(r"^[a-zA-Z0-9_\-]+$", tok):
                            self.declared_selectors.add(f".{tok}")
                else:
                    if pat.pattern.startswith("id="):
                        self.declared_selectors.add(f"#{val}")
                    elif "test" in pat.pattern:
                        self.declared_selectors.add(val)
                        self.declared_selectors.add(f"[data-testid='{val}']")
                    else:
                        self.declared_selectors.add(val)
                        self.declared_selectors.add(f".{val}")

        # CSS / SCSS selectors
        if self.rel_path.endswith((".css", ".scss", ".sass", ".less")):
            for cm in re.findall(r"""([.#][a-zA-Z0-9_\-]+)""", self.content):
                self.declared_selectors.add(cm)

    def _extract_symbols(self) -> None:
        # Python
        for m in re.finditer(r"""(?:def|class)\s+([a-zA-Z0-9_]+)""", self.content):
            self.declared_symbols.add(m.group(1))

        # JS / TS
        js_patterns = [
            re.compile(r"""(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z0-9_$]+)"""),
            re.compile(r"""(?:export\s+)?(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"""),
            re.compile(r"""(?:export\s+default\s+)?class\s+([a-zA-Z0-9_$]+)"""),
        ]
        for pat in js_patterns:
            for m in pat.finditer(self.content):
                self.declared_symbols.add(m.group(1))

    def _extract_imports(self) -> None:
        import_patterns = [
            re.compile(r"""import\s+.*?from\s+["']([^"']+)["']"""),
            re.compile(r"""require\s*\(\s*["']([^"']+)["']\s*\)"""),
            re.compile(r"""from\s+([a-zA-Z0-9_.]+)\s+import"""),
            re.compile(r"""import\s+([a-zA-Z0-9_.]+)"""),
        ]
        for pat in import_patterns:
            for m in pat.finditer(self.content):
                self.imported_modules.add(m.group(1).strip())


# ---------------------------------------------------------------------------
# Test-to-Code Mapper & Bidirectional Graph
# ---------------------------------------------------------------------------

class TestToCodeGraph:
    """In-memory bidirectional relationship graph between test cases and code files."""
    __test__ = False

    def __init__(self, project_id: str = "default_project") -> None:
        self.project_id = project_id
        self.mappings: list[TestCodeMapping] = []
        self._test_to_mappings: dict[str, list[TestCodeMapping]] = {}
        self._file_to_mappings: dict[str, list[TestCodeMapping]] = {}
        self._route_to_tests: dict[str, set[str]] = {}
        self._selector_to_tests: dict[str, set[str]] = {}

    def add_mapping(self, mapping: TestCodeMapping) -> None:
        """Add a verified mapping to the index."""
        self.mappings.append(mapping)
        self._test_to_mappings.setdefault(mapping.testcase_id, []).append(mapping)
        self._file_to_mappings.setdefault(mapping.file_path, []).append(mapping)

        if mapping.relation_type in ("exact_route", "route_prefix", "api_endpoint"):
            self._route_to_tests.setdefault(mapping.matched_entity.lower(), set()).add(mapping.testcase_id)
        elif mapping.relation_type == "exact_selector":
            self._selector_to_tests.setdefault(mapping.matched_entity.lower(), set()).add(mapping.testcase_id)

    def get_mappings_for_test(self, testcase_id: str) -> list[TestCodeMapping]:
        """Retrieve all code mappings for a given testcase."""
        return self._test_to_mappings.get(testcase_id, [])

    def get_mappings_for_file(self, file_path: str) -> list[TestCodeMapping]:
        """Retrieve all tests covering a given application file."""
        return self._file_to_mappings.get(file_path, [])

    def get_impacted_tests(
        self,
        changed_files: list[ChangedFile],
        all_tests: dict[str, str] | None = None,
    ) -> list[ImpactedTestResult]:
        """
        Identify and rank test cases impacted by code modifications.
        
        Evaluates evidence priority:
        1. Exact route matches (1.0)
        2. Exact selector matches (0.95)
        3. API endpoint modifications (0.90)
        4. Route prefix matches (0.85)
        5. Dependency/import modifications (0.70)
        6. Heuristic symbol matching (0.50)
        """
        impact_map: dict[str, ImpactedTestResult] = {}
        test_names = all_tests or {}

        for chg in changed_files:
            chg_path = chg.path
            old_path = chg.old_path

            # A. Direct file match (file modified that was previously mapped to tests)
            direct_mappings = self.get_mappings_for_file(chg_path)
            if old_path and not direct_mappings:
                direct_mappings = self.get_mappings_for_file(old_path)

            for m in direct_mappings:
                tc_id = m.testcase_id
                tc_name = test_names.get(tc_id, m.testcase_name)

                if tc_id not in impact_map:
                    impact_map[tc_id] = ImpactedTestResult(
                        testcase_id=tc_id,
                        testcase_name=tc_name,
                        project_id=self.project_id,
                        max_confidence=m.confidence,
                        primary_reason=f"Direct file modification in '{chg_path}' via {m.relation_type}",
                    )

                res = impact_map[tc_id]
                res.max_confidence = max(res.max_confidence, m.confidence)
                if chg_path not in res.affected_files:
                    res.affected_files.append(chg_path)
                reason = f"File '{chg_path}' changed ({m.relation_type}: '{m.matched_entity}')"
                if reason not in res.affected_reasons:
                    res.affected_reasons.append(reason)
                if m not in res.mappings:
                    res.mappings.append(m)

            # B. Selector matches (including critical removed/deleted selectors!)
            all_chg_selectors = set(chg.changed_selectors)
            for sel in all_chg_selectors:
                sel_lower = sel.lower()
                matched_tc_ids = self._selector_to_tests.get(sel_lower, set())
                # Substring/prefix matching for classes (e.g. .btn)
                for registered_sel, tcs in self._selector_to_tests.items():
                    if sel_lower == registered_sel or (len(sel_lower) > 3 and sel_lower in registered_sel):
                        matched_tc_ids.update(tcs)

                is_removed = sel in chg.removed_selectors
                conf = 0.98 if is_removed else 0.95
                severity = "DELETED / BROKEN" if is_removed else "modified"

                for tc_id in matched_tc_ids:
                    tc_name = test_names.get(tc_id, tc_id)
                    reason_msg = f"Interacts with {severity} selector '{sel}' in '{chg_path}'"
                    if tc_id not in impact_map:
                        impact_map[tc_id] = ImpactedTestResult(
                            testcase_id=tc_id,
                            testcase_name=tc_name,
                            project_id=self.project_id,
                            max_confidence=conf,
                            primary_reason=reason_msg,
                        )
                    res = impact_map[tc_id]
                    if conf > res.max_confidence or is_removed:
                        res.max_confidence = conf
                        res.primary_reason = reason_msg
                    if sel not in res.matched_selectors:
                        res.matched_selectors.append(sel)
                    if chg_path not in res.affected_files:
                        res.affected_files.append(chg_path)
                    reason = f"Selector '{sel}' was {severity} in '{chg_path}'"
                    if reason not in res.affected_reasons:
                        res.affected_reasons.append(reason)

            # C. Route matches (including removed routes)
            all_chg_routes = set(chg.changed_routes)
            for route in all_chg_routes:
                route_clean = route.lower().rstrip("/") or "/"
                is_removed = route in chg.removed_routes
                conf = 1.0 if is_removed else 0.95
                severity = "REMOVED" if is_removed else "modified"

                matched_tc_ids = set()
                for registered_route, tcs in self._route_to_tests.items():
                    if registered_route == route_clean or (route_clean != "/" and registered_route.startswith(route_clean)):
                        matched_tc_ids.update(tcs)

                for tc_id in matched_tc_ids:
                    tc_name = test_names.get(tc_id, tc_id)
                    if tc_id not in impact_map:
                        impact_map[tc_id] = ImpactedTestResult(
                            testcase_id=tc_id,
                            testcase_name=tc_name,
                            project_id=self.project_id,
                            max_confidence=conf,
                            primary_reason=f"Operates on {severity} route '{route_clean}' from '{chg_path}'",
                        )
                    res = impact_map[tc_id]
                    res.max_confidence = max(res.max_confidence, conf)
                    if route_clean not in res.matched_routes:
                        res.matched_routes.append(route_clean)
                    if chg_path not in res.affected_files:
                        res.affected_files.append(chg_path)
                    reason = f"Route '{route_clean}' was {severity} in '{chg_path}'"
                    if reason not in res.affected_reasons:
                        res.affected_reasons.append(reason)

        # Sort impacted tests by confidence descending
        results = sorted(impact_map.values(), key=lambda x: x.max_confidence, reverse=True)
        return results


# ---------------------------------------------------------------------------
# Test-to-Code Mapping Engine
# ---------------------------------------------------------------------------

class TestToCodeMapper:
    """Orchestrates codebase scanning, test profiling, and relationship graph generation."""
    __test__ = False

    def __init__(
        self,
        repo_path: Path | str = ".",
        project_id: str = "default_project",
        db_path: Path | str | None = None,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.project_id = project_id
        self.db_path = db_path
        self.file_indices: dict[str, CodebaseFileIndex] = {}

    def scan_codebase(self, search_dirs: list[str] | None = None) -> None:
        """Scan workspace application files and index routes, selectors, and imports."""
        target_dirs = search_dirs or ["src", "frontend", "backend", "app", "pages", "components", "lib"]
        scanned_count = 0

        # Scan explicitly targeted directories if they exist
        dirs_to_walk: list[Path] = []
        for d in target_dirs:
            p = self.repo_path / d
            if p.exists() and p.is_dir():
                dirs_to_walk.append(p)

        if not dirs_to_walk:
            dirs_to_walk = [self.repo_path]

        for base in dirs_to_walk:
            for root, dirs, files in os.walk(base):
                # Prune ignored directories
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

                for fn in files:
                    ext = Path(fn).suffix.lower()
                    if ext in CODE_EXTENSIONS:
                        abs_p = Path(root) / fn
                        rel_p = str(abs_p.relative_to(self.repo_path)).replace("\\", "/")
                        idx = CodebaseFileIndex(rel_p, abs_p)
                        idx.scan()
                        self.file_indices[rel_p] = idx
                        scanned_count += 1

        logger.debug("Scanned %d application code files for test mapping", scanned_count)

    def build_graph(
        self,
        test_cases: list[TestCase],
        persist: bool = True,
    ) -> TestToCodeGraph:
        """Construct the complete bidirectional TestToCodeGraph from testcases and code index."""
        if not self.file_indices:
            self.scan_codebase()

        graph = TestToCodeGraph(project_id=self.project_id)
        test_profiles = [TestReferenceExtractor.extract_profile(tc) for tc in test_cases]

        # Invert codebase index for rapid O(1) matching
        route_to_files: dict[str, set[str]] = {}
        selector_to_files: dict[str, set[str]] = {}
        symbol_to_files: dict[str, set[str]] = {}
        dep_graph: dict[str, set[str]] = {}

        for rel_p, c_idx in self.file_indices.items():
            for r in c_idx.declared_routes:
                route_to_files.setdefault(r.lower(), set()).add(rel_p)
            for s in c_idx.declared_selectors:
                selector_to_files.setdefault(s.lower(), set()).add(rel_p)
            for sym in c_idx.declared_symbols:
                symbol_to_files.setdefault(sym.lower(), set()).add(rel_p)
            # Track imported modules
            dep_graph[rel_p] = c_idx.imported_modules

        # Map each test case profile against the codebase
        for prof in test_profiles:
            tc_id = prof.testcase_id
            tc_name = prof.testcase_name

            # 1. Exact Route & API Endpoint Matches (Confidence 1.0 / 0.90)
            for r in prof.page_routes:
                matching_files = route_to_files.get(r, set())
                for mf in matching_files:
                    m_id = self._generate_mapping_id(tc_id, mf, "exact_route", r)
                    graph.add_mapping(
                        TestCodeMapping(
                            id=m_id,
                            testcase_id=tc_id,
                            testcase_name=tc_name,
                            project_id=self.project_id,
                            file_path=mf,
                            relation_type="exact_route",
                            matched_entity=r,
                            confidence=1.0,
                            evidence={"type": "page_route", "route": r},
                        )
                    )

            for api_r in prof.api_endpoints:
                matching_files = route_to_files.get(api_r, set())
                for mf in matching_files:
                    m_id = self._generate_mapping_id(tc_id, mf, "api_endpoint", api_r)
                    graph.add_mapping(
                        TestCodeMapping(
                            id=m_id,
                            testcase_id=tc_id,
                            testcase_name=tc_name,
                            project_id=self.project_id,
                            file_path=mf,
                            relation_type="api_endpoint",
                            matched_entity=api_r,
                            confidence=0.90,
                            evidence={"type": "network_request", "endpoint": api_r},
                        )
                    )

            # 2. Exact Selector Matches (Confidence 0.95)
            for sel in prof.selectors_used:
                sel_lower = sel.lower()
                matching_files = selector_to_files.get(sel_lower, set())
                for mf in matching_files:
                    m_id = self._generate_mapping_id(tc_id, mf, "exact_selector", sel)
                    graph.add_mapping(
                        TestCodeMapping(
                            id=m_id,
                            testcase_id=tc_id,
                            testcase_name=tc_name,
                            project_id=self.project_id,
                            file_path=mf,
                            relation_type="exact_selector",
                            matched_entity=sel,
                            confidence=0.95,
                            evidence={"type": "dom_selector", "selector": sel},
                        )
                    )

            # 3. Transitive Dependency Mapping (Confidence 0.70)
            # If file A is mapped to test, and file A imports file B, link B via dependency_import
            current_mapped_files = list({m.file_path for m in graph.get_mappings_for_test(tc_id)})
            for parent_file in current_mapped_files:
                # Check what parent_file imports
                imports = dep_graph.get(parent_file, set())
                for imp in imports:
                    # Resolve relative import to relative file path in workspace
                    resolved_file = self._resolve_import_to_file(parent_file, imp)
                    if resolved_file and resolved_file in self.file_indices and resolved_file != parent_file:
                        m_id = self._generate_mapping_id(tc_id, resolved_file, "dependency_import", imp)
                        graph.add_mapping(
                            TestCodeMapping(
                                id=m_id,
                                testcase_id=tc_id,
                                testcase_name=tc_name,
                                project_id=self.project_id,
                                file_path=resolved_file,
                                relation_type="dependency_import",
                                matched_entity=imp,
                                confidence=0.70,
                                evidence={
                                    "imported_by": parent_file,
                                    "import_statement": imp,
                                    "transitive": True,
                                },
                            )
                        )

        # 4. Optional Persistence into SQLite
        if persist and self.db_path:
            self._persist_mappings(graph.mappings)

        return graph

    def _resolve_import_to_file(self, source_file: str, import_str: str) -> str | None:
        """Resolve a relative import string (e.g. '../api/auth') to a known workspace file path."""
        if not import_str.startswith("."):
            # Check non-relative alias or module path (e.g. backend/services/...)
            for ext in ["", ".py", ".js", ".jsx", ".ts", ".tsx"]:
                candidate = f"{import_str}{ext}"
                if candidate in self.file_indices:
                    return candidate
            return None

        # Relative import from source_file directory
        source_dir = Path(source_file).parent
        resolved_base = (source_dir / import_str).as_posix()
        # Normalize relative path
        norm_p = os.path.normpath(resolved_base).replace("\\", "/")

        for ext in ["", ".py", ".js", ".jsx", ".ts", ".tsx", "/index.js", "/index.jsx", "/index.ts", "/index.tsx"]:
            cand = f"{norm_p}{ext}"
            if cand in self.file_indices:
                return cand

        return None

    def _generate_mapping_id(self, tc_id: str, file_path: str, relation: str, entity: str) -> str:
        """Generate a deterministic unique ID for a test-to-code mapping."""
        raw = f"{tc_id}::{file_path}::{relation}::{entity}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return f"map_{digest}"

    def _persist_mappings(self, mappings: list[TestCodeMapping]) -> None:
        """Persist mappings into SQLite database."""
        from tracecase.ui.db import init_studio_db, save_test_code_mappings
        init_studio_db(self.db_path)
        save_test_code_mappings(mappings, self.db_path)
