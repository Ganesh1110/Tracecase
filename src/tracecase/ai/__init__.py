"""Local-first AI analysis and QA intelligence module."""

from tracecase.ai.assertion_generator import (
    AssertionGenerationResult,
    AssertionSuggestion,
    generate_heuristic_assertions,
    suggest_assertions,
)
from tracecase.ai.coverage_analyst import (
    CoverageIntelligenceResult,
    RouteCoverage,
    analyze_corpus_coverage,
)
from tracecase.ai.failure_analyst import (
    FailureAnalysisResult,
    FailureCategory,
    analyze_execution_failure,
    analyze_failure_heuristics,
)
from tracecase.ai.models import AnalysisResult, Annotation, Message
from tracecase.ai.provider import (
    NullProvider,
    OllamaProvider,
    OpenAICompatProvider,
    Provider,
    get_provider,
)
from tracecase.ai.selectors import (
    SelectorAnalysis,
    SelectorAuditReport,
    audit_testcase_selectors,
    evaluate_selector,
)
from tracecase.ai.variations import (
    GeneratedVariation,
    VariationMutation,
    generate_heuristic_variations,
    generate_smart_variations,
)

__all__ = [
    "AnalysisResult",
    "Annotation",
    "AssertionGenerationResult",
    "AssertionSuggestion",
    "CoverageIntelligenceResult",
    "FailureAnalysisResult",
    "FailureCategory",
    "GeneratedVariation",
    "Message",
    "NullProvider",
    "OllamaProvider",
    "OpenAICompatProvider",
    "Provider",
    "RouteCoverage",
    "SelectorAnalysis",
    "SelectorAuditReport",
    "VariationMutation",
    "analyze_corpus_coverage",
    "analyze_execution_failure",
    "analyze_failure_heuristics",
    "audit_testcase_selectors",
    "evaluate_selector",
    "generate_heuristic_assertions",
    "generate_heuristic_variations",
    "generate_smart_variations",
    "get_provider",
    "suggest_assertions",
]
