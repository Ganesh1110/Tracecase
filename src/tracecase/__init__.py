"""
Tracecase — CLI tool for recording browser actions and generating test cases.

This package provides tools for QA engineers to:
- Record user actions in a browser
- Capture screenshots at each step
- Generate structured test case documentation (JSON, Markdown, HTML)
"""

__version__ = "0.2.0"
__author__ = "Tracecase Team"

from tracecase.models import (
    ConsoleLog,
    ElementInfo,
    NetworkRequest,
    PageError,
    Step,
    TestCase,
)

__all__ = [
    "__version__",
    "ConsoleLog",
    "ElementInfo",
    "NetworkRequest",
    "PageError",
    "Step",
    "TestCase",
]
