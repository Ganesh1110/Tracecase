"""HAR export and offline route fulfillment for recorded test cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qa_auto import __version__
from qa_auto.models import NetworkRequest, TestCase


def _har_headers(headers: dict[str, str]) -> list[dict[str, str]]:
    return [{"name": name, "value": value} for name, value in headers.items()]


def _har_entry(request: NetworkRequest) -> dict[str, Any]:
    request_data: dict[str, Any] = {
        "method": request.method,
        "url": request.url,
        "httpVersion": "HTTP/1.1",
        "headers": _har_headers(request.request_headers),
        "queryString": [],
        "cookies": [],
        "headersSize": -1,
        "bodySize": -1,
    }
    if request.request_body is not None:
        request_data["postData"] = {
            "mimeType": request.request_headers.get("content-type", ""),
            "text": request.request_body,
        }

    body = request.response_body or ""
    return {
        "startedDateTime": request.timestamp.isoformat(),
        "time": request.timing or 0.0,
        "request": request_data,
        "response": {
            "status": request.status or 0,
            "statusText": "",
            "httpVersion": "HTTP/1.1",
            "headers": _har_headers(request.response_headers),
            "cookies": [],
            "content": {
                "size": len(body),
                "mimeType": request.response_headers.get("content-type", ""),
                "text": body,
            },
            "redirectURL": "",
            "headersSize": -1,
            "bodySize": -1,
        },
        "cache": {},
        "timings": {"send": 0.0, "wait": request.timing or 0.0, "receive": 0.0},
        "comment": request.error or "",
    }


def build_har(testcase: TestCase) -> dict[str, Any]:
    """Build a HAR 1.2 document from a recorded test case."""
    return {
        "log": {
            "version": "1.2",
            "creator": {"name": "qa_auto", "version": __version__},
            "pages": [],
            "entries": [_har_entry(request) for request in testcase.network_requests],
        }
    }


def export_har(testcase: TestCase, output_path: Path) -> Path:
    """Write the test case network activity as a HAR file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(build_har(testcase), indent=2, ensure_ascii=False)
    output_path.write_text(content, encoding="utf-8")
    return output_path
