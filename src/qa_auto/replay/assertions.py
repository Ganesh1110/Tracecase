"""Derive assertions from recorded test cases."""

from urllib.parse import urlparse

from qa_auto.models import TestCase
from qa_auto.replay.models import Assertion


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
