"""Autonomous exploration and application navigation graph package for Tracecase."""

from tracecase.exploration.controller import ExplorationController, exploration_controller
from tracecase.exploration.extractor import extract_page_surface, is_destructive_element
from tracecase.exploration.models import (
    AppNavigationGraph,
    ExplorationConfig,
    FormField,
    FormSchema,
    InteractiveElement,
    PageNode,
    PageTransition,
    SynthesizedAssertion,
    SynthesizedStep,
    TestJourneyDraft,
    compute_state_fingerprint,
    normalize_url,
)
from tracecase.exploration.synthesizer import synthesize_test_journeys
from tracecase.exploration.worker import ExplorationWorker

__all__ = [
    "AppNavigationGraph",
    "ExplorationConfig",
    "ExplorationController",
    "ExplorationWorker",
    "FormField",
    "FormSchema",
    "InteractiveElement",
    "PageNode",
    "PageTransition",
    "SynthesizedAssertion",
    "SynthesizedStep",
    "TestJourneyDraft",
    "compute_state_fingerprint",
    "exploration_controller",
    "extract_page_surface",
    "is_destructive_element",
    "normalize_url",
    "synthesize_test_journeys",
]
