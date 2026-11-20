"""Configuration loader for Tracecase CI runs and Quality Gates."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel, Field

from tracecase.ci.policy import QualityGatePolicy, get_policy


class CIRunnerConfig(BaseModel):
    """Complete runtime configuration for the tracecase ci orchestrator."""
    base_ref: str | None = None
    target_ref: str | None = None
    staged_only: bool = False
    repo_path: str = "."
    project_id: str = "default_project"
    time_budget: str | None = "180s"
    min_risk_tier: str | None = None
    top_k: int | None = None
    strategy: str = "time_budget"
    concurrency: int = Field(default=2, ge=1, le=16)
    browser: str = "chromium"
    retries: int = Field(default=1, ge=0, le=3)
    headed: bool = False
    include_critical_exceptions: bool = False
    gate_policy: QualityGatePolicy = Field(default_factory=QualityGatePolicy)
    junit_path: str | None = None
    sarif_path: str | None = None
    markdown_path: str | None = None
    json_path: str | None = None

    @classmethod
    def load_from_file(cls, config_path: Path | str) -> CIRunnerConfig:
        """Load configuration from a YAML file."""
        p = Path(config_path)
        if not p.is_file():
            raise FileNotFoundError(f"Configuration file not found: {p}")
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CIRunnerConfig:
        """Construct from raw dictionary."""
        ci_section = data.get("ci", {})
        gate_section = data.get("quality_gate", {})
        reports_section = data.get("reports", {})

        # Resolve policy
        policy_name = gate_section.get("policy", "standard")
        base_policy = get_policy(policy_name)
        policy_dict = base_policy.model_dump()
        for k, v in gate_section.items():
            if k != "policy" and k in policy_dict:
                policy_dict[k] = v
        final_policy = QualityGatePolicy(**policy_dict)

        return cls(
            base_ref=ci_section.get("base_ref") or ci_section.get("base_branch"),
            target_ref=ci_section.get("target_ref"),
            staged_only=bool(ci_section.get("staged_only", False)),
            repo_path=ci_section.get("repo_path", "."),
            project_id=ci_section.get("project_id", "default_project"),
            time_budget=str(ci_section.get("budget", ci_section.get("time_budget", "180s"))),
            concurrency=int(ci_section.get("concurrency", 2)),
            browser=str(ci_section.get("browser", "chromium")),
            retries=int(ci_section.get("retries", 1)),
            headed=bool(ci_section.get("headed", False)),
            include_critical_exceptions=bool(ci_section.get("include_critical_exceptions", False)),
            gate_policy=final_policy,
            junit_path=reports_section.get("junit"),
            sarif_path=reports_section.get("sarif"),
            markdown_path=reports_section.get("markdown") or reports_section.get("report"),
            json_path=reports_section.get("manifest") or reports_section.get("json"),
        )
