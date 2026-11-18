"""Analysis engine: heuristics first, optional AI enrichment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qa_auto.ai.models import AnalysisResult, Annotation, Message
from qa_auto.ai.provider import Provider
from qa_auto.models import TestCase
from qa_auto.replay.models import Assertion


async def analyze_testcase(testcase: TestCase, provider: Provider) -> AnalysisResult:
    """Analyze a test case with deterministic heuristics and optional AI."""
    annotations: list[Annotation] = []
    risks: list[str] = []
    negative_scenarios: list[str] = []
    suggested_assertions: list[Assertion] = []

    # 1. Heuristic: Uncaught page errors
    for err in testcase.page_errors:
        risks.append(f"Recorded page error: {err.message}")
        annotations.append(
            Annotation(
                type="bug_report",
                message=f"Page error observed: {err.message}",
                severity="error",
                provider="heuristics",
            )
        )

    # 2. Heuristic: Empty input actions
    for step in testcase.steps:
        if step.action_type == "input" and not step.input_value:
            msg = f"Step {step.number} submitted an empty input value."
            annotations.append(
                Annotation(
                    type="risk",
                    message=msg,
                    severity="warning",
                    step_number=step.number,
                    provider="heuristics",
                )
            )

    summary = (
        f"Recorded {len(testcase.steps)} steps for '{testcase.name}' starting at "
        f"{testcase.start_url}."
    )

    # 3. Optional AI enrichment
    if provider.name != "null":
        prompt = (
            f"Analyze this UI test flow:\n"
            f"Name: {testcase.name}\n"
            f"URL: {testcase.start_url}\n"
            f"Steps: {[s.description_short for s in testcase.steps]}\n"
            f"Errors: {[e.message for e in testcase.page_errors]}\n\n"
            "Respond in JSON with keys: summary, risks (list of str), negative_scenarios (list of str), "
            "suggested_assertions (list of {kind, target, expected, step_number, confidence})."
        )
        ai_resp: dict[str, Any] = await provider.chat(
            [Message(role="user", content=prompt)], schema={}
        )
        if ai_resp:
            if "summary" in ai_resp:
                summary = str(ai_resp["summary"])
            if "risks" in ai_resp and isinstance(ai_resp["risks"], list):
                risks.extend(str(r) for r in ai_resp["risks"])
            if "negative_scenarios" in ai_resp and isinstance(ai_resp["negative_scenarios"], list):
                negative_scenarios.extend(str(s) for s in ai_resp["negative_scenarios"])
            if "suggested_assertions" in ai_resp and isinstance(
                ai_resp["suggested_assertions"], list
            ):
                for item in ai_resp["suggested_assertions"]:
                    if isinstance(item, dict):
                        step_num = int(item.get("step_number") or 1)
                        expected_val = (
                            str(item["expected"]) if item.get("expected") is not None else None
                        )
                        suggested_assertions.append(
                            Assertion(
                                kind=item.get("kind", "visible"),
                                target=item.get("target"),
                                expected=expected_val,
                                step_number=step_num,
                                source="ai",
                                confidence=float(item.get("confidence", 0.8)),
                                enforced=False,
                            )
                        )

    return AnalysisResult(
        testcase_id=testcase.id,
        testcase_name=testcase.name,
        provider=provider.name,
        model=provider.model,
        summary=summary,
        annotations=annotations,
        suggested_assertions=suggested_assertions,
        risks=risks,
        negative_scenarios=negative_scenarios,
    )


def write_analysis_result(result: AnalysisResult, output_dir: Path) -> Path:
    """Save analysis report to analysis.json in target directory."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "analysis.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path
