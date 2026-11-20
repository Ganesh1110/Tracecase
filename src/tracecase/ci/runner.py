"""Tracecase CI Execution Engine & Quality Gate Orchestrator.

Provides the standalone CIRunner that connects Git analysis, code mapping,
predictive risk scoring, intelligent regression selection, batch execution,
baseline snapshot resolution, regression drift detection, and multi-format reporting.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import logging
from pathlib import Path
import subprocess
import time
from typing import Any
import uuid

from tracecase.ci.baseline.executor import BaselineExecutor
from tracecase.ci.baseline.manager import BaselineManager
from tracecase.ci.baseline.models import BaselineSnapshot
from tracecase.ci.baseline.resolver import BaselineMatchStatus, BaselineResolutionResult, BaselineResolver
from tracecase.ci.config import CIRunnerConfig
from tracecase.ci.drift.analytics import DriftAnalytics
from tracecase.ci.drift.comparator import RegressionDriftComparator
from tracecase.ci.drift.models import DriftAnalysisResult
from tracecase.ci.gate import QualityGateEvaluator
from tracecase.ci.models import CIExitCode, CIRunResult, QualityGateResult, QualityGateRuleViolation
from tracecase.ci.reporters.json import generate_ci_json_manifest
from tracecase.ci.reporters.junit import generate_junit_xml
from tracecase.ci.reporters.markdown import generate_ci_markdown_report
from tracecase.ci.reporters.sarif import generate_sarif_report
from tracecase.intelligence.code_mapper import TestToCodeMapper
from tracecase.intelligence.explainer import PrioritizationExplainer
from tracecase.intelligence.git_analyzer import GitChangeAnalyzer
from tracecase.intelligence.risk_scorer import PredictiveRiskScorer
from tracecase.intelligence.selector import IntelligentRegressionSelector
from tracecase.models import TestCase
from tracecase.ui.db import get_execution_batch, init_studio_db, save_ci_run
from tracecase.ui.executor import ExecutionOrchestrator
from tracecase.ui.service import find_testcase_files, resolve_testcase_file

logger = logging.getLogger("tracecase.ci.runner")


class CIRunner:
    """Orchestrates an end-to-end continuous quality gate execution."""

    def __init__(
        self,
        config: CIRunnerConfig,
        db_path: Path | str | None = None,
        orchestrator: ExecutionOrchestrator | None = None,
    ) -> None:
        self.config = config
        self.db_path = db_path
        self._orchestrator = orchestrator
        self.baseline_manager = BaselineManager(self.db_path)
        self.baseline_resolver = BaselineResolver(self.baseline_manager)
        self.baseline_executor = BaselineExecutor(
            self.baseline_manager,
            orchestrator=self._orchestrator,
            db_path=self.db_path,
        )
        self.drift_analytics = DriftAnalytics(self.db_path)

    def _verify_git_env(self) -> None:
        """Validate repository and git references before running."""
        repo_p = Path(self.config.repo_path)
        if not repo_p.exists():
            raise FileNotFoundError(f"Repository directory does not exist: {repo_p}")

        # Check inside work tree
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(repo_p),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            raise RuntimeError(f"Path is not a valid git repository: {repo_p}")

        # If base_ref provided, verify existence
        if self.config.base_ref:
            res_ref = subprocess.run(
                ["git", "rev-parse", "--verify", self.config.base_ref],
                cwd=str(repo_p),
                capture_output=True,
                text=True,
                check=False,
            )
            if res_ref.returncode != 0:
                raise ValueError(
                    f"Invalid or missing git base ref '{self.config.base_ref}': {res_ref.stderr.strip()}"
                )

    async def run(self) -> CIRunResult:
        """Execute the complete CI quality gate workflow."""
        start_mono = time.monotonic()
        started_at = datetime.now().isoformat()
        run_id = f"ci_run_{uuid.uuid4().hex[:10]}"

        # Initialize studio db if required
        try:
            init_studio_db(self.db_path)
        except Exception as exc:
            logger.warning("Studio DB initialization notice: %s", exc)

        # 1. Environment & Git Validation
        try:
            self._verify_git_env()
        except Exception as exc:
            duration = time.monotonic() - start_mono
            gate_res = QualityGateResult(
                status="FAILED",
                passed=False,
                policy_name=self.config.gate_policy.name,
                summary=f"CI environment/configuration error: {exc}",
                violations=[
                    QualityGateRuleViolation(
                        rule_name="git_environment",
                        severity="critical",
                        message=str(exc),
                    )
                ],
            )
            return CIRunResult(
                run_id=run_id,
                project_id=self.config.project_id,
                base_ref=self.config.base_ref,
                target_ref=self.config.target_ref,
                started_at=started_at,
                finished_at=datetime.now().isoformat(),
                duration_seconds=duration,
                exit_code=int(CIExitCode.CONFIG_ERROR),
                gate_result=gate_res,
                error_category="config",
                error_detail=str(exc),
            )

        # 2. Git Diff Analysis
        analyzer = GitChangeAnalyzer(repo_path=self.config.repo_path)
        commit_hash, branch, _ = analyzer.get_repo_info()

        # Resolve exact base commit SHA if base_ref provided
        base_commit_sha: str | None = None
        if self.config.base_ref:
            try:
                res_sha = subprocess.run(
                    ["git", "rev-parse", self.config.base_ref],
                    cwd=str(self.config.repo_path),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if res_sha.returncode == 0:
                    base_commit_sha = res_sha.stdout.strip()
            except Exception:
                pass

        try:
            changeset = analyzer.analyze_repo(
                base_ref=self.config.base_ref,
                target_ref=self.config.target_ref,
                staged_only=self.config.staged_only,
            )
        except Exception as exc:
            duration = time.monotonic() - start_mono
            gate_res = QualityGateResult(
                status="FAILED",
                passed=False,
                policy_name=self.config.gate_policy.name,
                summary=f"Git diff analysis failed: {exc}",
                violations=[
                    QualityGateRuleViolation(
                        rule_name="git_diff_analysis",
                        severity="critical",
                        message=str(exc),
                    )
                ],
            )
            return CIRunResult(
                run_id=run_id,
                project_id=self.config.project_id,
                commit_hash=commit_hash,
                base_ref=self.config.base_ref,
                target_ref=self.config.target_ref,
                branch=branch,
                started_at=started_at,
                finished_at=datetime.now().isoformat(),
                duration_seconds=duration,
                exit_code=int(CIExitCode.CONFIG_ERROR),
                gate_result=gate_res,
                error_category="config",
                error_detail=str(exc),
            )

        # 3. Handle No Changed Files (Sensible pass, 0 cost)
        evaluator = QualityGateEvaluator(policy=self.config.gate_policy)
        if not changeset.files:
            gate_res = evaluator.evaluate(changeset=changeset, execution_runs=[])
            gate_res.summary = "No changes detected in repository. Quality gate passed with 0 test runs."
            duration = time.monotonic() - start_mono
            run_res = CIRunResult(
                run_id=run_id,
                project_id=self.config.project_id,
                commit_hash=commit_hash,
                base_ref=self.config.base_ref,
                target_ref=self.config.target_ref,
                branch=branch,
                started_at=started_at,
                finished_at=datetime.now().isoformat(),
                duration_seconds=duration,
                exit_code=int(CIExitCode.PASSED),
                gate_result=gate_res,
                total_considered=0,
                selected_count=0,
                executed_count=0,
            )
            try:
                save_ci_run(run_res, db_path=self.db_path)
            except Exception as db_exc:
                logger.warning("Failed to persist CI run record to SQLite: %s", db_exc)

            self._write_reports(run_res, gate_res, runs=[])
            return run_res

        # 4. Codebase Scanning and Test Discovery
        mapper = TestToCodeMapper(
            repo_path=self.config.repo_path,
            project_id=self.config.project_id,
        )
        mapper.scan_codebase()

        tc_files = find_testcase_files()
        testcases: list[TestCase] = []
        for f in tc_files:
            try:
                _, tc = resolve_testcase_file(str(f))
                testcases.append(tc)
            except Exception:
                pass

        graph = mapper.build_graph(testcases, persist=False)

        # 5. Risk Scoring & Predictive Selection
        scorer = PredictiveRiskScorer(project_id=self.config.project_id)
        risk_report = scorer.evaluate_suite_risk(testcases, graph, changeset, persist=False)

        selector = IntelligentRegressionSelector(project_id=self.config.project_id)
        selection = selector.select(
            testcases=testcases,
            risk_report=risk_report,
            strategy=self.config.strategy,
            time_budget=self.config.time_budget,
            min_risk_tier=self.config.min_risk_tier,
            top_k=self.config.top_k,
            include_critical_exceptions=self.config.include_critical_exceptions,
            persist=False,
        )

        explainer = PrioritizationExplainer(project_id=self.config.project_id)
        prioritization_report = explainer.build_report(
            selection=selection,
            risk_report=risk_report,
            changeset=changeset,
            graph=graph,
            persist=False,
        )

        # 6. Determine Tests to Run
        test_ids_to_run = list(selection.selected_test_ids)
        if self.config.include_critical_exceptions:
            for be in selection.budget_exceptions:
                if be not in test_ids_to_run:
                    test_ids_to_run.append(be)

        # 7. Baseline Snapshot Resolution (Phase 8.3)
        baseline_snap: BaselineSnapshot | None = None
        if self.config.gate_policy.baseline_enabled:
            resolution = self.baseline_resolver.resolve(
                project_id=self.config.project_id,
                base_ref=self.config.baseline_ref or self.config.base_ref,
                base_commit=base_commit_sha,
                browser=self.config.browser,
                require_exact_commit=self.config.require_exact_baseline,
                repo_path=self.config.repo_path,
                environment=self.config.environment,
            )
            if resolution.is_valid:
                baseline_snap = resolution.snapshot
            elif self.config.auto_run_baseline and base_commit_sha:
                try:
                    logger.info("Executing baseline in isolated worktree for base commit %s", base_commit_sha)
                    baseline_snap = await self.baseline_executor.execute_baseline_in_worktree(
                        repo_path=self.config.repo_path,
                        base_commit=base_commit_sha,
                        project_id=self.config.project_id,
                        branch=self.config.base_ref,
                        browser=self.config.browser,
                        concurrency=self.config.concurrency,
                        retries=self.config.retries,
                        testcase_ids=test_ids_to_run,
                    )
                except Exception as base_exc:
                    logger.warning("Failed to auto-execute baseline in worktree: %s", base_exc)

        # 8. Execute Tests via Orchestrator
        batch_id: str | None = None
        batch_record: dict[str, Any] | None = None
        execution_runs: list[dict[str, Any]] = []
        infra_error_msg: str | None = None

        if test_ids_to_run:
            orchestrator = self._orchestrator or ExecutionOrchestrator()
            shutdown_browser = self._orchestrator is None

            try:
                batch = await orchestrator.start_batch_execution(
                    testcase_ids=test_ids_to_run,
                    concurrency=self.config.concurrency,
                    project_id=self.config.project_id,
                    browser=self.config.browser,
                    headed=self.config.headed,
                    retries=self.config.retries,
                )
                batch_id = batch.get("id")
                task = orchestrator.active_tasks.get(batch_id)
                if task:
                    await task

                batch_record = get_execution_batch(batch_id, db_path=self.db_path)
                execution_runs = list(batch_record.get("runs") or []) if batch_record else []
            except (asyncio.CancelledError, KeyboardInterrupt):
                logger.warning("CI execution cancelled or interrupted. Cancelling batch %s...", batch_id)
                if batch_id:
                    try:
                        await orchestrator.cancel_batch(batch_id)
                    except Exception as cancel_exc:
                        logger.debug("Batch cancel exception: %s", cancel_exc)
                if shutdown_browser:
                    try:
                        await orchestrator.browser_pool.shutdown()
                    except Exception:
                        pass
                raise
            except Exception as exc:
                logger.exception("Batch execution encountered infrastructure error: %s", exc)
                infra_error_msg = str(exc)
            finally:
                if shutdown_browser:
                    try:
                        await orchestrator.browser_pool.shutdown()
                    except Exception:
                        pass

        # 9. Regression Drift Analysis (Phase 8.3)
        drift_result: DriftAnalysisResult | None = None
        if self.config.gate_policy.baseline_enabled or baseline_snap:
            tc_map = {tc.id: tc for tc in testcases}
            drift_result = RegressionDriftComparator.compare_batch(
                runs=execution_runs,
                baseline=baseline_snap,
                run_id=run_id,
                project_id=self.config.project_id,
                base_commit=base_commit_sha,
                pr_commit=commit_hash,
                browser=self.config.browser,
                testcases_map=tc_map,
            )
            if drift_result and len(drift_result.items) > 0:
                try:
                    self.drift_analytics.save_drift_result(drift_result)
                except Exception as exc:
                    logger.warning("Failed to persist drift result: %s", exc)

        # 10. Evaluate Quality Gate
        gate_res = evaluator.evaluate(
            selection=selection,
            report=prioritization_report,
            batch_record=batch_record,
            execution_runs=execution_runs,
            changeset=changeset,
            drift_result=drift_result,
        )

        # 11. Determine Exit Code
        duration = time.monotonic() - start_mono
        has_run_errors = any(r.get("status") == "error" for r in execution_runs)

        if infra_error_msg or has_run_errors:
            exit_code = int(CIExitCode.INFRASTRUCTURE_ERROR)
            error_cat = "infrastructure"
            error_det = infra_error_msg or "Execution runs encountered browser/system error"
        elif not gate_res.passed:
            exit_code = int(CIExitCode.GATE_FAILED)
            error_cat = "quality_gate"
            error_det = gate_res.summary
        else:
            exit_code = int(CIExitCode.PASSED)
            error_cat = "none"
            error_det = None

        run_res = CIRunResult(
            run_id=run_id,
            project_id=self.config.project_id,
            commit_hash=commit_hash,
            base_ref=self.config.base_ref,
            target_ref=self.config.target_ref,
            branch=branch,
            started_at=started_at,
            finished_at=datetime.now().isoformat(),
            duration_seconds=duration,
            exit_code=exit_code,
            gate_result=gate_res,
            selection_id=selection.id,
            batch_id=batch_id,
            total_considered=getattr(selection, "total_tests_considered", getattr(selection, "total_considered", len(selection.tests))),
            selected_count=len(selection.selected_test_ids),
            executed_count=len(execution_runs),
            selected_test_ids=selection.selected_test_ids,
            executed_test_ids=[r.get("testcase_id") for r in execution_runs if r.get("testcase_id")],
            test_results=execution_runs,
            drift_summary=drift_result.model_dump() if drift_result else None,
            error_category=error_cat,
            error_detail=error_det,
        )

        # 12. Persist CI Run record in SQLite
        try:
            save_ci_run(run_res, db_path=self.db_path)
        except Exception as db_exc:
            logger.warning("Failed to persist CI run record to SQLite: %s", db_exc)

        # 13. Generate and write reports
        self._write_reports(
            run_res=run_res,
            gate_res=gate_res,
            runs=execution_runs,
            selection=selection,
            report=prioritization_report,
            drift_result=drift_result,
        )

        return run_res

    def _write_reports(
        self,
        run_res: CIRunResult,
        gate_res: QualityGateResult,
        runs: list[dict[str, Any]],
        selection: Any = None,
        report: Any = None,
        drift_result: DriftAnalysisResult | None = None,
    ) -> None:
        """Generate and serialize requested report artifacts."""
        reports: dict[str, str] = {}

        # 1. JUnit XML
        junit_xml = generate_junit_xml(
            runs=runs,
            suite_name=f"Tracecase Quality Gate ({gate_res.policy_name})",
        )
        reports["junit"] = junit_xml
        if self.config.junit_path:
            p = Path(self.config.junit_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(junit_xml, encoding="utf-8")

        # 2. SARIF 2.1.0
        sarif_dict = generate_sarif_report(
            gate_result=gate_res,
            runs=runs,
            selection=selection,
            repo_path=self.config.repo_path,
            drift_result=drift_result,
        )
        sarif_json = json.dumps(sarif_dict, indent=2)
        reports["sarif"] = sarif_json
        if self.config.sarif_path:
            p = Path(self.config.sarif_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(sarif_json, encoding="utf-8")

        # 3. Markdown PR / Step Summary
        md_text = generate_ci_markdown_report(
            run_result=run_res,
            gate_result=gate_res,
            selection=selection,
            report=report,
            drift_result=drift_result,
        )
        reports["markdown"] = md_text
        if self.config.markdown_path:
            p = Path(self.config.markdown_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(md_text, encoding="utf-8")

        # 4. JSON Manifest
        json_dict = generate_ci_json_manifest(
            run_result=run_res,
            gate_result=gate_res,
            drift_result=drift_result,
        )
        json_str = json.dumps(json_dict, indent=2)
        reports["json"] = json_str
        if self.config.json_path:
            p = Path(self.config.json_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json_str, encoding="utf-8")

        run_res.reports = reports

        # 5. Upload to Tracecase Studio if upload_url configured
        if self.config.upload_url:
            self._upload_manifest_if_configured(json_dict, run_res)

    def _upload_manifest_if_configured(self, manifest: dict[str, Any], run_res: CIRunResult) -> None:
        """Upload CI run manifest to hosted Tracecase Studio instance."""
        if not self.config.upload_url:
            return
        import urllib.request
        import urllib.error

        base_url = self.config.upload_url.rstrip("/")
        if not base_url.endswith("/api"):
            endpoint = f"{base_url}/api/ci/ingest"
        else:
            endpoint = f"{base_url}/ci/ingest"

        headers = {"Content-Type": "application/json"}
        if self.config.upload_token:
            headers["Authorization"] = f"Bearer {self.config.upload_token}"

        payload_bytes = json.dumps({"manifest": manifest}).encode("utf-8")
        req = urllib.request.Request(endpoint, data=payload_bytes, headers=headers, method="POST")

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    logger.info("Successfully uploaded CI run %s to Studio: HTTP %s", run_res.run_id, resp.status)
                    return
            except Exception as exc:
                if attempt == max_retries:
                    logger.warning(
                        "Failed to upload CI run manifest to Studio (%s) after %d attempts: %s. Quality gate result (exit code %d) preserved.",
                        endpoint,
                        max_retries + 1,
                        exc,
                        run_res.exit_code,
                    )
                else:
                    time.sleep(0.2 * (attempt + 1))
