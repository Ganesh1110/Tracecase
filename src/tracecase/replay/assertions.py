"""Derive assertions from recorded test cases."""

from urllib.parse import urlparse

from tracecase.models import Step, TestCase
from tracecase.replay.models import Assertion, AssertionResult


def _origin(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    return parsed.scheme, parsed.netloc


def derive_assertions(testcase: TestCase) -> list[Assertion]:
    """Derive conservative assertions from recorded network activity."""
    assertions: list[Assertion] = []
    origin = _origin(testcase.start_url)

    for step in testcase.steps:
        final_document_url: str | None = None
        for request in step.network_requests:
            if request.error is not None or request.status is None:
                continue
            if _origin(request.url) != origin:
                continue
            if request.resource_type in ("xhr", "fetch"):
                if 200 <= request.status < 300:
                    assertions.append(
                        Assertion(
                            kind="status",
                            target=request.url,
                            expected="2xx",
                            step_number=step.number,
                        )
                    )
            elif request.resource_type == "document":
                final_document_url = request.url
        if step.action_type == "click" and final_document_url is not None:
            assertions.append(
                Assertion(
                    kind="url",
                    target=final_document_url,
                    expected=urlparse(final_document_url).path,
                    step_number=step.number,
                )
            )
        assertions.append(Assertion(kind="no_page_error", step_number=step.number))

    return assertions


def _status_matches(expected: str | int | None, actual: int) -> bool:
    if expected == "2xx":
        return 200 <= actual < 300
    return actual == expected


def evaluate_assertions(
    step: Step,
    assertions: list[Assertion],
    *,
    response_statuses: dict[str, list[int]],
    final_url: str,
    new_page_errors: list[str],
    visible_targets: set[str] | list[str] | None = None,
    page_text: str | None = None,
) -> list[AssertionResult]:
    """Evaluate assertions belonging to a single step."""
    results: list[AssertionResult] = []

    for assertion in assertions:
        if assertion.step_number != step.number:
            continue

        if assertion.kind == "status":
            target = assertion.target or (step.url or "")
            statuses = response_statuses.get(assertion.target) if assertion.target else None
            if not statuses and target:
                statuses = next(
                    (v for k, v in response_statuses.items() if target in k or k in target),
                    None,
                )
            if not statuses and response_statuses:
                statuses = next(iter(response_statuses.values()), None)

            if not statuses:
                results.append(
                    AssertionResult(
                        assertion=assertion,
                        passed=False,
                        actual="not observed",
                        message=f"No response observed for {target or 'request'}",
                    )
                )
                continue
            status = statuses[-1]
            passed = _status_matches(assertion.expected, status)
            results.append(
                AssertionResult(
                    assertion=assertion,
                    passed=passed,
                    actual=str(status),
                    message="" if passed else f"Expected {assertion.expected}, got {status}",
                )
            )
        elif assertion.kind == "no_page_error":
            passed = not new_page_errors
            actual = "; ".join(new_page_errors) if new_page_errors else "no errors"
            results.append(
                AssertionResult(
                    assertion=assertion,
                    passed=passed,
                    actual=actual,
                    message="" if passed else f"Page errors: {actual}",
                )
            )
        elif assertion.kind == "url":
            actual_path = urlparse(final_url).path
            passed = actual_path == assertion.expected
            results.append(
                AssertionResult(
                    assertion=assertion,
                    passed=passed,
                    actual=actual_path,
                    message=(
                        "" if passed else f"Expected path {assertion.expected}, got {actual_path}"
                    ),
                )
            )
        elif assertion.kind == "visible":
            vis_target = assertion.target or (step.element.selector if step.element else None)
            vis_set = set(visible_targets or [])
            passed = vis_target in vis_set if vis_target else False
            results.append(
                AssertionResult(
                    assertion=assertion,
                    passed=passed,
                    actual="visible" if passed else "not visible",
                    message="" if passed else f"Element {target} not visible",
                )
            )
        elif assertion.kind == "text":
            expected_text = str(assertion.expected or "")
            passed = expected_text in (page_text or "")
            results.append(
                AssertionResult(
                    assertion=assertion,
                    passed=passed,
                    actual=f"'{expected_text}' found" if passed else "text not found",
                    message="" if passed else f"Expected text '{expected_text}' not found on page",
                )
            )
        else:
            results.append(
                AssertionResult(
                    assertion=assertion,
                    passed=False,
                    message=f"Unsupported assertion kind: {assertion.kind}",
                )
            )

    return results
