"""Autonomous exploration and application navigation graph package for QA Auto."""

from qa_auto.exploration.models import (
    AppNavigationGraph,
    ExplorationConfig,
    FormField,
    FormSchema,
    InteractiveElement,
    PageNode,
    PageTransition,
    compute_state_fingerprint,
    normalize_url,
    SynthesizedAssertion,
    SynthesizedStep,
    TestJourneyDraft,
)
from qa_auto.exploration.extractor import extract_page_surface, is_destructive_element
from qa_auto.exploration.worker import ExplorationWorker
from qa_auto.exploration.controller import ExplorationController, exploration_controller
from qa_auto.exploration.synthesizer import synthesize_test_journeys

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
